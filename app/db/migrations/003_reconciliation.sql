ALTER TABLE chunk_embeddings ADD COLUMN status TEXT NOT NULL DEFAULT 'current' CHECK(status IN ('current','stale'));
CREATE TABLE reextraction_candidates (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), base_revision INTEGER NOT NULL,
 proposed_revision INTEGER NOT NULL, cause TEXT NOT NULL DEFAULT 'reextract' CHECK(cause='reextract'),
 body_json TEXT NOT NULL CHECK(json_valid(body_json)), state TEXT NOT NULL CHECK(state IN ('review_required','accepted','stale','rejected')),
 created_at TEXT NOT NULL, job_id TEXT UNIQUE REFERENCES jobs(id)
);
CREATE INDEX candidates_document ON reextraction_candidates(document_id,base_revision,state);
