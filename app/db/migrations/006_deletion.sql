CREATE TABLE deletion_receipts (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL UNIQUE REFERENCES documents(id),
 owner_id TEXT NOT NULL REFERENCES users(id), requested_at TEXT NOT NULL, completes_by TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','failed','complete')),
 completed_at TEXT, counts_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(counts_json)), error_code TEXT
);
CREATE INDEX deletion_receipts_owner ON deletion_receipts(owner_id);
CREATE TABLE purge_guards (document_id TEXT PRIMARY KEY REFERENCES documents(id));
CREATE TRIGGER purge_guard_only_deleting BEFORE INSERT ON purge_guards
 WHEN NOT EXISTS (SELECT 1 FROM documents WHERE id=new.document_id AND state='deleting')
 BEGIN SELECT RAISE(ABORT,'purge requires a deleting document'); END;
DROP TRIGGER block_versions_no_delete;
CREATE TRIGGER block_versions_no_delete BEFORE DELETE ON block_versions
 WHEN NOT EXISTS (SELECT 1 FROM blocks b JOIN purge_guards g ON g.document_id=b.document_id JOIN documents d ON d.id=g.document_id WHERE b.id=old.block_id AND d.state='deleting')
 BEGIN SELECT RAISE(ABORT,'block_versions are append-only'); END;
DROP TRIGGER manifests_no_delete;
CREATE TRIGGER manifests_no_delete BEFORE DELETE ON manifests
 WHEN NOT EXISTS (SELECT 1 FROM purge_guards g JOIN documents d ON d.id=g.document_id WHERE g.document_id=old.document_id AND d.state='deleting')
 BEGIN SELECT RAISE(ABORT,'manifests are immutable'); END;
DROP TRIGGER packages_no_delete;
CREATE TRIGGER packages_no_delete BEFORE DELETE ON packages
 WHEN NOT EXISTS (SELECT 1 FROM purge_guards g JOIN documents d ON d.id=g.document_id WHERE g.document_id=old.document_id AND d.state='deleting')
 BEGIN SELECT RAISE(ABORT,'packages are immutable'); END;
DROP TRIGGER audio_manifests_no_delete;
CREATE TRIGGER audio_manifests_no_delete BEFORE DELETE ON audio_manifests
 WHEN NOT EXISTS (SELECT 1 FROM artifacts a JOIN purge_guards g ON g.document_id=a.document_id JOIN documents d ON d.id=g.document_id WHERE a.id=old.artifact_id AND d.state='deleting')
 BEGIN SELECT RAISE(ABORT,'audio manifests are immutable'); END;
