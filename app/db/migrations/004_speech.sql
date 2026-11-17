ALTER TABLE artifacts ADD COLUMN scope_user_id TEXT REFERENCES users(id);
CREATE INDEX artifacts_scope_user ON artifacts(scope_user_id);
CREATE TABLE glossary_terms (
 id TEXT PRIMARY KEY, document_id TEXT REFERENCES documents(id), user_id TEXT REFERENCES users(id), term TEXT NOT NULL,
 language TEXT NOT NULL CHECK(language IN ('en','hi')), scope TEXT NOT NULL CHECK(scope IN ('document','user')),
 spoken_alias TEXT NOT NULL, phoneme TEXT, created_at TEXT NOT NULL,
 CHECK((scope='document' AND document_id IS NOT NULL AND user_id IS NULL) OR (scope='user' AND user_id IS NOT NULL AND document_id IS NULL))
);
CREATE UNIQUE INDEX glossary_document ON glossary_terms(document_id,term,language) WHERE scope='document';
CREATE UNIQUE INDEX glossary_user ON glossary_terms(user_id,term,language) WHERE scope='user';
CREATE INDEX glossary_document_id ON glossary_terms(document_id);
CREATE INDEX glossary_user_id ON glossary_terms(user_id);
CREATE TABLE audio_manifests (
 artifact_id TEXT PRIMARY KEY REFERENCES artifacts(id), cache_key TEXT NOT NULL,
 body_json TEXT NOT NULL CHECK(json_valid(body_json)), glossary_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX audio_cache_key ON audio_manifests(cache_key);
CREATE TABLE artifact_clips (
 artifact_id TEXT NOT NULL REFERENCES artifacts(id), asset_id TEXT NOT NULL REFERENCES assets(id),
 PRIMARY KEY(artifact_id,asset_id)
);
CREATE INDEX clips_asset ON artifact_clips(asset_id);
CREATE TABLE packages (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), revision INTEGER NOT NULL,
 manifest_id TEXT NOT NULL REFERENCES manifests(id), artifact_id TEXT NOT NULL UNIQUE REFERENCES artifacts(id),
 body_json TEXT NOT NULL CHECK(json_valid(body_json)), sha256 TEXT NOT NULL, total_bytes INTEGER NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX packages_document ON packages(document_id,revision);
CREATE TRIGGER packages_no_update BEFORE UPDATE ON packages BEGIN SELECT RAISE(ABORT,'packages are immutable'); END;
CREATE TRIGGER packages_no_delete BEFORE DELETE ON packages BEGIN SELECT RAISE(ABORT,'packages are immutable'); END;
CREATE TRIGGER audio_manifests_no_update BEFORE UPDATE ON audio_manifests BEGIN SELECT RAISE(ABORT,'audio manifests are immutable'); END;
CREATE TRIGGER audio_manifests_no_delete BEFORE DELETE ON audio_manifests BEGIN SELECT RAISE(ABORT,'audio manifests are immutable'); END;
