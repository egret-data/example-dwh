---
name: dwh-implement
description: Use when a design is approved or a reuse change is agreed, and dbt models, snapshots, tests or DAGs must be written or changed
---

# dwh-implement: tests first, then SQL

## Steps

1. **Scaffold.** Run
   `uv run --project tools/dwh dwh scaffold <model> --from <upstream> --grain <columns> [--metric <name>] --write`.
   A transaction DWD also takes `--event-at <column>` (`05-facts.md` STD-05-08); an accumulating snapshot is
   written by hand. Scaffold writes the `.sql` and the `.yml` with contract, grain and relationships tests and the
   selection tag. For an SCD4 dimension it also writes the `_hist` snapshot.
2. **Complete the YAML.** Fill every description, check each `data_type`, and list every column the SQL selects
   (DWH-D02 cannot see unlisted columns). Scaffold copies a passed-through column's type from the upstream model's
   `.yml`, or from the ODS model's `cast(<c> as <type>) as <c>`; it never uses the source's own type. It refuses an
   ODS column it cannot type. The columns and measures it had to guess from the name are listed in a comment at
   the top of the `.yml`.
3. **Unit tests for logic.** Add dbt unit tests for non-trivial logic in `_<folder>__unit_tests.yml`: day windows,
   SCD point-in-time joins, metric filters. Incremental models need `overrides.macros.is_incremental`. Run them and
   watch them fail.
4. **Write the SQL** to the layer rules.
   - Use `get_dt()`, `in_business_day()` and `source_ts()`, never `{{ ds }}`.
   - Use CTEs, filter `dt` early, join on durable keys.
5. **Orchestration** (`11-airflow.md`): a new source gets a `dbt_ods_<source>` DAG; a new domain gets a
   `dbt_<domain>` DAG. Every model, `dim_pub_*` and `_hist` snapshots included, must be selected by one DAG
   (STD-11-08).
6. **Lint.** Run `make sql-lint` and `make dwh-lint` until both are clean, then go to `dwh-verify`.

## Red flags

- SQL written before the `.yml` tests exist.
- Editing `.claude/`, `.cursor/`, `CLAUDE.md` or another generated file. Edit `skills/` or `AGENTS.md` and run
  `make sync-agents`.
- `select *` outside ODS, a join without a fan-out check, or `approx_distinct` outside ADS.
- A ratio stored in DWD or DWS.

## Rules

`docs/standards/04-dimensions.md`, `05-facts.md`, `08-iceberg-incremental.md`, `09-dbt-conventions.md`,
`10-trino-sql-style.md`, `11-airflow.md`.
