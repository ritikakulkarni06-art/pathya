# Backend decisions

- Follow the supplied playbook inside the existing Pathya repository on `person-3`; do not create a second repository. Backend packages use the requested root `app/` layout.
- Python 3.12, UUID4 identifiers, SQLite and plain SQL; no ORM or external queue.
- P1 readiness checks storage and DB reachability. Migration verification is added in P2.
- Windows without GNU Make uses `python -m scripts.check`, the same commands as `make check`.
- API docs endpoints are disabled until an authenticated documentation route is supplied; OpenAPI is exported offline.
- Worker execution deliberately refuses until P7, rather than claiming jobs were processed.
- No LLM, cloud call or embedding model is enabled or downloaded during P1?P5.
- Existing main/person branches and teammates' work areas are preserved.

- Supplied Uvicorn commands disable access logs to avoid raw question URLs; structured logs use route templates.
