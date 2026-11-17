# Revisions and correction consistency

```
upload -> extraction -> immutable revision 1 -> manifest build 1
                           |
                      correction(base block revision)
                           |
                 BEGIN IMMEDIATE + permission recheck
                    /                       \
             base differs                base matches
             append conflict             apply operations
             COMMIT -> 409               append block versions
                                         append document revision
                                         stale dependents + enqueue rebuild
                                         COMMIT
                                             |
                                rebuild -> validate assets/dependencies
                                             |
                                  immutable manifest build N
```

Published manifests and block-version rows reject ordinary UPDATE/DELETE. Blocks are current materialized state; accepted events append history. Each correction increments its block revision and the document revision together. Dependent audio, chunks, embedding rows and answers are marked stale in the same transaction. Retrieval must additionally filter the current document revision, even for unchanged historical chunks.

A stale base returns 409 `revision_conflict` with current_revision, your_base, current_text, your_text and field_hints. Conflict records commit without changing content. Other errors roll back content, versions and invalidation together.

Split/merge support adjacent plain-text blocks without children. Old IDs remain readable with historical=true and successor_ids. New IDs are UUID4. Split offsets use Unicode code points, not UTF-16 code units; frontend code must convert offsets. Merge accepts optional with_base_revision; if omitted it expects the same base as the first block. Complex unsupported structural changes return explicit errors. Successors inherit source geometry (merged boxes use their union); precise line geometry still needs the extraction module.

Current containment, reading-order, header and caption edges are materialized and rebuilt after structural changes. Previous immutable manifests retain the old graph. Table header assignment supports complete rows under one header row; ambiguous or incomplete tables are rejected rather than guessed. Metadata references to split captions follow successor IDs.

Manifests include current block revisions/hashes, printed page labels separately from PDF indexes, reviewed math/descriptions, and explicit ready/pending/text_only states. A ready artifact must have matching block dependencies, an existing private asset, byte count and checksum. An invalid ready asset prevents publication. Current manifests never reference stale artifacts as ready. GET with an explicit old revision retrieves historical manifests; it does not label them current. Default content/manifest reads use a consistent database snapshot and recheck permissions.

P8's rebuild has a prose-only indexing baseline and explicit text-only audio fallback. P9 installs speech scheduling; P10 replaces the baseline with full structured retrieval. Reading text and source views do not depend on those optional outputs.

Re-extraction creates a separate review-required candidate, with tentative proposed_revision=current+1 and a recorded base. It does not allocate a published revision or overwrite corrections. Geometry/text matching proposes links and preserves corrected/reviewed text in the reconciliation plan. Ambiguous/unmatched blocks require review. Repeating the same job reuses its candidate receipt. A later accepted correction makes an older candidate stale. Automatic candidate acceptance is deliberately not implemented; publishing must be an explicit reconciled action.
