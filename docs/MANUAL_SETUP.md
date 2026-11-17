# Manual steps and handoff gates

## Pending teammate integration

1. Send Person 1 `docs/CONTRACTS.md`, `contracts/extraction_output.schema.json`, the synthetic fixture and `docs/HANDOFF_FOR_EXTRACTION.md`. Get their written acceptance or requested changes. Share their reply with Codex; it will be recorded in `docs/CONTRACT_APPROVALS.md`. The user explicitly deferred this gate on 16 November 2026; implementation may continue with the draft and synthetic adapter.
2. Confirm the identifier/page-label rules and proposed speech-unit boundary with Person 2. Their actual speech adapter is not required until P9, but agreement is needed before integration.
3. Add teammates in GitHub repository Settings > Collaborators, using their GitHub usernames. Create a main-branch protection/ruleset requiring a pull request and at least one approving review. The agent has not changed these account settings.

## Already checked or handled

Python 3.12, Git and SQLite FTS5 are available. A project-local .venv was installed. Use `python -m scripts.check` instead of GNU Make on Windows. No separate repository is needed; work stays on person-3 in pathya. No real API secret is present or required for P1-P9.

## Later, when the corresponding stages exist

- Session deployment: generate a long random SESSION_SECRET locally, keep it in .env, and use trusted HTTPS for secure cookies. Do not paste secrets into chat, issues or commits.
- P11/P12: obtain a Gemini key privately; verify current official model ID, tariff, retention and terms; choose a hard INR budget; fill the price table before enabling paid calls. No model or price has been assumed, and none of these APIs is called yet.
- Optional embeddings: obtain the local model, license and checksum; a native Hindi speaker must review retrieval examples.
- Data: agree rights/consent/retention wording with the guide; assemble authorized demo/evaluation chapters and the rights ledger.
- P15: humans write and adjudicate the 60-question set, keep dev/held-out separate, and review generated claims against sources. The synthetic fixture is not the evaluation corpus.
- Deployment/release: run manual security/failure drills, restore a backup on a clean machine, review all licenses, send both handoffs and appoint a maintenance owner.

The complete original checklist remains in docs/PLAYBOOK.md. No proposed accuracy, accessibility conformance or security-assessment result has been asserted.


For speech integration, Person 2 must provide the import paths for their segmenter
and speech provider, and confirm tested English/Hindi voices. See the P9 section
in docs/CONTRACTS.md. The included WAV output is silence for development; it is
not usable narration. No live provider, voice or pricing has been verified.
