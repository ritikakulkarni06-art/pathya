import json
from pathlib import Path

from app.config import Settings
from app.main import create_app


def main() -> None:
    Path("contracts").mkdir(exist_ok=True)
    schema = create_app(Settings(_env_file=None, pathya_env="test")).openapi()
    Path("contracts/openapi.json").write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
