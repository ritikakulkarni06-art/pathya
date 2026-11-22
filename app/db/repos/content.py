import sqlite3
from typing import Any

CURRENT_BLOCK = "json_array_length(blocks.successor_ids_json)=0"
NEEDS_REVIEW = f"{CURRENT_BLOCK} AND (blocks.critical_flag=1 OR blocks.status='needs_review')"


def current_blocks(connection: sqlite3.Connection, document_id: str) -> list[dict[str, Any]]:
    return list(
        connection.execute(
            f"""SELECT blocks.* FROM blocks JOIN pages ON pages.id=blocks.page_id
            WHERE blocks.document_id=? AND {CURRENT_BLOCK}
            ORDER BY pages.pdf_index_0, blocks.order_key, blocks.id""",
            (document_id,),
        )
    )


def get_block(connection: sqlite3.Connection, block_id: str) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        "SELECT * FROM blocks WHERE id=?", (block_id,)
    ).fetchone()
    return row
