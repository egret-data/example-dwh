# Plan 4 follow-ups - live scheduler measurements

Measured on 2026-11-05 on branch `fix/plan4-followups`. It closes three "Known limits" of
`2026-11-05-plan4-verification.md`: the `MULTIPLE` path, the manual `dbt_pub` run under `dbt_trade`'s AND schedule,
and the first-run namespace race. The full chain on a fresh stack at `1ff9782` ended `EXIT=0` (lint, sql-lint,
test-repo 30, dwh-test 234, validate/dwh-lint/check-standards 0 findings, pre-commit, test-dags 27,
test-integration 33, e2e OK).

## Set-up

- A fresh stack: `make dev-down && make dev-up`. Before the run, `show schemas from iceberg` listed only
  `information_schema` and `system`.
- `airflow standalone` in `example-dwh-airflow:dev` (Airflow 3.3.2), started with `docker compose run` on the dev
  network.
- The metadata database is Postgres (a database `airflow` on the dev Postgres), with `LocalExecutor` (parallelism
  32), so tasks really run concurrently. SQLite would hide the race.
- The DAGs are the repository's, unchanged.
- Measurement C ran with `DWH_TASK_RETRIES` unset (2 retries, 5 minutes apart). The container was then restarted on
  the same metadata database with `DWH_TASK_RETRIES=0` for A and B, so a failing run fails at once.
- Evidence comes from `airflow` CLI output, task logs under `/opt/airflow/logs`, and the `dag_run`, `asset_event`
  and `asset_dag_run_queue` tables.
- Each "night" below is a `dbt_ods_shop` run made with `airflow backfill create` for one or two Vietnam days. A
  backfill run has the same data interval as a scheduled run. Measured: it emits the same Asset events and queues
  `dbt_trade` the same way.
- Everything was torn down afterwards: `docker rm -f dwh-live`, then `make dev-down`.

## C - first-run namespace race (default retries)

Unpausing the three DAGs made the scheduled run `scheduled__2026-11-04T17:00:00+00:00` of `dbt_ods_shop` (Vietnam
day 2026-11-04).

| Run | Task | Attempt 1 | Attempt 2 |
|-----|------|-----------|-----------|
| `dbt_ods_shop` scheduled | `ods_shop_payments_di.run` | failed: `ICEBERG_CATALOG_ERROR ... Failed to create a namespace dev_ods` | success |
| `dbt_trade` `asset_triggered__2026-11-05T02:43:28.885979+00:00_EGOi2YHD` | `dws_trade_customer_1d.run` | failed: `Failed to create a namespace dev_dws` | success |

- The other three ODS runs and the other DWS tasks won their races.
- Both DAG runs ended `success`. `dbt_pub` (`asset_triggered__2026-11-05T02:38:34.851221+00:00_ZFlw54Rw`) ran with
  `dt: '2026-11-04'`, and so did `dbt_trade`.
- **Result: the race happens (in ODS and again in DWS), and the default retries absorb it.** The first retry
  succeeds, at a cost of the 5-minute retry delay.
- Whether `DWH_TASK_RETRIES=0` (the e2e setting) fails such a first run was not measured. `make e2e` runs the DAGs
  with `airflow dags test` and did not hit the race in this branch's chain.

## A - collapsed business days (`MULTIPLE`)

1. `dbt_pub` was paused, so its events would not queue, and the `asset_dag_run_queue` table was empty.
2. A two-day backfill ran: `airflow backfill create --dag-id dbt_ods_shop --from-date 2026-11-01T00:00:00+07:00
   --to-date 2026-11-02T00:00:00+07:00 --max-active-runs 1`.
   - It made `backfill__2026-11-01T17:00:00+00:00` (Vietnam day 11-01) and `backfill__2026-11-02T17:00:00+00:00`
     (11-02). Both succeeded.
   - The queue then held `ods_shop_orders_di`, `ods_shop_payments_di` and `ods_shop_shops_df` for `dbt_trade`.
     `dbt_trade` did not run: the DIM half of its AND was missing.
3. `dbt_pub` was unpaused and triggered with `--conf '{"dt": "2026-11-02"}'`
   (`manual__2026-11-05T03:00:45.635250+00:00`, success).
   - Its DIM events completed the AND. `dbt_trade` run `asset_triggered__2026-11-05T03:02:51.633303+00:00_RkPUAiZ0`
     started at once and **failed**.
   - Rendered vars: `{dt: 'MULTIPLE:2026-11-01,2026-11-02'}`. Task log of `dwd_trade_order_di.run`:
     `Compilation Error in model dwd_trade_order_di ... dt MULTIPLE:2026-11-01,2026-11-02: this asset-triggered run
     collapsed several business days into one, and one run builds exactly one ...`, raised by `get_dt`.
   - `dwd_trade_order_di.run` and `dwd_trade_payment_di.run` failed, and every DWD/DWS/ADS task downstream was
     `upstream_failed`. `dim_trade_shop`, a current-state table that reads no `dt`, ran.
   - The `dbt_pub` `conf.dt` was not a candidate: the listed days are the two ODS days.
4. `dbt_trade` was rerun by hand, oldest first:
   - `--conf '{"dt": "2026-11-01"}'` (`manual__2026-11-05T03:06:20.301105+00:00`) succeeded;
   - then `--conf '{"dt": "2026-11-02"}'` (`manual__2026-11-05T03:10:39.911077+00:00`) succeeded.
   - Trino afterwards: `dwd_trade_order_di` 11-01: 2 rows, 11-02: 1; `dws_trade_customer_1d` 11-01: 2, 11-02: 1.
     Order 2 (placed on 11-01, first loaded on 11-02) is counted on 11-01 because both ODS days existed.

**Result: confirmed live.** The collapsed run fails loudly with `MULTIPLE:`, and the per-day reruns with `conf.dt`,
oldest first, succeed.

## B - a manual `dbt_pub` run with `conf.dt`

1. The queue was empty. `dbt_pub` ran with `--conf '{"dt": "2026-11-01"}'`
   (`manual__2026-11-05T03:13:27.994477+00:00`, success at 03:14:03).
   - 2 min 40 s later there was still no `dbt_trade` run.
   - The queue held `dim_pub_date`, `dim_pub_customer` and `dim_pub_customer_hist` for `dbt_trade`.
   - **It does not trigger `dbt_trade` at once. Its events stay queued.** (In A, the same kind of run did trigger
     `dbt_trade` at once, because ODS events were already queued.)
2. Next night: a backfill run for Vietnam day 11-03 (`backfill__2026-11-03T17:00:00+00:00`).
   - Its ODS events (03:17:19) started `dbt_pub` (`..._STIlkZyC`) and `dbt_trade` (`..._G9dkJQp6`) in the same
     second.
   - `dbt_trade` rendered `dt: '2026-11-03'`, one candidate, and succeeded. **The day is right.**
   - **But `dbt_trade` no longer waits for that night's `dbt_pub`.** `dwd_trade_order_di.run` started at
     03:17:59.150, while `dim_pub_customer_hist_snapshot` ran from 03:17:59.149 to 03:18:13.601. The queued events of
     the manual run had already met the DIM half of the AND.
   - That night's `dbt_pub` events were then left in the queue.
3. A second night (Vietnam day 11-04) repeated it.
   - `dbt_trade` (`..._k1oSYCSS`, 03:20:49.615) was created before `dbt_pub` (`..._8MNkUy3c`, 03:20:49.749).
   - `dwd_trade_order_di.run` (03:21:26.776-03:21:40.969) ran alongside the snapshot (03:21:26.780-03:21:41.041).
   - `dt` was `2026-11-04`.
   - **The state perpetuates itself.**
4. Clearing the queue restores the order.
   - `DELETE /api/v2/dags/dbt_trade/assets/queuedEvents` returned 204 and emptied the queue. The Airflow CLI has no
     command for it: `airflow assets` offers only `details`, `list` and `materialize`.
   - The next night (11-03 again), `dbt_pub` ran from 03:25:02 to 03:25:47.58. `dbt_trade` was created at 03:25:47.38,
     after the snapshot event, with `dt: '2026-11-03'`.

**Consequence.** The day logic is right: the queued `dbt_pub` events plus the night's ODS events give one candidate
day. The ordering is wrong after any manual `dbt_pub` run: every later night's DWD can join a `_hist` snapshot that
has not taken that night's changes yet, until the queue is cleared.

The manual rebuild order for one past day, written into `dwh-backfill` and STD-11-03:
1. From DWD upward, trigger only `dbt_trade` with `conf.dt` (oldest first, wait for each run). Do not trigger
   `dbt_pub`: its DIMs are current-state tables that read no `dt`.
2. If `dbt_pub` must run by hand (a DIM logic fix), remove only its DIM events from `dbt_trade`'s queue after it
   succeeds, with `DELETE /api/v2/dags/dbt_trade/assets/<asset_id>/queuedEvents` per DIM Asset (ids from
   `GET /api/v2/dags/dbt_trade/assets/queuedEvents` and `GET /api/v2/assets?uri_pattern=dim_pub_`). Never delete
   the whole queue: it can hold the ODS events of a night whose `dbt_trade` has not run, and that night would then
   never run.

What was verified for step 2:
- Measured live: the whole-queue DELETE on a queue that held only DIM events (204, queue empty, normal order the next
  night).
- Read, not exercised: the per-asset endpoint `DELETE /api/v2/dags/{dag_id}/assets/{asset_id}/queuedEvents` and the
  `uri_pattern` filter of `GET /api/v2/assets`. Both are in the Airflow 3.3.2 API source in the image
  (`airflow/api_fastapi/core_api/routes/public/assets.py`). `GET .../queuedEvents` returns `asset_id` but no URI,
  hence the second GET.
- Not measured: a DWD actually reading a stale `_hist` row. Only the overlap in time is measured.

## Known limits after this record

- **Not fixed: the overlap after a manual `dbt_pub` run.** It is avoided by procedure (skill, STD-11-03,
  STD-11-08). A redesign is planned in a separate change: `dbt_trade` will be scheduled on `dbt_pub`'s DIM Assets,
  with `dt` carried in the Asset event extra.
- **The night is a backfill run, not a cron tick.** Its data interval and Asset events are the same, but no scheduled
  midnight run was observed beyond the first one (C).
- The live run used `DWH_TASK_RETRIES=0` for A and B. Retries would only delay the `MULTIPLE` failure: it is a
  compile error, and a retry renders the same `dt`.
