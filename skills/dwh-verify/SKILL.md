---
name: dwh-verify
description: Use when dbt models or DAGs have been written or changed, before saying the change is done, opening or updating a PR, or reporting numbers to anyone
---

# dwh-verify: evidence before claims

No command output, no claim. "Looks right" and "should work" are not evidence.

## Steps

1. **Build** on dev for the dt you changed:

   ```bash
   docker compose -f dev/compose.yml run --rm airflow \
     'cd dags/dbt && $DBT_EXECUTABLE_PATH build --select <model>+ --vars "{dt: YYYY-MM-DD}"'
   ```

   Every model, unit test and data test must pass.
2. **Lint.** `make dwh-lint`, `make sql-lint` and `make lint` must each report 0 findings.
3. **Numbers** (`12-data-quality.md`):
   - rows per dt against the source;
   - grain uniqueness;
   - one amount reconciled across each hop (ODS ↔ DWD, DWD ↔ DWS).
4. **Idempotency.** Build the same dt twice; the counts must not change.
5. **Performance baseline.** Record wall time, input rows and bytes, output rows, and Iceberg file count and size
   for the dt. For a change to an existing model, record the same numbers before and after.
6. **Paste the evidence.** Put the commands and their real output in the PR description. If anything failed, say
   so; do not round it away.

## Red flags

| Thought | Reality |
|---------|---------|
| "The SQL is simple, it obviously works" | Simple SQL still fans out on a bad join. Run the counts. |
| "Tests passed earlier" | Earlier is not this code or this dt. Run them again. |
| "I'll add the evidence after review" | Reviewers cannot check a claim without its output. |
| "I verified a different dt" | Verify the dt you changed, plus the next one. |

## Rules

`docs/standards/12-data-quality.md`, `08-iceberg-incremental.md`.
