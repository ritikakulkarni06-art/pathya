# Dependency inventory

Resolved for Python 3.12. Versions are pinned in requirements.lock. License metadata is recorded as supplied by each distribution, not legal advice. Redistribution review: pending for every entry. Native bundled code requires separate review.

| Distribution | Version | Declared license | Purpose | Redistribution |
| --- | --- | --- | --- | --- |
| annotated-doc | 0.0.6 | MIT | Runtime, tooling or transitive dependency | Pending review |
| annotated-types | 0.8.0 | MIT | Runtime, tooling or transitive dependency | Pending review |
| anyio | 4.16.0 | MIT | Runtime, tooling or transitive dependency | Pending review |
| argon2-cffi | 25.1.0 | MIT | Runtime, tooling or transitive dependency | Pending review |
| argon2-cffi-bindings | 26.2.0 | MIT | Runtime, tooling or transitive dependency | Pending review |
| ast_serialize | 0.13.1 | MIT | Runtime, tooling or transitive dependency | Pending review |
| attrs | 26.1.0 | MIT | Runtime, tooling or transitive dependency | Pending review |
| certifi | 2026.10.23 | MPL-2.0 | Runtime, tooling or transitive dependency | Pending review |
| cffi | 2.1.1 | MIT-0 | Runtime, tooling or transitive dependency | Pending review |
| click | 8.5.1 | BSD-3-Clause | Runtime, tooling or transitive dependency | Pending review |
| colorama | 0.4.6 | BSD License | Runtime, tooling or transitive dependency | Pending review |
| coverage | 7.17.3 | Apache-2.0 | Runtime, tooling or transitive dependency | Pending review |
| fastapi | 0.163.1 | MIT | Runtime, tooling or transitive dependency | Pending review |
| h11 | 0.16.0 | MIT | Runtime, tooling or transitive dependency | Pending review |
| httpcore | 1.0.9 | BSD-3-Clause | Runtime, tooling or transitive dependency | Pending review |
| httptools | 0.9.0 | MIT | Runtime, tooling or transitive dependency | Pending review |
| httpx | 0.28.1 | BSD-3-Clause | Runtime, tooling or transitive dependency | Pending review |
| idna | 3.20 | BSD-3-Clause | Runtime, tooling or transitive dependency | Pending review |
| iniconfig | 2.3.1 | MIT | Runtime, tooling or transitive dependency | Pending review |
| jsonschema | 4.26.0 | MIT | Runtime, tooling or transitive dependency | Pending review |
| jsonschema-specifications | 2025.9.1 | MIT | Runtime, tooling or transitive dependency | Pending review |
| librt | 0.16.0 | MIT | Runtime, tooling or transitive dependency | Pending review |
| mypy | 2.4.1 | MIT | Runtime, tooling or transitive dependency | Pending review |
| mypy_extensions | 1.2.0 | MIT | Runtime, tooling or transitive dependency | Pending review |
| opentelemetry-api | 1.45.2 | Apache-2.0 | Runtime, tooling or transitive dependency | Pending review |
| orjson | 3.13.0 | MPL-2.0 AND (Apache-2.0 OR MIT) | Runtime, tooling or transitive dependency | Pending review |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | Runtime, tooling or transitive dependency | Pending review |
| pathspec | 1.1.1 | Mozilla Public License 2.0 (MPL 2.0) | Runtime, tooling or transitive dependency | Pending review |
| pillow | 13.0.0 | MIT-CMU | Runtime, tooling or transitive dependency | Pending review |
| pip | 25.0.1 | MIT | Runtime, tooling or transitive dependency | Pending review |
| pluggy | 1.7.0 | MIT | Runtime, tooling or transitive dependency | Pending review |
| pycparser | 3.12 | BSD-3-Clause | Runtime, tooling or transitive dependency | Pending review |
| pydantic | 2.14.3 | MIT | Runtime, tooling or transitive dependency | Pending review |
| pydantic-settings | 2.16.3 | MIT | Runtime, tooling or transitive dependency | Pending review |
| pydantic_core | 2.50.4 | MIT | Runtime, tooling or transitive dependency | Pending review |
| Pygments | 2.21.0 | BSD-2-Clause | Runtime, tooling or transitive dependency | Pending review |
| pypdf | 7.1.0 | BSD-3-Clause | Runtime, tooling or transitive dependency | Pending review |
| pytest | 9.2.0 | MIT | Runtime, tooling or transitive dependency | Pending review |
| pytest-asyncio | 1.5.0 | Apache-2.0 | Runtime, tooling or transitive dependency | Pending review |
| python-dotenv | 1.2.4 | BSD-3-Clause | Runtime, tooling or transitive dependency | Pending review |
| python-multipart | 0.0.34 | Apache-2.0 | Runtime, tooling or transitive dependency | Pending review |
| PyYAML | 6.0.3 | MIT | Runtime, tooling or transitive dependency | Pending review |
| referencing | 0.37.0 | MIT | Runtime, tooling or transitive dependency | Pending review |
| rpds-py | 2026.9.1 | MIT | Runtime, tooling or transitive dependency | Pending review |
| ruff | 0.17.5 | MIT | Runtime, tooling or transitive dependency | Pending review |
| starlette | 1.10.0 | BSD-3-Clause | Runtime, tooling or transitive dependency | Pending review |
| typing-inspection | 0.4.5 | MIT | Runtime, tooling or transitive dependency | Pending review |
| typing_extensions | 4.16.0 | PSF-2.0 | Runtime, tooling or transitive dependency | Pending review |
| uvicorn | 0.54.0 | BSD-3-Clause | Runtime, tooling or transitive dependency | Pending review |
| watchfiles | 1.3.0 | MIT | Runtime, tooling or transitive dependency | Pending review |
| websockets | 17.4 | BSD-3-Clause | Runtime, tooling or transitive dependency | Pending review |

Python/SQLite use the standard library; SQLite is public domain. pypdf is used for
upload inspection. No E5 model, numpy, eSpeak or PDFium is bundled in the default
environment. No cloud API has been enabled.


P10 optional extra (not installed in the default environment):

| Component | Version | License | Purpose / redistribution |
| --- | --- | --- | --- |
| sentence-transformers | 6.3.0 | Apache-2.0 | Optional local E5 runner; not bundled |
| numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Optional CPU cosine; not bundled |
| intfloat/multilingual-e5-small | local checksum required | MIT | Optional 384-dimensional model; user supplies files, not bundled |

Optional transitive dependencies (including torch and transformers) must be locked
and inventoried in the target environment before redistribution. This default
lock does not install or redistribute them. Version metadata was checked on PyPI
on 2026-11-17. The actual E5 model has not been downloaded or accuracy-tested.

## Final integration inventory notes (P16)

`python -m scripts.license_report` prints installed distribution/version/license
metadata, purpose and redistribution-review status without network access.
`--json` supplies a machine-readable report. This is an inventory, not legal
approval or a vulnerability audit. Review the installed LICENSE files, native
bundled components and target-platform transitive dependencies before shipping.

| Component | Backend status / purpose | Redistribution decision |
| --- | --- | --- |
| pypdf | Installed locked dependency; PDF inspection and synthetic demo PDFs | Review its declared BSD-3-Clause license and bundled notices |
| Pillow | Installed locked dependency; image validation/metadata removal | Review distribution license/native codec notices |
| argon2-cffi / bindings | Installed locked dependencies; password hashing | Review declared MIT license and native binding notices |
| SQLite / Python stdlib | Built-in WAL/FTS5, storage/jobs/backup/metrics; no ORM | SQLite public domain; Python/runtime redistribution still needs review |
| numpy | Optional local embeddings extra only, not in default environment | Not bundled; inspect selected wheel's composite license/notices |
| multilingual-e5-small | Optional local model only; checksum/license must be recorded before use | Not downloaded/bundled; model-card MIT declaration still needs review |
| sentence-transformers / torch / transformers | Optional model runtime/transitives only | Not installed by the default lock; target lock/inventory required |
| eSpeak | No backend binary/runtime included; any real speech integration belongs to Person 2 | No redistribution approved; verify the selected binary/version/license first |
| PDFium | Not used or bundled; this backend uses pypdf inspection | No redistribution approved or required for this implementation |
| Hosted Gemini | Optional httpx adapter; no model weights bundled or live call measured | Provider pricing/retention/terms are a separate manual approval |

No additional package was added in P11-P16. CI/source checkout uses the exact
requirements.lock environment. A software license for this project has not been
selected; reports and third-party materials retain their own rights.
