ALTER TABLE blocks ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json));
CREATE TABLE extraction_imports (
 document_id TEXT PRIMARY KEY REFERENCES documents(id), schema_version TEXT NOT NULL,
 payload_sha256 TEXT NOT NULL, metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json)), created_at TEXT NOT NULL
);
CREATE TABLE extraction_identifiers (
 document_id TEXT NOT NULL REFERENCES documents(id), external_id TEXT NOT NULL, internal_id TEXT NOT NULL UNIQUE,
 PRIMARY KEY(document_id,external_id)
);
