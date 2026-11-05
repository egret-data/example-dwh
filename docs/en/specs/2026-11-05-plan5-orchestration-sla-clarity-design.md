# Plan 5 design: dependable orchestration, SLA watchdog, clearer conventions

Status: draft for owner review (2026-11-05). Amends the main spec
[2026-11-04-kimball-dwh-design.md](2026-11-04-kimball-dwh-design.md) (D10, §4, §7, §10).

## 1. Why

A peer review of the repo (after plan 4) and our own live-scheduler measurements
([plan 4 follow-ups](../verification/2026-11-05-plan4-followups.md)) found:

| # | Finding | Evidence |
|---|---------|----------|
| F1 | With Asset scheduling, a missing event means nothing runs **and nothing alerts**. There is no SLA. | design; no watchdog exists |
| F2 | A manual `dbt_pub` run leaves DIM events queued for `dbt_trade`; later nights `dbt_trade` starts alongside `dbt_pub` until someone clears the queue. | measured live |
| F3 | `dt` for asset-triggered runs is reverse-engineered from the producer's data interval (`ASSET_DT_TEMPLATE`), which is hard to reason about. | `dags/_common/dates.py` |
| F4 | Backfill cannot stop between layers to check data: events push the next DAG automatically. | peer review |
| F5 | Technical columns (`dt`, `valid_from`, `valid_to`, `is_current`, …) look like business columns. | peer review |
| F6 | The docs mix layers, table types and concepts; there is no architecture page; the Vietnamese guide reads as a translation; small projects see no minimal path. | peer review |

Owner decisions (2026-11-05): keep Asset scheduling and add an SLA; prefix **every** technical column with
`dw_`, including the partition column (`dt` → `dw_dt`); a pluggable alert callback (Slack webhook via the
Airflow connection `dwh_alert`, else log); default SLA deadline 06:00 Asia/Ho_Chi_Minh, overridable per model;
the Vietnamese guide and the new architecture page are written natively in Vietnamese. The folder layout is out
of scope until the reviewer names what to change.

## 2. Orchestration: one "done" Asset per DAG, carrying `dt`

### 2.1 Design

Every pipeline DAG (`dbt_ods_<source>`, `dbt_<domain>`) ends with one small task, `publish_done`, that emits a
single DAG-level Asset with the day it built:

```text
Asset name : dwh_done/<dag_id>            e.g. dwh_done/dbt_pub
Event extra: {"dt": "2026-11-02"}
```

- Downstream DAGs are scheduled **only** on upstream `dwh_done/*` Assets, never on model Assets.
  - `dbt_ods_shop` (cron 00:00 VN) → emits `dwh_done/dbt_ods_shop`.
  - `dbt_pub` schedule: `dwh_done/dbt_ods_shop`.
  - `dbt_trade` schedule: `dwh_done/dbt_pub` only. `dbt_pub` already waited for the whole ODS DAG, so the shop
    ODS tables `dbt_trade` reads are built for that day.
  - A domain that needs several upstream DAGs uses an AND of their `dwh_done` Assets (rule in STD-11).
- Cosmos keeps emitting model Assets: they stay for lineage in the Airflow UI, not for scheduling.
- `publish_done` depends on every other task (`all_success`), so a partly failed run emits nothing.

### 2.2 How `dt` is chosen (replaces `ASSET_DT_TEMPLATE`)

```text
dt = own conf.dt
   else the "dt" extra of the triggering dwh_done events:
        one distinct day  -> that day
        several days      -> "MULTIPLE:d1,d2"   (get_dt rejects it; rerun each day by hand, oldest first)
        none              -> ""                 (get_dt rejects it)
```

Cron DAGs keep `DT_TEMPLATE` (own conf.dt, else the VN day of the data interval). The data-interval lookup of a
producer run (`source_dag_run.data_interval_start`) is removed.

### 2.3 Why this fixes F2–F4

- **F2:** `dbt_trade` waits on one Asset. A manual `dbt_pub` run emits `dwh_done/dbt_pub` with its own `dt` and
  starts `dbt_trade` for that day immediately; nothing stays queued, so the next night is normal.
- **F3:** the day travels with the event, written by the DAG that built it.
- **F4:** a manual run accepts `conf.propagate` (default `true`). With `false`, `publish_done` is skipped, so no
  event is emitted and nothing downstream starts. Backfill becomes: run layer N for day D with
  `propagate=false`, check the data, then run layer N+1 for D (§4).

### 2.4 Risks to measure first (Task 1 spike)

1. Setting `outlet_events[asset].extra` from a plain `@task` in Airflow 3.3.2, and reading it in the consumer's
   template via `triggering_asset_events`.
2. A skipped `publish_done` emits no event.
3. Two `dbt_ods_shop` runs that complete while `dbt_pub` is paused give one `dbt_pub` run with two events →
   `MULTIPLE`.
If (1) fails, fall back to one Asset per day-independent name plus an XCom read of the producer run — the spike
report decides, and the owner is told before Task 2.

## 3. SLA watchdog and alerts

### 3.1 Watchdog DAG `dwh_sla_watchdog`

- Cron hourly from 02:00 to 12:00 Asia/Ho_Chi_Minh. Each run checks business day `D` = yesterday (VN).
- For every model in the dbt manifest whose deadline (default `06:00`, override `config.meta.sla: "HH:MM"`) has
  passed at run time:
  - partitioned models (ODS, DWD, DWS, partitioned ADS): `D` has at least one row **or** the model's
    `meta.sla_allow_empty: true` and its DAG's `publish_done` for `D` succeeded;
  - unpartitioned DIM / ADS and `_hist` snapshots: the latest Iceberg snapshot was committed after `D + 1 00:00`
    VN (`"<table>$snapshots"`).
- Any miss: one alert listing every late model with its layer, owning DAG and deadline; the task fails (red in
  the UI). It alerts again each hour until the miss clears.
- It reads the manifest built in the image (no `dbt ls` at run time) and queries Trino with the read-only
  connection.

### 3.2 Alert callback

`dags/_common/alerts.py::notify(context_or_message)`:
- If the Airflow connection `dwh_alert` exists (type HTTP, host = Slack webhook URL), POST a short message.
- Otherwise log at ERROR. Never raises (an alert failure must not hide the original failure).
- Used as `on_failure_callback` in `DEFAULT_ARGS` for every DAG, and by the watchdog.

### 3.3 Rules

STD-11 gains: every pipeline DAG ends with `publish_done`; downstream DAGs schedule only on `dwh_done/*`;
every model has an SLA (default or `meta.sla`); alerts go through `alerts.notify`. A lint check (DWH-L or a new
code in the existing families) fails a DAG schedule that names a model Asset.

## 4. Backfill, step by step

`skills/dwh-backfill` and STD-11 are rewritten around `conf.propagate`:

1. Pause nothing. For each day `D`, oldest first, one at a time:
   1. Trigger the first DAG to rebuild with `{"dt": "D", "propagate": false}`.
   2. Verify `D` for that layer (row counts, reconciliation, grain).
   3. Trigger the next DAG with `{"dt": "D", "propagate": false}`; repeat to the last layer.
2. Or, when no check between layers is needed: one run with `{"dt": "D"}` (propagate defaults to true) chains
   the rest automatically.
3. nd/td DWS: continue through today. Never reload past ODS for `di`/`df` sources. Respect retention.

## 5. Technical columns: prefix `dw_`

| Today | New | Where |
|-------|-----|-------|
| `dt` | `dw_dt` | partition column of every ODS, DWD, DWS and partitioned ADS table; DIM daily snapshots |
| `valid_from`, `valid_to` | `dw_valid_from`, `dw_valid_to` | `_hist` (snapshot meta column names) |
| `is_current` | `dw_is_current` | `_hist` |
| `is_inferred` | `dw_is_inferred` | DIM inferred members |
| dbt snapshot `dbt_scd_id`, `dbt_updated_at` | `dw_scd_id`, `dw_snapshot_at` | `snapshot_meta_column_names` |

- The run parameter stays `dt`: `conf.dt`, the dbt var `dt`, `get_dt()`. It names the business day being built;
  `dw_dt` names the stored column.
- New rule STD-02-xx: technical (warehouse-managed) columns start with `dw_` and come from a closed list in
  `warehouse/glossary.yml`; a column starting with `dw_` that is not on the list, or a listed name without the
  prefix, is a lint error (new DWH-N code).
- Amend D10: "partition column is `dw_dt` (DATE)".
- Migration: dev and CI rebuild from scratch (`make dev-down`); there is no production data yet. The maintenance
  macro, scaffold, sqlfluff stub, tests, catalogue, skills, rulebook examples and both guides change with it.

## 6. Documentation

- **Architecture page** `docs/en/architecture.md` and `docs/vi/kien-truc.md` (Vietnamese written natively, not
  translated):
  1. layers (one diagram, one paragraph each: purpose, who reads it, what it may read);
  2. table types inside each layer, one table per layer: ODS `di`/`df`; DIM current, `_hist`, date; DWD
     transaction/event, accumulating snapshot, periodic snapshot (rule only); DWS `1d`/`nd`/`td`/`1w`; ADS;
     with "use when", naming pattern, partitioning, load strategy, example;
  3. technical columns;
  4. orchestration (done Assets, dt, SLA) in one diagram.
- **Minimal path** section: a small project starts with ODS → DWD + DIM; add DWS only under STD-07-04 and ADS only
  for a named application; the design gate still applies to new processes and conformed dimensions.
- **Glossary** stays in the guide but only as a lookup table pointing to the architecture page.
- **Vietnamese guide** rewritten natively (short sentences, the terms Vietnamese data teams use, English term in
  parentheses on first use). The English guide is updated for §2–§5.

## 7. Out of scope

- Folder layout changes (waiting for concrete proposals from the reviewer).
- Eval multi-run spending (machinery exists since PR #11; running it is a separate budget decision).

## 8. Acceptance

- Live scheduler: cron ODS → `dbt_pub` → `dbt_trade` chained by `dwh_done` with the right `dt`; a manual
  `dbt_pub` run with `conf.dt` starts `dbt_trade` for that day and leaves no queue; `propagate=false` stops the
  chain; the watchdog alerts (log) for a model whose day is missing after its deadline and clears after the
  rebuild.
- `dw_dt` everywhere; the new lint codes catch an unprefixed technical column and a model-Asset schedule.
- Full chain `EXIT=0` on a fresh stack; integration fixture values unchanged.
- Architecture page and native Vietnamese guide reviewed by the owner.
