import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.adapters.llm import DisabledLLM, FakeLLM, GeminiClient, LLMUnavailable
from app.config import Settings
from app.services.costs import (
    BudgetExhausted,
    Price,
    PricesUnavailable,
    cost_micro,
    load_price,
    reserve,
    settle,
    usage_summary,
)
from tests.test_auth import session_app as session_app
from tests.test_auth import signed_client

PAYLOAD = {
    "question": "What is shown?",
    "document_revision": 1,
    "evidence": [{"block_id": "b", "rev": 1, "text": "Synthetic text"}],
}
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}


@pytest.fixture
def llm_settings(tmp_path):
    settings = Settings(
        _env_file=None,
        pathya_env="test",
        pathya_data_dir=tmp_path,
        llm_enabled=True,
        llm_provider="gemini",
        llm_model_id="fixture-model",
        gemini_api_key="private-test-key",
        api_budget_inr_hard_cap=1,
        document_budget_inr_hard_cap=1,
        llm_prices_path=tmp_path / "prices.json",
    )
    price = Price(
        provider="gemini",
        model="fixture-model",
        input_inr_per_million_tokens=Decimal("1.25"),
        output_inr_per_million_tokens=Decimal("2.5"),
        updated_at=datetime.now(UTC),
        source_note="Synthetic tariff, not a provider price",
        verified=True,
    )
    settings.llm_prices_path.write_text(
        json.dumps({"prices": [price.model_dump(mode="json")]}), encoding="utf-8"
    )
    return settings


def response(answer=None, **usage):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": json.dumps(answer or {"answer": "Synthetic"})}]},
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 4,
                "thoughtsTokenCount": 2,
                **usage,
            },
        },
    )


def test_disabled_and_scripted_fake():
    with pytest.raises(LLMUnavailable, match="assistant_disabled"):
        DisabledLLM().generate_structured("system", PAYLOAD, SCHEMA, 100, 5)
    fake = FakeLLM([{"unexpected": "malicious invalid output"}, LLMUnavailable()])
    result = fake.generate_structured("system", PAYLOAD, SCHEMA, 100, 5)
    assert result.parsed == {"unexpected": "malicious invalid output"}
    assert len(result.raw_text_hash) == 64
    with pytest.raises(LLMUnavailable):
        fake.generate_structured("system", PAYLOAD, SCHEMA, 100, 5)
    with pytest.raises(LLMUnavailable):
        fake.generate_structured("system", PAYLOAD, SCHEMA, 100, 5)


def test_price_validation_and_fractional_micro_rupees(llm_settings):
    price = load_price(llm_settings)
    assert cost_micro(price, 1, 1) == 4
    assert cost_micro(price, 0, 0) == 0
    with pytest.raises(ValueError):
        cost_micro(price, -1, 0)
    for change in [
        {"verified": False},
        {"input_inr_per_million_tokens": "0"},
        {"updated_at": (datetime.now(UTC) - timedelta(days=31)).isoformat()},
        {"updated_at": "2026-01-01T00:00:00"},
        {"output_inr_per_million_tokens": "NaN"},
    ]:
        row = {**price.model_dump(mode="json"), **change}
        llm_settings.llm_prices_path.write_text(json.dumps({"prices": [row]}), encoding="utf-8")
        with pytest.raises(PricesUnavailable):
            load_price(llm_settings)


def test_atomic_reservations_exact_cap_and_unknown_outcome(seeded, llm_settings):
    price = load_price(llm_settings)
    worst = cost_micro(price, llm_settings.llm_max_input_tokens, llm_settings.llm_max_output_tokens)
    llm_settings.api_budget_inr_hard_cap = worst / 1_000_000
    llm_settings.document_budget_inr_hard_cap = worst / 1_000_000

    def attempt(index):
        try:
            return reserve(seeded, llm_settings, price, "d", "u", "call", index)
        except BudgetExhausted:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        events = list(pool.map(attempt, [1, 2]))
    assert len([e for e in events if e]) == 1
    event = next(e for e in events if e)
    settle(seeded, event, price, "timeout_unknown_cost")
    assert usage_summary(seeded)["total"]["cost_inr_micro"] == worst
    with pytest.raises(BudgetExhausted):
        reserve(seeded, llm_settings, price, "d", "u", "other", 1)
    with pytest.raises(ValueError):
        settle(seeded, event, price, "again", 1, 1)


@pytest.mark.parametrize("cap_field", ["api_budget_inr_hard_cap", "document_budget_inr_hard_cap"])
def test_each_cap_independently_prevents_a_retry(seeded, llm_settings, cap_field, monkeypatch):
    monkeypatch.setattr("app.adapters.llm.time.sleep", lambda delay: None)
    setattr(llm_settings, cap_field, 0.0064)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    with pytest.raises(BudgetExhausted):
        GeminiClient(
            llm_settings, seeded, "d", "u", transport=httpx.MockTransport(handler)
        ).generate_structured("system", PAYLOAD, SCHEMA, 100, 5)
    assert len(calls) == 1
    assert usage_summary(seeded)["by_call"][0]["attempts"] == 1


def test_success_sends_only_selected_data_and_settles_usage(seeded, llm_settings, caplog):
    requests = []

    def handler(request):
        requests.append(request)
        return response()

    client = GeminiClient(llm_settings, seeded, "d", "u", transport=httpx.MockTransport(handler))
    with caplog.at_level("INFO"):
        result = client.generate_structured("fixed system", PAYLOAD, SCHEMA, 100, 5)
    assert result.parsed == {"answer": "Synthetic"}
    assert result.usage.output_tokens == 6
    sent = json.loads(requests[0].content)
    assert sent["generationConfig"]["responseJsonSchema"] == SCHEMA
    assert json.loads(sent["contents"][0]["parts"][0]["text"]) == PAYLOAD
    assert requests[0].headers["x-goog-api-key"] == "private-test-key"
    assert "private-test-key" not in str(requests[0].url)
    summary = usage_summary(seeded)
    assert summary["total"]["cost_inr_micro"] == 28
    assert summary["by_call"][0]["attempts"] == 1
    for secret in ["private-test-key", "What is shown?", "Synthetic text", "owner@example.test"]:
        assert secret not in caplog.text


@pytest.mark.parametrize("status", [429, 500])
def test_transient_retries_are_bounded_and_each_reserves(seeded, llm_settings, monkeypatch, status):
    monkeypatch.setattr("app.adapters.llm.time.sleep", lambda delay: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="private provider diagnostic")

    client = GeminiClient(llm_settings, seeded, "d", "u", transport=httpx.MockTransport(handler))
    with pytest.raises(LLMUnavailable, match="assistant_unavailable"):
        client.generate_structured("system", PAYLOAD, SCHEMA, 100, 5)
    assert len(calls) == 3
    totals = usage_summary(seeded)
    assert totals["by_call"][0]["attempts"] == 3
    assert totals["total"]["cost_inr_micro"] == 3 * 6400


def test_retry_then_success_and_timeout_never_retried(seeded, llm_settings, monkeypatch):
    monkeypatch.setattr("app.adapters.llm.time.sleep", lambda delay: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else response()

    GeminiClient(
        llm_settings, seeded, "d", "u", transport=httpx.MockTransport(handler)
    ).generate_structured("system", PAYLOAD, SCHEMA, 100, 5)
    assert len(calls) == 2

    def timeout(request):
        raise httpx.ReadTimeout("private-test-key", request=request)

    with pytest.raises(LLMUnavailable, match="assistant_unavailable"):
        GeminiClient(
            llm_settings, seeded, "d", "u", transport=httpx.MockTransport(timeout)
        ).generate_structured("system", PAYLOAD, SCHEMA, 100, 5)
    assert usage_summary(seeded)["by_kind"][0]["attempts"] == 3


@pytest.mark.parametrize("status", [400, 401, 403, 302])
def test_permanent_errors_and_redirects_not_retried(seeded, llm_settings, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"Location": "https://other.invalid"})

    with pytest.raises(LLMUnavailable):
        GeminiClient(
            llm_settings, seeded, "d", "u", transport=httpx.MockTransport(handler)
        ).generate_structured("system", PAYLOAD, SCHEMA, 100, 5)
    assert len(calls) == 1


def test_refusals_precede_network_and_oversize_never_truncates(seeded, llm_settings):
    calls = []
    client = GeminiClient(
        llm_settings,
        seeded,
        "d",
        "u",
        transport=httpx.MockTransport(lambda request: calls.append(request)),
    )
    with pytest.raises(LLMUnavailable, match="invalid_llm_payload"):
        client.generate_structured("system", {**PAYLOAD, "filename": "private.pdf"}, SCHEMA, 100, 5)
    with pytest.raises(LLMUnavailable, match="assistant_input_too_long"):
        client.generate_structured("x" * 5000, PAYLOAD, SCHEMA, 100, 5)
    llm_settings.api_budget_inr_hard_cap = 0
    with pytest.raises(BudgetExhausted):
        client.generate_structured("system", PAYLOAD, SCHEMA, 100, 5)
    llm_settings.api_budget_inr_hard_cap = 1
    llm_settings.document_budget_inr_hard_cap = 0
    with pytest.raises(BudgetExhausted):
        client.generate_structured("system", PAYLOAD, SCHEMA, 100, 5)
    llm_settings.llm_enabled = False
    with pytest.raises(LLMUnavailable, match="assistant_disabled"):
        client.generate_structured("system", PAYLOAD, SCHEMA, 100, 5)
    assert calls == []


@pytest.mark.parametrize("bad_usage", [{"promptTokenCount": -1}, {"candidatesTokenCount": True}])
def test_malformed_usage_keeps_reservation_and_refuses_output(seeded, llm_settings, bad_usage):
    with pytest.raises(LLMUnavailable, match="assistant_invalid_response"):
        GeminiClient(
            llm_settings,
            seeded,
            "d",
            "u",
            transport=httpx.MockTransport(lambda request: response(**bad_usage)),
        ).generate_structured("system", PAYLOAD, SCHEMA, 100, 5)
    assert usage_summary(seeded)["total"]["cost_inr_micro"] == 6400


@pytest.mark.parametrize(
    "user,status", [(None, 401), ("u", 403), ("reader", 403), ("other", 403), ("admin", 200)]
)
def test_admin_usage_access_control(session_app, user, status):
    with signed_client(session_app, user) as client:
        result = client.get("/admin/usage")
    assert result.status_code == status
    if status == 200:
        assert result.json()["total"]["cost_inr_micro"] == 0
