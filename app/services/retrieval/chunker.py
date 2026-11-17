import math
import unicodedata
from typing import Any

from app.services.retrieval.eligibility import is_eligible, metadata


def words(text: str) -> list[str]:
    # Keep Devanagari combining marks attached to letters.
    normalized = unicodedata.normalize("NFC", text).casefold()
    result: list[str] = []
    current = ""
    for char in normalized:
        if unicodedata.category(char)[0] in {"L", "M", "N"}:
            current += char
        elif current:
            result.append(current)
            current = ""
    if current:
        result.append(current)
    return result


def grams(text: str) -> set[str]:
    return {
        word[i : i + min(3, len(word))]
        for word in words(text)
        for i in range(max(1, len(word) - 2))
    }


def tokens(text: str) -> int:
    # Approximation only: English words*1.3, Devanagari code points/2.
    hindi = sum(0x900 <= ord(c) <= 0x97F for c in text)
    return max(1, math.ceil(len(words(text)) * 1.3 + hindi / 2))


def chunk_blocks(blocks: list[dict[str, Any]], pages: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {b["id"]: b for b in blocks}
    output: list[dict[str, Any]] = []
    heading = ""
    heading_block: dict[str, Any] | None = None
    pending: dict[str, Any] | None = None

    def emit(
        text: str,
        sources: list[dict[str, Any]],
        *,
        standalone: bool = False,
        offsets: list[dict[str, Any]] | None = None,
    ) -> None:
        nonlocal pending
        sources = [*sources, *([heading_block] if heading_block else [])]
        deps = {b["id"]: b["revision"] for b in sources}
        refs = [pages[pid] for pid in dict.fromkeys(b["page_id"] for b in sources)]
        markers = ["not_scored"] if any(b["status"] == "not_scored" for b in sources) else []
        item = {
            "text": text,
            "heading_context": heading,
            "dependencies": deps,
            "page_refs": refs,
            "markers": markers,
            "offsets": offsets or [],
            "lang": sources[0]["lang"],
        }
        if (
            pending is not None
            and not standalone
            and pending["page_refs"] == refs
            and pending["heading_context"] == heading
            and pending["lang"] == item["lang"]
            and tokens(pending["text"] + "\n" + text) <= 350
        ):
            pending["text"] += "\n" + text
            pending["dependencies"].update(deps)
            pending["markers"] = sorted(set(pending["markers"] + markers))
            pending["offsets"].extend(item["offsets"])
        else:
            if pending is not None:
                output.append(pending)
            pending = item
        if standalone or tokens(pending["text"]) >= 150:
            output.append(pending)
            pending = None

    for block in blocks:
        if block["type"] == "heading":
            heading_block = block if is_eligible(block) else None
            heading = block["text_current"] if heading_block else ""
        if not is_eligible(block):
            if pending is not None:
                output.append(pending)
                pending = None
            continue
        kind = block["type"]
        if kind == "heading":
            if pending is not None:
                output.append(pending)
                pending = None
            heading = block["text_current"]
        if kind == "table_cell":
            continue
        if kind == "table":
            cells = [
                b for b in blocks if b["parent_id"] == block["id"] and b["type"] == "table_cell"
            ]
            for cell in cells:
                header_ids = metadata(cell).get("header_cell_ids", [])
                if not header_ids:
                    continue
                headers = [by_id[h] for h in header_ids if h in by_id]
                if len(headers) != len(header_ids) or not all(
                    is_eligible(b) for b in [cell, *headers]
                ):
                    continue
                # Same-row label cells are carried with their own column headers.
                import json

                bbox = json.loads(cell["bbox_json"])
                row = [
                    c
                    for c in cells
                    if c["id"] != cell["id"]
                    and metadata(c).get("header_cell_ids")
                    and abs(json.loads(c["bbox_json"])[1] - bbox[1]) < 1
                ]
                if not all(is_eligible(c) for c in row):
                    continue
                peers = row
                peer_headers = [
                    by_id[h]
                    for c in peers
                    for h in metadata(c).get("header_cell_ids", [])
                    if h in by_id
                ]
                if not all(is_eligible(c) for c in peer_headers):
                    continue
                label = "; ".join(h["text_current"] for h in headers) + "; " + cell["text_current"]
                for peer in peers:
                    hs = [
                        by_id[h]["text_current"]
                        for h in metadata(peer).get("header_cell_ids", [])
                        if h in by_id
                    ]
                    label += "; " + "; ".join(hs) + "; " + peer["text_current"]
                emit(label, [block, cell, *headers, *peers, *peer_headers], standalone=True)
            continue
        if kind == "equation":
            emit(str(metadata(block)["spoken_fallback"]), [block], standalone=True)
            continue
        if kind == "figure":
            captions = [
                by_id[c]
                for c in metadata(block).get("caption_block_ids", [])
                if c in by_id and is_eligible(by_id[c])
            ]
            emit(
                "\n".join(
                    [str(metadata(block)["alt_text_short"]), *[c["text_current"] for c in captions]]
                ),
                [block, *captions],
                standalone=True,
            )
            continue
        text = block["text_current"]
        if not text.strip():
            continue
        # Bound long paragraphs by code-point slices at whitespace; retain exact offsets.
        start = 0
        while start < len(text):
            end = min(len(text), start + 1200)
            while end > start + 1 and tokens(text[start:end]) > 330:
                end = start + (end - start) * 3 // 4
            if end < len(text):
                boundary = text.rfind(" ", start, end)
                if boundary > start:
                    end = boundary
            emit(
                text[start:end],
                [block],
                offsets=[{"block_id": block["id"], "start": start, "end": end}],
            )
            start = end
            while start < len(text) and text[start].isspace():
                start += 1
    if pending is not None:
        output.append(pending)
    return output
