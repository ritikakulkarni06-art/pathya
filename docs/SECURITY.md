# Security model and operational limits (P14)

This is an implementation threat model and test inventory, **not a completed
security assessment**. Real deployment, dependency auditing, manual IDOR sweeps,
worker-kill/disk-full drills and institutional approval remain required.

| Threat | Implemented control | Automated evidence |
| --- | --- | --- |
| Another user's document/asset IDs | Owner/grant filtering on every resource route; administrators have operations roles only | test_auth.py, test_retrieval.py, test_answers.py, test_deletions.py |
| Revocation during generation/publication | Transactional correction/deletion invalidation; post-generation revision/access checks; upload/grant/audio writes recheck access | test_revisions.py, test_answers.py, test_deletions.py |
| Malicious or oversized upload | Rights note, filename/magic checks, parser limits, pixel/page/byte caps, bounded multipart overhead, private staging | test_uploads.py, test_storage.py |
| Upload resource exhaustion | Per-user/IP request windows, allocated-upload cap and atomic per-user UTC-day page quota | test_hardening.py |
| Huge JSON or request floods | Configurable ASGI byte limit; bounded schema fields; per-user/IP windows for questions/corrections/uploads | test_hardening.py, test_auth.py |
| Instructions embedded in source | Fixed JSON-only LLM boundary, untrusted-data prompt, supplied/current citation and exact-quote validation | test_answers.py, test_llm.py |
| Fluent unsupported generated claims | Abstention, extractive fallback, incomplete number/unit/negation/conflict signals; manual support review required | test_answers.py demonstrates both rejection and limits |
| Key, password or question leakage | SecretStr, fixed error responses, content-free logs, safe startup config error wrapper, header API key, no raw access logs in supplied commands | test_scaffold.py, test_llm.py, test_hardening.py |
| Silent paid retry/budget overspend | Durable worst-case per-attempt reservations, verified prices, global/document caps, bounded explicit 429/5xx retries only | test_llm.py |
| Stale/offline cache confusion | Immutable revision manifests/packages, stale checks, deleted-manifest 410/purge flag; client purge on lost access | test_revisions.py, test_speech.py, test_deletions.py |
| Path traversal/deletion escape | Validated private paths; confined marked backup children; no symlink-following snapshot; tracked purge guards | test_storage.py, test_deletions.py |

Run **one API process and one durable worker**. In-memory request limits are
single-process and reset on restart. They hash IP/user identifiers and bound
stored windows. Shared IPs share an allowance; source IPs are trustworthy only
when reverse-proxy forwarding is configured correctly. Invalid requests can
consume a request allowance. Duplicate file uploads consume request counts but
not additional daily page quota. Deletion does not refund the day's page quota.

`MAX_CONCURRENT_UPLOADS` counts allocated documents in `uploading` under the same
write transaction that reserves page quota. It controls backend allocation, not
all TCP connections or pre-auth multipart spooling. A stopped upload can leave a
visible uploading row; its owner can remove it. Configure proxy connection/body
limits and service-account disk quotas for stronger transport-level protection.
Reading existing chapters remains available when an upload allowance is reached.

`MAX_JSON_BODY_BYTES` defaults to 256 KiB, capped at 1 MiB. Request windows and
upload/question/correction counts are configurable in config.py/.env.example.
429 responses include Retry-After; UTC page quota resets at the next UTC day.
Trusted CORS origins must be explicit. All authenticated JSON is no-store, with
nosniff and no-referrer headers. Sessions require Secure cookies and CSRF checks.
Production refuses local auth, short/missing session secrets and wildcard CORS.

`load_settings()` is used by runtime API/worker/migration/backup entrypoints.
It suppresses raw Pydantic input representations on invalid environment values.
Do not add ordinary traceback logging with request payloads or configuration
objects. Disable proxy/raw query-string access logs as well as Uvicorn logs:
search queries use URLs, and exception scrubbing cannot protect unrelated tools.

Administrator-only `/admin/jobs`, `/admin/storage`, `/admin/usage` and
`/admin/metrics` contain numeric/identifier metadata, no source/private paths.
Observed stage timing records ordinary worker attempts; SIGKILL/hard-timeout
attempts may lack a timing record and must be checked in job failure counters.
Job timing and upload-quota metadata are pruned after 30 days by the daily worker
sweep; cost ledger entries persist to maintain lifetime caps. SQLite-busy writes
return a safe 503 and Retry-After. Backups hold a publication lock, so schedule
them when write interruption is acceptable.

`sh scripts/run_dev.sh` starts the API and worker on loopback. The production
variant forces session mode/prod and still needs an explicitly configured HTTPS
proxy, trusted origin, private OS permissions and secret provisioning. No Docker
or additional service is required. `python -m scripts.seed_demo` and
`python -m scripts.reset_demo` operate on an isolated synthetic demo directory;
silent WAV clips are explicitly marked. Reset deletes only recorded demo IDs
through the ordinary deletion API, never a whole user directory.

Before user sessions, perform the playbook's manual checks: every route with
another user's IDs, malicious/renamed/password PDFs and huge images, logs checked
for private content, secrets/data absent from Git history, and an installed-package
vulnerability audit. Rotate any exposed key. Confirm real extraction/speech/LLM
adapter contracts and assign a maintenance owner. This code does not establish
accessibility conformance, learning gains or measured answer accuracy.
