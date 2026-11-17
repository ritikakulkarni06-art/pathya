import json
from collections.abc import Callable
from pathlib import Path


def recall_at_five(
    path: Path, retrieve: Callable[[str], list[str]]
) -> dict[str, int | float | None]:
    found = total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        gold = set(row["gold_block_ids"])
        found += len(gold & set(retrieve(row["question"])))
        total += len(gold)
    return {"found": found, "gold": total, "recall_at_5": found / total if total else None}
