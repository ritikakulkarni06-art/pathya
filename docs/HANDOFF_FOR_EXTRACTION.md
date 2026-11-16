# Person 1 handoff

The extraction contract is a draft awaiting your approval. Read `docs/CONTRACTS.md`, inspect `contracts/extraction_output.schema.json`, and validate your output against `tests/fixtures/chapter_demo.json` as an example.

Please reply in writing with approval or concrete changes to: required fields, quality/status flags, normalized coordinates and transform, local stable IDs, printed page labels, reading order, table header associations and reviewed equation/figure metadata. We must settle these before P6.

## Integration options

- `EXTRACTION_ADAPTER=fixture`: synthetic canned content for dev/test only; never OCR and refused in production.
- `EXTRACTION_ADAPTER=python:your_package.module:YourAdapter`: trusted installed Python adapter with a no-argument constructor and the contract's `extract` method. This executes trusted teammate code inside the worker; it is not a security sandbox.
- `EXTRACTION_ADAPTER=subprocess`, `EXTRACTION_COMMAND=["/absolute/path/to/python","your_extractor.py"]`: Linux only. The wrapper uses an unprivileged user/network namespace, CPU/address-space/file-size/file-descriptor limits, bounded output and process-group timeout termination. If namespaces are unavailable, extraction fails instead of running unsandboxed. Network isolation must be smoke-tested on the deployment host. The current Windows host cannot run this mode; use fixture/trusted Python mode for development.

The subprocess reads `{source_path,languages,page_range}` on stdin, with PDF indexes in page_range, and emits a single UTF-8 extraction result on stdout. Credentials are not passed in the child environment. Do not fetch external links embedded in a document. Resource limits are conservative and may need tuning against authorized examples.

Run `python -m scripts.export_contracts` to regenerate schemas and `python -m scripts.check` to validate the backend. Start from an activated Python 3.12 environment with requirements.lock installed. Critical or needs_review blocks remain visible for review but cannot become trusted evidence merely because OCR returned fluent text.

No upload or worker endpoint has been implemented yet: those begin at P6/P7 after contract acceptance. Re-extraction must later preserve teacher corrections through reconciliation, not call initial import to overwrite them.
