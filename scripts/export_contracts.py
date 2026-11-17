import json
from pathlib import Path

from app.config import Settings
from app.main import create_app
from app.schemas.answers import GeneratedAnswer, QuestionRequest
from app.schemas.content import Artifact, Block, Correction, Document, Edge, ExtractionResult, Page
from app.schemas.corrections import CorrectionRequest


def main() -> None:
    Path("contracts").mkdir(exist_ok=True)
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
        Path("contracts", name + ".schema.json").write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    schema = create_app(Settings(_env_file=None, pathya_env="test")).openapi()
    Path("contracts/openapi.json").write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
