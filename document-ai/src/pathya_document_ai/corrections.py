"""Validate and apply one content correction (contract 1.2.0 correction policy).

P1 computes what a correction does; **P3 alone authorizes and commits it** (in
one transaction, checking the base revision and invalidating dependants). This
module never persists anything: :func:`apply_correction` returns a new,
fully validated ``Document`` that P3 may commit or discard.

The three approved P1 correction operations (P2/P3 written approval, 21 Nov 2026):

=====================  ======================  ==================================================
P3 API operation       Recorded in history as  Effect on the block
=====================  ======================  ==================================================
``replace_text``       ``replace_text``        ``current_text`` replaced. Not allowed on blocks
                                               without text (figures/equations/tables whose
                                               ``raw_text`` is null).
``set_language``       ``set_language``        ``language`` replaced.
``mark_reviewed``      ``set_review_status``   ``review_status`` becomes ``approved``. Approving
                       (``approved``)          a critical block does not remove the flag; it
                                               records the human decision.
=====================  ======================  ==================================================

Every operation: block ``id``, ``raw_text`` and ``provenance`` unchanged;
``revision`` += 1; the correction is appended to ``Document.corrections``;
quality flags are never removed (including ``critical_symbol_uncertain``);
``base_revision`` must equal the block's current revision. Review status is
never changed implicitly by text or language corrections.

Structural corrections (block type, reading order, split, merge) are not part
of 1.2.0: P3 rejects them for P1 chapters (``p1_correction_unsupported``).

Derived data is P3's: the Document carries no sentence ranges or audio. P3
regenerates ranges after a text change and decides audio validity from the
text, language, voice, pronunciation settings and segmenter (a review-only
correction bumps the revision but does not by itself invalidate audio).
"""

from __future__ import annotations

from typing import Any


class CorrectionError(ValueError):
    """The correction is not allowed by the correction policy."""


class CorrectionConflictError(CorrectionError):
    """The correction was made against an outdated block revision."""


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
    if correction.operation is op.REPLACE_TEXT:
        if block.raw_text is None:
            raise CorrectionError(f"block_type '{block.block_type.value}' without text cannot take replace_text")
        update["current_text"] = correction.new_text
    elif correction.operation is op.SET_LANGUAGE:
        update["language"] = correction.new_language
    elif correction.operation is op.SET_REVIEW_STATUS:
        update["review_status"] = correction.new_review_status
    else:  # pragma: no cover - enum is exhaustive
        raise CorrectionError(f"unsupported operation {correction.operation}")

    data = document.model_dump()
    data.update(blocks=[(b.model_copy(update=update) if b.id == block.id else b).model_dump()
                        for b in document.blocks],
                corrections=[*data["corrections"], correction.model_dump()])
    return m.Document.model_validate(data)
