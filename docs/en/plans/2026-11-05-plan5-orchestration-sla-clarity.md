# Plan 5 — dependable orchestration, SLA watchdog, `dw_` technical columns, clearer docs

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the nightly chain dependable and visible. Every pipeline DAG ends with one `dwh_done/<dag_id>` Asset
that carries the day it built. Downstream DAGs schedule only on those Assets. A watchdog alerts when a model misses
its deadline. Every warehouse-managed column starts with `dw_`. The dbt project moves to `dbt/warehouse/`, with one folder per
model. The
docs gain an architecture page, a minimal path, and a natively written Vietnamese guide.

**Architecture:**
- **Spike first (Task 1).** The three Airflow risks of design §2.4 are measured on a live scheduler, plus three
  facts later tasks rely on. A STOP rule guards Task 3.
- **Repository layout (Tasks 2a, 2b; owner input 2026-11-05).**
  - `dags/dbt` moves to `dbt/warehouse/`. git-sync clones the whole repository; `dags.gitSync.subPath` only tells
    Airflow where the DAG folder sits inside the clone.
  - Paths, Makefile targets and `dwh` take a project name, so a RisingWave project can join later as
    `dbt/streaming/`.
  - Each model gets its own folder with its own `.yml` (DWH-L07).
- **Orchestration (Tasks 3–6).**
  - `publish_done` and `dwh_done/<dag_id>` Assets; the dt template `DONE_DT_TEMPLATE`.
  - The lint code DWH-L06.
  - `alerts.notify` as every task's `on_failure_callback`.
  - The `dwh_sla_watchdog` DAG.
- **Technical columns (Tasks 7a, 7b).** First the rename, then the rule (DWH-N07, STD-02-10). Each half can be
  approved or rejected on its own.
- **Backfill (Task 8).** It is rewritten around `conf.propagate`.
- **Docs (Task 9).** The architecture page, the minimal path and both guides.
- **Final chain (Task 10).** The full chain on a fresh stack, the live-scheduler acceptance and the record.

**Tech Stack:**
- Airflow 3.3.2 (Task SDK, Assets), Cosmos 1.16.0;
- dbt-core 1.11.16 and dbt-trino 1.11.0;
- Trino 483 with Iceberg;
- Python 3.12 and uv; pytest 9.2.0; sqlfluff 4.5.0; ruff 0.17.3;
- `@mermaid-js/mermaid-cli@11.4.2` (diagram validation only).

**Spec:** `docs/en/specs/2026-11-05-plan5-orchestration-sla-clarity-design.md` (the approved design, the source of
truth). It amends `docs/en/specs/2026-11-04-kimball-dwh-design.md` (§3, D10, §4, §7, §10, §11). Measured facts:
`docs/en/verification/2026-11-05-plan4-verification.md` and `docs/en/verification/2026-11-05-plan4-followups.md`.

**Base.** This plan was written against `origin/main` (`eabf757`). PR #11 (`fix/plan4-followups`) changes files this
plan touches:
- `tools/dwh/src/dwh/scaffold.py` (scaffold typing) and the new `tools/dwh/src/dwh/column_types.py`;
- `skills/dwh-backfill/SKILL.md`, `docs/standards/11-airflow.md`, `docs/standards/05-facts.md`;
- both guides and `dags/_common/dates.py` (comments only).

The text and line numbers below follow that branch. **Execution starts from `main` after PR #11 merges.** If it has
not merged, the controller stops and asks the owner.

## Global Constraints

- **Branch.** `feat/plan5-orchestration-sla` off `main` (after PR #11). Merge only after green CI (`lint`, `stack`)
  and the owner's "merge đi". No `design-approved` label is needed: no domain, process, dimension or metric is
  added.
- **Follow the repository's own process.** Read `AGENTS.md` and the matching `skills/*/SKILL.md` before each task.
  Every rule in `docs/standards/` applies; cite rule IDs in the report when a choice follows one.
- **Paths.**
  - Task 1 runs on the old layout.
  - From Task 2a on, the dbt project is `dbt/warehouse/`, never `dags/dbt`. In production and in the dev compose
    stack it is `/opt/airflow/dags/repo/dbt/warehouse`: git-sync clones the whole repository, and compose mounts it
    read-only at `/opt/airflow/dags/repo`.
  - Code resolves it with `_common.dbt.dbt_project_dir("warehouse")`, the Makefile with
    `DBT_PROJECT ?= warehouse`, and `dwh` with `--project warehouse`.
  - From Task 2b on, a model lives in `dbt/warehouse/models/<layer>/<domain or source>/<model>/<model>.sql`, next to
    `<model>.yml`. Sources stay in `models/ods/<source>/_<source>__sources.yml`.
  - Later tasks name files in this layout, for example
    `dbt/warehouse/models/dwd/trade/dwd_trade_order_di/dwd_trade_order_di.sql`. The `_hist` snapshot path is the one
    Task 2b Step 1 decided.
  - Per-model folders and named projects are the owner's decisions of 2026-11-05. A streaming project is out of
    scope.
- **Values copied from the design (verbatim, do not change):**
  - Asset name: `dwh_done/<dag_id>` (for example `dwh_done/dbt_pub`). Event extra: `{"dt": "2026-11-02"}`, key
    `dt`.
  - `dbt_ods_shop` (cron 00:00 VN) emits `dwh_done/dbt_ods_shop`. `dbt_pub` is scheduled on
    `dwh_done/dbt_ods_shop`, and `dbt_trade` on `dwh_done/dbt_pub` only. A domain that needs several upstream DAGs
    uses an AND of their `dwh_done` Assets.
  - Cosmos keeps emitting model Assets, for lineage only; no schedule names one.
  - `publish_done` depends on every other task (`all_success`).
  - `conf.propagate` defaults to `true`. With `false`, `publish_done` is skipped and no event is emitted.
  - dt of an asset-triggered run:
    - its own `conf.dt`;
    - else the `dt` extra of the triggering `dwh_done` events: one distinct day gives that day; several give
      `"MULTIPLE:d1,d2"`, which `get_dt` rejects; none gives `""`, which `get_dt` rejects.
  - Cron DAGs keep `DT_TEMPLATE`. The producer data-interval lookup (`source_dag_run.data_interval_start`) is
    removed.
  - The watchdog `dwh_sla_watchdog`:
    - runs on a cron, hourly from 02:00 to 12:00 Asia/Ho_Chi_Minh, and checks business day `D` = yesterday (VN);
    - uses the default deadline `06:00` and the per-model override `config.meta.sla: "HH:MM"`, plus
      `meta.sla_allow_empty: true`;
    - sends one alert per run listing every late model with its layer, owning DAG and deadline, and the task
      fails;
    - reads the manifest built in the image (no `dbt ls` at run time).
  - Alerts: `dags/_common/alerts.py::notify(context_or_message)`.
    - The Airflow connection `dwh_alert` (type HTTP, host = Slack webhook URL) gets a POST; without it, the alert
      is logged at ERROR.
    - It never raises.
  - The technical-column prefix is `dw_`. The mapping:

    | Today | New | Where |
    |-------|-----|-------|
    | `dt` | `dw_dt` | partition column of every ODS, DWD, DWS and partitioned ADS table; DIM daily snapshots |
    | `valid_from`, `valid_to` | `dw_valid_from`, `dw_valid_to` | `_hist` (snapshot meta column names) |
    | `is_current` | `dw_is_current` | `_hist` |
    | `is_inferred` | `dw_is_inferred` | DIM inferred members |
    | dbt snapshot `dbt_scd_id`, `dbt_updated_at` | `dw_scd_id`, `dw_snapshot_at` | `snapshot_meta_column_names` |

  - **The run parameter stays `dt`:** `conf.dt`, the dbt var `dt`, `get_dt()`. It names the business day being
    built; `dw_dt` names the stored column.
- **The fixture stays.** The source fixture (`dev/postgres/init/01-init.sql`) and every expected value of the plan
  1–4 integration tests are unchanged. Task 7a changes column names in SQL text only.
  - The orders per day are 1 / 1 / 2, and 2 / 2 / 2 after the backfill.
  - The DWS, ADS and reconciliation values are those of `docs/en/plans/2026-11-04-plan4-trade-domain.md`, "The
    fixture and what it proves".
  - A changed number is a defect, never a new expectation.
- **dbt YAML.** Generic test arguments go under `arguments:`, and `meta` and `tags` under `config:`.
- **Lint and tests must stay green after every task:**
  - `make dwh-lint` and `make sql-lint` report 0 findings, and `make lint` is clean. ruff 0.17 formats Python inside
    Markdown, with line length 110. This plan itself must pass `make lint`.
  - `make check-standards`, `make sync-agents-check`, `make dwh-test` and `make test-repo` pass.
  - Tasks that touch DAGs or dbt also pass `make test-dags`, `make test-integration` and `make e2e` on a fresh stack
    (`make dev-down && make image && make dev-up`).
- **Destructive operations.**
  - Integration tests and spikes drop only `itest*` schemas, and restore any source row they change (in `finally`).
  - Never use shell `rm`/`cp`: they are aliased interactive and hang. Use git, `command cp -f`, or Python.
  - The live-scheduler containers (`dwh-spike`, `dwh-live`) are removed with `docker rm -f` and the stack with
    `make dev-down`.
- **Spikes never land in `dags/`.** Spike DAGs live in `.superpowers/sdd/2026-11-05-plan5/` (untracked; never
  `git add` it). Every commit step names its paths explicitly.
- **Commits.** Code, comments, docs and commit messages are in English, except the Vietnamese docs of Task 9.
  Commits follow Conventional Commits and end with:

  ```text
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```

## Task order

| Task | What | Depends on |
|------|------|------------|
| 1 | Spike on a live scheduler (STOP rule) | — |
| 2a | Move the dbt project to `dbt/warehouse/`; project-name plumbing | — |
| 2b | One folder per model; scaffold; DWH-L07; STD-09-08 and STD-09-09 | 2a |
| 3 | `publish_done`, `dwh_done/<dag_id>`, `conf.propagate`, `DONE_DT_TEMPLATE`, schedules | 1 (STOP), 2b |
| 4 | Lint DWH-L06: no DAG schedule names a model Asset | 3 |
| 5 | `alerts.notify` and `on_failure_callback` | 2b |
| 6 | `dwh_sla_watchdog` | 1, 3, 5 |
| 7a | `dw_` rename in code, models and tests | 2b, 6 |
| 7b | The `dw_` rule: closed list, DWH-N07, STD-02-10, rulebook and docs sweep, D10 | 7a |
| 8 | Backfill rewritten around `propagate=false` | 3 |
| 9 | Architecture page, minimal path, guides, README | 3–8 |
| 10 | Spec, live acceptance, full chain, verification record | all |

---

### Task 1: Spike — done Assets with `dt` on a live scheduler

**Files:**
- Create (untracked): `.superpowers/sdd/2026-11-05-plan5/spike_dags/spike_done.py`
- Create: `docs/en/verification/<date>-plan5-spike.md` (`<date>` = the execution date)

**Interfaces:**
- Produces: measured answers to M1–M6. Tasks 3 and 6 build on them:
  - **M1** (design §2.4 risk 1): `outlet_events[asset].extra` set in a plain `@task` reaches the consumer's
    template through `triggering_asset_events`.
  - **M2** (risk 2): a skipped `publish_done` emits no event, and no consumer run starts.
  - **M3** (risk 3): two producer runs that complete while the consumer is paused give one consumer run with two
    events, which renders `MULTIPLE`.
  - **M4** (for Task 6): a `@task` with the done Asset as an inlet reads those events and their `extra` through
    `inlet_events[asset][-10:]`.
  - **M5** (for Task 6): whether a dbt snapshot run with no source change commits a new Iceberg snapshot.
  - **M6:** `Asset(name="dwh_done/spike_producer")` (no URI scheme) is accepted and listed by `airflow assets list`.

- [ ] **Step 1: Write the spike DAGs.** Create `.superpowers/sdd/2026-11-05-plan5/spike_dags/spike_done.py`. The
  template is the exact `DONE_DT_TEMPLATE` Task 3 adds.

```python
"""Airflow spike DAGs (plan 5 Task 1): a done Asset whose event extra carries the business day."""

from airflow.exceptions import AirflowSkipException
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Asset, task

DONE = Asset(name="dwh_done/spike_producer")
DONE_DT_TEMPLATE = (
    "{% set found = namespace(days=[]) %}"
    "{% for events in triggering_asset_events.values() %}{% for event in events %}"
    "{% set day = (event.extra or {}).get('dt') %}"
    "{% if day and day not in found.days %}{% set found.days = found.days + [day] %}{% endif %}"
    "{% endfor %}{% endfor %}"
    "{% set days = found.days | sort %}"
    "{{ (dag_run.conf or {}).get('dt') or (days | first if days | length == 1 else "
    "('MULTIPLE:' ~ days | join(',') if days else '')) }}"
)

with DAG(dag_id="spike_producer", schedule=None, catchup=False, tags=["spike"]):

    @task(task_id="publish_done", outlets=[DONE])
    def publish_done(dt: str, *, dag_run=None, outlet_events=None) -> None:
        if (dag_run.conf or {}).get("propagate", True) is False:
            raise AirflowSkipException("propagate=false")
        outlet_events[DONE].extra = {"dt": dt}

    publish_done(dt="{{ dag_run.conf['dt'] }}")

with DAG(dag_id="spike_consumer", schedule=DONE, catchup=False, tags=["spike"]):
    BashOperator(task_id="show_dt", bash_command=f"echo SPIKE_DT=[{DONE_DT_TEMPLATE}]")

with DAG(dag_id="spike_watch", schedule=None, catchup=False, tags=["spike"]):

    @task(task_id="read_done", inlets=[DONE])
    def read_done(*, inlet_events=None) -> None:
        print("SPIKE_INLET", [(event.extra or {}).get("dt") for event in inlet_events[DONE][-10:]])

    read_done()
```

- [ ] **Step 2: Start a live scheduler** (Postgres metadata DB and `LocalExecutor`, as in the plan 4 follow-ups:
  SQLite would hide concurrency):

```bash
make image && make dev-up
docker compose -f dev/compose.yml exec -T postgres psql -U dwh -d dwh -c 'CREATE DATABASE airflow_spike'
docker compose -f dev/compose.yml run -d --name dwh-spike \
  -e AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/dags/repo/.superpowers/sdd/2026-11-05-plan5/spike_dags \
  -e AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://dwh:dwhsecret@postgres:5432/airflow_spike \
  -e AIRFLOW__CORE__EXECUTOR=LocalExecutor -e DWH_TASK_RETRIES=0 \
  airflow 'airflow standalone'
until docker logs dwh-spike 2>&1 | grep -q 'Airflow is ready'; do sleep 5; done
A='docker exec dwh-spike airflow'
PSQL='docker compose -f dev/compose.yml exec -T postgres psql -U dwh -d airflow_spike -At -c'
$A dags unpause spike_producer && $A dags unpause spike_consumer && $A dags unpause spike_watch
```

Evidence queries, used after each measurement:

```bash
$PSQL "select e.id, a.name, e.extra, e.source_run_id from asset_event e join asset a on a.id = e.asset_id order by e.id"
$PSQL "select run_id, state, run_type from dag_run where dag_id = 'spike_consumer' order by id"
$PSQL "select * from asset_dag_run_queue"
docker exec dwh-spike bash -c 'grep -rh "SPIKE_DT=\|SPIKE_INLET" /opt/airflow/logs | tail -20'
```

- [ ] **Step 3: M1 and M6.** Run `$A dags trigger spike_producer --conf '{"dt": "2026-11-02"}'`, then wait for
  `spike_consumer`.
  - Expected: one `asset_event` row for `dwh_done/spike_producer` with extra `{"dt": "2026-11-02"}`.
  - Expected: one `asset_triggered` consumer run, whose log holds `SPIKE_DT=[2026-11-02]`.
  - Expected: `$A assets list --output plain` lists `dwh_done/spike_producer`.
- [ ] **Step 4: M2.** Run `$A dags trigger spike_producer --conf '{"dt": "2026-11-03", "propagate": false}'`.
  - Expected: `publish_done` is `skipped` (check `task_instance`), and there is no new `asset_event` row.
  - Expected: the queue is empty, and there is still no new consumer run after 2 minutes.
- [ ] **Step 5: M3.**
  1. Run `$A dags pause spike_consumer`.
  2. Trigger the producer with dt `2026-11-04` and wait for success; then with `2026-11-05` and wait.
  3. Record the queue, then run `$A dags unpause spike_consumer` and wait 2 minutes.
  - **Outcome (a):** one consumer run whose log holds `SPIKE_DT=[MULTIPLE:2026-11-04,2026-11-05]`. Risk 3 behaves
    as the design says.
  - **Outcome (b):** no consumer run, because a paused DAG queues nothing. Then trigger the producer once more with
    `2026-11-06`, and record which events the resulting consumer run consumed
    (`select * from dagrun_asset_event`) and the `SPIKE_DT` it rendered.

  Either outcome is a valid measurement. Task 3's STD-11-03 wording follows the record.
- [ ] **Step 6: M4.** Run `$A dags trigger spike_watch`. Expected: the log holds
  `SPIKE_INLET ['2026-11-02', '2026-11-04', '2026-11-05', ...]`, the dt of every event emitted so far, oldest first.
- [ ] **Step 7: M5** (in schema `itest_spike`, so destructive operations stay on `itest*`):

```bash
DBT='docker compose -f dev/compose.yml run --rm -e DBT_SCHEMA=itest_spike -e DBT_TARGET_PATH=/tmp/dbt/target-spike airflow'
SNAPS='SELECT count(*), max(committed_at) FROM iceberg.itest_spike_dim."dim_pub_customer_hist$snapshots"'
$DBT 'cd dags/dbt && $DBT_EXECUTABLE_PATH build --select +dim_pub_customer_hist --vars "{dt: 2026-11-02}"'
docker compose -f dev/compose.yml exec -T trino trino --execute "$SNAPS"
$DBT 'cd dags/dbt && $DBT_EXECUTABLE_PATH snapshot --select dim_pub_customer_hist'
docker compose -f dev/compose.yml exec -T trino trino --execute "$SNAPS"
$DBT "/opt/dbt-venv/bin/python -c \"import sys; sys.path.insert(0, 'tests/integration'); from helpers import drop_schemas; drop_schemas('itest_spike')\""
```

  Record both counts. If the count did not grow, an unchanged `_hist` gets no new Iceberg snapshot. Then the
  watchdog cannot use the commit time alone for `_hist`, and Task 6's "or its DAG's done event for D" clause for
  snapshots is required (it is in the code either way).
- [ ] **Step 8: Tear down.** Run `docker rm -f dwh-spike && make dev-down`.
- [ ] **Step 9: Write the verification note** `docs/en/verification/<date>-plan5-spike.md`. Include:
  - the set-up (image tag, metadata DB, executor);
  - the spike DAG source (copy Step 1);
  - for M1–M6, the command, the evidence rows and log lines, and a one-line result;
  - "Consequences for Tasks 3 and 6".

- [ ] **Step 10: Commit**

```bash
git add docs/en/verification/*-plan5-spike.md
git commit -m "docs(verification): measure done Assets carrying dt on a live scheduler (plan 5 spike)" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**STOP rules (controller):**
- **M1 or M2 fails.** The extra does not reach the consumer template, or a skipped `publish_done` still emits an
  event. Stop and ask the owner before Task 3. Design §2.4 names the fallback: one day-independent Asset name plus an
  XCom read of the producer run.
- **M4 fails.** Tell the owner before Task 6. The watchdog would then read done events through the Airflow REST API
  (`GET /api/v2/assets/events?asset_id=...`) instead of `inlet_events`.
- **M5 shows no snapshot commit for an unchanged `_hist`.** Tell the owner that `_hist` also passes the SLA on its
  DAG's done event for `D`. This is a narrowing of design §3.1 forced by Iceberg. It is not blocking.
- **M3 outcome (b).** Tell the owner that `MULTIPLE` appears only when the next event arrives, and continue.

---

### Task 2a: Move the dbt project to `dbt/warehouse/` and pass the project name

Owner input (2026-11-05). git-sync clones the **whole** repository, and `dags.gitSync.subPath: "dags"` only tells
Airflow where the DAG folder sits inside the clone. So a root `dbt/` is on disk in production too, at
`/opt/airflow/dags/repo/dbt`. The plan 1 assumption that only `subPath` is synced was wrong.

The project is named `warehouse` (the Trino/Iceberg batch warehouse). A RisingWave streaming project will be added
later next to it, as `dbt/streaming/`. That project is out of scope now. But nothing may hard-code a single project:
the path resolution, the Makefile and CI targets, and `dwh` all take a project name. Each project keeps its own
`dbt_project.yml`, packages and profiles.

**Files:**
- Move: `dags/dbt/` → `dbt/warehouse/` (`git mv`)
- Modify: `dags/_common/dbt.py`, every DAG file (it passes `project=`), `dags/maintenance/iceberg_maintenance.py`,
  `dags/.airflowignore`
- Modify: `dbt/warehouse/dbt_project.yml` (`packages-install-path`), `dev/compose.yml`, `Dockerfile`, `Makefile`,
  `.gitignore`, `.sqlfluff`, `.pre-commit-config.yaml`
- Modify: `tools/dwh/src/dwh/cli.py`, `scaffold.py`, `manifest.py` (docstring), `tools/dwh/tests/test_lint.py`,
  `test_manifest.py`, `test_scaffold.py`
- Modify: `tests/integration/helpers.py`, `tests/repo/test_sqlfluff.py`, `tests/dags/test_transform_dags.py`
- Modify: `AGENTS.md`, `skills/dwh-verify/SKILL.md` (then `make sync-agents`), `docs/standards/09-dbt-conventions.md`,
  `10-trino-sql-style.md`, `11-airflow.md` (STD-11-02, STD-11-07), both guides, `README.md`
- Modify: `docs/en/specs/2026-11-04-kimball-dwh-design.md` (§3 layout and bullets, §11)

**Interfaces:**
- Produces:
  - `_common.dbt.dbt_project_dir(project: str) -> Path`. It is `<root>/<project>`, where `<root>` is
    `$DWH_DBT_ROOT` when set, else `Path(__file__).absolute().parents[2] / "dbt"`. Use `absolute()`, not
    `resolve()`: git-sync swaps a symlink, so resolving would pin one checkout. The module already says so.
  - `_common.dbt.dbt_dag_kwargs(*, project: str, select: list[str], dt_template: str = DT_TEMPLATE)`. `project` is
    required, so every DAG names its project.
  - `_common.dbt.WAREHOUSE = "warehouse"`, the project name the DAGs pass.
  - Makefile variables `DBT_PROJECT ?= warehouse` and `DBT_DIR := dbt/$(DBT_PROJECT)`. Every dbt, sqlfluff and dwh
    target uses them, so `make dwh-lint DBT_PROJECT=streaming` will work later.
  - `dwh lint|scaffold --project NAME` (default `warehouse`) means `--project-dir dbt/NAME`. An explicit
    `--project-dir` still wins.
  - Packages per project: `packages-install-path` is `$DWH_DBT_PACKAGES_ROOT/<project>`. The image sets
    `DWH_DBT_PACKAGES_ROOT=/opt/dbt_packages`; a host run uses `.dbt/packages`.
  - Profiles per project: `dbt/warehouse/profiles.yml`. Code passes the project dir as the profiles dir and never
    relies on one global `DBT_PROFILES_DIR`.
- **Shared macros.** Macros shared across projects (for example `get_dt`) move to a local package when the second
  project arrives. That is YAGNI now; the spec amendment says so.

- [ ] **Step 1: Write the failing tests.** Append to `tests/dags/test_transform_dags.py`:

```python
def test_dbt_projects_sit_under_dbt_at_the_repository_root():
    from _common.dbt import WAREHOUSE, dbt_project_dir

    project = dbt_project_dir(WAREHOUSE)
    assert (project.parent.name, project.name) == ("dbt", "warehouse")
    assert project.parent.parent.name != "dags"
    assert (project / "dbt_project.yml").is_file()
    assert (project / "profiles.yml").is_file()


def test_the_dbt_root_can_be_overridden(monkeypatch, tmp_path):
    from _common.dbt import dbt_project_dir

    monkeypatch.setenv("DWH_DBT_ROOT", str(tmp_path))
    assert dbt_project_dir("streaming") == tmp_path / "streaming"


def test_every_dbt_task_runs_the_warehouse_project(dagbag):
    from _common.dbt import WAREHOUSE, dbt_project_dir

    for dag_id in ("dbt_ods_shop", "dbt_pub", "dbt_trade"):
        assert dagbag.get_dag(dag_id).project_config.dbt_project_path == dbt_project_dir(WAREHOUSE)
```

If `DbtDag` does not expose `project_config`, read the path the way Cosmos stores it (check
`cosmos/airflow/dag.py` in the image) and keep the assertion.

Run: `make image && make dev-up && make test-dags`. Expected: FAIL (`dbt_project_dir` does not exist).

- [ ] **Step 2: Move and re-point.**
  - `git mv dags/dbt dbt/warehouse` (create `dbt/` first with `mkdir -p dbt`).
  - `dags/_common/dbt.py`. `dbt_dag_kwargs` takes `*, project: str` and uses `dbt_project_dir(project)` for
    `ProjectConfig` and `ProfileConfig`. Delete `DBT_PROJECT_DIR`.

    ```python
    # Not resolve(): git-sync swaps a symlink; keep the stable /opt/airflow/dags/repo path.
    DAGS_DIR = Path(__file__).absolute().parent.parent
    # git-sync clones the whole repository, so dbt projects sit next to dags/ (/opt/airflow/dags/repo/dbt/<name>).
    WAREHOUSE = "warehouse"  # the Trino/Iceberg batch warehouse; a streaming project will sit next to it


    def dbt_project_dir(project: str) -> Path:
        """The directory of dbt project `project`: $DWH_DBT_ROOT/<project>, else <repo>/dbt/<project>."""
        return Path(os.environ.get("DWH_DBT_ROOT") or DAGS_DIR.parent / "dbt") / project
    ```

  - Every `dbt_dag_kwargs(...)` call passes `project=WAREHOUSE`. Tasks 3 and later show it.
  - `iceberg_maintenance.py`: `project = dbt_project_dir(WAREHOUSE)`, and the command gains
    `--profiles-dir {project}`.
  - `dags/.airflowignore`: delete `dbt/` and keep `_common/`.
  - `dbt/warehouse/dbt_project.yml`:
    `packages-install-path: "{{ env_var('DWH_DBT_PACKAGES_ROOT', 'dbt_packages') }}/warehouse"`.
  - `dev/compose.yml`: `DBT_PROFILES_DIR: /opt/airflow/dags/repo/dbt/warehouse` (only for interactive `dbt` in the
    container). The read-only mount `..:/opt/airflow/dags/repo:ro` already holds the whole repository. Target and
    logs stay under `/tmp/dbt` (STD-11-07).
  - `Dockerfile`:
    - `ENV DWH_DBT_PACKAGES_ROOT=/opt/dbt_packages` replaces `DBT_PACKAGES_INSTALL_PATH`;
    - `COPY dbt/warehouse/dbt_project.yml dbt/warehouse/packages.yml dbt/warehouse/package-lock.yml /tmp/dbt-deps/warehouse/`;
    - `RUN cd /tmp/dbt-deps/warehouse && /opt/dbt-venv/bin/dbt deps ...`.
  - `Makefile`:
    - add `DBT_PROJECT ?= warehouse` and `DBT_DIR := dbt/$(DBT_PROJECT)` at the top;
    - `dbt-parse` runs `cd $(DBT_DIR)`;
    - `sql-lint` and `sql-fix` lint `$(DBT_DIR)/models`;
    - `HOST_DBT_ENV` has `DBT_PROFILES_DIR=$(DBT_DIR)` and `DWH_DBT_PACKAGES_ROOT=$(CURDIR)/.dbt/packages`, and drops
      `DBT_PACKAGES_INSTALL_PATH`;
    - the target and log paths become `.dbt/$(DBT_PROJECT)/target` and `.dbt/$(DBT_PROJECT)/logs`;
    - `manifest` and `catalog` use `--project-dir $(DBT_DIR)`;
    - `dwh-lint` uses `--project $(DBT_PROJECT) --manifest .dbt/$(DBT_PROJECT)/target/manifest.json`;
    - `catalog` reads `.dbt/$(DBT_PROJECT)/target/static_index.html`.

    CI (`ci.yml`, `catalog.yml`) calls the same targets with the default project, so no workflow change is needed.
    State this in the report.
  - `.gitignore`: `dbt/*/target/`, `dbt/*/dbt_packages/`, `dbt/*/logs/`.
  - `.sqlfluff`: `load_macros_from_path = dbt/warehouse/macros,dev/sqlfluff/macros`, with a comment saying a second
    project gets its own `.sqlfluff` in its folder.
  - `.pre-commit-config.yaml`:
    - sqlfluff `files: ^dbt/[^/]+/models/.*\.sql$`;
    - dwh-lint `files: ^(dbt/|warehouse/)`, with `--project warehouse`.
  - `tools/dwh/src/dwh/cli.py`. Add to `lint` and `scaffold`:

    ```python
    p.add_argument("--project", default="warehouse", help="dbt project name under dbt/ (default: warehouse)")
    p.add_argument("--project-dir", default=None, help="dbt project directory; default dbt/<--project>")
    ```

    Resolve once in `main`: `args.project_dir = args.project_dir or f"dbt/{args.project}"` for commands that have
    both. Lint's `--manifest` default becomes `None`, resolved to `.dbt/<project>/target/manifest.json`.
  - `scaffold.py`: `project_dir: str = "dbt/warehouse"`.
  - `manifest.py` docstring: "(e.g. dbt/warehouse)".
  - In the dwh tests, replace every `dags/dbt` with `dbt/warehouse` (`git grep -n "dags/dbt" tools/dwh/tests`).
    Add a CLI test: `main(["scaffold", "ods_shop_orders_di", "--project", "streaming", ...])` prints paths under
    `dbt/streaming/`.
  - `tests/integration/helpers.py`: `MAIN_PROJECT = REPO / "dbt" / "warehouse"`. `run_dbt` already uses
    `DBT_PROFILES_DIR=MAIN_PROJECT` and the target `/tmp/dbt/target-warehouse`; replace `str(MAIN_PROJECT)` with
    `str(project_dir)`, so each project uses its own profiles.
  - `tests/repo/test_sqlfluff.py`: `lint("dbt/warehouse/models")`.
- [ ] **Step 3: Docs and rules.**
  - `AGENTS.md` layout: the `dags/` row (`sources/`, `transform/`, `maintenance/`, `_common/`), plus a row
    `| `dbt/warehouse/` | dbt-trino project (batch warehouse); models by layer `ods/ dim/ dwd/ dws/ ads/` |`.
  - `skills/dwh-verify/SKILL.md`, STD-09 and STD-10: replace `dags/dbt` with `dbt/warehouse`.
  - STD-11-02: the example passes `project=WAREHOUSE`.
  - STD-11-07: the projects are `dbt/<name>/` at the root of the clone, `/opt/airflow/dags/repo/dbt/warehouse`;
    git-sync clones the whole repository and `subPath` only names the DAG folder. Update both examples to
    `/opt/airflow/dags/repo/dbt/warehouse`.
  - Both guides: replace `dags/dbt` with `dbt/warehouse`.
  - `README.md`:
    - the Layout rows;
    - every path;
    - "How it runs in production": "git-sync clones the **whole** repository to `/opt/airflow/dags/repo`.
      `subPath: dags` tells Airflow where the DAG folder sits inside the clone. dbt projects sit in
      `/opt/airflow/dags/repo/dbt/<name>`; today only `warehouse`."
  - Spec §3: the tree shows `dbt/warehouse/` beside `dags/`, and the `.airflowignore` comment drops "excludes dbt/".
    The bullet on packages says "per project".
  - Spec §11, append:

    ```text
    - **Plan 5 (owner input):** dbt projects move from `dags/dbt` to `dbt/<name>/` at the repository root; today
      only `dbt/warehouse/` (Trino/Iceberg batch), with a RisingWave project (`dbt/streaming/`) expected later.
      Plan 1 assumed git-sync syncs only `dags.gitSync.subPath`; in fact it clones the whole repository and
      `subPath` only names the DAG folder inside the clone, so `dbt/` is on disk in production at
      `/opt/airflow/dags/repo/dbt`. Each project keeps its own `dbt_project.yml`, packages and profiles, and
      paths, Makefile targets and `dwh` take a project name. Macros shared across projects (e.g. `get_dt`) move
      to a local package when the second project arrives, not before.
    ```

  - `make sync-agents`.
- [ ] **Step 4: Run green.** `git grep -n "dags/dbt" -- ':!docs/en/plans' ':!docs/en/verification'` prints nothing.

```bash
make lint && make sql-lint && make test-repo && make dwh-test && make validate && make dwh-lint \
  && make check-standards && make sync-agents-check \
  && make dev-down && make image && make dev-up && make test-dags && make test-integration && make e2e
```

Expected: all pass, `e2e OK`, and dwh-lint findings (if any are seeded) point at `dbt/warehouse/models/...`.

- [ ] **Step 5: Commit**

```bash
git add -A dbt dags tests tools dev Dockerfile Makefile .gitignore .sqlfluff .pre-commit-config.yaml AGENTS.md \
  skills .claude .cursor .github/copilot-instructions.md docs/standards docs/en/guides docs/vi/guides README.md \
  docs/en/specs/2026-11-04-kimball-dwh-design.md
git commit -m "refactor: move the dbt project to dbt/warehouse and pass the project name everywhere" \
  -m "git-sync clones the whole repository; subPath only names the DAG folder." \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2b: One folder per model

**Files:**
- Move: every model to `dbt/warehouse/models/<layer>/<domain>/<model>/<model>.sql`, plus a new `<model>.yml` per
  model
- Split and delete: `_shop__models.yml`, `_shop__unit_tests.yml`, `_pub__models.yml`, `_trade__models.yml` (DIM,
  DWD, DWS), `_trade__unit_tests.yml` and `_crm__models.yml`
- Keep: `dbt/warehouse/models/ods/shop/_shop__sources.yml`, and the layer `.sqlfluff` files (sqlfluff reads config
  from parent folders)
- Move: `dbt/warehouse/snapshots/dim_pub_customer_hist.yml`, to the place the Step 1 measurement decides
- Modify: `dbt/warehouse/dbt_project.yml` (only if Step 1 picks the model folder for snapshots)
- Modify: `tools/dwh/src/dwh/manifest.py` (`patch_path`, the snapshot folder), `codes.py`, `rules/layers.py` (new
  DWH-L07), `scaffold.py` (writes the folder), `catalog.py` (if it builds model paths: `git grep -n "models/"
  tools/dwh/src/dwh/catalog.py`)
- Modify: `tools/dwh/tests/fixtures/manifest.py`, `test_rules_layers.py`, `test_scaffold.py`, `test_manifest.py`,
  `tests/repo/test_scaffold_sqlfluff.py` (its comment)
- Modify: `docs/standards/09-dbt-conventions.md` (new STD-09-08 and STD-09-09), the skills (dwh-implement, and any
  that name `_<domain>__models.yml`), both guides, `README.md`

**Interfaces:**
- Produces:
  - **The layout.** `models/<layer>/<domain or source>/<model>/<model>.sql` + `<model>.yml`. The `.yml` holds that
    model's description, columns, tests, contract, `config` and its `unit_tests:`. Sources stay one file per source
    system.
  - **Code `DWH-L07`:** "a model or snapshot is not in its own folder with a same-named .yml". It is checked from
    the manifest's `original_file_path` and `patch_path`.
  - **Rules.** STD-09-08 (one folder per model) and STD-09-09 (one-off migration scripts never go under
    `model-paths`; use `analyses/` or a `migrations/` folder outside it).
  - **`_hist` location**, decided in Step 1. Either:
    - (a) the model's folder, `models/dim/pub/dim_pub_customer/dim_pub_customer_hist.yml`; or
    - (b) `snapshots/dim/pub/dim_pub_customer_hist/dim_pub_customer_hist.yml`.

- [ ] **Step 1: Measure where a snapshot YAML can live** (dbt-core 1.11.16, in the image). Work on a scratch copy,
  never on the real project:

```bash
docker compose -f dev/compose.yml run --rm airflow '
  set -euo pipefail
  mkdir -p /tmp/snapspike && cp -r dbt/warehouse/. /tmp/snapspike/ && cd /tmp/snapspike
  mkdir -p models/dim/pub/dim_pub_customer
  mv snapshots/dim_pub_customer_hist.yml models/dim/pub/dim_pub_customer/
  export DBT_TARGET_PATH=/tmp/snapspike/target DBT_PROFILES_DIR=/tmp/snapspike
  for paths in "[\"models\"]" "[\"snapshots\", \"models\"]"; do
    sed -i "s|^snapshot-paths:.*|snapshot-paths: $paths|" dbt_project.yml
    echo "== snapshot-paths: $paths"
    $DBT_EXECUTABLE_PATH parse --no-partial-parse && \
      $DBT_EXECUTABLE_PATH ls --resource-type snapshot && \
      $DBT_EXECUTABLE_PATH ls --resource-type model | wc -l
  done'
```

(`cp` and `mv` here run inside the throwaway container, not in the agent's shell.) Record for each variant:
- whether `parse` succeeds;
- whether `ls --resource-type snapshot` lists `example_dwh.dim_pub_customer_hist` once;
- whether the model count is unchanged (14);
- every warning (for example a node parsed twice, or a path overlap).

**Decision.** Choose (a) only if one variant parses with no warning, lists the snapshot once and keeps 14 models.
Otherwise choose (b), and record dbt's message as the reason. Write the result into the report and into the
STD-09-08 text.

- [ ] **Step 2: Write the failing tests.**
  - `fixtures/manifest.py`:
    - `ManifestBuilder.model` gains `patch_path=None`; when omitted it defaults to
      `f"{PROJECT}://{PurePosixPath(path).with_suffix('.yml')}"` for `.sql` paths;
    - every `good_project` path becomes per-model, for example `models/ods/shop/ods_shop_orders_di/ods_shop_orders_di.sql`;
    - the snapshot path follows the Step 1 decision.
  - `manifest.py`: `Node` gains `patch_path: str = ""`, loaded from `raw.get("patch_path") or ""`. The `folder`
    property keeps returning `parts[2]` for models, and returns the `<scope>` part for (b) snapshots.
  - Append to `test_rules_layers.py`:

```python
def test_l07_good_project_has_one_folder_per_model(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-L07") == []


def test_l07_a_model_outside_its_own_folder_fails(lint):
    builder, ids = good_project()
    node = builder.node(ids["dwd_order"])
    node["original_file_path"] = "models/dwd/trade/dwd_trade_order_di.sql"
    node["patch_path"] = "example_dwh://models/dwd/trade/_trade__models.yml"
    assert lint(builder, prefix="DWH-L07") == ["DWH-L07"]


def test_l07_a_shared_yml_fails(lint):
    builder, ids = good_project()
    builder.node(ids["dws_customer"])["patch_path"] = "example_dwh://models/dws/trade/_trade__models.yml"
    assert lint(builder, prefix="DWH-L07") == ["DWH-L07"]


def test_l07_a_model_without_a_yml_fails(lint):
    builder, ids = good_project()
    builder.node(ids["ads_customer"])["patch_path"] = None
    assert lint(builder, prefix="DWH-L07") == ["DWH-L07"]
```

  - Add one test for the snapshot location chosen in Step 1 (a snapshot at the other place fails).
  - `test_scaffold.py`: every file key becomes per-model, for example
    `"models/dim/pub/dim_pub_customer/dim_pub_customer.sql"`, `".../dim_pub_customer/dim_pub_customer.yml"`, and the
    snapshot per Step 1.

  Run `make dwh-test`. Expected: FAIL.

- [ ] **Step 3: Implement the tooling.**
  - `codes.py`: `"DWH-L07": "a model or snapshot is not in its own folder with a same-named .yml",`.
  - `rules/layers.py` (`SNAPSHOT_IN_MODEL_FOLDER` follows Step 1):

```python
SNAPSHOT_IN_MODEL_FOLDER = False  # Step 1 decision: True = models/dim/<scope>/<dim>/<dim>_hist.yml


def expected_files(node: Node) -> tuple[str, str]:
    """Where `node` lives (STD-09-08): its .sql (or snapshot .yml) and the .yml that describes it."""
    folder = node.folder or "<folder>"
    if node.resource_type == "snapshot":
        if SNAPSHOT_IN_MODEL_FOLDER:
            path = f"models/dim/{folder}/{node.name.removesuffix('_hist')}/{node.name}.yml"
        else:
            path = f"snapshots/dim/{folder}/{node.name}/{node.name}.yml"
        return path, path
    base = f"models/{node.layer}/{folder}/{node.name}/{node.name}"
    return f"{base}.sql", f"{base}.yml"


def l07_one_folder_per_model(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        if node.layer is None:
            continue  # reported by DWH-L01
        sql, yml = expected_files(node)
        described = node.patch_path.split("://", 1)[-1] if node.patch_path else node.project_path
        if node.project_path != sql or described != yml:
            yield Finding(node.path, "DWH-L07", f"{node.name}: a model lives in {sql}, described by {yml}")
```

    Add it to `RULES`. The ODS folder is the source, which `node.folder` already returns.
  - `scaffold.py`: the folder of every file becomes `f"{folder}/{name}"`. The `_hist` snapshot goes where Step 1
    decided, and the per-model `.yml` is no longer merged by hand: it is the final file.
  - `catalog.py`: fix any model path it builds (if the grep finds none, record "no change").
- [ ] **Step 4: Move the real project.** Run from the repository root:

```bash
uv run --locked --project tools/dwh python - <<'EOF'
import subprocess
from pathlib import Path

import yaml

ROOT = Path("dbt/warehouse/models")
for shared in sorted(ROOT.rglob("_*__models.yml")):
    folder = shared.parent
    models = yaml.safe_load(shared.read_text())["models"]
    tests_file = folder / f"_{folder.name}__unit_tests.yml"
    unit_tests = yaml.safe_load(tests_file.read_text())["unit_tests"] if tests_file.exists() else []
    for model in models:
        name = model["name"]
        target = folder / name
        target.mkdir(exist_ok=True)
        subprocess.run(["git", "mv", str(folder / f"{name}.sql"), str(target / f"{name}.sql")], check=True)
        doc = {"version": 2, "models": [model]}
        mine = [t for t in unit_tests if t["model"] == name]
        if mine:
            doc["unit_tests"] = mine
        (target / f"{name}.yml").write_text(yaml.safe_dump(doc, sort_keys=False, width=110, allow_unicode=True))
        print("wrote", target / f"{name}.yml")
    subprocess.run(["git", "rm", "-q", str(shared)], check=True)
    if tests_file.exists():
        subprocess.run(["git", "rm", "-q", str(tests_file)], check=True)
EOF
```

Then:
- Move the snapshot with `git mv` to its Step 1 place. For (a), set `snapshot-paths: ["models"]` (or the variant
  that measured clean) in `dbt_project.yml`.
- Copy the header comments of the deleted unit-test files into the model `.yml` they belong to:
  - the "D12 boundary tests ..." comment goes into `ods_shop_orders_di.yml`;
  - the "The merge itself is covered by test_capabilities ..." comment goes into `dwd_trade_order_lifecycle_di.yml`.
- Check with `git status`:
  - every model has exactly two files in its folder;
  - `models/ods/shop/_shop__sources.yml` is untouched;
  - `.gitkeep` files stay only in empty layer folders.

- [ ] **Step 5: Write the rules and the docs.**
  - **STD-09-08 One folder per model (MUST).**
    - Each model lives in `models/<layer>/<domain or source>/<model>/`, with `<model>.sql` and `<model>.yml`. The
      `.yml` holds its description, columns, tests, contract, config and unit tests, so one change touches one
      folder.
    - Sources stay one `_<source>__sources.yml` per source system.
    - `_hist` snapshots live at the Step 1 place, with the reason.
    - Correct:

      ```text
      models/dwd/trade/dwd_trade_order_di/dwd_trade_order_di.sql
      models/dwd/trade/dwd_trade_order_di/dwd_trade_order_di.yml
      ```

    - Incorrect:

      ```text
      models/dwd/trade/dwd_trade_order_di.sql
      models/dwd/trade/_trade__models.yml   # one file for every model of the domain
      ```

    - Source: Spec §3. Checked by: DWH-L07.
  - **STD-09-09 One-off migration scripts stay out of `model-paths` (MUST).** A script run once (a backfill helper,
    a table fix, a data repair) goes in `analyses/` (compiled, never run) or in a `migrations/` folder outside
    `model-paths`. It never goes in `models/`, where dbt would build it every night.
    - Correct:

      ```text
      dbt/warehouse/analyses/2026-11-10-fix-order-status.sql
      ```

    - Incorrect:

      ```text
      dbt/warehouse/models/dwd/trade/fix_order_status.sql   # dbt builds it on every run
      ```

    - Source: Spec §3.
  - STD-09-07 (start from the scaffold): the scaffold writes the model's folder.
  - In the skills, replace "merge the generated `.yml` into `_<folder>__models.yml`" with "keep the generated
    per-model `.yml`" (`git grep -n "__models.yml\|__unit_tests.yml" skills AGENTS.md docs README.md`). Then
    `make sync-agents`.
  - Both guides and `README.md`: the layout and the plan 4 build steps that merged `.yml` files.
  - Spec §3 tree: show one model folder as an example. Spec §11, append:

    ```text
    - **Plan 5 (owner input):** one folder per model (`models/<layer>/<domain>/<model>/<model>.sql` + `.yml`, the
      `.yml` holding columns, tests, contract and unit tests); sources stay one file per source system; `_hist`
      snapshots live at <Step 1 place> because <Step 1 reason>; one-off scripts stay out of model-paths (STD-09-08,
      STD-09-09, DWH-L07).
    ```

    Fill in the two angle-bracket parts from the Step 1 record when committing.
- [ ] **Step 6: Run green on a fresh stack.**

```bash
make lint && make sql-lint && make test-repo && make dwh-test && make validate && make dwh-lint \
  && make check-standards && make sync-agents-check && make catalog \
  && make dev-down && make image && make dev-up && make test-dags && make test-integration && make e2e
```

Expected:
- all pass, with 0 findings;
- the integration suite reports the same tests and values as after Task 2a;
- `make dwh-lint` with a model moved back to `models/dwd/trade/` (try it, then `git checkout`) reports `DWH-L07`.

- [ ] **Step 7: Commit**

```bash
git add -A dbt/warehouse tools/dwh tests/repo docs/standards skills .claude .cursor .github/copilot-instructions.md \
  AGENTS.md docs/en/guides docs/vi/guides README.md docs/en/specs/2026-11-04-kimball-dwh-design.md
git commit -m "refactor(dbt): one folder per model with its own yml; DWH-L07 checks the layout" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Reviewer note:** 2a (location and project name) and 2b (layout) are separate commits. Each can be approved or
reverted alone.

---

### Task 3: Done Assets, `conf.propagate` and the dt template

**Files:**
- Modify: `dags/_common/assets.py` (`model_asset` is removed: no schedule may use it, so it is dead code)
- Create: `dags/_common/pipelines.py`
- Modify: `dags/_common/dates.py` (`DONE_DT_TEMPLATE` replaces `ASSET_DT_TEMPLATE`), `dags/_common/dbt.py`
  (docstring)
- Modify: `dags/sources/dbt_ods_shop.py`, `dags/transform/dbt_pub.py`, `dags/transform/dbt_trade.py`
- Modify: `dbt/warehouse/macros/get_dt.sql` (comment)
- Modify: `tests/dags/test_business_day.py`, `tests/dags/test_transform_dags.py`, `tests/dags/test_dag_integrity.py`
- Modify: `dev/e2e.sh`; create `dev/check_done_events.py`
- Modify: `docs/standards/11-airflow.md` (STD-11-03, STD-11-04, STD-11-08, new STD-11-09)

**Interfaces:**
- Produces (Tasks 4, 6 and 8 rely on these):
  - `_common.assets.done_asset(dag_id) -> Asset`, whose name and URI are `dwh_done/<dag_id>`.
  - `_common.assets.done_extra(dt, conf) -> dict | None`, which returns `{"dt": dt}`, or `None` when
    `conf.propagate` is false. It raises `ValueError` for a dt that is not one ISO date, or for an unknown
    `propagate` value.
  - `_common.assets.add_publish_done(dag, dt_template)`, which adds the task `publish_done`.
  - `_common.pipelines.PIPELINES` (dag_id → dbt selectors) and `owner_of(tags) -> str | None`.
  - `_common.dates.DONE_DT_TEMPLATE`.

- [ ] **Step 1: Write the failing tests.**

In `tests/dags/test_business_day.py`:
- Delete `asset_event`, `render_asset_template`, `sdk_event`, `NOV2_RUN` and every `test_asset_template_*`.
- Import `DONE_DT_TEMPLATE` instead of `ASSET_DT_TEMPLATE`.
- In `test_ods_shop_dag_uses_the_vn_timetable_and_dt_template`, loop over
  `[t for t in dag.tasks if t.task_id != "publish_done"]`.
- Append:

```python
def done_event(dt):
    """A triggering dwh_done event as the SDK exposes it: the producer wrote {"dt": <day>} into its extra."""
    return SimpleNamespace(extra={"dt": dt} if dt else {})


def render_done_template(events, conf=None):
    return Template(DONE_DT_TEMPLATE).render(
        triggering_asset_events={"dwh_done/dbt_pub": events}, dag_run=SimpleNamespace(conf=conf or {})
    )


def test_done_template_takes_the_day_the_producer_built():
    assert render_done_template([done_event("2026-11-02")]) == "2026-11-02"


def test_done_template_takes_the_day_when_several_events_share_it():
    assert render_done_template([done_event("2026-11-02"), done_event("2026-11-02")]) == "2026-11-02"


def test_done_template_rejects_two_days_whatever_the_event_order():
    # One run builds one dt; picking either day would leave the other unbuilt with nothing failing.
    nov1, nov2 = done_event("2026-11-01"), done_event("2026-11-02")

    assert render_done_template([nov2, nov1]) == "MULTIPLE:2026-11-01,2026-11-02"
    assert render_done_template([nov1, nov2]) == "MULTIPLE:2026-11-01,2026-11-02"


def test_done_template_prefers_its_own_conf_dt():
    events = [done_event("2026-11-01"), done_event("2026-11-02")]

    assert render_done_template(events, conf={"dt": "2026-10-30"}) == "2026-10-30"


def test_done_template_is_empty_without_a_done_day():
    assert render_done_template([]) == ""
    assert render_done_template([done_event(None)]) == ""


def test_done_template_reads_a_real_sdk_event():
    from airflow.sdk.api.datamodels._generated import AssetReferenceAssetEventDagRun
    from airflow.sdk.execution_time.comms import AssetEventDagRunReferenceResult

    event = AssetEventDagRunReferenceResult(
        asset=AssetReferenceAssetEventDagRun(name="dwh_done/dbt_pub", uri="dwh_done/dbt_pub", extra={}),
        extra={"dt": "2026-11-02"},
        source_task_id="publish_done",
        source_dag_id="dbt_pub",
        source_run_id="run",
        source_map_index=-1,
        source_aliases=[],
        timestamp=datetime(2026, 11, 2, 17, 5, tzinfo=UTC),
    )

    assert render_done_template([event]) == "2026-11-02"
```

Replace `tests/dags/test_transform_dags.py` with the following. It keeps the three Task 2a tests at its end, and keeps the
indirect-selection and target-path tests restricted to dbt tasks.

```python
"""Pipeline DAGs end with publish_done and schedule only on upstream dwh_done Assets (STD-11-04, STD-11-09)."""

import os

import pytest

from _common.assets import done_asset, done_extra
from _common.dates import DONE_DT_TEMPLATE, DT_TEMPLATE
from _common.pipelines import PIPELINES, owner_of

TEMPLATES = {"dbt_ods_shop": DT_TEMPLATE, "dbt_pub": DONE_DT_TEMPLATE, "dbt_trade": DONE_DT_TEMPLATE}


def dbt_tasks(dag):
    return [t for t in dag.tasks if t.task_id != "publish_done"]


def schedule_names(dag) -> set[str]:
    condition = dag.timetable.asset_condition
    if hasattr(condition, "name"):  # a single Asset
        return {condition.name}
    return {asset.name for asset in condition.objects}


def test_done_asset_is_named_after_the_dag():
    asset = done_asset("dbt_pub")

    assert (asset.name, asset.uri) == ("dwh_done/dbt_pub", "dwh_done/dbt_pub")


def test_done_extra_carries_the_day():
    assert done_extra("2026-11-02", None) == {"dt": "2026-11-02"}
    assert done_extra("2026-11-02", {"propagate": True}) == {"dt": "2026-11-02"}


@pytest.mark.parametrize("propagate", [False, "false"])
def test_done_extra_is_none_when_the_run_does_not_propagate(propagate):
    assert done_extra("2026-11-02", {"dt": "2026-11-02", "propagate": propagate}) is None


@pytest.mark.parametrize("dt", ["", "MULTIPLE:2026-11-01,2026-11-02", "2026-13-01"])
def test_done_extra_refuses_a_day_that_is_not_one_date(dt):
    with pytest.raises(ValueError):
        done_extra(dt, None)


def test_done_extra_refuses_an_unknown_propagate_value():
    with pytest.raises(ValueError, match="propagate"):
        done_extra("2026-11-02", {"propagate": "maybe"})


@pytest.mark.parametrize("dag_id", sorted(PIPELINES))
def test_publish_done_is_the_last_task_and_follows_every_other(dagbag, dag_id):
    dag = dagbag.get_dag(dag_id)
    done = dag.get_task("publish_done")

    assert [t.task_id for t in dag.tasks if not t.downstream_list] == ["publish_done"]
    assert {t.task_id for t in done.get_flat_relatives(upstream=True)} == set(dag.task_ids) - {"publish_done"}
    assert done.trigger_rule == "all_success"
    assert [asset.name for asset in done.outlets] == [f"dwh_done/{dag_id}"]
    assert done.op_kwargs == {"dt": TEMPLATES[dag_id]}


def test_downstream_dags_schedule_only_on_upstream_done_assets(dagbag):
    assert schedule_names(dagbag.get_dag("dbt_pub")) == {"dwh_done/dbt_ods_shop"}
    assert schedule_names(dagbag.get_dag("dbt_trade")) == {"dwh_done/dbt_pub"}


@pytest.mark.parametrize("dag_id", ["dbt_pub", "dbt_trade"])
def test_asset_scheduled_dags_take_dt_from_done_events(dagbag, dag_id):
    for task in dbt_tasks(dagbag.get_dag(dag_id)):
        assert task.vars == {"dt": DONE_DT_TEMPLATE}, task.task_id


def test_owner_of_names_the_one_pipeline_selecting_a_tag():
    assert owner_of(["layer:ods", "ods_shop"]) == "dbt_ods_shop"
    assert owner_of(["layer:dim", "domain:pub"]) == "dbt_pub"
    assert owner_of(["layer:ads", "app:crm"]) == "dbt_trade"
    assert owner_of(["layer:dim"]) is None
    assert owner_of(["domain:pub", "domain:trade"]) is None


def test_pub_and_trade_dags_select_their_models(dagbag):
    pub = dagbag.get_dag("dbt_pub")
    trade = dagbag.get_dag("dbt_trade")

    assert any("dim_pub_customer" in t for t in pub.task_ids)
    assert any("dim_pub_date" in t for t in pub.task_ids)
    assert not any("dwd_" in t for t in pub.task_ids)
    assert any("dwd_trade_order_di" in t for t in trade.task_ids)
    assert any("ads_crm_customer_value" in t for t in trade.task_ids)
    assert not any("dim_pub_" in t for t in trade.task_ids)


def test_maintenance_dag_runs_weekly_with_owner_and_tags(dagbag):
    dag = dagbag.get_dag("iceberg_maintenance")
    assert dag.owner == "data-eng"
    assert "layer:maintenance" in dag.tags
    assert os.path.basename(dag.fileloc) == "iceberg_maintenance.py"


def test_test_tasks_do_not_pick_up_tests_of_models_built_by_another_dag(dagbag):
    for dag_id in ("dbt_pub", "dbt_trade"):
        tests = [t for t in dagbag.get_dag(dag_id).tasks if t.task_id.endswith(".test")]
        assert tests
        assert all(t.indirect_selection == "buildable" for t in tests), dag_id


def test_every_dbt_task_writes_its_dbt_artifacts_to_its_own_target_path(dagbag):
    # A shared DBT_TARGET_PATH lets concurrent tasks emit events for the wrong asset (measured, plan 4).
    for dag_id in PIPELINES:
        for task in dbt_tasks(dagbag.get_dag(dag_id)):
            assert "{{ ti.task_id }}" in task.env["DBT_TARGET_PATH"], task.task_id
```

In `tests/dags/test_dag_integrity.py::test_ods_shop_dag_renders_only_shop_ods_models`, compare only
`task_ids - {"publish_done"}`, and add `assert "publish_done" in task_ids`.

Run: `make test-dags`. Expected: FAIL (`done_asset`, `PIPELINES` and `DONE_DT_TEMPLATE` do not exist).

- [ ] **Step 2: Implement.**

`dags/_common/pipelines.py`:

```python
"""Which pipeline DAG builds which dbt models (STD-11-08): each DAG's dbt selectors, by dag_id.

The DAG files select with these, and the SLA watchdog names a late model's DAG from them. No Airflow import:
the integration tests (dbt venv) import it through _common.sla.
"""

from collections.abc import Iterable

PIPELINES: dict[str, tuple[str, ...]] = {
    "dbt_ods_shop": ("tag:ods_shop",),
    "dbt_pub": ("tag:domain:pub",),
    "dbt_trade": ("tag:domain:trade", "tag:app:crm"),
}


def owner_of(tags: Iterable[str]) -> str | None:
    """The one pipeline DAG whose selectors match `tags` (a model's dbt tags); None for zero or several."""
    tags = set(tags)
    owners = [
        dag_id
        for dag_id, selectors in PIPELINES.items()
        if any(selector.removeprefix("tag:") in tags for selector in selectors)
    ]
    return owners[0] if len(owners) == 1 else None
```

`dags/_common/assets.py` (replaces the whole file):

```python
"""The done Asset of a pipeline DAG (plan 5, design §2): `dwh_done/<dag_id>`, its event carrying {"dt": <day>}.

Downstream DAGs schedule only on these (STD-11-04). Cosmos still emits one Asset per model, for lineage only.
"""

from datetime import date

from airflow.exceptions import AirflowSkipException
from airflow.sdk import DAG, Asset, task

DONE_PREFIX = "dwh_done/"


def done_asset(dag_id: str) -> Asset:
    return Asset(name=f"{DONE_PREFIX}{dag_id}", uri=f"{DONE_PREFIX}{dag_id}")


def done_extra(dt: str, conf: dict | None) -> dict | None:
    """The done event's extra, or None when the run asked not to propagate (conf.propagate false)."""
    propagate = (conf or {}).get("propagate", True)
    if propagate in (False, "false", "False"):
        return None
    if propagate not in (True, "true", "True"):
        raise ValueError(f"conf.propagate must be true or false, got {propagate!r}")
    date.fromisoformat(dt)  # MULTIPLE:, an empty or a malformed day must fail here, never reach a consumer
    return {"dt": dt}


def add_publish_done(dag: DAG, dt_template: str) -> None:
    """End `dag` with publish_done: once every other task succeeded, emit dwh_done/<dag_id> with {"dt": <day>}.

    A run with conf {"propagate": false} skips it: no event, so no downstream DAG starts (backfill, STD-11-09).
    """
    asset = done_asset(dag.dag_id)
    leaves = [t for t in dag.tasks if not t.downstream_list]

    @task(task_id="publish_done", outlets=[asset], retries=0)
    def publish_done(dt: str, *, dag_run=None, outlet_events=None) -> None:
        extra = done_extra(dt, dag_run.conf if dag_run else None)
        if extra is None:
            raise AirflowSkipException(
                "conf.propagate is false: no dwh_done event, so no downstream DAG starts"
            )
        outlet_events[asset].extra = extra

    with dag:
        done = publish_done(dt=dt_template)
    for leaf in leaves:
        leaf >> done
```

If Airflow 3.3.2 warns that `airflow.exceptions.AirflowSkipException` is deprecated, import it from the path the
warning names.

In `dags/_common/dates.py`, delete `ASSET_DT_TEMPLATE` and its comment, and add:

```python
# For a DAG scheduled on upstream dwh_done Assets (design §2.2). Its own conf.dt (a manual run) wins. Otherwise
# dt is the "dt" extra the producer's publish_done wrote: one distinct day is dt; several days (producer runs of
# different days collapsed into one run) render MULTIPLE:<day>,<day> (oldest first), which get_dt rejects, so the
# operator reruns each day with conf.dt, oldest first; no day renders "", which get_dt rejects too.
DONE_DT_TEMPLATE = (
    "{% set found = namespace(days=[]) %}"
    "{% for events in triggering_asset_events.values() %}{% for event in events %}"
    "{% set day = (event.extra or {}).get('dt') %}"
    "{% if day and day not in found.days %}{% set found.days = found.days + [day] %}{% endif %}"
    "{% endfor %}{% endfor %}"
    "{% set days = found.days | sort %}"
    "{{ (dag_run.conf or {}).get('dt') or (days | first if days | length == 1 else "
    "('MULTIPLE:' ~ days | join(',') if days else '')) }}"
)
```

Keep the module docstring's D12 sentence, and add "or the day a producer published (DONE_DT_TEMPLATE)". In
`_common/dbt.py`, change the docstring to "DT_TEMPLATE for cron DAGs, DONE_DT_TEMPLATE for DAGs scheduled on
dwh_done Assets".

The three DAG files:

```python
"""Airflow DAG: load source system `shop` into ODS (Iceberg) for the Vietnam business day."""

from cosmos import DbtDag

from _common.assets import add_publish_done
from _common.dates import DT_TEMPLATE, daily_vn, vn_date
from _common.dbt import WAREHOUSE, dbt_dag_kwargs
from _common.defaults import DEFAULT_ARGS
from _common.pipelines import PIPELINES

dbt_ods_shop = DbtDag(
    dag_id="dbt_ods_shop",
    schedule=daily_vn(),
    start_date=vn_date(2026, 11, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["layer:ods", "source:shop"],
    **dbt_dag_kwargs(project=WAREHOUSE, select=list(PIPELINES["dbt_ods_shop"])),
)
add_publish_done(dbt_ods_shop, DT_TEMPLATE)
```

```python
"""Airflow DAG: build the shared dimensions (dim_pub_*) and their _hist snapshots."""

from cosmos import DbtDag

from _common.assets import add_publish_done, done_asset
from _common.dates import DONE_DT_TEMPLATE, vn_date
from _common.dbt import WAREHOUSE, dbt_dag_kwargs
from _common.defaults import DEFAULT_ARGS
from _common.pipelines import PIPELINES

dbt_pub = DbtDag(
    dag_id="dbt_pub",
    schedule=done_asset("dbt_ods_shop"),
    start_date=vn_date(2026, 11, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["layer:dim", "domain:pub"],
    **dbt_dag_kwargs(project=WAREHOUSE, select=list(PIPELINES["dbt_pub"]), dt_template=DONE_DT_TEMPLATE),
)
add_publish_done(dbt_pub, DONE_DT_TEMPLATE)
```

```python
"""Airflow DAG: build the trade domain (DIM, DWD, DWS) and the CRM customer-value ADS."""

from cosmos import DbtDag

from _common.assets import add_publish_done, done_asset
from _common.dates import DONE_DT_TEMPLATE, vn_date
from _common.dbt import WAREHOUSE, dbt_dag_kwargs
from _common.defaults import DEFAULT_ARGS
from _common.pipelines import PIPELINES

# dbt_pub waited for the whole ODS DAG, so the shop ODS tables this DAG reads are built for the day (design §2.1).
dbt_trade = DbtDag(
    dag_id="dbt_trade",
    schedule=done_asset("dbt_pub"),
    start_date=vn_date(2026, 11, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["layer:dwd", "layer:dws", "layer:ads", "domain:trade"],
    **dbt_dag_kwargs(project=WAREHOUSE, select=list(PIPELINES["dbt_trade"]), dt_template=DONE_DT_TEMPLATE),
)
add_publish_done(dbt_trade, DONE_DT_TEMPLATE)
```

In `dbt/warehouse/macros/get_dt.sql`, change the comment line to "rendered from _common.dates.DT_TEMPLATE or
DONE_DT_TEMPLATE", and "DONE_DT_TEMPLATE renders 'MULTIPLE:<day>,<day>' ...". The error text stays.

- [ ] **Step 3: Extend the e2e.** Create `dev/check_done_events.py`:

```python
"""Fail unless each named DAG emitted exactly one dwh_done event, carrying the expected dt (plan 5).

Usage (inside the Airflow image, after `airflow dags test`):
    python dev/check_done_events.py <dag_id>=<dt> [<dag_id>=<dt> ...]
"""

import sys

from airflow.models.asset import AssetEvent, AssetModel
from airflow.utils.session import create_session
from sqlalchemy import select


def main(expected: dict[str, str]) -> int:
    failures = 0
    with create_session() as session:
        for dag_id, dt in sorted(expected.items()):
            extras = session.scalars(
                select(AssetEvent.extra)
                .join(AssetModel, AssetEvent.asset_id == AssetModel.id)
                .where(AssetModel.name == f"dwh_done/{dag_id}")
                .order_by(AssetEvent.id)
            ).all()
            print(f"dwh_done/{dag_id}: {extras}")
            if [(extra or {}).get("dt") for extra in extras] != [dt]:
                print(f"dwh_done/{dag_id}: expected exactly one event with dt {dt}", file=sys.stderr)
                failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(dict(arg.split("=", 1) for arg in sys.argv[1:])))
```

In `dev/e2e.sh`, inside the container command after the `dbt_trade` run, add the following, and add one header
comment line explaining the `propagate=false` run:

```bash
  # propagate=false rebuilds the day but skips publish_done: dbt_pub must still have exactly one done event.
  airflow dags test dbt_pub 2026-11-04 --conf '{\"dt\": \"$DT\", \"propagate\": false}'
```

After the `--- asset events` block, add:

```bash
  echo '--- done events'
  python dev/check_done_events.py dbt_ods_shop=$DT dbt_pub=$DT dbt_trade=$DT
```

- [ ] **Step 4: Rewrite the STD-11 rules.** Keep the IDs, levels and Source lines, and give every rule a Correct
  and an Incorrect example.
  - **STD-11-03 Business-day schedule.**
    - Cron DAGs: `daily_vn()` and `DT_TEMPLATE` as today.
    - A DAG scheduled on done Assets passes `dt_template=DONE_DT_TEMPLATE`. Its `conf.dt` wins. Otherwise the day
      is the `dt` extra of its triggering `dwh_done` events: one day, `MULTIPLE:<day>,<day>` (rerun each day with
      `conf.dt`, oldest first), or empty (rejected).
    - Delete the queued-events procedure and the "redesign is planned" sentence. A manual `dbt_pub` run now emits
      its own done event and starts `dbt_trade` for that day; nothing stays queued.
    - Use the Task 1 M3 wording for when `MULTIPLE` appears.
  - **STD-11-04 Done Assets, not model Assets or sensors (MUST).**
    - A downstream DAG schedules only on `done_asset(<upstream dag_id>)`, with an AND (`&`) when it needs several
      upstream DAGs.
    - Cosmos model Assets are for lineage.
    - Correct:

      ```python
      from cosmos import DbtDag

      from _common.assets import done_asset

      dag = DbtDag(dag_id="dbt_trade", schedule=done_asset("dbt_pub"))
      ```

    - Incorrect: `schedule=Asset("trino://trino:8080/iceberg/dev_dim/dim_pub_customer")`, with the comment
      "starts when one model lands, not when its DAG finished; no day travels with it".
    - Keep the `ExternalTaskSensor` incorrect example as a second one.
  - **STD-11-08 Every model has a DAG.**
    - The selectors live in `_common.pipelines.PIPELINES`.
    - `dbt_pub` is scheduled on `dwh_done/dbt_ods_shop`.
    - Snapshots run before the DWD that joins them, because `dbt_trade` waits for `dwh_done/dbt_pub`, which is
      emitted only after the snapshot succeeded.
    - Delete the queued-events sentence. Update the Correct example to the Task 3 `dbt_pub` file.
  - **New STD-11-09 Every pipeline DAG ends with publish_done (MUST).**
    - Every `dbt_ods_<source>` and `dbt_<domain>` DAG calls `add_publish_done(dag, <its dt template>)`.
    - The task follows every other task (`all_success`), so a partly failed run emits nothing.
    - `conf.propagate` (default `true`) set to `false` skips it, so no downstream DAG starts.
    - Correct: the `add_publish_done(dbt_ods_shop, DT_TEMPLATE)` line under the DAG.
    - Incorrect: an `EmptyOperator(outlets=[...])` placed after only some tasks, with the comment "emits while
      other tasks still fail; carries no dt".
    - Source: Spec §4.

- [ ] **Step 5: Run green**

```bash
make lint && make check-standards && make dev-down && make image && make dev-up \
  && make test-dags && make test-integration && make e2e
```

Expected: all pass. The e2e prints `dwh_done/dbt_ods_shop: [{'dt': '2026-11-02'}]`, the same for `dbt_pub` (one
event, despite the second, non-propagating run) and `dbt_trade`, then `e2e OK`.

- [ ] **Step 6: Commit**

```bash
git add dags dbt/warehouse/macros/get_dt.sql tests/dags dev/e2e.sh dev/check_done_events.py docs/standards/11-airflow.md
git commit -m "feat(dags): schedule on dwh_done Assets that carry dt; add publish_done and conf.propagate" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Lint DWH-L06 — no DAG schedule names a model Asset

**Files:**
- Modify: `tools/dwh/src/dwh/codes.py`, `tools/dwh/src/dwh/lint.py`, `tools/dwh/src/dwh/rules/layers.py`,
  `tools/dwh/src/dwh/cli.py`
- Modify: `tools/dwh/tests/test_rules_layers.py`
- Modify: `Makefile` (`dwh-lint`), `.pre-commit-config.yaml` (dwh-lint hook)
- Modify: `docs/standards/11-airflow.md` (STD-11-04 `Checked by: DWH-L06`)

**Interfaces:**
- Produces:
  - code `DWH-L06`: "a DAG schedule names a model Asset instead of an upstream dwh_done Asset".
  - `Context(warehouse, project, dags=None)`, where `dags` is the DAG folder to scan.
  - `dwh lint --dags DIR`. When the flag is absent, DWH-L06 does not run.
- Code family: L (layer placement and dependencies). A schedule is a cross-layer dependency, and design §3.3 names
  DWH-L.

- [ ] **Step 1: Write the failing tests.** Append to `tools/dwh/tests/test_rules_layers.py`:

```python
from dwh.lint import Context, run_lint
from dwh.manifest import load_manifest
from dwh.warehouse import load_warehouse

DONE_SCHEDULE = 'dag = DbtDag(dag_id="dbt_trade", schedule=done_asset("dbt_pub"))\n'


def lint_dags(tmp_path, make_warehouse, write_manifest, files: dict[str, str]) -> list[str]:
    dags = tmp_path / "dags"
    for name, text in files.items():
        path = dags / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    builder, _ = good_project()
    ctx = Context(load_warehouse(make_warehouse()), load_manifest(write_manifest(builder)), dags=dags)
    return [f.code for f in run_lint(ctx) if f.code == "DWH-L06"]


def test_l06_done_asset_schedules_pass(tmp_path, make_warehouse, write_manifest):
    files = {"transform/dbt_trade.py": DONE_SCHEDULE}
    assert lint_dags(tmp_path, make_warehouse, write_manifest, files) == []


def test_l06_a_done_asset_literal_passes(tmp_path, make_warehouse, write_manifest):
    files = {"transform/dbt_trade.py": 'dag = DAG(schedule=[Asset("dwh_done/dbt_pub")])\n'}
    assert lint_dags(tmp_path, make_warehouse, write_manifest, files) == []


def test_l06_model_asset_schedule_fails(tmp_path, make_warehouse, write_manifest):
    files = {"transform/dbt_trade.py": 'dag = DbtDag(schedule=model_asset("dim", "dim_pub_customer"))\n'}
    assert lint_dags(tmp_path, make_warehouse, write_manifest, files) == ["DWH-L06"]


def test_l06_a_model_asset_inside_an_and_fails(tmp_path, make_warehouse, write_manifest):
    text = 'dag = DbtDag(schedule=done_asset("dbt_pub") & Asset("trino://t:8080/iceberg/dev_ods/x"))\n'
    assert lint_dags(tmp_path, make_warehouse, write_manifest, {"transform/x.py": text}) == ["DWH-L06"]


def test_l06_an_unparsable_dag_file_is_reported(tmp_path, make_warehouse, write_manifest):
    files = {"transform/broken.py": "dag = DbtDag(schedule=\n"}
    assert lint_dags(tmp_path, make_warehouse, write_manifest, files) == ["DWH-L06"]


def test_l06_does_not_run_without_a_dags_folder(lint):
    builder, _ = good_project()
    assert "DWH-L06" not in lint(builder)
```

Merge the new imports into the module's existing import block (ruff `I`). Run `make dwh-test`. Expected: FAIL
(`Context` has no `dags`, and the code is unregistered).

- [ ] **Step 2: Implement.**
  - `codes.py`: add `"DWH-L06": "a DAG schedule names a model Asset instead of an upstream dwh_done Asset",` after
    `DWH-L05`.
  - `lint.py`: add `from pathlib import Path`, and give `Context` the field `dags: Path | None = None`.
  - `rules/layers.py`: add `import ast`, `from dwh.findings import Finding, rel` and:

```python
DONE_PREFIX = "dwh_done/"


def call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def asset_literal(node: ast.Call) -> str | None:
    """The literal name or URI an `Asset(...)` call is built from, if it is a string literal."""
    for arg in [*node.args[:1], *(k.value for k in node.keywords if k.arg in ("name", "uri"))]:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return None


def model_assets_in(schedule: ast.expr) -> Iterator[ast.Call]:
    """Calls in a schedule expression that name a model Asset: model_asset(...) or Asset("<not dwh_done/>")."""
    for node in ast.walk(schedule):
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node)
        literal = asset_literal(node) if name == "Asset" else None
        if name == "model_asset" or (name == "Asset" and not (literal or "").startswith(DONE_PREFIX)):
            yield node


def l06_schedules_on_done_assets(ctx: Context) -> Iterator[Finding]:
    if ctx.dags is None:
        return
    for path in sorted(ctx.dags.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError as error:
            yield Finding(rel(path), "DWH-L06", f"cannot parse ({error.msg}), so its schedule is unchecked")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "schedule":
                    continue
                for asset in model_assets_in(keyword.value):
                    yield Finding(
                        rel(path),
                        "DWH-L06",
                        f"line {asset.lineno}: schedule names a model Asset; schedule on "
                        "done_asset(<upstream dag_id>) (STD-11-04)",
                    )
```

  Add `l06_schedules_on_done_assets` to `RULES`.
  - `cli.py`:
    - add `p.add_argument("--dags", type=Path, default=None, help="DAG folder for DWH-L06 (schedules)")` to `lint`;
    - in `cmd_lint`, if `args.dags is not None and not args.dags.is_dir()`, print
      `dwh: {args.dags} is not a directory` to stderr and return 2;
    - build `Context(load_warehouse(args.warehouse), project, dags=args.dags)`.
  - `Makefile`: `dwh-lint` appends `--dags dags`. In `.pre-commit-config.yaml`, add `--dags dags` to the dwh-lint
    entry and `dags/` to its `files` pattern.
  - STD-11-04: add the line `Checked by: DWH-L06`.

- [ ] **Step 3: Prove the check on the real DAGs.**
  1. Temporarily change `dags/transform/dbt_trade.py` to
     `schedule=Asset("trino://trino:8080/iceberg/dev_dim/dim_pub_customer")` (import `Asset`).
  2. Run `make dwh-lint`. Expected: `dags/transform/dbt_trade.py: DWH-L06 line ...` and `1 finding(s)`.
  3. Restore it with `git checkout -- dags/transform/dbt_trade.py`.

- [ ] **Step 4: Run green.** Run `make dwh-test && make dwh-lint && make check-standards && make lint`. Expected:
  all pass, with 0 findings.

- [ ] **Step 5: Commit**

```bash
git add tools/dwh Makefile .pre-commit-config.yaml docs/standards/11-airflow.md
git commit -m "feat(lint): DWH-L06 fails a DAG schedule that names a model Asset" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Alerts — `alerts.notify` and `on_failure_callback`

**Files:**
- Create: `dags/_common/alerts.py`, `tests/dags/test_alerts.py`
- Modify: `dags/_common/defaults.py`, `deploy/helm/values.example.yaml`
- Modify: `docs/standards/11-airflow.md` (new STD-11-10)

**Interfaces:**
- Produces: `notify(context_or_message, *, get_connection=None, post=None) -> bool`. It returns True when the
  webhook accepted the alert and never raises. `DEFAULT_ARGS["on_failure_callback"] = notify`.

- [ ] **Step 1: Write the failing tests.** Create `tests/dags/test_alerts.py`:

```python
"""alerts.notify posts to the dwh_alert webhook, else logs; it never raises and never logs the URL."""

import logging
from types import SimpleNamespace

import requests

from _common.alerts import notify
from _common.defaults import DEFAULT_ARGS

URL = "https://hooks.example.test/services/secret-token"


def missing(conn_id):
    raise LookupError(conn_id)


def connection(host, schema=None):
    return lambda conn_id: SimpleNamespace(host=host, schema=schema)


class Recorder:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def __call__(self, url, json, timeout):
        self.calls.append((url, json, timeout))
        if self.error:
            raise self.error
        return SimpleNamespace(raise_for_status=lambda: None)


def failure_context():
    ti = SimpleNamespace(
        dag_id="dbt_trade", task_id="dwd_trade_order_di.run", try_number=3, log_url="http://log"
    )
    return {"ti": ti, "dag_run": SimpleNamespace(run_id="manual__1"), "exception": ValueError("boom")}


def test_without_the_connection_the_alert_is_logged(caplog):
    with caplog.at_level(logging.ERROR):
        assert notify("SLA missed", get_connection=missing, post=Recorder()) is False
    assert "no dwh_alert connection" in caplog.text
    assert "SLA missed" in caplog.text


def test_the_alert_is_posted_to_the_webhook():
    post = Recorder()

    assert notify(failure_context(), get_connection=connection(URL), post=post) is True
    url, body, timeout = post.calls[0]
    assert url == URL
    assert timeout == 10
    assert "dbt_trade.dwd_trade_order_di.run" in body["text"]
    assert "manual__1" in body["text"]
    assert "boom" in body["text"]
    assert "http://log" in body["text"]


def test_a_host_without_a_scheme_gets_https():
    post = Recorder()

    notify("x", get_connection=connection("hooks.example.test/services/t"), post=post)
    assert post.calls[0][0] == "https://hooks.example.test/services/t"


def test_a_failing_webhook_never_raises_and_never_logs_the_url(caplog):
    post = Recorder(error=requests.ConnectionError(f"cannot reach {URL}"))

    with caplog.at_level(logging.ERROR):
        assert notify("SLA missed", get_connection=connection(URL), post=post) is False
    assert "SLA missed" in caplog.text
    assert "secret-token" not in caplog.text


def test_an_unformattable_context_still_alerts(caplog):
    with caplog.at_level(logging.ERROR):
        assert notify({"ti": object(), "exception": None}, get_connection=missing) is False
    assert "Airflow task failed" in caplog.text


def callbacks(task) -> list:
    value = task.on_failure_callback
    return list(value) if isinstance(value, list | tuple) else [value]


def test_every_task_alerts_on_failure(dagbag):
    assert DEFAULT_ARGS["on_failure_callback"] is notify
    for dag in dagbag.dags.values():
        for task in dag.tasks:
            assert notify in callbacks(task), f"{dag.dag_id}.{task.task_id}"
```

Run: `make test-dags`. Expected: FAIL (no module `_common.alerts`).

- [ ] **Step 2: Implement** `dags/_common/alerts.py`:

```python
"""Failure and SLA alerts (plan 5, design §3.2): a Slack webhook through the Airflow connection dwh_alert,
else the log at ERROR.

notify() never raises: an alert that fails must not hide the failure it reports. It never logs the webhook URL,
which is a secret.
"""

import logging
from collections.abc import Callable, Mapping
from typing import Any

import requests

CONNECTION_ID = "dwh_alert"
TIMEOUT_SECONDS = 10
log = logging.getLogger(__name__)


def message_from(context_or_message: Mapping[str, Any] | str) -> str:
    if isinstance(context_or_message, str):
        return context_or_message
    context = context_or_message
    ti = context.get("ti") or context.get("task_instance")
    run = context.get("dag_run")
    dag_id = getattr(ti, "dag_id", None) or getattr(context.get("dag"), "dag_id", "?")
    lines = [
        f"Airflow task failed: {dag_id}.{getattr(ti, 'task_id', '?')} "
        f"(run {getattr(run, 'run_id', '?')}, try {getattr(ti, 'try_number', '?')})"
    ]
    if context.get("exception") is not None:
        lines.append(str(context["exception"]))
    if getattr(ti, "log_url", None):
        lines.append(f"Log: {ti.log_url}")
    return "\n".join(lines)


def default_get_connection(conn_id: str) -> Any:
    from airflow.sdk import Connection

    return Connection.get(conn_id)


def webhook_url(get_connection: Callable[[str], Any]) -> str | None:
    try:
        conn = get_connection(CONNECTION_ID)
    except Exception:  # the connection is optional: missing means "log only"
        return None
    host = (getattr(conn, "host", None) or "").strip()
    if not host:
        return None
    if host.startswith(("http://", "https://")):
        return host
    return f"{getattr(conn, 'schema', None) or 'https'}://{host}"


def notify(
    context_or_message: Mapping[str, Any] | str,
    *,
    get_connection: Callable[[str], Any] | None = None,
    post: Callable[..., Any] | None = None,
) -> bool:
    """Send one alert. True when the webhook accepted it; False when it was only logged. Never raises."""
    try:
        message = message_from(context_or_message)
    except Exception:
        message = "Airflow task failed (the alert could not be formatted; see the task log)"
    try:
        url = webhook_url(get_connection or default_get_connection)
        if url is None:
            log.error("dwh alert (no %s connection): %s", CONNECTION_ID, message)
            return False
        response = (post or requests.post)(url, json={"text": message}, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return True
    except Exception as error:
        log.error("dwh alert: the webhook failed (%s); the alert was: %s", type(error).__name__, message)
        return False
```

The test `test_an_unformattable_context_still_alerts` passes `object()` as `ti`. `message_from` then still renders
"Airflow task failed: ?.?" through the `getattr` defaults. Keep the outer `try` anyway: a broken `__str__` on an
exception must not escape.

In `dags/_common/defaults.py`, add `from _common.alerts import notify` and `"on_failure_callback": notify,` with the
comment "# alerts.notify: Slack via the dwh_alert connection, else the log (STD-11-10)".

In `deploy/helm/values.example.yaml`, after `extraEnvFrom`, add:

```yaml
# Alerts (STD-11-10): the Airflow connection dwh_alert, from a Secret holding
#   AIRFLOW_CONN_DWH_ALERT='{"conn_type": "http", "host": "https://hooks.slack.com/services/..."}'
# Without it, alerts are logged at ERROR in the task log.
```

STD-11-10 **Alerts go through alerts.notify (MUST)**:
- `DEFAULT_ARGS` sets `on_failure_callback=notify`, and every alert goes through `notify`.
- `notify` posts to the `dwh_alert` webhook, else logs at ERROR, and never raises.
- Correct: `default_args=DEFAULT_ARGS`.
- Incorrect: a DAG-local `on_failure_callback=lambda ctx: requests.post(WEBHOOK, ...)`, with the comment "raises when
  Slack is down and hides the failure; the URL sits in code".
- Source: Spec §4.

- [ ] **Step 3: Run green.** Run `make lint && make check-standards && make test-dags`. Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add dags/_common tests/dags/test_alerts.py deploy/helm/values.example.yaml docs/standards/11-airflow.md
git commit -m "feat(dags): alert every task failure through alerts.notify (dwh_alert webhook, else the log)" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The SLA watchdog DAG `dwh_sla_watchdog`

**Files:**
- Create: `dags/_common/sla.py`, `dags/maintenance/dwh_sla_watchdog.py`
- Create: `tests/dags/test_sla.py`, `tests/integration/test_sla_watchdog.py`
- Modify: `Dockerfile` (a manifest parsed at build time)
- Modify: `docs/standards/11-airflow.md` (new STD-11-11), `docs/standards/09-dbt-conventions.md` (document
  `meta.sla` and `meta.sla_allow_empty` next to the other `config.meta` keys)

**Interfaces:**
- Consumes: Task 1 (M4 and M5), Task 3 (`PIPELINES`, `owner_of`, `done_asset`) and Task 5 (`notify` as the
  `on_failure_callback`).
- Produces `_common.sla`. It imports no Airflow, so the dbt venv can import it. It holds:
  - `Model` and `Miss`;
  - `load_models(manifest_path)`, `parse_deadline(value, model)`, `owner_of`-based ownership, and
    `layer_schema(layer)`;
  - `find_misses(models, *, day, now, query, schema_for, done_dags) -> list[Miss]`;
  - `published(events, day) -> bool`, `render(misses, day) -> str` and `trino_query(sql) -> list[tuple]`.
- **One alert per run.** The check task raises `AirflowFailException(render(...))` with `retries=0`. The DAG's
  `on_failure_callback` (`alerts.notify`, Task 5) then sends that one message, and a crash of the watchdog itself
  (for example Trino down) alerts the same way. That is how the watchdog uses `alerts.notify` (design §3.2) without
  a second alert.
- **Decision on the read-only connection.** The watchdog runs only `SELECT` statements, through Trino's REST
  protocol with `requests`. `requests` is in both locks; the Airflow venv has no `trino` client, so no lock change
  is needed. It sends the user `$DWH_WATCHDOG_TRINO_USER` (default `dwh_sla_watchdog`). Production makes that user
  read-only in Trino's access control (a deployment concern, recorded in Known limits).
- **Rule for `_hist`.** A `_hist` passes if its latest Iceberg snapshot was committed after `D + 1 00:00` VN, or if
  its DAG's `publish_done` for `D` succeeded. The second clause covers an unchanged snapshot that commits nothing
  (Task 1 M5).

- [ ] **Step 1: Write the failing unit tests.** Create `tests/dags/test_sla.py`:

```python
"""The SLA watchdog core (design §3.1), with a fake query function: no Trino, no Airflow."""

import json
from datetime import date, datetime, time
from types import SimpleNamespace

import pytest

from _common.sla import (
    BUSINESS_TZ,
    Model,
    QueryError,
    find_misses,
    load_models,
    parse_deadline,
    published,
    render,
)

DAY = date(2026, 11, 2)
AT_7 = datetime(2026, 11, 3, 7, 0, tzinfo=BUSINESS_TZ)
AFTER_CUTOFF = datetime(2026, 11, 3, 0, 30, tzinfo=BUSINESS_TZ).timestamp()
BEFORE_CUTOFF = datetime(2026, 11, 2, 23, 0, tzinfo=BUSINESS_TZ).timestamp()


def model(
    name="dwd_trade_order_di", layer="dwd", partitioned=True, allow_empty=False, snapshot=False, sla="06:00"
):
    return Model(name, layer, "dbt_trade", parse_deadline(sla, name), partitioned, allow_empty, snapshot)


class FakeTrino:
    def __init__(self, answer):
        self.answer, self.sql = answer, []

    def __call__(self, sql):
        self.sql.append(sql)
        if isinstance(self.answer, Exception):
            raise self.answer
        return [(self.answer,)]


def misses(models, answer, now=AT_7, done=()):
    query = FakeTrino(answer)
    found = find_misses(
        models, day=DAY, now=now, query=query, schema_for=lambda layer: f"dev_{layer}", done_dags=set(done)
    )
    return found, query


def test_a_partition_with_rows_passes():
    found, query = misses([model()], 3)
    assert found == []
    assert query.sql == [
        'SELECT count(*) FROM iceberg."dev_dwd"."dwd_trade_order_di" WHERE dw_dt = DATE \'2026-11-02\''
    ]


def test_an_empty_partition_is_a_miss_with_layer_dag_and_deadline():
    found, _ = misses([model()], 0)
    assert [(m.layer, m.name, m.dag_id, m.deadline) for m in found] == [
        ("dwd", "dwd_trade_order_di", "dbt_trade", "06:00")
    ]
    assert found[0].reason == "no rows for dw_dt = 2026-11-02"


def test_allow_empty_passes_only_when_its_dag_published_the_day():
    assert misses([model(allow_empty=True)], 0, done={"dbt_trade"})[0] == []
    assert len(misses([model(allow_empty=True)], 0)[0]) == 1


def test_a_model_before_its_deadline_is_not_checked():
    found, query = misses([model(sla="08:30")], 0)
    assert found == []
    assert query.sql == []


def test_an_unpartitioned_table_passes_on_a_commit_after_the_day():
    found, query = misses([model("dim_trade_shop", "dim", partitioned=False)], AFTER_CUTOFF)
    assert found == []
    assert query.sql == [
        'SELECT to_unixtime(max(committed_at)) FROM iceberg."dev_dim"."dim_trade_shop$snapshots"'
    ]


def test_an_unpartitioned_table_committed_before_the_day_ended_is_a_miss():
    assert len(misses([model("dim_trade_shop", "dim", partitioned=False)], BEFORE_CUTOFF)[0]) == 1
    assert len(misses([model("dim_trade_shop", "dim", partitioned=False)], None)[0]) == 1


def test_an_unchanged_hist_passes_when_its_dag_published_the_day():
    hist = model("dim_pub_customer_hist", "dim", partitioned=False, snapshot=True)
    assert misses([hist], BEFORE_CUTOFF, done={"dbt_trade"})[0] == []
    assert len(misses([hist], BEFORE_CUTOFF)[0]) == 1


def test_a_failed_query_is_a_miss_that_names_the_error():
    found, _ = misses([model()], QueryError("Table 'dev_dwd.dwd_trade_order_di' does not exist"))
    assert found[0].reason.startswith("query failed: Table")


@pytest.mark.parametrize("value", ["8:30", "24:00", "06:60", "", 6])
def test_a_deadline_must_be_hh_mm(value):
    with pytest.raises(ValueError, match="meta.sla"):
        parse_deadline(value, "m")


def test_parse_deadline_reads_hh_mm():
    assert parse_deadline("08:30", "m") == time(8, 30)


def test_published_matches_the_dt_extra():
    events = [SimpleNamespace(extra={"dt": "2026-11-01"}), SimpleNamespace(extra={"dt": "2026-11-02"})]
    assert published(events, DAY)
    assert not published(events[:1], DAY)
    assert not published([SimpleNamespace(extra=None)], DAY)


def test_render_lists_every_miss():
    found, _ = misses([model(), model("dws_trade_customer_1d", "dws")], 0)
    text = render(found, DAY)
    assert text.splitlines()[0] == "SLA missed for business day 2026-11-02: 2 model(s)"
    assert "- dwd dwd_trade_order_di (DAG dbt_trade, deadline 06:00): no rows for dw_dt = 2026-11-02" in text
    assert "dws_trade_customer_1d" in text


def node(name, path, tags, resource_type="model", meta=None, partitioning=None):
    config = {"tags": tags, "meta": meta or {}}
    if partitioning:
        config["properties"] = {"partitioning": partitioning}
    return {
        "name": name,
        "resource_type": resource_type,
        "package_name": "example_dwh",
        "original_file_path": path,
        "tags": tags,
        "config": config,
    }


def test_load_models_reads_layer_owner_deadline_and_partitioning(tmp_path):
    nodes = {
        "model.example_dwh.ods_shop_orders_di": node(
            "ods_shop_orders_di",
            "models/ods/shop/ods_shop_orders_di.sql",
            ["layer:ods", "ods_shop"],
            meta={"sla": "05:00", "sla_allow_empty": True},
            partitioning="ARRAY['dw_dt']",
        ),
        "snapshot.example_dwh.dim_pub_customer_hist": node(
            "dim_pub_customer_hist",
            "snapshots/dim_pub_customer_hist.yml",
            ["domain:pub"],
            resource_type="snapshot",
        ),
        "model.dbt_utils.x": {**node("x", "models/x.sql", []), "package_name": "dbt_utils"},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"metadata": {"project_name": "example_dwh"}, "nodes": nodes}))

    ods, hist = load_models(path)
    assert (ods.layer, ods.dag_id, ods.deadline, ods.partitioned, ods.allow_empty) == (
        "ods",
        "dbt_ods_shop",
        time(5),
        True,
        True,
    )
    assert (hist.layer, hist.dag_id, hist.deadline, hist.partitioned, hist.snapshot) == (
        "dim",
        "dbt_pub",
        time(6),
        False,
        True,
    )


def test_load_models_refuses_a_model_no_dag_selects(tmp_path):
    nodes = {"model.example_dwh.dim_pub_x": node("dim_pub_x", "models/dim/pub/dim_pub_x.sql", ["layer:dim"])}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"metadata": {"project_name": "example_dwh"}, "nodes": nodes}))
    with pytest.raises(ValueError, match="STD-11-08"):
        load_models(path)
```

Add to the same file the DAG and manifest tests. They need the image's manifest, which Step 3 bakes:

```python
import os
from pathlib import Path

from _common.pipelines import PIPELINES


def test_every_model_in_the_image_manifest_has_one_dag_and_a_valid_sla():
    models = load_models(Path(os.environ["DWH_MANIFEST_PATH"]))
    assert {m.dag_id for m in models} == set(PIPELINES)
    assert any(m.snapshot for m in models)


def test_watchdog_runs_hourly_from_2_to_12_vietnam_time_and_reads_every_done_asset(dagbag):
    dag = dagbag.get_dag("dwh_sla_watchdog")
    check = dag.get_task("check_sla")

    assert dag.timetable.serialize()["expression"] == "0 2-12 * * *"
    assert dag.timetable.serialize()["timezone"] == "Asia/Ho_Chi_Minh"
    assert {asset.name for asset in check.inlets} == {f"dwh_done/{dag_id}" for dag_id in PIPELINES}
    assert check.retries == 0
```

Move these imports to the top of the file. The file must pass `make lint`; run `make fmt` once to wrap the long
lines. Run: `make test-dags`. Expected: FAIL (no `_common.sla`).

- [ ] **Step 2: Implement `dags/_common/sla.py`:**

```python
"""SLA watchdog core (plan 5, design §3.1): which models missed their deadline for business day D.

No Airflow import: the DAG, the unit tests and the integration tests (dbt venv) all import it.
- Deadline: 06:00 Asia/Ho_Chi_Minh on D + 1, or config.meta.sla "HH:MM".
- Partitioned models (dw_dt): D has a row, or meta.sla_allow_empty and the owning DAG published D.
- Other tables: the latest Iceberg snapshot was committed after D + 1 00:00 VN; a _hist snapshot also passes
  when its DAG published D (an unchanged snapshot commits nothing).
"""

import json
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

import requests

from _common.pipelines import owner_of

BUSINESS_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
DEFAULT_DEADLINE = "06:00"
DEADLINE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
PARTITION = "dw_dt"
LAYERS = ("ods", "dim", "dwd", "dws", "ads")
CATALOG = os.environ.get("TRINO_CATALOG", "iceberg")

Query = Callable[[str], list[tuple]]


class QueryError(RuntimeError):
    """Trino answered with an error."""


@dataclass(frozen=True)
class Model:
    name: str
    layer: str
    dag_id: str
    deadline: time
    partitioned: bool
    allow_empty: bool
    snapshot: bool


@dataclass(frozen=True)
class Miss:
    layer: str
    name: str
    dag_id: str
    deadline: str
    reason: str


def parse_deadline(value: object, model: str) -> time:
    if not isinstance(value, str) or not DEADLINE.match(value):
        raise ValueError(f"{model}: meta.sla must be 'HH:MM' (24-hour), got {value!r}")
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def layer_of(node: dict) -> str | None:
    if node["resource_type"] == "snapshot":
        return "dim"
    parts = PurePosixPath(node["original_file_path"]).parts
    return parts[1] if len(parts) >= 3 and parts[0] == "models" and parts[1] in LAYERS else None


def load_models(manifest_path: Path) -> list[Model]:
    """Every model and snapshot of the root project, with its owning DAG and deadline."""
    manifest = json.loads(Path(manifest_path).read_text())
    project = manifest["metadata"]["project_name"]
    models = []
    for node in manifest["nodes"].values():
        if node.get("package_name") != project or node["resource_type"] not in ("model", "snapshot"):
            continue
        config = node.get("config") or {}
        meta = config.get("meta") or node.get("meta") or {}
        layer, dag_id = layer_of(node), owner_of(node.get("tags") or config.get("tags") or [])
        if layer is None or dag_id is None:
            raise ValueError(f"{node['name']}: no layer folder, or not exactly one owning DAG (STD-11-08)")
        partitioning = str((config.get("properties") or {}).get("partitioning", ""))
        models.append(
            Model(
                name=node["name"],
                layer=layer,
                dag_id=dag_id,
                deadline=parse_deadline(meta.get("sla", DEFAULT_DEADLINE), node["name"]),
                partitioned=f"'{PARTITION}'" in partitioning,
                allow_empty=meta.get("sla_allow_empty") is True,
                snapshot=node["resource_type"] == "snapshot",
            )
        )
    return sorted(models, key=lambda m: (LAYERS.index(m.layer), m.name))


def layer_schema(layer: str) -> str:
    """The schema generate_schema_name gives a layer: the bare layer in prod, <DBT_SCHEMA>_<layer> elsewhere."""
    if os.environ.get("DBT_TARGET", "dev") == "prod":
        return layer
    return f"{os.environ.get('DBT_SCHEMA', 'dev')}_{layer}"


def cutoff(day: date) -> datetime:
    return datetime.combine(day + timedelta(days=1), time(0), BUSINESS_TZ)


def check(model: Model, day: date, query: Query, schema: str, done: bool) -> str | None:
    """None when the model has its day, else why not."""
    table = f'{CATALOG}."{schema}"."{model.name}'
    try:
        if model.partitioned:
            rows = query(f"SELECT count(*) FROM {table}\" WHERE {PARTITION} = DATE '{day.isoformat()}'")
            if rows[0][0] > 0 or (model.allow_empty and done):
                return None
            return f"no rows for {PARTITION} = {day.isoformat()}"
        committed = query(f'SELECT to_unixtime(max(committed_at)) FROM {table}$snapshots"')[0][0]
    except (QueryError, requests.RequestException) as error:
        return f"query failed: {error}"
    if committed is not None and committed > cutoff(day).timestamp():
        return None
    if model.snapshot and done:
        return None
    when = "never" if committed is None else datetime.fromtimestamp(committed, BUSINESS_TZ).isoformat()
    return f"last commit {when} is before {cutoff(day).isoformat()}"


def find_misses(
    models: Iterable[Model],
    *,
    day: date,
    now: datetime,
    query: Query,
    schema_for: Callable[[str], str],
    done_dags: set[str],
) -> list[Miss]:
    """The models whose deadline for `day` has passed at `now` and whose data for `day` is missing."""
    misses = []
    for model in models:
        if now < datetime.combine(day + timedelta(days=1), model.deadline, BUSINESS_TZ):
            continue
        reason = check(model, day, query, schema_for(model.layer), model.dag_id in done_dags)
        if reason:
            deadline = model.deadline.strftime("%H:%M")
            misses.append(Miss(model.layer, model.name, model.dag_id, deadline, reason))
    return misses


def published(events: Iterable, day: date) -> bool:
    """Whether one of a DAG's dwh_done events carries `day`."""
    return any((event.extra or {}).get("dt") == day.isoformat() for event in events)


def render(misses: list[Miss], day: date) -> str:
    lines = [f"SLA missed for business day {day.isoformat()}: {len(misses)} model(s)"]
    lines += [f"- {m.layer} {m.name} (DAG {m.dag_id}, deadline {m.deadline}): {m.reason}" for m in misses]
    return "\n".join(lines)


def trino_query(sql: str, timeout: float = 30.0) -> list[tuple]:
    """Run one read-only statement through Trino's REST protocol (the Airflow venv has no trino client)."""
    scheme = os.environ.get("TRINO_HTTP_SCHEME", "http")
    base = f"{scheme}://{os.environ.get('TRINO_HOST', 'localhost')}:{os.environ.get('TRINO_PORT', '8080')}"
    headers = {
        "X-Trino-User": os.environ.get("DWH_WATCHDOG_TRINO_USER", "dwh_sla_watchdog"),
        "X-Trino-Source": "dwh_sla_watchdog",
    }
    response = requests.post(f"{base}/v1/statement", data=sql.encode(), headers=headers, timeout=timeout)
    rows: list = []
    while True:
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise QueryError(payload["error"].get("message", "query failed"))
        rows.extend(payload.get("data") or [])
        if not payload.get("nextUri"):
            return [tuple(row) for row in rows]
        response = requests.get(payload["nextUri"], headers=headers, timeout=timeout)
```

The unit tests pin the exact SQL text. `table` deliberately leaves its closing quote to the two statements, so the
`$snapshots` suffix sits inside the quoted identifier. If a reviewer finds that unclear, build the two relation
strings explicitly. Keep the SQL the tests expect.

`dags/maintenance/dwh_sla_watchdog.py`:

```python
"""Airflow DAG: the SLA watchdog. Hourly 02:00-12:00 Asia/Ho_Chi_Minh, it checks yesterday's data of every model.

One alert per run lists every late model: the check raises AirflowFailException, and the default
on_failure_callback (alerts.notify) sends its message (STD-11-11). It alerts again each hour until the miss clears.
"""

import os
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.exceptions import AirflowFailException
from airflow.sdk import DAG, task
from airflow.timetables.trigger import CronTriggerTimetable

from _common.assets import done_asset
from _common.dates import BUSINESS_TZ, vn_date
from _common.defaults import DEFAULT_ARGS
from _common.pipelines import PIPELINES
from _common.sla import find_misses, layer_schema, load_models, published, render, trino_query

MANIFEST = Path(os.environ.get("DWH_MANIFEST_PATH", "/opt/dbt_manifest/warehouse/manifest.json"))
DONE_ASSETS = {dag_id: done_asset(dag_id) for dag_id in PIPELINES}

with DAG(
    dag_id="dwh_sla_watchdog",
    schedule=CronTriggerTimetable("0 2-12 * * *", timezone=BUSINESS_TZ),
    start_date=vn_date(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["layer:maintenance"],
):

    @task(task_id="check_sla", inlets=list(DONE_ASSETS.values()), retries=0)
    def check_sla(*, dag_run=None, inlet_events=None) -> None:
        now = pendulum.instance(dag_run.run_after).in_timezone(BUSINESS_TZ)
        day = now.date() - timedelta(days=1)
        done = {dag_id for dag_id, asset in DONE_ASSETS.items() if published(inlet_events[asset][-50:], day)}
        misses = find_misses(
            load_models(MANIFEST),
            day=day,
            now=now,
            query=trino_query,
            schema_for=layer_schema,
            done_dags=done,
        )
        if misses:
            raise AirflowFailException(render(misses, day))
        print(f"SLA met for business day {day.isoformat()}")

    check_sla()
```

`Dockerfile`, in the `base` stage after the `dbt deps` block:

```dockerfile
# The SLA watchdog reads the model list from a manifest parsed at build time (no dbt ls at run time). It reads
# names, layers, tags and meta only, never schemas, so one manifest serves every target.
COPY dbt/warehouse /tmp/dbt-manifest/
USER root
RUN cd /tmp/dbt-manifest \
    && DBT_PROFILES_DIR=/tmp/dbt-manifest DBT_TARGET_PATH=/opt/dbt_manifest/warehouse /opt/dbt-venv/bin/dbt parse --no-partial-parse \
    && rm -rf /tmp/dbt-manifest \
    && chown -R airflow: /opt/dbt_manifest /tmp/dbt
USER airflow
ENV DWH_MANIFEST_PATH=/opt/dbt_manifest/warehouse/manifest.json
```

STD-11-11 **Every model has an SLA (MUST)**:
- The deadline is 06:00 Asia/Ho_Chi_Minh the day after `D`, or `config.meta.sla: "HH:MM"`.
- A model whose day may be empty sets `config.meta.sla_allow_empty: true`, and then passes on its DAG's done event.
- The watchdog runs hourly 02:00–12:00 VN, alerts once per run listing every miss, and alerts again each hour until
  the miss clears.
- A model added after the image was built is watched from the next image.
- Correct:

  ```yaml
  config:
    meta:
      sla: "08:30"
  ```

- Incorrect: `sla: "8:30"`, with the comment "not HH:MM: the watchdog fails to load the manifest".
- Source: Spec §4.

- [ ] **Step 3: Write the integration test** `tests/integration/test_sla_watchdog.py`:

```python
"""The SLA watchdog core on the local stack: a missing partition is caught and clears after the build (plan 5)."""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from helpers import MAIN_PROJECT, REPO, drop_schemas, run_dbt

sys.path.insert(0, str(REPO / "dags"))

from _common.sla import BUSINESS_TZ, find_misses, load_models, trino_query  # noqa: E402

SCHEMA = "itest_sla"
DAY = date(2026, 11, 2)
NOW = datetime(2026, 11, 3, 7, 0, tzinfo=BUSINESS_TZ)  # past the 06:00 default deadline for 2026-11-02
WATCHED = {"ods_shop_orders_di", "dim_trade_shop"}


@pytest.fixture(scope="module", autouse=True)
def clean():
    drop_schemas(SCHEMA)
    yield
    drop_schemas(SCHEMA)


@pytest.fixture(scope="module")
def models():
    run_dbt(MAIN_PROJECT, ["parse"], SCHEMA)
    return [
        m
        for m in load_models(Path(f"/tmp/dbt/target-{MAIN_PROJECT.name}/manifest.json"))
        if m.name in WATCHED
    ]


def misses(models, day=DAY, now=NOW) -> dict[str, str]:
    found = find_misses(
        models,
        day=day,
        now=now,
        query=trino_query,
        schema_for=lambda layer: f"{SCHEMA}_{layer}",
        done_dags=set(),
    )
    return {m.name: m.reason for m in found}


def test_a_model_never_built_is_a_miss(models):
    found = misses(models)
    assert set(found) == WATCHED
    assert all(reason.startswith("query failed:") for reason in found.values())


def test_a_missing_partition_is_caught_and_clears_after_the_build(models):
    run_dbt(MAIN_PROJECT, ["build", "--select", "ods_shop_orders_di", "--vars", "{dt: '2026-11-01'}"], SCHEMA)
    assert misses(models)["ods_shop_orders_di"] == "no rows for dw_dt = 2026-11-02"

    run_dbt(MAIN_PROJECT, ["build", "--select", "ods_shop_orders_di", "--vars", "{dt: '2026-11-02'}"], SCHEMA)
    assert "ods_shop_orders_di" not in misses(models)


def test_a_rebuilt_table_passes_only_for_days_that_ended_before_its_commit(models):
    run_dbt(MAIN_PROJECT, ["build", "--select", "+dim_trade_shop", "--vars", "{dt: '2026-11-02'}"], SCHEMA)
    assert "dim_trade_shop" not in misses(models)  # committed now, after 2026-11-03 00:00 VN

    today = datetime.now(BUSINESS_TZ).date()
    later = misses(
        models,
        day=today,
        now=datetime.combine(today + timedelta(days=1), datetime.min.time(), BUSINESS_TZ)
        + timedelta(hours=7),
    )
    assert later["dim_trade_shop"].startswith("last commit ")
```

`run_dbt` writes to `/tmp/dbt/target-warehouse` (`DBT_TARGET_PATH = /tmp/dbt/target-<project dir name>`). The model
`ods_shop_orders_di` only exists with the `dw_dt` column after Task 7a. Until then, the second test's expected
reason reads `dw_dt` while the table holds `dt`, and that test is marked:

```python
@pytest.mark.xfail(reason="dw_dt arrives in Task 7a", strict=True)
```

Task 7a removes the mark. `strict=True` makes the removal mandatory.

- [ ] **Step 4: Run green.**

```bash
make lint && make check-standards && make dev-down && make image && make dev-up \
  && make test-dags && make test-integration && make e2e
```

Expected: all pass (`test_a_missing_partition...` xfails, strictly). `docker run --rm --entrypoint ls
example-dwh-airflow:dev /opt/dbt_manifest/warehouse` lists `manifest.json`.

- [ ] **Step 5: Commit**

```bash
git add dags tests/dags/test_sla.py tests/integration/test_sla_watchdog.py Dockerfile docs/standards
git commit -m "feat(dags): add the dwh_sla_watchdog DAG with per-model deadlines (meta.sla)" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7a: `dw_` technical columns — the rename in code, models and tests

**Files:**
- Modify: every `.sql` and `.yml` under `dbt/warehouse/models`, the `dim_pub_customer_hist.yml` snapshot (at its
  Task 2b place), `dbt/warehouse/macros/maintenance.sql`
- Modify: `tools/dwh/src/dwh/scaffold.py`, `tools/dwh/src/dwh/column_types.py`, `tools/dwh/src/dwh/rules/metrics.py`,
  `tools/dwh/src/dwh/codes.py` (DWH-M03 meaning)
- Modify: `tools/dwh/tests/test_scaffold.py`, `test_scaffold_types.py`, `test_rules_metrics.py`,
  `tools/dwh/tests/fixtures/manifest.py`, `fixtures/warehouse.py` (`WORDS`)
- Modify: `warehouse/glossary.yml` (words `dw`, `scd`, `snapshot`)
- Modify: `tests/integration/test_ods_shop.py`, `test_maintenance.py`, `test_trade_domain.py`,
  `test_sla_watchdog.py` (drop the xfail)
- Modify: `dev/e2e.sh` (`check_rows` column)

**Interfaces:**
- Produces: every stored partition column is `dw_dt`. `_hist` has `dw_valid_from`, `dw_valid_to`, `dw_scd_id` and
  `dw_snapshot_at`. The run parameter stays `dt`.
- **Out of scope (deliberate):**
  - `dev/smoke.sql` and `tests/integration/dbt_capabilities/` measure engine capabilities, not warehouse tables.
    dwh lint does not read them, and they keep their columns.
  - No model has `is_current` or `is_inferred` today. Their `dw_` names enter only the closed list (Task 7b).

- [ ] **Step 1: Write the failing tests.**
  - In `tools/dwh/tests/test_scaffold.py`, change every expectation that names the column `dt`:
    - lines 71, 163, 165, 193, 230, 239, 241, 314, 391, 399, 401: `dt` → `dw_dt` in the SQL and YAML expectations;
    - `get_dt()` and `TODAY` stay.
  - Lines 107–108, the snapshot names, become:

    ```python
    "dbt_valid_from": "dw_valid_from",
    "dbt_valid_to": "dw_valid_to",
    "dbt_scd_id": "dw_scd_id",
    "dbt_updated_at": "dw_snapshot_at",
    ```

  - In `test_scaffold_types.py`: line 19 becomes `as dw_dt`, line 94 `"dw_dt": "date"`, and line 191 asserts
    `" dw_dt" not in comment`.
  - In `fixtures/manifest.py`, rename every column `"dt"` to `"dw_dt"` (lines 160–245).
  - In `fixtures/warehouse.py`, add `dw scd snapshot` to `WORDS`.
  - In `test_rules_metrics.py`, make every DWS fixture column `dw_dt`, and add:

```python
def test_m03_the_old_partition_column_name_is_not_a_dws_column(lint):
    builder, ids = good_project()
    builder.node(ids["dws_customer"])["columns"]["dt"] = {"name": "dt", "description": "Old.", "meta": {}}
    assert lint(builder, prefix="DWH-M") == ["DWH-M03"]
```

  Run `make dwh-test`. Expected: FAIL.

- [ ] **Step 2: Implement the tooling.**
  - `scaffold.py`: replace the column `dt` with `dw_dt`. The line numbers below are PR #11's. Task 2b shifts them,
    so find each by content with `grep -n -w dt tools/dwh/src/dwh/scaffold.py`. The PR #11 lines are 23, 24, 32, 39, 71, 98, 105, 112, 152,
    405, 409, 420, 558, 563, 564, 595, 602, 618, 620, 622, 652, 673, 687, 694, 714, 717 and 721.
    - Keep `TODAY` (`get_dt()`) and the prose that names the business day at 392, 394, 612–615 and 751.
    - Add `"dbt_scd_id": "dw_scd_id"` and `"dbt_updated_at": "dw_snapshot_at"` to `snapshot_meta_column_names`, and
      rename the two existing values.
  - `column_types.py`: line 6 doc `as dw_dt`, the line 22 regex `\s+as dw_dt,?\s*$`, and line 64 `"dw_dt"`.
  - `rules/metrics.py`: line 59 becomes `column.name == "dw_dt"`, and the message says "grain columns, dw_dt, or
    metrics". In `codes.py`, DWH-M03 becomes "DWS column is not a grain column, dw_dt or metric, or the grain is
    undeclared".
  - `warehouse/glossary.yml`: keep `dt` (it names the run parameter in prose, and the `dw_dt` token check needs it),
    and add after it:

    ```yaml
      - {word: dw, meaning: "Prefix of technical (warehouse-managed) columns, e.g. dw_dt (STD-02-10)."}
      - {word: scd, meaning: "Slowly changing dimension, as in dw_scd_id."}
      - {word: snapshot, meaning: "A dbt snapshot run, as in dw_snapshot_at."}
    ```

  - `make dwh-test` passes.
- [ ] **Step 3: Rename in the dbt project.** Run this one-off script from the repository root. It touches column
  references only; vars blocks and `get_dt()` are left alone.

```bash
python3 - <<'EOF'
import re
from pathlib import Path

SQL = re.compile(r"\bdt\b")  # never matches get_dt: "_" is a word character
YML = [
    (re.compile(r"^(\s*- name: )dt$", re.M), r"\1dw_dt"),
    (re.compile(r"^(\s*- )dt$", re.M), r"\1dw_dt"),
    (re.compile(r"(combination_of_columns: \[[^\]]*), dt\]"), r"\1, dw_dt]"),
    (re.compile(r", dt: '"), ", dw_dt: '"),  # unit-test rows; `vars: {dt: ...}` follows "{" and stays
]
for path in sorted(Path("dbt/warehouse/models").rglob("*.sql")) + [Path("dbt/warehouse/macros/maintenance.sql")]:
    text = path.read_text()
    new = SQL.sub("dw_dt", text) if path.name != "maintenance.sql" else text.replace("'dt'", "'dw_dt'").replace(" where dt <", " where dw_dt <")
    if new != text:
        path.write_text(new)
        print("sql", path)
for path in sorted(Path("dbt/warehouse/models").rglob("*.yml")):
    text = path.read_text()
    new = text
    for pattern, repl in YML:
        new = pattern.sub(repl, new)
    if new != text:
        path.write_text(new)
        print("yml", path)
EOF
```

Then, by hand:
- The snapshot `dim_pub_customer_hist.yml` (at its Task 2b place):
  - `snapshot_meta_column_names` becomes `dbt_valid_from: dw_valid_from`, `dbt_valid_to: dw_valid_to`,
    `dbt_scd_id: dw_scd_id` and `dbt_updated_at: dw_snapshot_at`;
  - the description says `dw_valid_from and dw_valid_to are the source change times`.
- `dbt/warehouse/models/dwd/trade/dwd_trade_order_di/dwd_trade_order_di.sql`, `history` CTE: `valid_from` → `dw_valid_from` and `valid_to` →
  `dw_valid_to`. The CTE's output aliases may keep short names, but the join reads `h.dw_valid_from` and
  `h.dw_valid_to`; prefer prefixed aliases.
- Read every changed `description:` that mentions the partition. "rows whose updated_at falls on dt" names the
  business day and stays. "Partition date ..." on the `dw_dt` column stays.
- Check with `git grep -nw dt -- dbt/warehouse`. The only hits left are `vars` blocks, prose descriptions and `get_dt.sql`.
- [ ] **Step 4: Rename in the tests and the e2e.** In the SQL strings only, never in Python names or in
  `--vars "{dt: ...}"`:
  - `test_ods_shop.py`: line 22 `WHERE dw_dt =`; line 73 `SELECT DISTINCT dw_dt ... ORDER BY dw_dt`; lines 82
    and 90 `WHERE dw_dt =`.
  - `test_maintenance.py`: line 23 `column_name <> 'dw_dt'`; lines 33–34 `({cols}, dw_dt)` and `WHERE dw_dt =`;
    lines 51 and 91 `where dw_dt < date_add(`; lines 55 and 69 `dw_dt`.
  - `test_trade_domain.py`: lines 86 and 88 `h.dw_valid_from, h.dw_valid_to` and `ORDER BY h.dw_valid_from`; lines
    113, 141–142, 163, 172, 181, 231 and 238–242: the SQL column `dt` → `dw_dt` (aliases `s.dw_dt`, `a.dw_dt`).
  - `test_sla_watchdog.py`: delete the `xfail` mark.
  - `dev/e2e.sh` `check_rows`: `WHERE dw_dt = DATE '$DT'`. The printed label may keep `dt=$DT` (the run day).
  - Every expected number stays as it is (Global Constraints, "The fixture stays").
- [ ] **Step 5: Run green on a fresh stack**

```bash
make lint && make sql-lint && make test-repo && make dwh-test && make validate && make dwh-lint \
  && make dev-down && make image && make dev-up && make test-dags && make test-integration && make e2e
```

Expected:
- all pass;
- the integration suite reports the same passing tests as before plus Task 6's, with no xfail;
- e2e prints the same row counts (2, 3, 1, 1) and `e2e OK`;
- `make dwh-lint` reports 0 findings.

- [ ] **Step 6: Commit**

```bash
git add dbt tools/dwh warehouse/glossary.yml tests/integration dev/e2e.sh
git commit -m "refactor!: prefix technical columns with dw_ (dt -> dw_dt, snapshot meta columns)" \
  -m "The run parameter stays dt (conf.dt, var dt, get_dt). Integration fixture values are unchanged." \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7b: The `dw_` rule — closed list, DWH-N07, STD-02-10, rulebook and docs sweep

**Files:**
- Modify: `warehouse/glossary.yml` (`technical_columns`), `warehouse/schemas/glossary.schema.json`
- Modify: `tools/dwh/src/dwh/warehouse.py`, `codes.py`, `rules/naming.py`, `rules/metrics.py`, `yaml_rules.py`
  (Y02 uniqueness), `catalog.py`
- Modify: `tools/dwh/tests/test_rules_naming.py`, `test_rules_metrics.py`, `test_validate.py`, `test_catalog.py`,
  `fixtures/warehouse.py` (MINIMAL gets the closed list)
- Modify: `docs/standards/02-naming.md` (new STD-02-10, the Differences line), plus the examples in 01, 04, 05, 07,
  08, 09, 10, 12 and the remaining 11
- Modify: `skills/*/SKILL.md` where SQL names the column (then `make sync-agents`), `AGENTS.md` if it does
- Modify: `docs/en/specs/2026-11-04-kimball-dwh-design.md` (D10, §7 rows 02 and 08, §11)

**Interfaces:**
- Produces:
  - `glossary.yml` key `technical_columns`: a list of `{name, meaning, replaces?}`.
  - `Warehouse.technical_columns -> dict[str, dict]`.
  - Code `DWH-N07`: "a dw_ column is not on the closed technical-column list, or a listed column lacks the dw_
    prefix".
  - Rule STD-02-10.

- [ ] **Step 1: Write the failing tests.**
  - In `fixtures/warehouse.py` MINIMAL, add to `"glossary"`:

```python
"technical_columns": [
    {"name": "dw_dt", "meaning": "Partition date.", "replaces": ["dt"]},
    {"name": "dw_valid_from", "meaning": "Version start.", "replaces": ["valid_from", "dbt_valid_from"]},
    {"name": "dw_valid_to", "meaning": "Version end.", "replaces": ["valid_to", "dbt_valid_to"]},
],
```

  - Append to `test_rules_naming.py`:

```python
def test_n07_an_unlisted_dw_column_fails(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["columns"]["dw_loaded_at"] = {
        "name": "dw_loaded_at",
        "description": "X.",
        "meta": {},
    }
    assert lint(builder, prefix="DWH-N07") == ["DWH-N07"]


def test_n07_a_listed_column_without_the_prefix_fails_in_every_layer(lint):
    builder, ids = good_project()
    builder.node(ids["ods_orders"])["columns"]["dt"] = {"name": "dt", "description": "Old.", "meta": {}}
    builder.node(ids["hist"])["columns"]["valid_from"] = {
        "name": "valid_from",
        "description": "Old.",
        "meta": {},
    }
    assert lint(builder, prefix="DWH-N07") == ["DWH-N07", "DWH-N07"]


def test_n07_listed_columns_pass(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-N07") == []
```

  - In `test_validate.py`, add:
    - a glossary with `technical_columns: [{name: dt, meaning: x}]` gives `DWH-Y01` (the name must start with
      `dw_`);
    - a duplicated technical column name gives `DWH-Y02`.
  - In `test_catalog.py`, assert that the catalogue shows a "Technical columns" table containing `dw_dt`.

  Run `make dwh-test`. Expected: FAIL.

- [ ] **Step 2: Implement.**
  - In `glossary.schema.json`, add the optional property:

```json
"technical_columns": {
  "type": "array",
  "items": {
    "type": "object",
    "additionalProperties": false,
    "required": ["name", "meaning"],
    "properties": {
      "name": {"type": "string", "pattern": "^dw_[a-z0-9]+(_[a-z0-9]+)*$"},
      "meaning": {"type": "string", "minLength": 1},
      "replaces": {"type": "array", "items": {"type": "string", "pattern": "^[a-z0-9_]+$"}}
    }
  }
}
```

  - In `warehouse/glossary.yml`, append the closed list:

```yaml
# Technical (warehouse-managed) columns: the closed list of STD-02-10. Every other dw_ name is a lint error
# (DWH-N07), and so is a listed name without its prefix (`replaces`).
technical_columns:
  - {name: dw_dt, meaning: "Partition date: the Asia/Ho_Chi_Minh business day the row belongs to.", replaces: [dt]}
  - {name: dw_valid_from, meaning: "Start of an SCD4 _hist version (snapshot meta column).", replaces: [valid_from, dbt_valid_from]}
  - {name: dw_valid_to, meaning: "End of an SCD4 _hist version; null for the current one.", replaces: [valid_to, dbt_valid_to]}
  - {name: dw_is_current, meaning: "True for the current version of a _hist row.", replaces: [is_current]}
  - {name: dw_is_inferred, meaning: "True for an inferred DIM member created for a late-arriving fact.", replaces: [is_inferred]}
  - {name: dw_scd_id, meaning: "dbt snapshot version id (snapshot meta column).", replaces: [dbt_scd_id]}
  - {name: dw_snapshot_at, meaning: "When dbt snapshotted the version (snapshot meta column).", replaces: [dbt_updated_at]}
```

  - `warehouse.py`: add

    ```python
    @property
    def technical_columns(self) -> dict[str, dict]:
        return self.by_name("glossary", "technical_columns")
    ```

  - `yaml_rules.py` `UNIQUE_COLLECTIONS`: add `("glossary", "technical_columns", "name")`.
  - `codes.py`: add `"DWH-N07": "a dw_ column is not on the closed technical-column list, or a listed column lacks
    the dw_ prefix",`.
  - `rules/naming.py`:

```python
def n07_technical_columns(ctx: Context) -> Iterator[Finding]:
    listed = ctx.warehouse.technical_columns
    unprefixed = {old: name for name, spec in listed.items() for old in spec.get("replaces", [])}
    for node in ctx.project.nodes.values():
        for column in node.columns:
            if column.startswith("dw_") and column not in listed:
                yield Finding(
                    node.path, "DWH-N07", f"{node.name}.{column}: not a technical column in glossary.yml"
                )
            elif column in unprefixed:
                yield Finding(
                    node.path,
                    "DWH-N07",
                    f"{node.name}.{column}: technical columns are named {unprefixed[column]}",
                )
```

    Add it to `RULES`.
  - `rules/metrics.py` M03: `column.name in ctx.warehouse.technical_columns` replaces `== "dw_dt"`. The message
    becomes "grain columns, technical (dw_) columns, or metrics". Update the DWH-M03 meaning to match.
  - `catalog.py`: after the glossary table, render `table(["column", "meaning", "replaces"], ...)` under the heading
    `Technical columns`.
  - Snapshot columns: dbt adds `dw_scd_id` and the others without listing them in the snapshot `.yml`, so N07 sees
    only declared columns. Declare nothing new.
- [ ] **Step 3: Write STD-02-10 and the rulebook sweep.**
  - **STD-02-10 Technical columns start with `dw_` (MUST).**
    - Technical columns are those the warehouse manages, not the business: the partition day, SCD version bounds
      and flags, and the snapshot bookkeeping. They start with `dw_` and come from the closed list
      `technical_columns` in `warehouse/glossary.yml`.
    - A `dw_` column that is not listed fails, and so does a listed name without its prefix.
    - The run parameter stays `dt` (`conf.dt`, the dbt var, `get_dt()`).
    - Correct:

      ```sql
      select order_id, order_amt, date '{{ get_dt() }}' as dw_dt
      ```

    - Incorrect:

      ```sql
      select order_id, order_amt, date '{{ get_dt() }}' as dt   -- looks like a business column
      select order_id, current_timestamp as dw_loaded_at        -- dw_ but not on the closed list
      ```

    - Source: Spec §7. Checked by: DWH-N07.
  - The "Differences from Alibaba" line becomes "The partition column is `dw_dt` DATE, not Alibaba's `ds` STRING".
  - STD-02-08: add "Technical columns follow STD-02-10".
  - In every SQL and YAML example of 01, 04, 05, 07, 08, 09, 10 and 12, and in the STD-11 examples, rename the
    column `dt` → `dw_dt`, `valid_from`/`valid_to` → `dw_valid_from`/`dw_valid_to`, and the snapshot meta names. In
    prose, "`dt`" stays where it means the day being built ("one run builds one dt"); where it means the column,
    write `dw_dt`. Rename the rule titles: STD-08-01 "Partition by dw_dt", and STD-08-02 "dt comes from the data
    interval" stays.
  - Skills: `git grep -nw -E "dt|valid_from|valid_to" skills AGENTS.md evals/scenarios`. Rename only SQL and column
    references (for example dwh-debug's `dt = date 'YYYY-MM-DD'` → `dw_dt = date 'YYYY-MM-DD'`). Then
    `make sync-agents`.
  - Spec:
    - D10: "No business-segment prefix in table names; the partition column is `dw_dt` (DATE). Technical columns
      start with `dw_` (amended in plan 5)."
    - §7 row 02: add "technical columns `dw_*` from the closed list in `glossary.yml` (STD-02-10)".
    - §7 row 08: "Partition by `dw_dt`".
    - §11, append:

      ```text
      - **Plan 5:** D10 amended: the partition column is `dw_dt`; every technical column starts with `dw_` and
        comes from the closed list in `glossary.yml` (STD-02-10, DWH-N07). The run parameter stays `dt`.
      ```

- [ ] **Step 4: Prove the rule on the real project.**
  1. Temporarily add a column `dw_loaded_at` (description "x") to
     `dbt/warehouse/models/dws/trade/dws_trade_customer_1d/dws_trade_customer_1d.yml`.
  2. Run `make dwh-lint`. Expected: `DWH-N07` and `1 finding(s)`.
  3. Restore it with `git checkout -- dbt/warehouse/models/dws`.
- [ ] **Step 5: Run green.**

```bash
make lint && make sql-lint && make test-repo && make dwh-test && make validate && make dwh-lint \
  && make check-standards && make sync-agents-check && make catalog
```

Expected: all pass with 0 findings, and `site/index.html` holds the Technical columns table.

- [ ] **Step 6: Commit**

```bash
git add warehouse tools/dwh docs/standards skills .claude .cursor .github/copilot-instructions.md AGENTS.md \
  docs/en/specs/2026-11-04-kimball-dwh-design.md
git commit -m "feat(lint): technical columns come from a closed dw_ list (STD-02-10, DWH-N07)" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Backfill, step by step with `propagate=false`

**Files:**
- Modify: `skills/dwh-backfill/SKILL.md` (then `make sync-agents`)
- Modify: `docs/standards/11-airflow.md` (new STD-11-12)
- Check: `evals/scenarios/backfill-after-fix.md`

**Interfaces:**
- Consumes: Task 3 (`conf.propagate`). Produces the procedure Task 9's guides describe.

- [ ] **Step 1: Rewrite `skills/dwh-backfill/SKILL.md`.** Keep the front matter. Replace the `## Steps` section
  with the following, and keep `## Rules` with `11-airflow.md` added.

```text
## Steps

1. **Scope.** List the affected models (`dbt ls --select <model>+`), the DAGs that build them
   (`_common.pipelines.PIPELINES`), and the dt range. Estimate rows and Trino cost from the performance baseline.
2. **Dry run.** Build one dt on dev and compare its counts with prod.
3. **Run one day at a time, oldest first, one layer at a time.** Pause nothing. For each day D:
   1. Trigger the first DAG to rebuild with propagate off:
      `airflow dags trigger <dag> --conf '{"dt": "D", "propagate": false}'`. Its `publish_done` is skipped, so
      no `dwh_done` event is emitted and nothing downstream starts.
   2. Verify D for that layer (`dwh-verify` steps 3-4: row counts, reconciliation, grain).
   3. Trigger the next DAG the same way (`{"dt": "D", "propagate": false}`); repeat to the last layer.
   - No check needed between layers? One run with `{"dt": "D"}` (propagate defaults to true) chains the rest
     through the `dwh_done` Assets, each DAG building D.
   - From DWD upward, the first DAG is the domain DAG (`dbt_trade`). Never re-run past `di`/`df` ODS days (red
     flags).
   - **A run failed with `dt MULTIPLE:<day>,<day>`.** Runs of several days collapsed into one asset-triggered run,
     which builds only one dt. Trigger that DAG by hand once per listed day with `conf.dt`, oldest first.
   - **Cron-scheduled DAGs (`dbt_ods_*`):** `airflow backfill create --dag-id <dag> --from-date <d> --to-date <d>
     --max-active-runs 1` emits done events and chains downstream; pass `--run-backwards` never.
   - **Without Airflow:** `dbt build --select <model>+ --vars "{dt: <dt>}"` in a loop, oldest dt first.
4. **Rebuild windowed DWS to today.** `nd` and `td` DWS tables are rebuilt for every dt from the earliest
   changed dt to today, because a `td` value depends on every earlier day.
5. **Leave history alone.** Re-running snapshots does not rebuild `dim_*_hist`. Rebuild history only with an
   approved, written plan.
6. **Verify each dt** and record the range and the evidence in the PR. The SLA watchdog clears once every
   rebuilt day is present.
```

  Keep the red-flag rows on parallel runs, past ODS, `di` ODS, downstream, old event-DWD dts and `td`, and on
  picking one day of a collapsed run. Replace the two queue rows with:

```text
| "Let it chain, I'll check at the end" | A wrong layer then feeds every layer below it before you look. Use `"propagate": false` and verify each layer when the fix is not trivial. |
| "Clear the asset queue to stop the chain" | No need: `"propagate": false` stops it, and the queue holds nothing between nights. |
```

- [ ] **Step 2: Write STD-11-12 Backfill one layer at a time (MUST).**
  - One day at a time, oldest first. Each DAG runs with `{"dt": "D", "propagate": false}`, then its layer is
    verified, then the next DAG runs. Or one `{"dt": "D"}` run chains the rest when no check between layers is
    needed.
  - Correct:

    ```bash
    airflow dags trigger dbt_trade --conf '{"dt": "2026-11-01", "propagate": false}'
    ```

  - Incorrect:

    ```bash
    airflow dags trigger dbt_trade --conf '{"dt": "2026-11-01"}' & airflow dags trigger dbt_trade --conf '{"dt": "2026-11-02"}'
    ```

    with the comment "two days in parallel".
  - Source: Spec §4.
- [ ] **Step 3: Check the eval scenario.** Run `git grep -n -E "queue|queuedEvents|dbt_pub" evals/scenarios/backfill-after-fix.md`.
  Expected: no hit. The criteria (one dt at a time, no past ODS, oldest first through today, verify each dt) do not
  name the old procedure, so the scenario stays unchanged. Record this in the report. No eval runs.
- [ ] **Step 4: Run green.** Run `make sync-agents && make sync-agents-check && make check-standards && make lint`.
  Expected: all pass.
- [ ] **Step 5: Commit**

```bash
git add skills .claude .cursor docs/standards/11-airflow.md
git commit -m "docs(backfill): rebuild layer by layer with conf.propagate=false; drop the queue procedure" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Architecture page, minimal path, guides and README

**Files:**
- Create: `docs/en/architecture.md`, `docs/vi/kien-truc.md`
- Rewrite: `docs/vi/guides/data-model-development.md` (natively, not translated)
- Modify: `docs/en/guides/data-model-development.md` (glossary as a lookup table, §4–§6 for design §2–§5, and a new
  minimal path section)
- Modify: `README.md` (links)

**Interfaces:**
- Consumes: Tasks 2–8, as merged on the branch. Every name in the docs must exist in the code: check each with
  `git grep`.

- [ ] **Step 1: Write `docs/en/architecture.md`.** The first line is `[Tiếng Việt](../vi/kien-truc.md)`. Sections,
  in order:
  1. **Layers.** One mermaid `flowchart LR` (`sources --> ODS --> DIM & DWD`, `DWD --> DWS --> ADS`, `DIM --> DWD`,
     `BI --> DWD & DIM`). Then one paragraph per layer: its purpose, who reads it, and what it may read (STD-01;
     ADS may read DIM; an accumulating snapshot reads DWD).
  2. **Table types, one table per layer.** Columns: type | use when | name | partition | load | example.

     | Layer | Type | Use when | Name | Partition | Load | Example |
     |-------|------|----------|------|-----------|------|---------|
     | ODS | `di` | the source has a reliable watermark and no hard deletes | `ods_{source}_{table}_di` | `dw_dt` = the day the row changed | delete the partition, append the rows whose watermark falls in the day | `ods_shop_orders_di` |
     | ODS | `df` | small or reference tables; a watermark that can lag; hard deletes | `ods_{source}_{table}_df` | `dw_dt` = the snapshot day | delete the partition, append a full copy | `ods_shop_customers_df` |
     | DIM | current | one row per durable key, current attributes | `dim_{pub\|domain}_{dimension}` | none | full rebuild (table) | `dim_pub_customer` |
     | DIM | `_hist` (SCD4) | attributes whose history facts need | `dim_..._hist` | none | dbt snapshot, `strategy: timestamp` on the source `updated_at`; `dw_valid_from`, `dw_valid_to` | `dim_pub_customer_hist` |
     | DIM | date | the mandatory calendar | `dim_pub_date` | none | generated 2020–2030, full rebuild | `dim_pub_date` |
     | DWD | transaction / event | one row per business event on its event day | `dwd_{domain}_{process}_di` | `dw_dt` = the event day | append; the earliest ODS version per key (STD-05-08) | `dwd_trade_order_di` |
     | DWD | accumulating snapshot | one row per process instance, updated at milestones | `dwd_{domain}_{process}_di` | `dw_dt` = the start day | merge on the key; reads DWD only | `dwd_trade_order_lifecycle_di` |
     | DWD | periodic snapshot | the state at a regular interval (rule only, `05-facts.md`) | `dwd_{domain}_{process}_df` | `dw_dt` = the snapshot day | replace the partition | none yet |
     | DWS | `1d`, `nd`, `td`, `1w` | ≥ 2 consumers or performance evidence (STD-07-04) | `dws_{domain}_{grain}_{period}` | `dw_dt` | replace the partition; a window ending on the day | `dws_trade_customer_1d`, `_nd`, `_td` |
     | ADS | application table | one named application | `ads_{app}_{subject}[_{period}]` | `dw_dt` or none | replace the partition or rebuild | `ads_crm_customer_value` (full table) |

     Split it into one table per layer in the page. The rows above are the content.
  3. **Technical columns.** The closed list from `warehouse/glossary.yml`, as a table (column, meaning, replaces),
     plus the sentence "the run parameter stays `dt`; `dw_dt` names the stored column".
  4. **Orchestration.** One mermaid `flowchart LR`:
     - `cron 00:00 VN --> dbt_ods_shop -->|dwh_done/dbt_ods_shop {dt}| dbt_pub -->|dwh_done/dbt_pub {dt}| dbt_trade`;
     - `dwh_sla_watchdog -. hourly 02-12 VN, checks D .-> tables`;
     - `alerts.notify -->|dwh_alert or log| Slack`.

     Then a short list: the dt rule (design §2.2), `conf.propagate`, the deadline 06:00 and `meta.sla`, and alerts.
  5. **Minimal path.**
     - A small project starts with ODS, then DWD + DIM.
     - Add DWS only under STD-07-04, and ADS only for a named application.
     - The design gate still applies to new processes and conformed dimensions.
     - The same three DAG types and the watchdog apply from day one.
- [ ] **Step 2: Write `docs/vi/kien-truc.md` natively,** with the same sections and facts. Write each section in
  Vietnamese from the facts above. Do **not** translate the English page sentence by sentence. The first line is
  `[English](../en/architecture.md)`. The style rules:
  - Short sentences: one idea each, about 25 words at most.
  - Active voice, with the actor first. Avoid "được ... bởi" (a calque of the English passive).
  - Use the terms Vietnamese data teams use. Give the English term in parentheses on first use only.
  - No calques, no nominal chains ("việc thực hiện", "tiến hành"), and no overused "nó" for things.
  - Code names, table names, commands and rule IDs stay as they are, in backticks.

  Term table (use these):

  | English | Viết | Ghi chú |
  |---------|------|---------|
  | layer | tầng (layer) | "tầng ODS", "tầng DWD" |
  | business day | ngày dữ liệu (business day) | the day `dt` builds |
  | partition | partition | keep |
  | technical column | cột kỹ thuật | `dw_*` |
  | backfill | chạy bù (backfill) | |
  | rerun | chạy lại | |
  | schedule | lịch chạy | |
  | run | lượt chạy | |
  | event | sự kiện | Asset event: sự kiện Asset |
  | deadline | hạn chót (SLA) | "hạn 06:00" |
  | alert | cảnh báo | |
  | upstream / downstream DAG | DAG phía trước / phía sau | English in parentheses on first use |
  | fact table / dimension table | bảng fact / bảng dim | |
  | grain | grain (mức chi tiết) | |
  | snapshot | snapshot | keep |

  Translationese versus native:

  | Tránh (dịch máy) | Viết |
  |------------------|------|
  | Tài liệu này giải thích cách mà chúng ta thêm hoặc sửa dữ liệu trong kho dữ liệu. | Tài liệu này hướng dẫn thêm hoặc sửa dữ liệu trong kho. |
  | Bảng này được dựng bởi DAG `dbt_pub`. | DAG `dbt_pub` dựng bảng này. |
  | Nó cập nhật YAML thiết kế rồi đi thẳng vào code. | Loại này chỉ sửa YAML thiết kế rồi viết code luôn. |
  | Việc thực hiện kiểm tra dữ liệu được tiến hành sau mỗi layer. | Chạy xong tầng nào thì kiểm tra tầng đó. |
  | Khi tài liệu này và một file rule nói khác nhau, file rule đúng. | Tài liệu này mà vênh với file rule thì theo file rule. |
  | Một lần chạy được kích hoạt bởi một sự kiện Asset của DAG phía trước. | Sự kiện Asset của DAG phía trước kích hoạt lượt chạy. |

- [ ] **Step 3: Rewrite `docs/vi/guides/data-model-development.md` natively,** with the same style rules and term
  table. Keep the section structure of the English guide, so the two can be linked. Write fresh text from the
  content; do not edit the old translation. Cover design §2–§5 and §6:
  - the glossary as a lookup table pointing to `kien-truc.md`;
  - the daily run with `dwh_done` and the dt rule;
  - the SLA and alerts;
  - backfill with `propagate=false`;
  - `dw_` columns;
  - the minimal path.
- [ ] **Step 4: Update `docs/en/guides/data-model-development.md`.**
  - §2 Glossary: keep the terms as a lookup table, and point each layer or type row to the architecture page; do not
    repeat its explanations. Add rows for `dwh_done/<dag_id>`, `publish_done`, `conf.propagate`, `dwh_sla_watchdog`,
    `meta.sla`, `dwh_alert` and `dw_dt`.
  - §5 The daily run:
    - the DAG table (schedules `dwh_done/dbt_ods_shop` and `dwh_done/dbt_pub`; add `dwh_sla_watchdog`);
    - the sequence diagram (each DAG ends with `publish_done`, and the next starts on its event);
    - "How `dt` is chosen" (design §2.2; replace the `ASSET_DT_TEMPLATE` flowchart with the done-event one);
    - a new "SLA and alerts" subsection.
  - §6 Backfill: Task 8's procedure.
  - §4 and every SQL example: `dw_dt`.
  - A new "Minimal path" section after §4, with the Step 1 item 5 content.
  - The contents list and the FAQ entries that mention the queue or `ASSET_DT_TEMPLATE`.
- [ ] **Step 5: README.** Add the links `Architecture: [English](docs/en/architecture.md) ·
  [Tiếng Việt](docs/vi/kien-truc.md)` under the guide links. In "How it runs in production", add the done Assets,
  the watchdog, the `dwh_alert` connection, and the run with `dt` and the stored `dw_dt`.
- [ ] **Step 6: Validate the diagrams and links.**

```bash
mkdir -p /tmp/plan5-mmdc
for f in docs/en/architecture.md docs/vi/kien-truc.md docs/en/guides/data-model-development.md docs/vi/guides/data-model-development.md; do
  npx -y @mermaid-js/mermaid-cli@11.4.2 -i "$f" -o "/tmp/plan5-mmdc/$(basename "$f")" || echo "MERMAID FAIL $f"
done
git grep -n -E "ASSET_DT_TEMPLATE|queuedEvents|dags/dbt|__models.yml" -- docs/en/guides docs/vi docs/en/architecture.md README.md
```

Expected: no `MERMAID FAIL`, and the grep prints nothing.

- [ ] **Step 7: Run green and commit.** Run `make lint && make test-repo`. Expected: pass.

```bash
git add docs/en/architecture.md docs/vi/kien-truc.md docs/en/guides docs/vi/guides README.md
git commit -m "docs: add the architecture page and minimal path; rewrite the Vietnamese guide natively" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Controller gate:** the owner reviews the architecture page and the Vietnamese guide (design §8) before Task 10's
PR is marked ready.

---

### Task 10: Spec, live acceptance, the full chain and the verification record

**Files:**
- Modify: `docs/en/specs/2026-11-04-kimball-dwh-design.md` (§4, §7 row 11, §10, §11)
- Create: `docs/en/verification/<date>-plan5-verification.md`

- [ ] **Step 1: Spec.**
  - §4 diagram and Orchestration bullet: each pipeline DAG ends with `publish_done`, which emits
    `dwh_done/<dag_id>` with `{"dt": ...}`. Downstream DAGs schedule only on those. Cosmos model Assets are lineage
    only. Add the watchdog and alerts.
  - §4 Business day: asset-triggered runs take dt from the done event (design §2.2).
  - §7 row 11: done Assets, `publish_done`, `conf.propagate`, SLA and `alerts.notify`; DWH-L06.
  - §10: replace the "Asset-triggered runs and `dt`" item with the done-event rule and the Task 1 measurements. Keep
    the per-task target path item.
  - §11: append

    ```text
    - **Plan 5:** one `dwh_done/<dag_id>` Asset per pipeline DAG carrying `dt`; `conf.propagate` for layer-by-layer
      backfill; SLA watchdog (06:00 default, `meta.sla`) and `alerts.notify` (`dwh_alert`); DWH-L06; architecture
      page and native Vietnamese docs.
    ```

- [ ] **Step 2: Live-scheduler acceptance (design §8).** Use the repository's DAGs, on a fresh stack with a Postgres
  metadata DB and `LocalExecutor`. Start as in Task 1 Step 2, with container name `dwh-live`, database
  `airflow_live`, and no `DAGS_FOLDER` override. Unpause `dbt_ods_shop`, `dbt_pub`, `dbt_trade` and
  `dwh_sla_watchdog`.
  - **A. The chain.** `airflow backfill create --dag-id dbt_ods_shop --from-date 2026-11-02T00:00:00+07:00 --to-date
    2026-11-02T00:00:00+07:00 --max-active-runs 1`.
    - Expected: `dbt_pub`, then `dbt_trade`, each once, both rendering `dt: '2026-11-02'`.
    - Expected: three `asset_event` rows for `dwh_done/*`, each with `{"dt": "2026-11-02"}`.
    - Expected: `dbt_trade`'s first task starts after `dbt_pub`'s `publish_done` ended.
  - **B. A manual `dbt_pub`.** `airflow dags trigger dbt_pub --conf '{"dt": "2026-11-01"}'`.
    - Expected: one `dbt_trade` run starts at once with `dt: '2026-11-01'`.
    - Expected: afterwards `select * from asset_dag_run_queue` is empty.
  - **C. `propagate=false`.** `airflow dags trigger dbt_pub --conf '{"dt": "2026-11-01", "propagate": false}'`.
    - Expected: `publish_done` is skipped, there is no new `dwh_done/dbt_pub` event, and no `dbt_trade` run follows
      within 3 minutes.
  - **D. The watchdog.**
    1. Delete the partition for one day in a throwaway way: run the chain for `2026-11-02` only, as in A, then
       trigger `dwh_sla_watchdog` with logical date `2026-11-04T07:00:00+07:00`, so `D` = 2026-11-03.
       - Expected: `check_sla` fails, and its log holds one ERROR line `dwh alert (no dwh_alert connection): SLA
         missed for business day 2026-11-03: N model(s)`, listing each model with layer, DAG and deadline.
    2. Run the A backfill for 2026-11-03, then trigger the watchdog again for the same logical date.
       - Expected: success, `SLA met for business day 2026-11-03`.

  Tear down with `docker rm -f dwh-live && make dev-down`.
- [ ] **Step 3: The full chain on a fresh stack**

```bash
bash -c 'set -o pipefail; make dev-down && make lint && make sql-lint && make test-repo && make dwh-test \
  && make validate && make dwh-lint && make check-standards && make sync-agents-check && make pre-commit \
  && make catalog && make image && make dev-up && make smoke && make test-dags && make test-integration \
  && make e2e; echo EXIT=$?' 2>&1 | tee /tmp/plan5-final-chain.log | tail -40
```

Expected: `EXIT=0`.

- [ ] **Step 4: Write the verification record** `docs/en/verification/<date>-plan5-verification.md`, in the format
  of the plan 4 record:
  - the head commit, and each chain step with its result;
  - **V1:** the Task 1 spike results (a link to the spike note) and the Step 2 acceptance A–D, with run ids, the
    `asset_event` rows and log lines;
  - **V2:** the integration fixture values unchanged. Copy the plan 4 V1 table and add the column names now used
    (`dw_dt`, `dw_valid_from`).
  - **V3:** DWH-L06 and DWH-N07 caught their seeded violations (Task 4 Step 3, Task 7b Step 4), and dwh-lint reports
    0 findings on the real project;
  - **V4:** the e2e output (the done events);
  - **Known limits:**
    - the read-only Trino user is enforced by deployment, not by this repo;
    - a model added after the image build is watched from the next image;
    - M3 as measured;
    - no eval run (out of scope, design §7).

- [ ] **Step 5: Commit**

```bash
git add docs/en/specs/2026-11-04-kimball-dwh-design.md docs/en/verification
git commit -m "docs: record plan 5 orchestration, SLA and dw_ columns, with the live acceptance" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

After the plan: the controller opens the PR. CI must be green, and the merge waits for the owner's "merge đi".

---

## Self-review: design coverage

| Design | Covered by |
|--------|------------|
| §1 F1 no SLA | Tasks 5, 6 |
| §1 F2 queued DIM events | Task 3 (single `dwh_done/dbt_pub` schedule), Task 10 acceptance B |
| §1 F3 reverse-engineered dt | Task 3 (`DONE_DT_TEMPLATE`, producer interval lookup removed) |
| §1 F4 backfill cannot stop | Task 3 (`conf.propagate`), Task 8 |
| §1 F5 technical columns | Tasks 7a, 7b |
| §1 F6 docs | Task 9 |
| §2.1 one done Asset per DAG, schedules, AND rule, model Assets lineage only, `all_success` | Task 3 (code, tests, STD-11-04, STD-11-09), Task 4 (lint) |
| §2.2 dt rule | Task 3 (template and tests), STD-11-03 |
| §2.3 why it fixes F2–F4 | Task 10 acceptance B and C |
| §2.4 risks and fallback | Task 1 (M1–M3, STOP rules) |
| §3.1 watchdog: cron, D, deadline, `meta.sla`, allow_empty, `$snapshots`, one alert, hourly repeat, manifest in image, read-only | Task 6 (`_hist` clause and read-only user as recorded decisions), Task 10 acceptance D |
| §3.2 alert callback | Task 5 |
| §3.3 rules and lint | Tasks 3, 4, 5, 6 (STD-11-04, -09, -10, -11; DWH-L06) |
| §4 backfill | Task 8 (skill, STD-11-12; eval scenario checked) |
| §5 mapping, run parameter `dt`, STD-02-xx, DWH-N code, D10, migration by rebuild | Task 7a (rename on a fresh stack), Task 7b (STD-02-10, DWH-N07, closed list, D10, §11) |
| §6 architecture page, minimal path, glossary as lookup, native Vietnamese, EN guide §2–§5 | Task 9 |
| §7 out of scope (folder layout, evals) | Superseded for the folder layout by the owner's decisions of 2026-11-05 (Tasks 2a, 2b). A streaming project stays out. No eval runs (Task 8 Step 3). |
| §8 acceptance | Task 10 (live A–D, full chain, fixture values, owner review gate in Task 9) |
| Owner input: dbt project at the root | Task 2a (`dbt/warehouse/`, project-name plumbing, per-project packages and profiles; spec §3 and §11 amended with why plan 1 was wrong and the shared-macro note) |
| Owner input: one folder per model | Task 2b (snapshot location measured, scaffold, DWH-L07, STD-09-08, STD-09-09 for migration scripts) |

Gaps closed while writing:
- **The `_hist` SLA rule.** Iceberg likely commits nothing for an unchanged snapshot, so `_hist` also passes on its
  DAG's done event. This is measured in M5 and reported to the owner.
- **The watchdog reads done events through `inlet_events`.** This is measured in M4, with a STOP rule.
- **Schemas come from `layer_schema`,** not from the manifest, so one baked manifest serves every target.
- **`is_current` and `is_inferred` are listed but not produced.** No model has them today.
- **`model_asset` is removed as dead code.** DWH-L06 still rejects it if it comes back.
