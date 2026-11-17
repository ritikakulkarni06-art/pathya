# Optional LLM boundary and usage ledger (P11)

Reading and chapter search make no LLM calls. No live Gemini call has been made
or tested. The default adapter is disabled, both budget caps are zero, and the
price file contains unverified placeholders. No model ID is chosen for you.

Before enabling calls, manually verify model support, current INR tariffs,
currency conversion, taxes, data retention and provider terms. Fill exactly one
matching entry in `config/prices.json`, mark it verified, and set a UTC timestamp
and source note. Zero, missing, duplicate, future, naive or older-than-configured
prices fail closed with `prices_unverified`. Set both
`API_BUDGET_INR_HARD_CAP` and `DOCUMENT_BUDGET_INR_HARD_CAP`; each is a lifetime
ledger cap, not a monthly allowance. All kinds of usage count toward the caps.
There are no automatic resets or top-ups.

Each HTTP attempt reserves the configured maximum input/output cost in one
`BEGIN IMMEDIATE` transaction, checking global and document totals together.
Concurrent calls cannot spend the same remaining allowance. Reaching the cap
blocks the next call. Reservations and settled events use integer micro-INR;
Decimal arithmetic rounds fractional micro-INR upwards. A successful response
settles using reported prompt tokens plus candidate and thinking output tokens.
The price rates and timestamp are recorded with each reservation.

A timeout, malformed usage, provider error or worker crash retains the full
reservation. These amounts are conservative estimates, not confirmed invoices.
No automatic refund is applied for an ambiguous outcome. Reported usage above
the reservation is charged in full and flagged in event metadata; subsequent
calls still see that cost. A local cap cannot enforce provider-side token limits,
tariffs or billing behavior. Configure the provider's own spending limit too.
Transport timeouts are not retried. Only explicit HTTP 429 and 5xx responses may
retry, at most twice (`LLM_MAX_RETRIES`), with jitter. Every retry reserves and
records another attempt under the same call ID. A retry can itself be refused
for insufficient budget. Automatic worker retry must not wrap these calls.

The adapter uses a fixed HTTPS endpoint, a header API key, no redirects, no
environment proxy discovery, an explicit timeout, and a 1 MB response ceiling.
Only a strict selected-evidence payload is accepted: question, document revision,
and block IDs/revisions/excerpts. Metadata fields such as filenames and owner
email are rejected. No uploaded file or whole-document field is transmitted.
The input limit uses UTF-8 bytes plus 512 framing bytes as a conservative bound,
including system prompt and JSON schema. This is not an exact model tokenizer;
it can refuse useful inputs early. Nothing is silently truncated. Output schema
and grounding validation belong to P12; JSON mode alone supplies no such proof.

`GET /admin/usage` requires the administrator role and reports totals by kind,
document, UTC day and call, with attempt counts. It contains no excerpts,
questions, API keys or provider diagnostic bodies. A call ID is the cost unit
until a question/job workflow binds it to an application action.

The request shape follows the official
[generateContent API](https://aistudio.google.com/api-reference/generate-content)
and [structured output documentation](https://aistudio.google.com/docs/structured-output),
checked on 17 November 2026. `generateContent` is the stateless adapter used here;
the docs also describe Interactions. Actual model availability, JSON-schema
support, tariffs and terms remain a manual deployment check.
