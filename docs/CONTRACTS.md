# Extraction contract for Person 1 ? approval required

Status: **draft v1.0.0, awaiting written teammate approval**. P6 and later stages must wait for Person 1's acceptance or requested changes. The synthetic fixture is a development aid, not a measured OCR result.

## Files to review

- `contracts/extraction_output.schema.json`: normative JSON Schema generated from Pydantic models.
- `tests/fixtures/chapter_demo.json`: complete synthetic ten-page English/Hindi example.
- `app/adapters/extraction.py`: callable adapter interface and transport.
- `docs/HANDOFF_FOR_EXTRACTION.md`: setup and review questions.

## Identifiers and pages

The extraction result belongs to the document supplied by the backend. Do not put owner IDs, private paths or a document ID in this payload. Page and block `id` values are stable **within that document's extraction output** and use letters, digits, hyphens or underscores (1?128 characters). Page and block IDs must be distinct. The backend stores a persistent mapping to opaque UUID4 IDs; integrations use returned backend IDs after import. Identical local IDs in two books cannot collide.

`pdf_index_0` is the zero-based source PDF index. `printed_label` is a separate string (for example `iii`, `11` or `A-3`), never inferred from the PDF index. `bbox` is `[x0,y0,x1,y1]`, normalized to a top-left coordinate origin, strictly ordered and within [0,1]. `width`/`height` are original page dimensions in the parser's declared units. `transform` is `[a,b,c,d,e,f]` mapping normalized displayed coordinates to original pixel coordinates: `x'=a*x+c*y+e`, `y'=b*x+d*y+f`; include rotation/crop effects.

Reading order is sorted by page index and `order_key`; keys are unique per page and parent. Parents must be on the same page and cannot form cycles. Split a cross-page table into page-local table blocks and preserve explicit references as needed. Relations are contains, precedes, caption_of, refers_to, header_for and supersedes.

## Confidence and review

- `ok`: scored extraction without a review flag; a score is required.
- `not_scored`: native/unscored text; `score` must be null, never an invented 100%.
- `needs_review`: uncertain content requiring human review.
- `corrected`: accepted correction; backend transactions own subsequent revisions.
- `reviewed`: human-reviewed content with a reviewer identifier.
- `unsupported`: content the extraction system cannot represent reliably.

`critical_flag=true` and `needs_review` enter the review queue and will be excluded from trusted answer evidence. A score alone never proves correctness. Flags are machine-readable strings; the fixture uses `critical_minus_sign_uncertain`. Confirm the vocabulary with the team before freezing v1.0.0.

Reviewed equations require the supported inert MathML subset and a spoken fallback. Reviewed figures require a short description. Table-cell header references must point to cells with the same table parent. Metadata is stored separately from source text; it is not silently flattened or discarded.

## Required and optional fields

Unknown fields are rejected at every level. The generated JSON Schema's `required` arrays are normative. The field tables below are generated from the same models. Null is an explicit value, not omission, unless a field is optional.

### ExtractionResult

| Field | Presence |
| --- | --- |
| `schema_version` | Required |
| `pages` | Required |
| `blocks` | Required |
| `edges` | Required |
| `quality_flags` | Required |
| `parser_versions` | Required |

### Page

| Field | Presence |
| --- | --- |
| `id` | Required |
| `pdf_index_0` | Required |
| `printed_label` | Required |
| `width` | Required |
| `height` | Required |
| `rotation` | Optional; schema documents the default |
| `source_asset_id` | Optional; schema documents the default |
| `transform` | Required |

### Block

| Field | Presence |
| --- | --- |
| `id` | Required |
| `page_id` | Required |
| `type` | Required |
| `parent_id` | Required |
| `order_key` | Required |
| `bbox` | Required |
| `text_raw` | Required |
| `text_current` | Required |
| `lang` | Required |
| `revision` | Optional; schema documents the default |
| `status` | Required |
| `confidence` | Required |
| `provenance` | Required |
| `critical_flag` | Optional; schema documents the default |
| `successor_ids` | Optional; schema documents the default |
| `metadata` | Optional; schema documents the default |

### Edge

| Field | Presence |
| --- | --- |
| `from_id` | Required |
| `relation` | Required |
| `to_id` | Required |

### Confidence

| Field | Presence |
| --- | --- |
| `engine` | Required |
| `score` | Required |
| `flags` | Required |

### Provenance

| Field | Presence |
| --- | --- |
| `parser` | Required |
| `model` | Required |
| `version` | Required |
| `reviewer` | Required |
| `changed_at` | Required |

### BlockMetadata

| Field | Presence |
| --- | --- |
| `alt_text_short` | Optional; schema documents the default |
| `alt_text_extended` | Optional; schema documents the default |
| `mathml` | Optional; schema documents the default |
| `spoken_fallback` | Optional; schema documents the default |
| `header_cell_ids` | Optional; schema documents the default |
| `caption_block_ids` | Optional; schema documents the default |

### Document

| Field | Presence |
| --- | --- |
| `id` | Required |
| `owner_id` | Required |
| `title` | Required |
| `languages` | Required |
| `current_revision` | Required |
| `state` | Required |
| `rights_note` | Required |
| `retention_until` | Required |

### Correction

| Field | Presence |
| --- | --- |
| `id` | Required |
| `document_id` | Required |
| `block_id` | Required |
| `base_revision` | Required |
| `operations` | Required |
| `reason` | Required |
| `author_id` | Required |
| `accepted_revision` | Optional; schema documents the default |
| `state` | Required |

### Artifact

| Field | Presence |
| --- | --- |
| `id` | Required |
| `document_id` | Required |
| `kind` | Required |
| `block_id` | Required |
| `dependency_revisions` | Required |
| `content_hash` | Required |
| `language` | Required |
| `voice` | Required |
| `engine_version` | Required |
| `status` | Required |
| `asset_id` | Required |


## Worked request

```json
{"source_path":"/private/source-file","languages":["en","hi"],"page_range":[0,1]}
```

The Python adapter signature is `extract(source_path: Path, languages: list[str], page_range: list[int] | None, progress_cb) -> ExtractionResult`. `page_range` is a list of PDF indexes, not printed labels. The callback receives `(pages_done, pages_total)` and never source text. `None` requests the complete document. For an executable adapter, read that request from UTF-8 JSON on stdin and write exactly one schema-conforming UTF-8 JSON object on stdout. Put no logs on stdout. A complete one-page response example:

```json
{
  "schema_version": "1.0.0",
  "pages": [
    {
      "id": "page-1",
      "pdf_index_0": 0,
      "printed_label": "11",
      "width": 600,
      "height": 800,
      "rotation": 0,
      "source_asset_id": null,
      "transform": [
        600,
        0,
        0,
        800,
        0,
        0
      ]
    }
  ],
  "blocks": [
    {
      "id": "heading-1",
      "page_id": "page-1",
      "type": "heading",
      "parent_id": null,
      "order_key": 0,
      "bbox": [
        0.05,
        0.02,
        0.95,
        0.08
      ],
      "text_raw": "Synthetic plant energy chapter",
      "text_current": "Synthetic plant energy chapter",
      "lang": "en",
      "revision": 1,
      "status": "not_scored",
      "confidence": {
        "engine": "synthetic-native",
        "score": null,
        "flags": []
      },
      "provenance": {
        "parser": "synthetic-fixture",
        "model": null,
        "version": "1.0.0",
        "reviewer": null,
        "changed_at": "2026-01-01T00:00:00Z"
      },
      "critical_flag": false,
      "successor_ids": [],
      "metadata": {}
    }
  ],
  "edges": [],
  "quality_flags": [
    "synthetic_demo_only"
  ],
  "parser_versions": {
    "synthetic-fixture": "1.0.0"
  }
}
```

The full fixture adds bilingual prose, columns, tables, equations, figures and review flags.

Import is all-or-nothing: validate relationships, append revision 1 and block versions, and store the ID mapping in one transaction. A matching retry returns the existing mapping. Different content cannot replace an imported/corrected chapter through this initial-import path; P8 supplies explicit reconciliation.

## Person 2 coordination ? proposed speech boundary, not implemented yet

P9 proposes `SpeechUnit {unit_id, block_id, text, lang, offset_start, offset_end, alias_applied}` and `SpeechClip {unit_id, audio_bytes, mime, duration_ms}`. Person 2 owns sentence segmentation and synthesis. Person 3 schedules jobs and stores assets. Confirm offset units, tested voices, MIME types and error vocabulary in writing before P9. Reader navigation must retain source-page labels and opaque backend block IDs. No word timing is claimed by this draft.

## Written acceptance

Person 1 should confirm the field/status/flag vocabulary, coordinate transform, ID stability, page labels, table headers and supported MathML/description subset. Record their actual reply in `docs/CONTRACT_APPROVALS.md`. Change `schema_version` if the agreed shape changes. Do not record an approval that has not happened.
