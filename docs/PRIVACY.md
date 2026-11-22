# Proposed project privacy and deletion policy

These are implementation defaults and project policy proposals, not a legal
compliance claim. The team/guide/institution must approve participant-facing
wording, retention periods and any cloud provider terms before user sessions.

The backend stores authorized originals, extraction text/structure, immutable
revision and correction history, private derived files/audio, indexes, generated
explanations, authentication records, and content-free operational metadata.
Questions are hashed rather than saved as a dedicated raw request field; model
output may still repeat user input. Explanations and their selected evidence
cards remain private to the requester and document owner.

Hosted generation is optional and off by default. When explicitly enabled, only
the selected question, excerpts and block/revision identifiers go to the configured
Gemini endpoint. Filenames, owner emails, uploads and whole-document fields are
excluded. Excerpt text and a question may themselves contain personal information;
the adapter is not an automatic personal-data anonymizer. Verify provider terms,
retention and institutional authorization manually before enabling calls.

With no project-end date configured, retention initially uses upload time plus
`RETENTION_DAYS_AFTER_END` (default 30 days), as documented in DECISIONS.md. A daily
durable worker job requests deletion of expired documents. Owners may extend
retention from the current time up to `RETENTION_EXTENSION_MAX_DAYS` (default 365).
Failed/missed sweeps require operator attention; the worker must remain running.

An owner request to `DELETE /documents/{id}` immediately sets `deleting`, cancels
processing, revokes grants and removes current derivative eligibility in one
transaction. New content, artifact, job, search and question reads are denied.
The owner gets a private receipt with a deadline no later than
`DELETION_SLA_DAYS` (default/max 7 days), progress counts and explicit failure state.
That deadline is a target to monitor, not a hardware-availability guarantee.
Files already sent to a client cannot be recalled.

The worker removes document source/derived directories and document-specific
staging files, then purges text rows, corrections, immutable history, manifests,
packages, FTS content and embeddings through a transaction-scoped purge guard.
Ordinary history mutation is still rejected. Publication checks refuse files
for deleting/deleted documents. A failed file removal leaves access revoked and
an explicit failed receipt; the owner can request a retry. Completion records
verified directory absence, counts and a tombstone without title, rights note,
original hash or source text. Minimal owner/receipt identifiers, audit actions
and content-free numeric usage costs remain for receipt access and budget integrity.

SQLite secure_delete is enabled for the row purge and FTS is rebuilt. Logical
row removal and path-confined file removal are not guaranteed forensic erasure
from SSDs, memory, filesystem journals, pinned SQLite WAL snapshots or external
copies. Protect the live database, private storage and backups with service-only
OS permissions. This project does not supply encrypted storage or backup key
management. Temporary HTTP upload spools rely on request/process cleanup; the
service's tracked document staging files are separately purged.

The owner's manifest request returns 410 with `purge_local_copy: true` as soon as
deletion is requested. Other users/former grantees receive 404 to avoid disclosing
document existence. Clients must purge cached copies on loss of document access
as well as an explicit purge flag. Disconnected devices cannot receive deletion
notifications: Person 2 must remove local downloads on reconnect or on the user's
local deletion action. Shared devices and browser downloads remain a user risk.

`python -m scripts.backup` takes a SQLite backup-API snapshot plus immutable source
and derived files while holding a publication/write lock. `BACKUP_DIR` defaults
to a sibling of the data directory. Backups must stay outside live data, use
service-only permissions and must never be committed. The script and the daily
worker sweep prune marked backups older than `BACKUP_DAYS` (default 30 days).
Backup creation itself remains an operator-scheduled task. If no worker or prune
task runs, old snapshots can persist longer: monitor this operational dependency.

Deleted content can remain in older backups until expiry. Restore only into a
new directory with `python -m scripts.backup --restore SNAPSHOT --destination NEW`.
Restores clear sessions. Operators must reapply deletion requests made after the
snapshot and review retention before allowing access. Test restore on a clean
machine and keep a current deletion-receipt inventory for reconciliation.
