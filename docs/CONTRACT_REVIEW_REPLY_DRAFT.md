# Draft reply to Tharun and Atul

Thanks, Tharun. P3 will use `Document` v1.1.0 at `39331e4` as the
current adapter target. We'll validate the pinned payload at the boundary,
preserve its fields, and test that the data survives import and readback
using the synthetic fixtures. Backend IDs and revisions will remain
authoritative, and producer IDs will be scoped to the extraction run.

We'll keep producer-version handling at the adapter boundary so we can
add the next schema with its own conformance cases. Please send the
verified full extraction entry point and the updated schema, version
and fixtures when they're ready. Then we can run the joint checks.

Atul, thanks for confirming the direct response and running the fixtures.
Let's use the existing block `id` and `revision` fields for stable backend
identity and revision. We'll test gap-free sentence ranges for headings,
paragraphs and list items, including the examples you sent and trailing
whitespace. Text corrections will publish fresh ranges for the new revision.
Keep the local splitter fallback until the backend fields are available.

I checked your sign-in commit and ran the four auth calls against the real
FastAPI app. Registration, login, session lookup and CSRF-protected logout
passed in the API smoke test. Let's use a shared HTTPS origin for the browser
test so the reader can read the host-scoped CSRF cookie.

I confirmed the gaps for reader job listing and retry, correction history,
daily question usage and source previews. P16 has individual job status and
cancellation. Cancellation returns HTTP 204, so the reader can refetch the
job status. The reader currently calls `/manifest`; switch to the direct
`/content` response once it is available. Let's align the reading-order
correction operation with Tharun's updated policy before wiring that control.

Tharun, Atul confirmed the direct Document fields. Please send the updated
schema version, commit and fixtures when they're ready. We'll run the
three agreed conformance checks before marking the integration complete.
