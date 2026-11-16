# Contributing

## Start work

Clone the repository, switch to your assigned branch, and pull before editing:

```bash
git switch person-3
git pull --ff-only origin person-3
```

Use `person-1` or `person-2` for the corresponding role. Keep each change focused and discuss shared API/schema changes with all three members.

## Integrate changes

1. Commit and push changes to your person branch.
2. Open a pull request targeting `main`, describe the behavior, and record validation.
3. Ask a teammate to review the affected integration contract.
4. Merge after review, then bring `main` into your person branch before the next task.

```bash
git fetch origin
git merge origin/main
```

Resolve conflicts locally and validate the affected workflow before pushing. Avoid force-pushing shared branches.

## Definition of done

- Changed behavior is documented and checked appropriately.
- Shared identifiers, revisions and source links remain consistent.
- Relevant accessibility, extraction, authorization or grounding checks are recorded.
- No secrets, private uploads, generated runtime data or unlicensed textbook samples are committed.
- Limitations and unavailable services are visible to users.

There is no application test suite or build workflow yet. Each module must add meaningful checks and reproducible setup instructions as it becomes runnable.
