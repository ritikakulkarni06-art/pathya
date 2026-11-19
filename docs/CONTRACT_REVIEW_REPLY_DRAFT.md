# Draft reply from Ritika / P3 - not sent

Thanks for the update. I verified the three CI jobs for commit `39331e4` and reviewed both
contracts against the current P3 implementation.

The conflict is real: all 12 P1 conformance vectors match their expected outcomes, but the
current P3 schema rejects all three valid P1 examples. I cannot confirm direct compatibility yet.

My proposal is to use P1's content Document as the canonical producer contract and update the
backend boundary losslessly. We need to preserve mixed/unknown language tags, nullable text,
table cells/spans, page status/warnings, structured transforms and the separate review/origin
fields for equations and figures. The backend will retain authority for access, ID mapping,
revision commits and invalidation; producer data must not override those controls.

I verified the hashes of the 18 producer files and reran all 12 vectors against
local P16 at 786fe47. All three valid P1 samples still fail direct P3 validation.
The latest P2 converter at 54493ac passes its nine
checks and opens all three positive samples. It now keeps page outcomes and
warnings, marks physical-page fallbacks, and combines stacked headers into
column labels. It also documents how it chooses an English or Hindi voice for
mul/und. Please confirm how we should carry the original language tags and table
header associations through the backend-to-reader package.

For P1, please confirm the producer contract family, versions, and commit we
should pin. Please also confirm which critical-symbol flags the producer emits
and how it represents PDF points, image pixels, rotation, crop, and DPI.

I have prepared a reconciliation matrix and compatibility evidence. Once the three of us agree
on that version, I will align the P3 schemas, persistence, adapter and consumer tests. I am not
marking the contract approved or the integration ready at this stage.
