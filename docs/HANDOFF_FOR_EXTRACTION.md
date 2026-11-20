# Person 1 handoff

The checked-in extraction schema describes the current draft backend adapter. The Person 1 `Document` payload needs a reconciled mapping before live integration. See `docs/CONTRACTS.md` and `contracts/extraction_output.schema.json` for the current adapter, and `tests/fixtures/chapter_demo.json` for a synthetic example.

Please reply in writing with approval or concrete changes to: required fields, quality/status flags, coordinate convention and transform, local stable IDs, printed page labels, reading order, table header associations and reviewed equation/figure metadata. The user explicitly deferred teammate approval on 16 November 2026 so backend work could continue with fixtures. That is not your acceptance; reconcile before real adapter integration.

## Integration options

For a whole-document P1 producer, set
`EXTRACTION_ADAPTER=p1:your_package.module:extract_document` after verifying
the pipeline. The trusted callable accepts `(source_path, languages)` and
returns UTF-8 JSON bytes for the pinned Document. A thin wrapper can adapt
the upstream signature. The worker requires an outcome for every physical
page, enforces `P1_MAX_OUTPUT_BYTES`, checks the original source checksum
and media type, and rejects producer-supplied correction history on import.
Re-extraction creates a separate review candidate. Synthetic integration
tests use a fixture callable until the verified pipeline is available.

- `EXTRACTION_ADAPTER=fixture`: synthetic canned content for dev/test only; never OCR and refused in production.
- `EXTRACTION_ADAPTER=python:your_package.module:YourAdapter`: trusted installed Python adapter with a no-argument constructor and the contract's `extract` method. This executes trusted teammate code inside the worker; it is not a security sandbox.
- `EXTRACTION_ADAPTER=subprocess`, `EXTRACTION_COMMAND=["/absolute/path/to/python","your_extractor.py"]`: Linux only. The wrapper uses an unprivileged user/network namespace, CPU/address-space/file-size/file-descriptor limits, bounded output and process-group timeout termination. If namespaces are unavailable, extraction fails instead of running unsandboxed. Network isolation must be smoke-tested on the deployment host. The current Windows host cannot run this mode; use fixture/trusted Python mode for development.

The subprocess reads `{source_path,languages,page_range}` on stdin, with PDF indexes in page_range, and emits a single UTF-8 extraction result on stdout. Credentials are not passed in the child environment. Do not fetch external links embedded in a document. Resource limits are conservative and may need tuning against authorized examples.

Run `python -m scripts.export_contracts` to regenerate schemas and `python -m scripts.check` to validate the backend. Start from an activated Python 3.12 environment with requirements.lock installed. Critical or needs_review blocks remain visible for review but cannot become trusted evidence merely because OCR returned fluent text.

Upload, worker, correction, search, question and deletion workflows are now implemented
and tested against the draft. POST /documents requires an authorization/rights note
and queues extraction; GET /jobs/{id} exposes attempts/progress. Extraction is
page-by-page, validated and imported once transactionally at revision 1. Stable
document-local adapter IDs map to opaque backend UUIDs. Preserve your IDs on retry;
do not assume they are globally unique or equal the backend correction IDs.

Allowed status vocabulary is ok, needs_review, corrected, reviewed, unsupported
and not_scored. critical_flag always excludes trusted retrieval even if text looks
fluent. Native not_scored text can be eligible with a visible marker. Equations
need reviewed spoken_fallback; figures need reviewed alt_text_short. Table evidence
keeps header/value/row-label associations and revisions attached. Do not label
generated explanations or teacher notes as source metadata/evidence.

Parents/reading order are page-local; printed page labels are separate from the
zero-based PDF index. Supply the agreed geometry/transform metadata, never silently
discard unknown layout or pretend an ambiguous header/diagram is supported. Current
JSON Schema plus cross-reference checks reject invalid references and unsafe MathML.

Accepted corrections create immutable history and new revisions. Re-extraction
creates a separate review candidate against a base revision and cannot overwrite
teacher corrections through initial import. An automatic candidate-acceptance
workflow is not implemented. Any incompatible contract change needs a versioned
schema/adapter reconciliation and tests, not an in-place mutation of published text.

Run `python -m scripts.export_contracts --check`, `python -m scripts.check`, and the
offline fixture demo. Deployment-host namespace isolation, real OCR output/rights,
Hindi review and written contract approval remain manual. No fixture result is a
claim about your extractor's actual accuracy.
