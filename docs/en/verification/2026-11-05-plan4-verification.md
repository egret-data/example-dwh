# Plan 4 - trade reference domain, evals and orchestration verification

Measured on 2026-11-05 at head `2cc9fb1` (the commit that adds this file follows it and changes only this file). One
chain run in bash on a fresh stack (`make dev-down` first), under `caffeinate`:

```bash
bash -c 'set -o pipefail; make dev-down && make lint && make sql-lint && make test-repo && make dwh-test \
  && make validate && make dwh-lint && make check-standards && make sync-agents-check && make pre-commit \
  && make catalog && make image && make dev-up && make smoke && make test-dags && make test-integration \
  && make e2e; echo EXIT=$?'   # -> EXIT=0
```

| Step | Result |
|------|--------|
| `make lint` | All checks passed; 125 files already formatted |
| `make sql-lint` | All Finished (no violations) |
| `make test-repo` | 22 passed |
| `make dwh-test` | 204 passed |
| `make validate`, `make dwh-lint`, `make check-standards` | 0 finding(s) each |
| `make sync-agents-check` | agent files are up to date |
| `make pre-commit` | 7 hooks Passed |
| `make catalog` | wrote `site/index.html` |
| `make smoke`, `make image`, `make dev-up` | completed |
| `make test-dags` | 27 passed |
| `make test-integration` | 33 passed (5 min 58 s) |
| `make e2e` | e2e OK |

The log is `.superpowers/sdd/2026-11-04-plan4-trade-domain/plan4-final-chain.log`; its tail is `e2e OK` then
`EXIT=0`, and it holds no `ABANDONED_QUERY`. An earlier attempt at `0126736` stopped at `make e2e` (see Known
limits); its log is kept next to this one.

## V1 - the trade domain's expected values

Each expected value from the fixture, with the integration test in `tests/integration/test_trade_domain.py` that
asserts it.

| Expected value | Test |
|----------------|------|
| Every DIM has `'-1' Unknown` and `'-2' Not applicable` (date, customer, shop) | `test_date_dimension_covers_the_calendar_and_special_members`, `test_customer_dimension_has_current_rows_and_labelled_special_members`, `test_shop_dimension` |
| Customer 102 has two history versions, valid from 2026-10-05 09:00 and 2026-11-02 10:00 (Vietnam time) | `test_customer_history_records_the_move_at_the_source_change_time` |
| Sequential run: DWD orders per day 1 / 1 / 2 on 11-01 / 11-02 / 11-03 (STD-05-08 late rows) | `test_sequential_run_misses_orders_first_loaded_after_their_event_day` |
| After re-running 11-01 and 11-02 oldest first: 2 / 2 / 2 | `test_backfill_oldest_first_picks_up_late_rows` |
| Order 2 carries `'Da Nang'`, order 5 carries `'Ho Chi Minh'` (point in time, STD-05-05) | `test_orders_carry_the_city_the_customer_had_when_ordering` |
| Payments land on the pay day | `test_payments_are_event_facts_on_the_pay_day` |
| One lifecycle row per order; unpaid orders 4 and 6 have `pay_date_key = '-2'` | `test_lifecycle_has_one_row_per_order_and_marks_unpaid_orders` |
| An order paid on a later day keeps its placed day and its payment | `test_lifecycle_order_paid_on_a_later_day_keeps_its_placed_day_and_payment` |
| Re-running an old day alone does not regress later payments | `test_rerunning_an_old_day_alone_does_not_regress_later_payments` |
| DWS 1d (six rows: 11-01 101: 120000 / 102: 80000; 11-02 101: 40000 / 103: 250000; 11-03 102: 99000 / 103: 15000; `app_order_amt_sum_1d` per row) | `test_dws_1d` |
| 11-03: `order_amt_sum_30d` and `order_amt_sum_td` 101: 160000, 102: 179000, 103: 265000; `order_cnt_td` 2 each | `test_dws_nd_and_td_on_the_last_day` |
| nd on an old day ends on that day (11-01: 101: 120000, 102: 80000) | `test_dws_nd_on_an_old_day_ends_on_that_day` |
| ADS on 11-03: `avg_order_amt_td` 101: 80000, 102: 89500, 103: 132500 | `test_ads_customer_value` |
| Reconciliation: DWD per dt equals DWS 1d (200000 / 290000 / 114000); `pay_amt` equals the source total 549000 | `test_reconciliation_dwd_to_dws_and_payments_to_source` |
| Re-running the last day is idempotent | `test_rerunning_the_last_day_is_idempotent` |
| The `date_key` relationships tests run under `--indirect-selection buildable` | `test_buildable_selection_still_runs_the_date_key_relationships_tests` |

## V2 - orchestration: Task 7 spike and the e2e chain

Spike evidence (Airflow 3.3.2 image):

- An asset-triggered run has no cron data interval. `AssetTriggeredTimetable` never schedules anything and its
  `infer_manual_data_interval` gives an interval at the moment of creation, one day too late for the Vietnam day.
- `triggering_asset_events` carries `source_dag_id` and `source_run_id`; its `source_dag_run` (fetched through the API
  inside the worker) has `conf` and `data_interval_start` as plain datetimes. `dt` comes from `dbt_ods_*` events
  (`_common.dates.ASSET_DT_TEMPLATE`).
- Cosmos emits an Asset for a snapshot (`dim_pub_customer_hist`), so `dbt_trade` needs no marker Asset.
- Cosmos renders `dbt test --select <model>` per model, and eager indirect selection errors on tests of unbuilt
  downstream models; the DAGs set `test_indirect_selection=BUILDABLE`. That dropped the four `dim_pub_date`
  relationships tests, which `-- depends_on: {{ ref('dim_pub_date') }}` in the DWD and DWS models restored.
- Live scheduler run (`airflow standalone` in the image, Task 7): a scheduled `dbt_ods_shop` run for the Vietnam day
  2026-11-04 triggered `dbt_pub`, then `dbt_trade` (an AND of six Assets), once each, and both ran dbt with
  `dt: 2026-11-04`. The live run also found that concurrent tasks shared one `DBT_TARGET_PATH`, so Asset events were
  attributed to the wrong model; each task now writes to `/tmp/dbt/target/{{ ti.task_id }}`.

The e2e of this chain (`dev/e2e.sh`) runs, in the image, `airflow dags test dbt_ods_shop 2026-11-03`, then `dbt_pub`
and `dbt_trade` with `--conf '{"dt": "2026-11-02"}'`. Output:

```text
--- assets
15 assets: ods x4 (customers_df, orders_di, payments_di, shops_df), dim x4 (pub_customer, pub_customer_hist,
pub_date, trade_shop), dwd x3, dws x3, ads x1
--- asset events
asset_event ... dev_ods/ods_shop_shops_df     source_task_id=ods_shop_shops_df.run
asset_event ... dev_ods/ods_shop_payments_di   source_task_id=ods_shop_payments_di.run
asset_event ... dev_ods/ods_shop_orders_di    source_task_id=ods_shop_orders_di.run
asset_event ... dev_ods/ods_shop_customers_df source_task_id=ods_shop_customers_df.run
--- rows for dt=2026-11-02
ods.ods_shop_orders_di dt=2026-11-02 rows: "2"
ods.ods_shop_customers_df dt=2026-11-02 rows: "3"
dwd.dwd_trade_order_di dt=2026-11-02 rows: "1"
dws.dws_trade_customer_1d dt=2026-11-02 rows: "1"
e2e OK
```

All three DAG runs ended `successful`. The `MULTIPLE:` rejection of collapsed days is covered by Jinja unit tests in
`tests/dags/test_business_day.py` and a `dbt compile` check, not by this run.

## V3 - skill evals (Claude Code only, model `sonnet`)

Runner: `evals/run.sh` (with and without skills at one commit), judge `evals/grade.py` (majority of 3 judge calls per
criterion), summary `evals/summary.py`, driver `make eval-all`. Ten scenarios. The table combines the clean full run
at `0ca9513` (nine rows) with the one scenario re-run at `ca1d49d` after its criteria were corrected; each row is
labelled with its own sha. The skill text in `skills/` was refactored twice before the clean run (`921b1d5`:
STD-07-04 before a new DWS, full scaffold commands in the answer, candidate causes before locating a layer;
`dfd239f`: STD-07-04 in `dwh-start`, count-and-sum debug queries per hop), and `dwh-backfill` and `dwh-debug` changed
again in the final fix wave.

| Scenario | sha | With skills | Without skills | Discriminates |
|----------|-----|-------------|----------------|---------------|
| backfill-after-fix | 0ca9513 | PASS 4/4 | PASS 4/4 | no |
| debug-number-mismatch | 0ca9513 | PASS 4/4 | PASS 4/4 | no |
| dimension-attribute-history | ca1d49d | FAIL 1/3 | FAIL 2/3 | no |
| new-source-crm | 0ca9513 | PASS 3/3 | PASS 3/3 | no |
| reuse-derived-metric | 0ca9513 | PASS 4/4 | PASS 4/4 | no |
| revenue-by-channel | 0ca9513 | FAIL 3/4 | FAIL 3/4 | no |
| review-bad-model | 0ca9513 | PASS 6/6 | FAIL 4/6 | yes |
| scaffold-dws | 0ca9513 | FAIL 3/4 | FAIL 2/4 | no |
| start-urgent-pressure | 0ca9513 | FAIL 2/3 | PASS 3/3 | no |
| verify-before-done | 0ca9513 | FAIL 1/2 | PASS 2/2 | no |

Result: 5 of 10 pass with skills and 1 of 10 discriminates. **The spec's success criterion (§1: scenarios pass on
Claude Code) is not met.** The user accepted this as the honest result. Why:

- One agent run per side is noisy. In the clean run only 3 of about 70 judge decisions had split votes, but the same
  scenario flipped between single agent runs on nearly identical skills (for example start-urgent-pressure,
  verify-before-done and scaffold-dws passed with skills earlier, and debug-number-mismatch and reuse-derived-metric
  passed without skills in this run).
- `docs/standards/` already carries many of the rules the skills teach, so the no-skills baseline passes many
  scenarios.

Multi-run evaluation (k agent runs per side, majority) is a recorded follow-up in `evals/README.md`. No eval was run
for this record.

## V4 - `dwh lint` on the real project

`make dwh-lint` (and `make validate`, `make check-standards`) report `0 finding(s)` on the project at `2cc9fb1`. The
project now holds domains `trade` and `crm`, three processes, 14 dbt models (4 ODS, 3 DIM, 3 DWD, 3 DWS, 1 ADS), one
snapshot, 55 data tests and 5 unit tests, so lint covers every layer.

## Known limits

The first three limits below were measured on a live scheduler afterwards: see `2026-11-05-plan4-followups.md`
(the `MULTIPLE` path works, a manual `dbt_pub` run leaves events queued with a nightly ordering consequence, and the
namespace race happens and the default retries absorb it).

- **Collapsed business days fail loudly and are rerun by hand.** When producer runs of different days collapse into
  one asset-triggered run, the template renders `MULTIPLE:<day>,<day>`, `get_dt` raises, and the operator reruns each
  listed day with `conf.dt`, oldest first (STD-11-03, `dwh-backfill`). This is unit-tested (Jinja templates) and
  compile-tested (`dbt compile --vars`); it is **not tested on a live scheduler**.
- **The producer `conf.dt` behaviour under `dbt_trade`'s AND schedule is reasoned, not measured live.** Events of a
  manual `dbt_pub` run are expected to stay queued until the next night's ODS events; this is why `dbt_pub` events are
  ignored.
- **First-run namespace race on an empty warehouse.** Four concurrent ODS tasks race to create the `dev_ods`
  namespace. The default two retries are expected to absorb it; this was not measured.
- **e2e attempt 1 (at `0126736`) hit `ABANDONED_QUERY`.** Two Trino queries in the `dbt_trade` lifecycle test task
  were abandoned after 1941 s, and the container clock lagged Airflow's by about 32 minutes. It looks like a host or
  Docker pause. It was not reproduced: the run in this record and the final fix wave's run had none.
- **Eval noise.** See V3: the verdicts rest on one agent run per side.
- **Open follow-ups from the final review:**
  - the scaffold types every `_id` column `bigint` although `payment_id` is varchar (M-2; the contract fails loudly at
    build, and the fix is to read the type from the upstream manifest);
  - M-3: the STD-05-03 example shows `order_amt` as `decimal(38, 4)`, but the reference domain uses
    `decimal(18, 2)` for DWD and `decimal(38, 2)` for DWS sums;
  - M-5: `dwh-backfill` still says to trigger `dbt_pub` with `conf.dt` before `dbt_trade`, which does nothing for a
    DWD-upward backfill because DIMs are current-state tables;
  - multi-run evaluation, as above.
