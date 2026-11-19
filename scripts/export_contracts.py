import argparse
import json
from pathlib import Path

from app.api.documentation import error_catalog
from app.config import Settings
from app.main import create_app
from app.schemas.answers import GeneratedAnswer, QuestionRequest
from app.schemas.content import Artifact, Block, Correction, Document, Edge, ExtractionResult, Page
from app.schemas.corrections import CorrectionRequest


def generated_contracts() -> dict[str, str]:
    files: dict[str, str] = {}
    for name, model in [
        ("generated_answer", GeneratedAnswer),
        ("question_request", QuestionRequest),
        ("document", Document),
        ("correction_request", CorrectionRequest),
        ("page", Page),
        ("block", Block),
        ("edge", Edge),
        ("correction", Correction),
        ("artifact", Artifact),
        ("extraction_output", ExtractionResult),
    ]:
        files[name + ".schema.json"] = (
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        )
    schema = create_app(
        Settings(
            _env_file=None,
            pathya_env="test",
            auth_mode="local",
            session_secret="",
            llm_enabled=False,
            llm_provider="none",
            llm_model_id="",
            gemini_api_key="",
            embeddings_enabled=False,
            cors_origins=["http://localhost:5173"],
        )
    ).openapi()
    files["openapi.json"] = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    files["error-codes.json"] = json.dumps(error_catalog(), indent=2, sort_keys=True) + "\n"
    return files


def main(*, check: bool = False) -> None:
    files = generated_contracts()
    if check:
        stale = [
            name
            for name, text in files.items()
            if not Path("contracts", name).is_file()
            or Path("contracts", name).read_text(encoding="utf-8") != text
        ]
        if stale:
            raise SystemExit(
                "Committed contracts are stale. Run python -m scripts.export_contracts. Files: "
                + ", ".join(stale)
            )
        print("Committed contracts are current.")
        return
    Path("contracts").mkdir(exist_ok=True)
    for name, text in files.items():
        Path("contracts", name).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export deterministic contracts or check committed freshness."
    )
    parser.add_argument("--check", action="store_true")
    main(check=parser.parse_args().check)
