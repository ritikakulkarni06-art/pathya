# Questions and evidence (P12)

`POST /questions` accepts `document_id`, `question`, optional current `revision`,
and optional `block_scope`. It checks document access before retrieval and again
before persistence. The question limit is configurable up to 2000 characters.
`GET /answers/{id}` requires document access and either the original requester
or the document owner. Administrators gain no document visibility.

Responses always have `origin: ai_explanation`, an `AI explanation` label,
document revision, `evidence` cards, `claims`, `abstain`, a reason and next action.
The navigation `return_token` is a client bookmark object containing an opaque ID,
document, revision and optional block ID. It is not an authorization credential;
all later source reads still require ordinary authentication and access checks.
Page references use printed page labels. Native `not_scored` evidence is marked.

Top-five chunks already include heading and complete table-row associations.
The LLM receives exact prose slices, current block revisions and reviewed spoken
math/figure metadata. Empty structural containers are not represented as quoted
source. Generated explanations and teacher notes are never evidence or indexed.
Only question hashes are stored, never raw question bodies. Explanation text and
selected source cards are stored privately in the separate answers table.

No evidence returns `no_evidence`. A lexical match to a flagged passage when no
eligible result exists returns `source_needs_review`, candidate IDs and
`open_review`. This is a simple lexical review hint, not a classifier of every
damaged topic. Low lexical support or otherwise-identical sentences with changed
numbers/negation return `low_support`. Thresholds use P10's document-local lexical
overlap score, not reciprocal-rank scores or calibrated confidence. Pure vector
matches therefore abstain conservatively by default. The contradiction heuristic
can miss contradictions and can flag legitimate differences. Tune on dev only.

Disabled, unavailable or over-budget generation returns eligible extractive cards
with `assistant_disabled`, `assistant_unavailable` or `budget_exhausted`. Input
refusal is recorded as an uncertainty code; no evidence is silently truncated.
The optional EntailmentChecker protocol is off by default and accepts injected
implementations only; its result can flag review, never establish ground truth.

The versioned prompt treats the whole JSON payload and each evidence text field
as untrusted data. A strict Pydantic schema rejects extra fields. Every claim
must cite supplied block IDs at their exact current block revisions. Every quoted
span must appear verbatim in one cited excerpt. A bad schema, quote, citation,
model or revision discards all model output and returns `answer_failed_validation`
with source cards. Logs record only the validation category.

Numbers, a small English/Hindi negation vocabulary, common units and percent signs
absent from cited text set `needs_human_check`. These are incomplete heuristics.
They do not catch all unit conversions, reversed meaning, unsupported nouns,
misleading premises or fluent fabricated claims. A valid citation is **not proof
of entailment**. The scripted tests demonstrate both rejected injections and a
misleading claim that passes structural checks. Prompts cannot guarantee safety
or groundedness. Real answer quality and accessibility remain unmeasured.

A correction during generation discards the result and returns `stale_revision`
with the current revision and no stale evidence. Saved historical explanations
have a visible stale warning after a correction; they are never reused as current.
No answer cache or automatic LLM retry job exists. See LLM_AND_BUDGET.md for
per-attempt HTTP retry/accounting behavior.

Before real use, review 20 answers against source text manually, check Hindi with
a native speaker, configure verified tariffs/model/terms, and tune thresholds
using only a human-authored development set. None of these manual steps is claimed
complete by fixture tests.
