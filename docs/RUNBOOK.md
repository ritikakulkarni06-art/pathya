# Backend operations runbook

## Shared HTTPS preview

Use a team-approved hostname with a trusted TLS certificate. Serve the
reader build and proxy the API through the same origin, for example with
the API under `/api` and `VITE_API_URL=/api`. The proxy strips that prefix
before forwarding to the loopback API. The reader resolves returned asset
paths against its API base so those requests also pass through the proxy.
Enable session authentication and configure a secret through the deployment
environment. Use a separate preview data directory and authorized or
synthetic chapters. Exercise registration, login, `/auth/me`, an
authenticated write, and logout through the browser before sharing the URL.

Maintenance owner after the project: **unassigned; team/institution must name one**.
This is a single-API/single-durable-worker backend. Real adapter contracts, host
security, HTTPS, participant wording and human evaluation remain manual gates.

## Install, start and stop

Use Python 3.11/3.12 and install `python -m pip install -r requirements.lock` in a
virtual environment. This source-checkout workflow avoids an unpinned editable
build bootstrap. Copy .env.example to .env and configure private paths; never
commit secrets/data. Run `python -m app.db.migrate` and `python -m scripts.check`.
`python -m scripts.export_contracts --check` must report current contracts.

Start one API with `python -m uvicorn app.main:create_app --factory --host 127.0.0.1
--port 8000 --workers 1 --no-access-log` (one shell line), and one worker with
`python -m app.worker` in another terminal. `sh scripts/run_dev.sh` starts both
on Unix. Stop with Ctrl+C/SIGTERM; allow the parent worker to stop its job child.
Hard termination can leave a visible lease to expire and be reaped on restart.

For production, use AUTH_MODE=session, PATHYA_ENV=prod, a random session secret
of at least 32 characters, explicit trusted CORS origins and HTTPS termination
at a trusted proxy. `sh scripts/run_prod.sh` forces prod/session but does not
provision TLS, accounts, OS permissions or secrets. Keep storage/database/backups
writable only by the service account. Do not expose local mode or raw storage.
Disable proxy query-string logs too. Do not run multiple API workers or use
in-memory limits as a distributed deployment claim.

Liveness is /healthz; /readyz checks storage/migrations without exposing secrets.
Operator roles must be provisioned offline under an approved process; there is
no public admin-promotion endpoint. An administrator can see /admin/jobs,
/admin/storage, /admin/usage and /admin/metrics but cannot read another user's
source without an ordinary grant. Metrics omit content/private paths.

## Demo and contract checks

`make demo` or `python -m scripts.demo` seeds data/demo, starts a loopback API and
durable worker, and prints URLs/local demo user. It forces fixed fixture/stub
adapters and empty LLM keys. WAVs are silence, not narration. Ctrl+C stops both.
`make demo-check` or `python -m scripts.demo --smoke --port 0` uses an ephemeral
port, verifies live chapter access and completion of a queued indexing job, and
stops automatically. Use an empty or previously seeded synthetic demo directory.
`python -m scripts.reset_demo` deletes only recorded synthetic demo IDs through
the normal deletion path. Never replace it with recursive deletion of live data.

`make openapi` regenerates contracts; `make contracts-check` verifies freshness.
Every operation has synthetic structural examples and a problem response. Core
populated workflows are in API_FOR_FRONTEND.md. Error catalog entries include
extraction-library possibilities; not every code applies to every route.

## Jobs, retries and failures

Owners inspect GET /jobs/{id}; operators inspect failed/expired entries through
/admin/jobs. Attempts count executions, leases are heartbeated, expiry is visible,
and JOB_MAX_ATTEMPTS bounds retries. Do not force a failed artifact to ready or
edit published history. Rebuild only through owner reindex/current correction
workflows. Re-extraction creates a review candidate and never overwrites source.
Cancellation is owner-only. Check extraction/speech adapter configuration and
explicit error states before retrying work; there is no generic public retry API.

The worker schedules a UTC-day retention sweep and prunes marked old backups and
30-day timing/quota metadata. Monitor missing/failed sweeps and overdue deletion
receipts; a stopped worker cannot meet deadlines. Observed job timing excludes
some killed processes, so inspect failure counts too. A SQLite-busy 503 means a
write/publication lock is held; respect Retry-After. Backups intentionally hold
that lock for consistency, so schedule them during an acceptable write window.

## Budget and provider failures

LLM_ENABLED=false and both budget caps=0 are safe defaults. No live provider is
required for reading, search or the demo. Before enabling, verify current model,
tariffs/currency/taxes, data retention and terms. Fill matching positive, verified,
fresh config/prices.json entries and both global/document lifetime caps. Runtime
does not download models or choose a provider/model for you.

GET /admin/usage shows settled costs plus conservative reservations. Every HTTP
attempt reserves the maximum configured cost before network I/O. Timeouts/crashes
retain reservations; 429/5xx alone may retry at most twice, each separately charged
in the ledger. Unknown reservations are estimates, not invoices. Never delete
ledger rows to bypass a cap; reconcile provider billing under an audited operator
procedure. Reaching the cap returns source cards with budget_exhausted. Reading
and search continue. Set a provider-side spending limit too; backend accounting
cannot enforce a provider's tariffs/token reporting/billing behavior.

Rotate an exposed provider key in the provider account, update the secret
environment and restart API/worker. Session-secret rotation requires revoking old
sessions too: token hashes alone are not keyed by that secret. Do not print
environment/configuration dictionaries while diagnosing startup failures.

## Disk-full and storage recovery

507/storage_full leaves explicit failure and cleans tracked partial files. Restore
free space/permissions, inspect /admin/storage and use tracked deletion or approved
backup pruning. Do not delete source files, SQLite pages or immutable history by
hand. A failed deletion keeps the document inaccessible and a failed receipt;
owner POST /deletions/{receipt_id}/retry resumes after the cause is fixed. Disk
or permission failures may require operator help; do not invent an online fallback.

## Backup and restore

Schedule `python -m scripts.backup` externally for backup creation. BACKUP_DIR
must be outside live data and service-private. Snapshots use SQLite's backup API
plus immutable sources/derived files under a publication lock. Marked backups
older than BACKUP_DAYS (default 30) are pruned by the script and daily worker.
Deleted source can remain in older backups until expiry; monitor prune failures.

Stop serving before restore. Run `python -m scripts.backup --restore SNAPSHOT
--destination NEW_DIRECTORY` (one line); it requires a new nonoverlapping path,
verifies SQLite integrity and clears restored sessions. Set PATHYA_DATA_DIR and
PATHYA_DB_PATH to the restored paths, migrate, and check readiness. Before reopening
access, reconcile newer deletion receipts/retention and account changes from a
current private operator inventory. A backup can contain older password hashes;
use an approved offline credential-reset process when needed. No public password
reset or automatic cross-backup deletion reconciliation is implemented. Test on
a clean machine and verify authorized assets/hashes as well as database startup.

## Removing a user's documents

For each owned document, use owner DELETE /documents/{id}, retain the private
receipt, and monitor completion/overdue counts. This immediately revokes grants
and current reads, then purges files, source/history, indexes and explanations.
Never disable immutable triggers globally. Notify the client to purge cached
copies on 410/purge flag or loss of access. Disconnected devices/downloads are
outside server control. Keep only policy-approved content-free receipt/cost/audit
metadata, and reconcile old backups on restore.

Document deletion is implemented; an account-wide erasure API across shared books,
personal glossaries/audio and institutional records is not. Use a reviewed operator
process for account requests, and do not promise complete account/forensic erasure
or bypass other document owners' permissions. Final retention wording, legal/ethics
review, vulnerability audit, manual hosting drills and maintenance ownership remain
institutional responsibilities. See PRIVACY.md and SECURITY.md.
