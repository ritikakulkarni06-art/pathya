"""Conservative, durable reservations share the same ledger as settled usage."""

import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.clock import now_utc
from app.config import Settings
from app.db.connection import Database
from app.services.access import check_document


class BudgetExhausted(Exception):
    code = "budget_exhausted"


class PricesUnavailable(Exception):
    code = "prices_unverified"


class Price(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    model: str
    input_inr_per_million_tokens: Decimal = Field(ge=0, allow_inf_nan=False)
    output_inr_per_million_tokens: Decimal = Field(ge=0, allow_inf_nan=False)
    updated_at: datetime
    source_note: str = Field(min_length=1)
    verified: bool = False


def load_price(settings: Settings) -> Price:
    try:
        entries = json.loads(settings.llm_prices_path.read_text(encoding="utf-8"))["prices"]
        matches = [
            Price.model_validate(row)
            for row in entries
            if row.get("provider") == settings.llm_provider
            and row.get("model") == settings.llm_model_id
        ]
        if len(matches) != 1:
            raise PricesUnavailable()
        price = matches[0]
        instant = datetime.now(UTC)
        if (
            not price.verified
            or not price.updated_at.tzinfo
            or price.updated_at > instant
            or instant - price.updated_at > timedelta(days=settings.llm_price_max_age_days)
            or price.input_inr_per_million_tokens <= 0
            or price.output_inr_per_million_tokens <= 0
        ):
            raise PricesUnavailable()
        return price
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ValidationError):
        raise PricesUnavailable() from None


def cost_micro(price: Price, input_tokens: int, output_tokens: int) -> int:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts must not be negative.")
    # INR / million tokens is numerically micro-INR / token. Round once, upwards.
    amount = (
        input_tokens * price.input_inr_per_million_tokens
        + output_tokens * price.output_inr_per_million_tokens
    )
    return int(amount.to_integral_value(rounding=ROUND_CEILING))


def cap_micro(amount: float) -> int:
    return int((Decimal(str(amount)) * 1_000_000).to_integral_value(rounding=ROUND_FLOOR))


def reserve(
    database: Database,
    settings: Settings,
    price: Price,
    document_id: str,
    user_id: str,
    call_id: str,
    attempt: int,
) -> str:
    worst = cost_micro(price, settings.llm_max_input_tokens, settings.llm_max_output_tokens)
    global_cap = cap_micro(settings.api_budget_inr_hard_cap)
    document_cap = cap_micro(settings.document_budget_inr_hard_cap)
    event_id = str(uuid4())
    with database.write_tx() as connection:
        check_document(connection, document_id, user_id)
        totals = connection.execute(
            "SELECT COALESCE(SUM(cost_inr_micro),0) AS total, COALESCE(SUM(CASE WHEN document_id=? THEN cost_inr_micro ELSE 0 END),0) AS document_total FROM usage_events",
            (document_id,),
        ).fetchone()
        if (
            worst <= 0
            or global_cap <= 0
            or document_cap <= 0
            or totals["total"] >= global_cap
            or totals["total"] + worst > global_cap
            or totals["document_total"] >= document_cap
            or totals["document_total"] + worst > document_cap
        ):
            raise BudgetExhausted()
        connection.execute(
            "INSERT INTO usage_events VALUES (?,?,?,'llm',?,0,0,?,?,?)",
            (
                event_id,
                document_id,
                user_id,
                price.provider,
                worst,
                now_utc(),
                json.dumps(
                    {
                        "state": "reserved",
                        "call_id": call_id,
                        "attempt": attempt,
                        "model_id": price.model,
                        "reserved_micro": worst,
                        "input_inr_per_million_tokens": str(price.input_inr_per_million_tokens),
                        "output_inr_per_million_tokens": str(price.output_inr_per_million_tokens),
                        "price_updated_at": price.updated_at.isoformat(),
                    }
                ),
            ),
        )
    return event_id


def settle(
    database: Database,
    event_id: str,
    price: Price,
    state: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> int:
    """Unknown outcomes retain their full reservation, including after process death."""
    with database.write_tx() as connection:
        row = connection.execute("SELECT * FROM usage_events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise ValueError("Usage reservation is unavailable.")
        meta = json.loads(row["meta_json"])
        if meta["state"] != "reserved":
            raise ValueError("Usage reservation is already settled.")
        amount = int(row["cost_inr_micro"])
        if input_tokens is not None and output_tokens is not None:
            amount = cost_micro(price, input_tokens, output_tokens)
        meta["state"] = state
        meta["usage_known"] = input_tokens is not None and output_tokens is not None
        meta["reservation_exceeded"] = amount > meta["reserved_micro"]
        connection.execute(
            "UPDATE usage_events SET input_units=?,output_units=?,cost_inr_micro=?,meta_json=? WHERE id=?",
            (input_tokens or 0, output_tokens or 0, amount, json.dumps(meta), event_id),
        )
    return amount


def usage_summary(database: Database) -> dict[str, Any]:
    with database.read_conn() as connection:
        connection.execute("BEGIN")
        total = connection.execute(
            "SELECT COALESCE(SUM(cost_inr_micro),0) AS cost_inr_micro FROM usage_events"
        ).fetchone()
        kinds = list(
            connection.execute(
                "SELECT kind,SUM(cost_inr_micro) AS cost_inr_micro,COUNT(*) AS attempts FROM usage_events GROUP BY kind"
            )
        )
        documents = list(
            connection.execute(
                "SELECT document_id,SUM(cost_inr_micro) AS cost_inr_micro FROM usage_events GROUP BY document_id"
            )
        )
        days = list(
            connection.execute(
                "SELECT substr(created_at,1,10) AS day,SUM(cost_inr_micro) AS cost_inr_micro FROM usage_events GROUP BY substr(created_at,1,10)"
            )
        )
        calls = list(
            connection.execute(
                "SELECT json_extract(meta_json,'$.call_id') AS call_id,COUNT(*) AS attempts,SUM(cost_inr_micro) AS cost_inr_micro FROM usage_events WHERE kind='llm' GROUP BY json_extract(meta_json,'$.call_id')"
            )
        )
    return {
        "total": total,
        "by_kind": kinds,
        "by_document": documents,
        "by_day": days,
        "by_call": calls,
    }
