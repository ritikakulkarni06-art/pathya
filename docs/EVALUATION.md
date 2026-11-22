# Evaluation workflow (P15)

The 12 records in `eval/data/sample.jsonl` are **marked synthetic samples** for
offline plumbing. They are not the 60-question human-authored evaluation set.
Fake speech is silence and fake hash embeddings have no semantic accuracy claim.
FakeLLM outputs are scripted using known sample expectations; their metrics must
never be presented as model performance, accessibility conformance or learning gain.

Run the sample end-to-end without network or keys:

```sh
python -m eval.run --questions eval/data/sample.jsonl
```

The harness creates a temporary synthetic chapter through the real API, drains
the worker, stores fake local vectors, queries the same question pipeline and
cleans up the temporary database/files. Sample external block labels are mapped
to generated opaque IDs. Those IDs belong to an ephemeral fixture run; they are
not IDs from a live study chapter. Real readings/search stay independent of LLMs.

Outputs go in a new timestamped child of `eval/out/` for every run, preserving
earlier human rating files. The directory is Git-ignored and must be private.
`metrics.json` contains the input hash, mode, sample marker, model/prompt/revision
identifiers, raw numerator/denominator/ratio objects and separately labeled
targets. Empty denominators have a null ratio, never a fabricated zero or success.
The console prints counts/targets and the output location, not question/source
text. Source/question content appears only in the private rating CSV.

Metrics include evidence Recall@5 (unique gold blocks as denominator), current
citation resolution (each claim citation occurrence), appropriate abstention on
records marked expected_abstain, unnecessary abstention on supported records, and
the count of answers flagged needs_human_check. A valid citation is not entailment.
Supported/unsupported claim rates remain pending with 0/0 until humans rate them.
Targets are Recall@5 >=90%, citation resolution >=95%, supported claims >=90%,
unsupported claims <=5%, appropriate abstention >=90% and unnecessary abstention
<=20%. They are targets, not achieved project results.

`human_ratings.csv` uses one row per claim, or one empty claim row for an abstention.
It includes id, category, question, answer_claims, cited_passages, rater1_supported,
rater2_supported and adjudicated. Human rating fields start blank. Spreadsheet
formula-leading cells are prefixed with an apostrophe; all source is untrusted
data. Two people must compare each claim against the cited source and adjudicate
disagreement. An optional LLM judge could only triage; none is implemented here.

The coverage/risk table applies additional abstention thresholds to the captured
lexical support scores without further LLM calls. It reports answered/total and
expected-abstain errors/answered, plus flags. It cannot recover responses already
abstained by the pipeline at a lower threshold. This is a post-hoc diagnostic,
not a calibrated risk curve or measured unsupported-claim rate. Human support
remains pending at every threshold. Do not hide conflicting coverage/abstention
targets behind a single accuracy number.

For real evaluation, manually author/review the corpus and gold block links first.
Separate dev and held-out **by chapter**, keeping every degradation variant in its
parent chapter's split. Never tune prompts, retrieval thresholds or policies on
held-out questions. Review Hindi with a native speaker. The playbook calls for
60 questions: 30 supported, 10 absent, 10 misleading premise, 10 damaged/ambiguous.
No such set has been generated or claimed complete by this implementation.

Use an authorized existing server/document and backend block IDs for human files:

```sh
python -m eval.run --mode real --url https://YOUR-API-ORIGIN --document-id DOCUMENT_ID --questions eval/data/dev.jsonl --out eval/out/
```

Session mode reads PATHYA_EVAL_SESSION and PATHYA_EVAL_CSRF from the environment,
never command-line values or reports. Session evaluation requires HTTPS. Local
loopback HTTP is supported only without a session cookie. URLs with credentials,
queries, fragments or an API path prefix are refused. The server controls whether
LLM generation is enabled; its configured prices/caps and authorization still apply.
Verify tariffs/model/terms and budget before real calls. An offline/disabled run
can measure availability/fallback behavior, not real model answer quality.

HTTP/validation/rate-limit failures stop the run explicitly; there are no hidden
evaluation retries or automatic online fallback. Configure a suitable development
rate allowance. The threshold table reuses results so it cannot multiply paid
calls. Real provider smoke tests, 20-answer manual support review, Hindi review,
the 60-question set and a held-out run remain manual.

The golden ASGI integration test covers upload -> review state -> audio/index ->
correction -> stale derivatives/answer -> rebuild -> corrected citation -> absent
topic abstention -> package -> deletion/purge. Failure tests cover disk-full
rollback, LLM timeout then budget refusal with reading/search intact, concurrent
HTTP correction conflicts and interrupted package publication. Existing worker
tests kill a real child and verify lease recovery. Automated drills use synthetic
inputs; repeat the physical hosting/phone/disk/worker drills manually before use.
