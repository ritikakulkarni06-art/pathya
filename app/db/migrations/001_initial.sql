CREATE TABLE users (
 id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT,
 role TEXT NOT NULL CHECK(role IN ('user','admin')), created_at TEXT NOT NULL
);
CREATE TABLE sessions (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), token_hash TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT
);
CREATE TABLE documents (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL,
 source_sha256 TEXT NOT NULL, rights_note TEXT NOT NULL, languages_json TEXT NOT NULL CHECK(json_valid(languages_json)),
 current_revision INTEGER NOT NULL DEFAULT 0 CHECK(current_revision>=0),
 state TEXT NOT NULL CHECK(state IN ('uploading','queued','processing','review_required','building','ready','failed','deleting','deleted')),
 retention_until TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT
);
CREATE UNIQUE INDEX documents_owner_source_active ON documents(owner_id,source_sha256) WHERE deleted_at IS NULL;
CREATE TABLE document_grants (
 document_id TEXT NOT NULL REFERENCES documents(id), user_id TEXT NOT NULL REFERENCES users(id),
 role TEXT NOT NULL CHECK(role IN ('reviewer','reader')), granted_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 PRIMARY KEY(document_id,user_id)
);
CREATE TABLE revisions (
 document_id TEXT NOT NULL REFERENCES documents(id), revision INTEGER NOT NULL CHECK(revision>=1),
 cause TEXT NOT NULL CHECK(cause IN ('initial','correction','reextract','restore')), parent_revision INTEGER,
 created_at TEXT NOT NULL, author_id TEXT NOT NULL REFERENCES users(id), PRIMARY KEY(document_id,revision),
 FOREIGN KEY(document_id,parent_revision) REFERENCES revisions(document_id,revision)
);
CREATE TABLE assets (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
 kind TEXT NOT NULL CHECK(kind IN ('source','crop','thumbnail','audio','package')),
 sha256 TEXT NOT NULL, bytes INTEGER NOT NULL CHECK(bytes>=0), mime TEXT NOT NULL, private_path TEXT NOT NULL UNIQUE,
 immutable INTEGER NOT NULL CHECK(immutable IN (0,1)), created_at TEXT NOT NULL, deleted_at TEXT
);
CREATE TABLE pages (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), pdf_index_0 INTEGER NOT NULL CHECK(pdf_index_0>=0),
 printed_label TEXT NOT NULL, width REAL NOT NULL CHECK(width>0), height REAL NOT NULL CHECK(height>0),
 rotation INTEGER NOT NULL CHECK(rotation IN (0,90,180,270)), source_asset_id TEXT REFERENCES assets(id),
 transform_json TEXT NOT NULL CHECK(json_valid(transform_json)), UNIQUE(document_id,pdf_index_0), UNIQUE(document_id,id)
);
CREATE TABLE blocks (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), page_id TEXT NOT NULL,
 type TEXT NOT NULL CHECK(type IN ('heading','paragraph','list_item','table','table_cell','equation','figure','caption')),
 parent_id TEXT, order_key REAL NOT NULL, bbox_json TEXT NOT NULL CHECK(json_valid(bbox_json)),
 text_raw TEXT NOT NULL, text_current TEXT NOT NULL, lang TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(revision>=1),
 status TEXT NOT NULL CHECK(status IN ('ok','needs_review','corrected','reviewed','unsupported','not_scored')),
 confidence_json TEXT NOT NULL CHECK(json_valid(confidence_json)), provenance_json TEXT NOT NULL CHECK(json_valid(provenance_json)),
 critical_flag INTEGER NOT NULL DEFAULT 0 CHECK(critical_flag IN (0,1)),
 successor_ids_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(successor_ids_json)),
 UNIQUE(document_id,id), FOREIGN KEY(document_id,page_id) REFERENCES pages(document_id,id),
 FOREIGN KEY(document_id,parent_id) REFERENCES blocks(document_id,id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE block_versions (
 block_id TEXT NOT NULL REFERENCES blocks(id), revision INTEGER NOT NULL CHECK(revision>=1),
 document_revision INTEGER NOT NULL CHECK(document_revision>=1), text TEXT NOT NULL, ops_json TEXT NOT NULL CHECK(json_valid(ops_json)),
 author_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, PRIMARY KEY(block_id,revision)
);
CREATE TABLE edges (
 from_id TEXT NOT NULL, relation TEXT NOT NULL CHECK(relation IN ('contains','precedes','caption_of','refers_to','header_for','supersedes')),
 to_id TEXT NOT NULL, document_id TEXT NOT NULL REFERENCES documents(id), PRIMARY KEY(from_id,relation,to_id),
 FOREIGN KEY(document_id,from_id) REFERENCES blocks(document_id,id), FOREIGN KEY(document_id,to_id) REFERENCES blocks(document_id,id)
);
CREATE TABLE corrections (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), block_id TEXT NOT NULL,
 base_revision INTEGER NOT NULL CHECK(base_revision>=1), operations_json TEXT NOT NULL CHECK(json_valid(operations_json)),
 author_id TEXT NOT NULL REFERENCES users(id), reason TEXT NOT NULL, created_at TEXT NOT NULL, accepted_revision INTEGER,
 state TEXT NOT NULL CHECK(state IN ('accepted','conflict','rejected')),
 FOREIGN KEY(document_id,block_id) REFERENCES blocks(document_id,id)
);
CREATE TABLE artifacts (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
 kind TEXT NOT NULL CHECK(kind IN ('audio_block','chunk_index','embedding','package')), block_id TEXT,
 dependency_revisions_json TEXT NOT NULL CHECK(json_valid(dependency_revisions_json)), content_hash TEXT,
 language TEXT, voice TEXT, engine_version TEXT,
 status TEXT NOT NULL CHECK(status IN ('pending','building','ready','stale','failed')),
 asset_id TEXT REFERENCES assets(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL, stale_reason TEXT,
 FOREIGN KEY(document_id,block_id) REFERENCES blocks(document_id,id)
);
CREATE TABLE manifests (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL, revision INTEGER NOT NULL, build_seq INTEGER NOT NULL CHECK(build_seq>=1),
 body_json TEXT NOT NULL CHECK(json_valid(body_json)), sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(document_id,revision,build_seq), FOREIGN KEY(document_id,revision) REFERENCES revisions(document_id,revision)
);
CREATE TABLE jobs (
 id TEXT PRIMARY KEY, document_id TEXT REFERENCES documents(id),
 kind TEXT NOT NULL CHECK(kind IN ('extract','build_audio','build_index','rebuild','delete','retention_sweep')),
 state TEXT NOT NULL CHECK(state IN ('queued','validating','extracting','review_required','building','ready','failed','cancelled')),
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts>=0),
 max_attempts INTEGER NOT NULL CHECK(max_attempts>=1), lease_owner TEXT, lease_expires_at TEXT,
 idempotency_key TEXT UNIQUE, progress_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(progress_json)),
 error_code TEXT, error_message TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE chunks (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL, revision INTEGER NOT NULL,
 block_ids_json TEXT NOT NULL CHECK(json_valid(block_ids_json)), heading_context TEXT NOT NULL, text TEXT NOT NULL,
 token_count INTEGER NOT NULL CHECK(token_count>=0), page_refs_json TEXT NOT NULL CHECK(json_valid(page_refs_json)),
 eligible INTEGER NOT NULL CHECK(eligible IN (0,1)), status TEXT NOT NULL CHECK(status IN ('current','stale')),
 FOREIGN KEY(document_id,revision) REFERENCES revisions(document_id,revision)
);
CREATE VIRTUAL TABLE chunks_fts USING fts5(text, document_id UNINDEXED, chunk_id UNINDEXED, tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER chunks_fts_insert AFTER INSERT ON chunks WHEN new.eligible=1 AND new.status='current' BEGIN
 INSERT INTO chunks_fts(text,document_id,chunk_id) VALUES(new.text,new.document_id,new.id);
END;
CREATE TRIGGER chunks_fts_update AFTER UPDATE ON chunks BEGIN
 DELETE FROM chunks_fts WHERE chunk_id=old.id;
 INSERT INTO chunks_fts(text,document_id,chunk_id) SELECT new.text,new.document_id,new.id WHERE new.eligible=1 AND new.status='current';
END;
CREATE TRIGGER chunks_fts_delete AFTER DELETE ON chunks BEGIN
 DELETE FROM chunks_fts WHERE chunk_id=old.id;
END;
CREATE TABLE chunk_embeddings (
 chunk_id TEXT NOT NULL REFERENCES chunks(id), model_id TEXT NOT NULL, dim INTEGER NOT NULL CHECK(dim>0), vector BLOB NOT NULL,
 PRIMARY KEY(chunk_id,model_id)
);
CREATE TABLE answers (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL, document_revision INTEGER NOT NULL, user_id TEXT NOT NULL REFERENCES users(id),
 question_hash TEXT NOT NULL, origin TEXT NOT NULL DEFAULT 'ai_explanation' CHECK(origin='ai_explanation'),
 response_json TEXT NOT NULL CHECK(json_valid(response_json)), model_id TEXT, prompt_version TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('current','stale')), abstained INTEGER NOT NULL CHECK(abstained IN (0,1)), created_at TEXT NOT NULL,
 FOREIGN KEY(document_id,document_revision) REFERENCES revisions(document_id,revision)
);
CREATE TABLE usage_events (
 id TEXT PRIMARY KEY, document_id TEXT REFERENCES documents(id), user_id TEXT REFERENCES users(id),
 kind TEXT NOT NULL CHECK(kind IN ('llm','ocr','tts','embedding')), provider TEXT NOT NULL,
 input_units INTEGER NOT NULL CHECK(input_units>=0), output_units INTEGER NOT NULL CHECK(output_units>=0),
 cost_inr_micro INTEGER NOT NULL CHECK(cost_inr_micro>=0), created_at TEXT NOT NULL, meta_json TEXT NOT NULL CHECK(json_valid(meta_json))
);
CREATE TABLE audit_log (
 id TEXT PRIMARY KEY, actor_id TEXT REFERENCES users(id), action TEXT NOT NULL,
 document_id TEXT REFERENCES documents(id), target_id TEXT, created_at TEXT NOT NULL, meta_json TEXT NOT NULL CHECK(json_valid(meta_json))
);
CREATE TRIGGER block_versions_no_update BEFORE UPDATE ON block_versions BEGIN
 SELECT RAISE(ABORT,'block_versions are append-only');
END;
CREATE TRIGGER block_versions_no_delete BEFORE DELETE ON block_versions BEGIN
 SELECT RAISE(ABORT,'block_versions are append-only');
END;
CREATE TRIGGER manifests_no_update BEFORE UPDATE ON manifests BEGIN
 SELECT RAISE(ABORT,'manifests are immutable');
END;
CREATE TRIGGER manifests_no_delete BEFORE DELETE ON manifests BEGIN
 SELECT RAISE(ABORT,'manifests are immutable');
END;
CREATE INDEX sessions_user ON sessions(user_id);
CREATE INDEX sessions_expiry ON sessions(expires_at,revoked_at);
CREATE INDEX documents_state ON documents(state,retention_until);
CREATE INDEX grants_user ON document_grants(user_id);
CREATE INDEX grants_granter ON document_grants(granted_by);
CREATE INDEX revisions_parent ON revisions(document_id,parent_revision);
CREATE INDEX revisions_author ON revisions(author_id);
CREATE INDEX assets_document ON assets(document_id,kind,deleted_at);
CREATE INDEX pages_source ON pages(source_asset_id);
CREATE INDEX blocks_page ON blocks(document_id,page_id,order_key);
CREATE INDEX blocks_parent ON blocks(document_id,parent_id,order_key);
CREATE INDEX blocks_review ON blocks(document_id,status,critical_flag);
CREATE INDEX versions_author ON block_versions(author_id);
CREATE INDEX edges_from ON edges(document_id,from_id);
CREATE INDEX edges_to ON edges(document_id,to_id);
CREATE INDEX corrections_block ON corrections(document_id,block_id);
CREATE INDEX corrections_author ON corrections(author_id);
CREATE INDEX artifacts_block ON artifacts(document_id,block_id,status);
CREATE INDEX artifacts_asset ON artifacts(asset_id);
CREATE INDEX jobs_document ON jobs(document_id,state);
CREATE INDEX jobs_claim ON jobs(state,lease_expires_at,created_at);
CREATE INDEX chunks_current ON chunks(document_id,revision,eligible,status);
CREATE INDEX answers_current ON answers(document_id,document_revision,status);
CREATE INDEX answers_user ON answers(user_id);
CREATE INDEX usage_document ON usage_events(document_id,created_at);
CREATE INDEX usage_user ON usage_events(user_id);
CREATE INDEX audit_document ON audit_log(document_id,created_at);
CREATE INDEX audit_actor ON audit_log(actor_id);
