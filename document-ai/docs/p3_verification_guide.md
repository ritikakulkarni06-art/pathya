# P3 verification guide: P1 contract 1.2.0 (proposed)

For Ritika (P3), with Atul (P2) for the reader-facing parts. It lists what
P3 serves around the producer-only P1 Document, how to check each response
against P1's reference code and fixtures, and what is still to change in P3.

**Status:** 1.2.0 is proposed, not finally pinned or frozen. Atul's P2
approval is conditional on `pathya-sentences/3` being the single pinned
segmenter. Ritika reports **45/45 P3 conformance fixtures** and **327 backend
tests passed**; these were reported to P1, not independently rerun by P1.
Final joint P1/P2/P3 approval remains pending in
`docs/contract_change_request_v1.2.0.md`. The frozen 1.1.0 integration baseline
at `39331e4` is preserved; this guide does not change the worker's pin.

`pathya-sentences/3` is the single intended pinned segmenter for 1.2.0.
Joint English/Hindi prepared-audio playback interoperability, `mul`/`und`
voice-selection verification and reconnect after review-only changes remain
**pending**. Reported conformance/backend results do not close these gates.

## Files

| What | Where (P1 branch `person-1`, folder `document-ai/`) |
|---|---|
| 1.2.0 JSON Schema | `contract/schemas/pathya_content.v1.2.0.schema.json` |
| 1.2.0 conformance documents and verdicts | `contract/conformance/v1.2.0/` (`index.json` lists expected results) |
| `pathya-sentences/3` fixtures (45 cases, offsets, UTF-16 offsets, hashes) | `contract/segmentation/pathya-sentences-3.fixtures.json` |
| Example bulk sentence-ranges response | `contract/segmentation/example_sentence_ranges_response.json` |
| Reference segmenter and response checker | `src/pathya_document_ai/sentences.py` |
| Trust policy | `src/pathya_document_ai/critical.py` (`is_trusted_evidence`, `critical_flag`) |
| Correction semantics | `src/pathya_document_ai/corrections.py` (`apply_correction`) |
| Core extraction entry point | `pathya_document_ai.extract_document` / `python -m pathya_document_ai extract` |

## Publication scope and recorded checks

The proposed **26-file core publication excludes**
`src/pathya_document_ai/p3_adapter.py` and
`tests/unit/test_p3_adapter.py`. The adapter source and its 12 tests are
**not available in that core publication**. All core instructions here use
the public API/CLI or reference segmenter, without an adapter import or
worker adapter configuration. Optional adapter work is described separately
in section 8 and must be reviewed, published and verified before use.

The completed P1 pre-publication review recorded the following; suites were
not rerun for this documentation-only update:

| Selected P1 check | Result |
|---|---|
| Unit tests, excluding the adapter test file | 479 passed |
| Strict real-engine integration tests | 29 passed, two Docling deprecation warnings, no skips |
| Segmentation fixtures | 45/45 passed |
| Conformance freshness | 25 files current (13 frozen baseline + 12 candidate, including indexes) |
| Schema freshness | 4 files current |
| Frozen/reference comparison | All 19 match `39331e4` |

The earlier 491-test working-copy total included 12 adapter tests and is
not the core total. Ritika's reported 45/45 P3 conformance and 327 P3 backend
tests are separate team results, not additional P1 tests or P1 reruns.
The existing handoff ZIP remains an unchanged historical snapshot; its
older status documentation is not this updated approval record.

## 1. `GET /documents/{id}/content`

The body is the P1 Document itself, with P3's IDs. No envelope and no extra
fields: the 1.2.0 schema rejects `integration` and any other unknown member.

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Document-Revision: 17
```
```json
{
  "schema_version": "1.2.0",
  "contract_family": "pathya.p1.content",
  "id": "…P3 document id…",
  "languages": ["en", "hi"],
  "pages": ["…"],
  "blocks": [
    {"id": "…P3 block id…", "block_type": "heading", "current_text": "4.2 Equations of Motion",
     "revision": 1, "review_status": "unreviewed", "heading_level": null, "role": "body", "…": "…"}
  ],
  "corrections": [],
  "…": "…"
}
```

**Check:**
```python
from pathya_document_ai.pipeline import validate_document_json
doc = validate_document_json(response.content)        # JSON Schema + Python rules
assert response.headers["X-Document-Revision"].isdigit()
```

## 2. `GET /documents/{id}/sentence-ranges` (bulk)

One request per document. Specification (approved 21 Nov 2026):

| Field | Rule |
|---|---|
| `document_revision` | The document revision this snapshot describes; equals `X-Document-Revision` on the same response and on the matching `/content` |
| `blocks[]` | **Every current block** of that revision, each exactly once |
| `blocks[].block_id` | The block's ID as served in `/content` |
| Response matching | Match by `block_id`. There is no ordering guarantee; reading order may be included for debugging only |
| `blocks[].text_sha256` | Lowercase hex SHA-256 of the exact UTF-8 bytes of `current_text`; null text hashes as `""` (`e3b0c442…b855`) |
| `blocks[].segmenter` | The segmenter that produced the ranges, e.g. `pathya-sentences/3` |
| `blocks[].ranges[]` | `{start, end}` in Unicode code points, start-inclusive, end-exclusive, covering `current_text` from 0 to its length with no gaps or overlaps; trailing whitespace with the preceding sentence. Headings, paragraphs and list items only; every other block, and empty text, has `[]` |

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Document-Revision: 3
Cache-Control: private, no-store
```
```json
{
  "document_revision": 3,
  "blocks": [
    {"block_id": "7d1e4c52-0000-4000-8000-0000000000a1",
     "text_sha256": "0729f9d04360823ea4e52127b6a031f28629e5206d5b5bcfa4af66eee51e5b57",
     "segmenter": "pathya-sentences/3",
     "ranges": [{"start": 0, "end": 23}]},
    {"block_id": "7d1e4c52-0000-4000-8000-0000000000a4",
     "text_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
     "segmenter": "pathya-sentences/3",
     "ranges": []}
  ]
}
```
The full example for the shared sample document is
`contract/segmentation/example_sentence_ranges_response.json`.

P3's inspected baseline (`person-3` `14d9aee`) ships this route. Its shape
matches; that historical baseline uses `pathya-reader-v1` (section 3).
Ritika now reports 45/45 P3 conformance fixtures passed for `/3`; P1 has not
independently rerun that P3 verification. The historical baseline comparison
below is not the latest P3 result.

**Check** (against the `/content` body of the same revision):
```python
from pathya_document_ai.sentences import check_sentence_ranges_response
problems = check_sentence_ranges_response(bulk.json(), doc,
                                          document_revision=int(content.headers["X-Document-Revision"]))
assert problems == [], problems
```
The checker reports a wrong or mismatched revision, missing, duplicate or
unknown blocks, wrong hashes, ranges on non-sentence blocks, gaps, overlaps,
short or long coverage, and, for entries labelled `pathya-sentences/3`, any
difference from the reference ranges. It does not require a block order.

## 3. Adopting `pathya-sentences/3`

P3 recorded: "Adopt `pathya-sentences/3` once the reference rules and
fixtures are available" (`docs/DECISIONS.md`, `14d9aee`). They are now
available.

**Option A (recommended):** import the reference from the pinned P1 package,
after it is separately published and installed for candidate verification.
The reference import does not require the excluded worker adapter:
```python
from pathya_document_ai.sentences import SEGMENTER, segment_sentences   # "pathya-sentences/3"
```
**Option B:** port the rules (listed in the fixture file's `rules` and in
`docs/p1_contract.md`) as `segment_sentences(text)` and run the fixtures in
P3's tests.

**Fixture check** (either option):
```python
import hashlib, json
fixtures = json.load(open("pathya-sentences-3.fixtures.json", encoding="utf-8"))
assert fixtures["segmenter"] == "pathya-sentences/3"
for f in fixtures["fixtures"]:
    assert hashlib.sha256(f["text"].encode("utf-8")).hexdigest() == f["text_sha256"]
    assert [list(r) for r in segment_sentences(f["text"])] == [[r["start"], r["end"]] for r in f["ranges"]], f["id"]
```

**Historical P3 baseline (`14d9aee`): `pathya-reader-v1` passes 31 of 45 fixtures.**
This predates Ritika's reported 45/45 `/3` result and is retained only as
a historical comparison, not an outstanding conformance failure.
The 14 that differ:

| Fixture | `pathya-sentences/3` | `pathya-reader-v1` baseline |
|---|---|---|
| `roman_lower`, `roman_upper_two_sentences`, `roman_long` | `iv.` / `IV.` / `viii.` stay with the item | Split off as a sentence |
| `letter_lower`, `letter_upper` | `a.` / `B.` stay with the item | Split off |
| `devanagari_numeral`, `devanagari_two_digit_numeral` | `१.` / `१०.` stay with the item | Split off (only ASCII digits are markers) |
| `abbrev_pp`, `abbrev_ch`, `abbrev_vol`, `abbrev_figs` | No split after `pp. Ch. Vol. figs.` | Splits after them |
| `guillemet_reversed` (`»Halt.« Dann`) | Splits after `.«` | No split (`«` is not a closer) |
| `lowercase_continuation` (`It rained. then`) | No split before a lowercase word | Splits |
| `list_step_then_number` (`Step 3. 4 apples`) | Splits after `Step 3.` | No split before a digit |

Changing the segmenter identifier changes P3's audio cache key, so existing
audio units are rebuilt once.

## 4. `GET /blocks/{id}` and `GET /blocks/{id}/audio`

`GET /blocks/{id}` already returns `text_sha256`, `document_revision` and,
when sentences are enabled, `sentences` and `segmenter`. The same coverage
rules apply.

Ready-audio response shape inspected at historical P3 `14d9aee`; the
example uses the intended `/3` identifier, not a claim of verified playback:
```json
{
  "status": "ready", "block_id": "…", "block_revision": 2,
  "text_sha256": "…", "segmenter": "pathya-sentences/3",
  "voice": "default", "language": "en", "engine_version": "…", "glossary_hash": "…", "synthetic": false,
  "units": [{"unit_id": "…", "text_offset_start": 0, "text_offset_end": 25, "clip_asset_id": "…",
             "duration_ms": 1840, "hash": "…", "bytes": 29440, "alias_applied": false}]
}
```
Unit offsets follow the same code-point rules and must lie on sentence
boundaries from the same segmenter.

**Audio validity policy (approved 21 Nov 2026):** reuse clips while the
text, language, voice, pronunciation settings (glossary) and segmenter are
unchanged. A review-only edit bumps the block and document revisions but does
not by itself invalidate audio. Chapter metadata refreshes and access is
revalidated on reconnect.

**P3 status (22 Nov 2026, Ritika's report relayed by P1):** review-only cache
preservation is complete locally. Her latest reported results are 45/45
P3 conformance fixtures and 327 backend tests passed; P1 has not independently
rerun those P3 checks. Review-only changes preserve audio clips and offline
packages locally; text corrections still invalidate affected clips and
packages. These reports do not establish joint playback or reconnect
interoperability.

**Prepared-audio lookup key:** `block_id` + `text_sha256` +
`sentence_index` + `voice_language`. P3 also owns the audio validity inputs
above. Verify the four-field key in the relevant P2 playback path, including
replacement of the previously reported short SHA-1 key; no completion
has been reported. Verify
`mul`/`und` voice selection and reconnect after review-only changes.
Joint English/Hindi prepared-audio playback interoperability, `mul`/`und`
voice-selection verification and reconnect after review-only changes all
remain **pending** verification by Atul/Ritika. Final joint P1/P2/P3 approval
also remains pending.

**Audio interoperability checks still required:**

| Action | Expected `GET /blocks/{id}/audio` |
|---|---|
| `mark_reviewed` | Still `ready`, same `clip_asset_id`s and `text_sha256` |
| `replace_text` | `409 audio_stale` until rebuilt; new `text_sha256` afterwards |
| `set_language` | `409 audio_stale` until rebuilt |
| Glossary change affecting the block | Stale until rebuilt |
| Segmenter change | Stale until rebuilt |

## 5. `PATCH /blocks/{id}`: the three approved operations

```json
{"base_revision": 1, "reason": "OCR misread", "operations": [{"op": "replace_text", "text": "Corrected text."}]}
{"base_revision": 2, "reason": "Hindi passage", "operations": [{"op": "set_language", "lang": "hi"}]}
{"base_revision": 3, "reason": "Checked against the page", "operations": [{"op": "mark_reviewed"}]}
```
These are the only operations for P1 chapters; P3 already rejects others with
`422 p1_correction_unsupported` and a stale `base_revision` with
`revision_conflict`. In the
served Document they appear in `corrections` as `replace_text`,
`set_language` and `set_review_status` with `new_review_status: "approved"`
(P3 already does this in `_add_corrections`).

**Checks:**
- After each operation `/content` passes `validate_document_json`; the block
  `id`, `raw_text`, `provenance` and quality flags are unchanged; `revision`
  increased; one history entry was added.
- After `replace_text` the bulk response has a new `text_sha256` and fresh
  ranges for that block.
- After `mark_reviewed` on a `critical_symbol_uncertain` block,
  `critical_flag` is false and the flag is still present.
- `set_type`, `reorder`, `split` and `merge` on a P1 chapter return `422`.

## 6. Trust policy

Mirror `critical.is_trusted_evidence(block, page)` for retrieval and answers:

| Condition | Excluded until |
|---|---|
| Page `needs_ocr`, `partial` or `failed` | The page is reprocessed |
| `needs_review` or `rejected` | Approved |
| `critical_symbol_uncertain` | `mark_reviewed` |
| `block_type_uncertain` | `mark_reviewed` (the type is verified) |
| `unsupported_content` | Reviewer approval (`mark_reviewed`); then eligible subject to other trust conditions |

Excluded blocks are still served in `/content`, and the reader shows them
with their warnings. After approval the `unsupported_content` flag and its
visible review marker remain. The eligibility check never approves a block;
`unreviewed`, `needs_review` and `rejected` blocks carrying this flag remain
excluded. Approval does not override an incomplete page's exclusion.

## 7. Heading levels

`heading_level` is set only when P1 can determine it reliably (at least two
distinct heading sizes in the document); otherwise it is `null` and the
reader shows the heading as level 2. No P3 action needed.

**P2 status:** Atul reports heading support complete (`a9fbda3`): level 1
remains level 1; level 2, deeper levels and null are read as level 2.

## 8. Core extraction and optional adapter integration

### Core: producer fixtures from the real extractor

Use the core CLI with the required Tesseract English/Hindi language data and
Docling models configured. This does not import or configure a worker adapter:

```bash
python -m pathya_document_ai extract chapter.pdf -o out.json --languages hin,eng --layout required
python -m pathya_document_ai validate out.json
```

The CLI defaults to the current 1.2.0 candidate. For an explicit 1.1.0
compatibility check, add `--target-version 1.1.0 --drop heading_level,role`;
loss of `critical_symbol_uncertain` is refused (exit 5). Local extraction is
candidate verification, not a change to P3's worker pin or final approval.

### Optional: additional P3 worker adapter (excluded from core)

`src/pathya_document_ai/p3_adapter.py` and
`tests/unit/test_p3_adapter.py` are local, deferred work outside the proposed
26-file core publication. The core package does not supply the adapter
module or its 12 tests. Do not set `EXTRACTION_ADAPTER` to this module or
import `pathya_document_ai.p3_adapter` when using the core publication.

Before enabling this adapter:

1. Separately review and approve publication of both adapter files and their
   integration scope. The core publication does not implicitly approve them.
2. Publish and install that separately approved source/test revision in the
   P3 worker environment with its locked dependencies and verified engine
   models. Confirm the adapter module and its tests are present.
3. Verify the worker interface, English/Hindi extraction, default 1.1.0
   output, explicit target-version behavior and refusal of critical-warning
   loss. The deferred adapter uses `PATHYA_P3_TARGET_VERSION` for an explicit
   target; setting it is not part of the core CLI instructions.
4. Run the adapter's 12 tests and the relevant P3 worker integration checks
   against that exact revision before configuring its worker entry point.
   Report these results separately from the core's 479 unit tests.

This additional adapter work does not close joint English/Hindi prepared-audio
playback, `mul`/`und` voice-selection, review-only reconnect or final joint
P1/P2/P3 approval gates. The historical handoff ZIP must remain unchanged.
