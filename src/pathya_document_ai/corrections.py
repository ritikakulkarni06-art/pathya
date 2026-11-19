"""Validate and apply one content correction (contract 1.2.0 correction policy).

P1 computes what a correction does; **P3 alone authorizes and commits it** (in
one transaction, checking the base revision and invalidating dependants). This
module never persists anything: :func:`apply_correction` returns a new,
fully validated ``Document`` that P3 may commit or discard.

Policy (proposed in 1.2.0; see docs/p1_contract.md "Correction policy"):

=====================  ==================================================================
Every operation        Block ``id`` unchanged. ``raw_text`` unchanged. ``provenance``
                       unchanged (it describes extraction, not editing). ``revision``
                       += 1. The correction is appended to ``Document.corrections``.
                       Quality flags are never removed (including
                       ``critical_symbol_uncertain``). Sentence ranges and audio of the
                       corrected block are removed (stale); ``voice_language`` is kept.
                       ``base_revision`` must equal the block's current revision.
``replace_text``       ``current_text`` replaced. Not allowed on blocks without text
                       (figures/equations/tables whose ``raw_text`` is null).
``set_language``       ``language`` replaced (``voice_language`` is a separate choice).
``set_review_status``  ``review_status`` replaced; ``approved`` on a critical block does
                       not remove the flag, it records the human decision.
``set_block_type``     Only between heading, paragraph, list_item and caption (blocks
                       with structural metadata need re-extraction). ``heading_level``
                       becomes null (unknown) whenever the type changes. A caption that
                       is linked (``caption_of`` edge or ``figure.caption_block_id``)
                       cannot be retyped until the link is resolved.
``set_reading_order``  Moves the block among its siblings (same page and parent);
                       siblings are renumbered 0..n-1 without a revision change, and
                       ``precedes`` edges between those siblings are rebuilt.
=====================  ==================================================================

Review status is never changed implicitly by text, type or order corrections.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class CorrectionError(ValueError):
    """The correction is not allowed by the correction policy."""


class CorrectionConflictError(CorrectionError):
    """The correction was made against an outdated block revision."""


def invalidate_derivatives(block: Any) -> Any:
    """Drop revision-bound sentence ranges and audio; keep the chosen voice language."""
    integration = block.integration
    if integration is None:
        return block
    if integration.voice_language is None:
        return block.model_copy(update={"integration": None})
    return block.model_copy(update={"integration": integration.model_copy(
        update={"sentences": None, "audio": []})})


def apply_correction(document: Any, correction: Any) -> Any:
    """Return a new validated ``Document`` with ``correction`` applied (nothing is persisted)."""
    from pathya_document_ai import models as m

    op = m.CorrectionOperation
    if correction.document_id != document.id:
        raise CorrectionError("correction belongs to a different document")
    if document.schema_version != m.SCHEMA_VERSION:
        raise CorrectionError(f"apply corrections to a {m.SCHEMA_VERSION} document; "
                              f"upgrade this {document.schema_version} document first")
    blocks = {b.id: b for b in document.blocks}
    block = blocks.get(correction.block_id)
    if block is None:
        raise CorrectionError(f"unknown block {correction.block_id}")
    if correction.base_revision != block.revision:
        raise CorrectionConflictError(
            f"correction made against revision {correction.base_revision}; block is at revision {block.revision}")

    update: dict[str, Any] = {"revision": block.revision + 1}
    edges = list(document.edges)
    renumber: dict[Any, int] = {}
    if correction.operation is op.REPLACE_TEXT:
        if block.raw_text is None:
            raise CorrectionError(f"block_type '{block.block_type.value}' without text cannot take replace_text")
        update["current_text"] = correction.new_text
    elif correction.operation is op.SET_LANGUAGE:
        update["language"] = correction.new_language
    elif correction.operation is op.SET_REVIEW_STATUS:
        update["review_status"] = correction.new_review_status
    elif correction.operation is op.SET_BLOCK_TYPE:
        new_type = correction.new_block_type
        if block.block_type not in m.RETYPEABLE_BLOCK_TYPES or new_type not in m.RETYPEABLE_BLOCK_TYPES:
            allowed = sorted(t.value for t in m.RETYPEABLE_BLOCK_TYPES)
            raise CorrectionError(f"set_block_type is only allowed between {allowed}")
        linked = [e for e in document.edges if e.edge_type is m.EdgeType.CAPTION_OF and e.source_id == block.id]
        linked += [b for b in document.blocks if b.figure is not None and b.figure.caption_block_id == block.id]
        if block.block_type is m.BlockType.CAPTION and new_type is not m.BlockType.CAPTION and linked:
            raise CorrectionError("this caption is linked to a figure/table/equation; resolve the caption link "
                                  "explicitly before changing its type (links are never dropped silently)")
        update["block_type"] = new_type
        if new_type is not block.block_type:
            update["heading_level"] = None
    elif correction.operation is op.SET_READING_ORDER:
        siblings = sorted((b for b in document.blocks
                           if b.page_id == block.page_id and b.parent_id == block.parent_id),
                          key=lambda b: b.reading_order)
        if not 0 <= correction.new_reading_order < len(siblings):
            raise CorrectionError(f"new_reading_order must be within 0..{len(siblings) - 1}")
        order = [b for b in siblings if b.id != block.id]
        order.insert(correction.new_reading_order, block)
        renumber = {b.id: i for i, b in enumerate(order)}
        sibling_ids = set(renumber)
        rebuilt = [e for e in edges if not (e.edge_type is m.EdgeType.PRECEDES
                                            and e.source_id in sibling_ids and e.target_id in sibling_ids)]
        had_precedes = len(rebuilt) != len(edges)
        if had_precedes:
            provenance = m.Provenance(method=m.ExtractionMethod.DERIVED, created_at=datetime.now(timezone.utc),
                                      parameters={"rebuilt_by_correction": str(correction.id)})
            rebuilt += [m.Edge(edge_type=m.EdgeType.PRECEDES, source_id=a.id, target_id=b.id, provenance=provenance)
                        for a, b in zip(order, order[1:])]
        edges = rebuilt
    else:  # pragma: no cover - enum is exhaustive
        raise CorrectionError(f"unsupported operation {correction.operation}")

    new_blocks = []
    for b in document.blocks:
        if b.id == block.id:
            b = invalidate_derivatives(b.model_copy(update=update))
        if b.id in renumber:
            b = b.model_copy(update={"reading_order": renumber[b.id]})
        new_blocks.append(b)
    data = document.model_dump()
    data.update(blocks=[b.model_dump() for b in new_blocks], edges=[e.model_dump() for e in edges],
                corrections=[*data["corrections"], correction.model_dump()])
    return m.Document.model_validate(data)
