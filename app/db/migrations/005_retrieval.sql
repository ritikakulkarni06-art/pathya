CREATE TABLE chunk_metadata (
 chunk_id TEXT PRIMARY KEY REFERENCES chunks(id), dependency_revisions_json TEXT NOT NULL CHECK(json_valid(dependency_revisions_json)),
 markers_json TEXT NOT NULL CHECK(json_valid(markers_json)), offsets_json TEXT NOT NULL CHECK(json_valid(offsets_json))
);
CREATE TABLE chunk_ngrams (chunk_id TEXT NOT NULL REFERENCES chunks(id), gram TEXT NOT NULL, PRIMARY KEY(chunk_id,gram));
CREATE INDEX chunk_ngrams_gram ON chunk_ngrams(gram);
