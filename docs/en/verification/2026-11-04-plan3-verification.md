# Plan 3 - rulebook, agent files and skills verification

Measured on 2026-11-04 at head `66999a6` (the commit that adds this file follows it and changes only the CI
workflow, pre-commit config, README, the spec and this file). One chain run in bash on a fresh stack
(`make dev-down` first):

```bash
bash -c 'set -o pipefail; make dev-down && make lint && make sql-lint && make test-repo && make dwh-test \
  && make validate && make dwh-lint && make check-standards && make sync-agents-check && make pre-commit \
  && make catalog && make image && make dev-up && make smoke && make test-dags && make test-integration \
  && make e2e; echo EXIT=$?'   # -> EXIT=0
```

| Step | Result |
|------|--------|
| `make lint` | All checks passed; 109 files already formatted |
| `make sql-lint` | All Finished (no violations) |
| `make test-repo` | 5 passed |
| `make dwh-test` | 186 passed |
| `make validate`, `make dwh-lint`, `make check-standards` | 0 finding(s) each |
| `make sync-agents-check` | agent files are up to date |
| `make pre-commit` | 7 hooks Passed (ruff check, ruff format, sqlfluff, dwh validate, dwh lint, dwh sync-agents, dwh check-standards) |
| `make catalog` | wrote `site/index.html` |
| `make test-dags` | 9 passed (first run; no DagBag timeout flake this time) |
| `make test-integration` | 10 passed |
| `make e2e` | e2e OK |

Tail of the chain log: `e2e OK` then `EXIT=0`.

## V1 - the rulebook

`dwh check-standards --require-all` reports `0 finding(s)`. Rules per file (93 in total):

| File | Rules | File | Rules |
|------|-------|------|-------|
| `00-principles.md` | 6 | `07-dws-ads.md` | 6 |
| `01-layers.md` | 8 | `08-iceberg-incremental.md` | 10 |
| `02-naming.md` | 9 | `09-dbt-conventions.md` | 7 |
| `03-domains-bus-matrix.md` | 5 | `10-trino-sql-style.md` | 6 |
| `04-dimensions.md` | 11 | `11-airflow.md` | 7 |
| `05-facts.md` | 7 | `12-data-quality.md` | 5 |
| `06-metrics.md` | 6 | | |

## V2 - generated agent files

`dwh sync-agents --check` prints `agent files are up to date`. Generated files (all tracked):

- `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`
- `.cursor/rules/agents.mdc` and `.cursor/rules/dwh-<skill>.mdc` for the eight skills
- `.claude/skills/dwh-<skill>/SKILL.md` for the eight skills

The eight skills: `dwh-start`, `dwh-requirement`, `dwh-model-design`, `dwh-implement`, `dwh-verify`, `dwh-review`,
`dwh-debug`, `dwh-backfill`.

## V3 - skills tested with scenarios (RED / GREEN)

Model for every run: `sonnet`, headless with `claude -p --setting-sources project` through `evals/run.sh`, graded
by hand against each scenario's Pass if / Fail if. Refactor rounds are rounds that changed the skill text after a
GREEN run.

RED refs: `da97356` (the plan 3 base) for Tasks 10 and 11, and for the first Task 12 runs. The controller found that
`da97356` contains the plan 3 document (`docs/en/plans/2026-11-04-plan3-rulebook-skills.md`) with the full skill
texts, and the agents read it, so a RED pass on that ref is not evidence. The Task 12 REDs were re-run on `ded533b`,
the last commit before the plan 3 document. The Task 10 and 11 REDs failed even on the contaminated ref, so their
conclusions stand.

| Skill | Scenario | RED | GREEN | Refactor rounds |
|-------|----------|-----|-------|-----------------|
| `dwh-start` | `start-urgent-pressure` | fail (0/3: SQL with no class, no metric or bus-matrix check, no next skill) | pass 3/3 after round 1 (GREEN first run lacked the path) | 1 |
| `dwh-requirement` | `new-source-crm` | plain prompt passes; with the pressure prompt it fails (calls the work ODS-only, skips the design gate) | pass | 0 |
| `dwh-model-design` | `new-source-crm` | same RED as above | partial on first GREEN (label not named, waiver accepted), pass after round 1 (red-flag row: a waiver is not the design-approved label) | 1 |
| `dwh-start` / `dwh-requirement` | `revenue-by-channel` | passes, plain and under pressure (does not discriminate) | pass | 0 |
| `dwh-start` | `reuse-derived-metric` | plain prompt passes; with the pressure prompt it fails (no class, no BI DWD/DIM note) | pass | 0 |
| `dwh-verify` | `verify-before-done` | fail (no evidence list, no contract) | pass | 0 |
| `dwh-review` | `review-bad-model` | partial fail (durable key, contract and `meta.process` missed) | pass | 0 |
| `dwh-implement` | (covered by the two scenarios above and the scaffold tests) | - | - | 0 |
| `dwh-debug` | `debug-number-mismatch` | fail on 3 of 4 criteria on `da97356`, and again on clean `ded533b` | pass 4/4 (caveat: the fixture has only ODS, so the hop-by-hop trace compares source to ODS) | 0 |
| `dwh-backfill` | `backfill-after-fix` | passes on `da97356` (contaminated) and on clean `ded533b` | pass 4/4 | 0 |

Refactor rounds by skill: `dwh-start` 1, `dwh-model-design` 1, all others 0.

What the table does and does not show:

- A real skill effect is shown by `start-urgent-pressure`, `new-source-crm` (pressure), `reuse-derived-metric`
  (pressure), `verify-before-done`, `review-bad-model` and `debug-number-mismatch` (fails on the clean ref too).
- `revenue-by-channel` and `backfill-after-fix` do not discriminate: RED passes, because the base model and the
  spec already behave. Their GREEN results are consistent with, but not proof of, skill value. Plan 4 must harden
  them.
- `dwh-implement` has no scenario of its own.

## V4 - scaffold dry run per layer, and sqlfluff on the output

Run in a scratch copy of the repo with `evals/fixtures/trade/warehouse` copied over `warehouse/`
(processes `order` and `shipment`, dimensions `date`, `customer`, `shop`). `--write` was used for DIM, DWD, DWS and
ADS; the ODS model already exists in the repo, so ODS was run as a print-only dry run.

```bash
dwh scaffold ods_shop_orders_di --grain order_id                      # print only
dwh scaffold dim_pub_customer --from ods_shop_customers_df --write    # dim + dim_pub_customer_hist snapshot
dwh scaffold dim_trade_shop --from ods_shop_customers_df --write      # SCD1, no snapshot
dwh scaffold dwd_trade_order_di --from ods_shop_orders_di --grain order_id --write
dwh scaffold dws_trade_customer_1d --from dwd_trade_order_di --grain customer_key \
  --metric order_amt_sum_1d order_cnt_1d --write
dwh scaffold dws_trade_customer_nd --from dwd_trade_order_di --grain customer_key \
  --metric app_order_amt_sum_30d --write
dwh scaffold ads_bi_customer_daily --from dws_trade_customer_1d --grain customer_key \
  --metric order_amt_sum_1d avg_order_amt_1d --write
uvx --python 3.12 sqlfluff==4.5.0 lint <the generated .sql files>      # -> All Finished!, no violations
```

Every command wrote its files (SQL, YAML, and the `_hist` snapshot for the SCD4 dimension) and sqlfluff reported no
violation on the generated SQL. The scaffold tests (`tools/dwh/tests/test_scaffold.py`) additionally lint the
scaffolded DWD, DWS and ADS against every `dwh lint` family. Descriptions are empty on purpose, so `DWH-D01` and
`DWH-D02` fail until a person fills them.

## V5 - pre-commit on all files

`make pre-commit` (`pre-commit run --all-files`) passes all seven hooks, including the two added in this task:
`dwh sync-agents --check` and `dwh check-standards`. CI's `lint` job now also runs `make check-standards` and
`make sync-agents-check`.

## Final review fixes

The final whole-branch review (`.superpowers/sdd/2026-11-04-plan3-rulebook-skills/final-review.md`, not committed)
asked for one design decision and a set of consistency fixes. Applied at `c198348`:

- **User decision (2026-11-04), STD-05-08:** a transaction DWD over an updated-in-place `di` source is an event fact.
  Its `dt` is the Vietnam day of the event timestamp, a run reads every ODS partition from `dt` on, and it keeps the
  earliest ODS version per grain key. Later changes go into an accumulating snapshot merged by key. `dwh scaffold`
  now requires `--event-at` for a transaction DWD, writes that shape with the new `in_business_day_tz()` macro, and
  refuses an accumulating snapshot. STD-05-05, STD-08-07, STD-12-03, `dwh-backfill`, `dwh-debug` and spec §7/§11
  follow it.
- **Scaffold output obeys the MUST rules:** DWD keys map a null natural key to `'-1'`; DIM unions the `'-1'` and `'-2'`
  members; every DIM, DWD, DWS, ADS and snapshot sets its selection tag; a DIM from a `di` upstream keeps the latest
  version per natural key.
- **Rulebook and skills:** the Reuse path goes through `dwh-model-design`; STD-11-08 gives every model a DAG;
  Correct examples in 01, 03, 09, 10 and 12 match the tooling; `airflow backfill create` replaces the removed
  `airflow dags backfill`; `make sql-fix` exists; README scaffold examples run against the eval fixture and exit 0.
- **Eval isolation:** `evals/run.sh` deletes `evals/`, `docs/en/plans/` and `docs/en/verification/` from the eval
  worktree before the agent runs (checked with a dry run that replaces the `claude` call by `ls`).

Commands, run at `c198348`:

```bash
make lint && make sql-lint && make test-repo && make dwh-test && make check-standards && make sync-agents-check \
  && make pre-commit; echo EXIT=$?   # -> EXIT=0
make dev-up && make test-integration; echo EXIT=$?   # -> EXIT=0
```

| Step | Result |
|------|--------|
| `make lint` | All checks passed; 111 files already formatted |
| `make sql-lint` | no violations |
| `make test-repo` | 5 passed (the scaffold sqlfluff probe now covers the event DWD and a DIM from a `di` upstream) |
| `make dwh-test` | 197 passed |
| `make check-standards`, `make validate` | 0 finding(s) each |
| `make sync-agents-check` | agent files are up to date |
| `make pre-commit` | 7 hooks Passed |
| `make test-integration` | 11 passed (new: `test_in_business_day_tz_keeps_exactly_the_vietnam_day`) |

The stack chain beyond `test-integration` (`make test-dags`, `make e2e`, `make catalog`) and the evals were not
re-run: no DAG, model or ODS code changed.

## Known limits

- Scenario grading is manual until plan 4.
- Skills were tested on Claude Code only (model `sonnet`); Cursor, Copilot, Codex and Gemini read the generated files
  but were not run.
- `DWH-D02` cannot see columns that are missing from the `.yml`.
- Plan 4's eval harness must exclude `docs/en/plans` from eval worktrees, or pin RED to a pre-plan commit (for
  example `ded533b`): a ref that contains the plan document lets the agent read the skill texts.
- `revenue-by-channel` and `backfill-after-fix` do not discriminate between RED and GREEN and need hardening in
  plan 4; the `debug-number-mismatch` fixture has only ODS models.
- `dwh lint --changed` scopes by folder, so a change to `warehouse/*.yml` that affects findings elsewhere is only
  caught by the full `make dwh-lint` in CI.
- GREEN eval runs made before the final review fixes could read their own scenario rubric in `evals/scenarios/`:
  at least `reuse-derived-metric-82c1260` did (its answer says the metric name "appears nowhere except the eval
  scenario text"). The answers do not quote the rubric and the RED/GREEN deltas match the skill changes, so the
  conclusions stand, but they were not measured blind. `evals/run.sh` now removes `evals/`, `docs/en/plans/` and
  `docs/en/verification/` from the eval worktree; no re-run was made.
