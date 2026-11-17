# Chapter search (P10)

`GET /documents/{document_id}/search?q=sunlight&k=5` requires reader access.
The response has the current document revision and ranked chunks with source
block IDs/revisions, printed page labels, source
markers and exact source offsets for prose. Search remains available with the
LLM disabled. Query text is excluded from request logs.

One eligibility function rejects critical, needs_review, unsupported, superseded
and generated content. Native not_scored text is eligible and explicitly marked.
Block revisions can be older than the document revision when a different block
was edited; dependencies must still match their current block revisions.

Paragraphs are grouped within page/language/heading boundaries to approximately
150-350 tokens where possible. Short paragraphs remain shorter. Long prose is
split at whitespace with Unicode code point offsets. The token count is an
approximation: words times 1.3 plus half the Devanagari code point count. A
structured table row can exceed the target to keep its headers attached. Complex
header associations remain dependent on reviewed extraction metadata. Reviewed
spoken math and reviewed figure descriptions may contribute evidence.

SQLite FTS5 uses unicode61. Local term overlap ranks already-authorized results;
global BM25 statistics are deliberately avoided. Hindi character trigrams provide
a fallback because unicode61 may separate combining marks. This is a development
fixture check, not measured Hindi retrieval accuracy or native-speaker approval.
Optional local E5 vectors are fused using reciprocal ranks (constant 60). Fake
hash vectors exercise storage and ranking only; they do not model meaning.

Every ranking pool is restricted to the authorized document, its current
revision, current chunk status and current eligible dependencies first. A
block_scope restricts all dependencies, including heading/header context; partial
structured context therefore produces no result instead of escaping the scope.
Neighbor IDs also stay within that scope. The response revision and result list
come from the same database snapshot, including an empty result after a correction.
Corrections immediately remove affected FTS entries and invalidate old evidence.
An index rebuild is idempotent for an unchanged revision and retains stale
history separately. Search can be temporarily empty before a rebuild completes.

Install the optional embeddings extra only when needed. Supply a local copy of
intfloat/multilingual-e5-small and record its checksum/license in the inventory.
No model is downloaded by the service. The default test environment does not
install this extra; loader behavior is checked with a fake local loader. Real
CPU/model smoke testing and ten native-Hindi-speaker queries remain manual.

The Recall@5 helper reports numerator and gold-block denominator. Empty gold
sets have a null ratio. Do not present sample fixture results as evaluation of
the held-out human-authored set.

Owners can schedule `POST /documents/{id}/reindex` after enabling local embeddings.
Eligible passages are indexed even while other passages await review. Unchanged
embedding vectors are copied across document revisions when all source/context
dependencies still match; their immutable historical chunk rows stay separate.

A search miss is an empty results list at the current document revision. It is
not an AI answer or a claim that the subject does not exist. An unauthorized
document is 404, an invalid query is 422, and a current index rebuild may
temporarily leave no results. A correction can change the revision between a
UI search and a later question; the question API must compare it again.

Result scores are ranking signals, not probabilities of correctness. Print page
labels from page_refs rather than adding one to a zero-based PDF index. Source
offsets are Unicode code points, including Hindi combining marks, rather than
UTF-16 code units used by JavaScript string indexing. Person 2 must convert
offsets at that boundary and keep revision IDs with offline references.
