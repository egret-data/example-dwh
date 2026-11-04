# Plan 4 — the `trade` reference domain and automated skill evals

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one complete domain, `trade` on the `shop` source, from ODS to ADS, by following the repository's own
skills, rulebook and `dwh scaffold`. The domain then doubles as the fixture for automated skill evals. This also
closes the plan 3 carry-forwards.

**Architecture:**
- **Design first.** The design is written and approved first: a design record plus `warehouse/*.yml` (Task 3), with
  a human design gate before any SQL.
- **Models.** Models are scaffolded, then completed. Integration tests on the local stack assert exact numbers from a
  fixture built to exercise the hard cases:
  - late rows;
  - a point-in-time city change;
  - special members;
  - reconciliation.
- **Orchestration.** DAGs follow STD-11-08, with Asset scheduling and a maintenance DAG.
- **Evals.** They run on Claude Code only (user decision) and gain:
  - a no-skills baseline on the same commit;
  - an LLM judge;
  - a run-all summary.

**Tech Stack:**
- Airflow 3.3.2 (Cosmos 1.16.0);
- dbt-core 1.11.16 and dbt-trino 1.11.0;
- Trino 483 with Iceberg;
- Python 3.12 and uv; pytest 9.2.0; sqlfluff 4.5.0;
- Claude Code CLI (`claude -p`).

**Spec:** `docs/en/specs/2026-11-04-kimball-dwh-design.md` (§8.2, §9 item 4, §10, §11). Rulebook: `docs/standards/`.

## Global Constraints

- **Branch.** `feat/plan4-trade-domain` off `main` (at or after `09acc21`). Merging needs `lint`, `stack` and
  `design-gate`. This PR adds a domain, processes, dimensions and atomic metrics, so it needs the
  `design-approved` label and a link to `docs/designs/2026-11-04-trade-reference-domain.md`.
- **Follow the repository's own process.** Read `AGENTS.md` and the matching `skills/*/SKILL.md` before each
  task's work: dwh-requirement, dwh-model-design, dwh-implement, dwh-verify. New models start from
  `dwh scaffold ... --write`. Every rule in `docs/standards/` applies; cite rule IDs in the report when a choice
  follows one.
- **Business day.** `dt` is the Asia/Ho_Chi_Minh business day; never `{{ ds }}`.
- **dbt YAML.** Generic test arguments go under `arguments:`, and `meta` and `tags` under `config:`.
- **Special members.** `'-1'` and `'-2'` rows carry the text labels `Unknown` and `Not applicable` on text attributes
  (user decision). Natural keys, numbers and dates stay null.
- **SCD4 history.**
  - `dim_*_hist` is a dbt snapshot of `dim_*` with `strategy: timestamp` on the dimension's source `updated_at`
    (measured 2026-11-04: `valid_from` is the source change time).
  - The point-in-time join treats each key's earliest version as valid from `1900-01-01`.
- **Facts from updated-in-place sources** follow STD-05-08 (user decision, plan 3):
  - an event DWD keyed by the event day, keeping the earliest ODS version per key;
  - status and payment milestones go to an accumulating-snapshot DWD, merged by key.
- **Evals run on Claude Code only** (user decision, plan 4). The runner keeps a `--tool` seam for later tools, but
  only `claude` is implemented.
- **Lint and tests must stay green after every task:**
  - `make dwh-lint` and `make sql-lint` report 0 findings, `make lint` is clean;
  - `make check-standards`, `make sync-agents-check`, `make dwh-test` and `make test-repo` pass.
- **Destructive operations.**
  - Integration tests drop only `itest*` schemas, and restore any source row they change (in `finally`).
  - Never `rm`/`cp` (aliased interactive); use git or Python.
- **Commits.** Code, comments, docs and commit messages are in English. Commits follow Conventional Commits and end
  with:

  ```text
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```

## The fixture and what it proves

The source `shop` (Postgres, naive timestamps in Vietnam local time) after Task 2:

| table | rows (key: values) |
|-------|--------------------|
| `shops` | `1: An Shop, Hanoi`; `2: Binh Shop, Ho Chi Minh` (created and updated 2026-10-01 08:00) |
| `customers` | `101: An, Hanoi` (2026-10-01 08:00); `102: Binh, Da Nang` (created and updated 2026-10-05 09:00); `103: Chi, Da Nang` (2026-10-09 10:00) |
| `orders` | see below |
| `payments` | `p1`: order 1, 120000, card, paid 11-01 09:30; `p4`: order 2, 80000, cash, paid 11-02 08:00; `p2`: order 3, 250000, wallet, paid 11-02 14:05; `p3`: order 5, 99000, card, paid 11-03 10:01. Each payment's `updated_at` = `paid_at`, plus its order's customer and shop. |

`orders`: the same six rows as before, plus `shop_id` and `channel`. The `updated_at` days stay as before (11-01: 1,
11-02: 2, 11-03: 3), so the plan 1–3 ODS tests are unchanged.

| order | customer | shop | channel | status | amount | created_at | updated_at |
|-------|----------|------|---------|--------|--------|------------|------------|
| 1 | 101 | 1 | app | paid | 120000 | 11-01 09:00 | 11-01 09:30 |
| 2 | 102 | 1 | web | shipped | 80000 | 11-01 11:00 | 11-02 08:00 |
| 3 | 103 | 2 | app | paid | 250000 | 11-02 14:00 | 11-02 14:05 |
| 4 | 101 | 2 | web | cancelled | 40000 | 11-02 20:00 | 11-03 07:00 |
| 5 | 102 | 1 | app | paid | 99000 | 11-03 10:00 | 11-03 10:01 |
| 6 | 103 | 2 | app | created | 15000 | 11-03 23:00 | 11-03 23:59:59 |

The integration test (Tasks 4–6) runs the pipeline day by day, exactly as the DAGs would:
1. For each day, ODS, then `domain:pub`, then `domain:trade` + `app:crm`.
2. Between day 1 and day 2 it changes customer 102's city to `Ho Chi Minh` (`updated_at` 2026-11-02 10:00), then
   restores it at the end.

What it proves, with exact expected values:
- **Late rows (STD-05-08).** Orders 2 and 4 first appear in the ODS partition after their event day. After the
  sequential run, `dwd_trade_order_di` holds 1 / 1 / 2 orders on 11-01 / 11-02 / 11-03. After re-running 11-01 and
  11-02 (dwh-backfill), it holds 2 / 2 / 2.
- **Point in time (STD-05-05).** Order 2 (11-01) carries `customer_city = 'Da Nang'`; order 5 (11-03) carries
  `'Ho Chi Minh'`. `dim_pub_customer_hist` has two versions for 102, valid from 2026-10-05 09:00 and 2026-11-02
  10:00 (Vietnam time).
- **Special members.** Every DIM has `'-1' Unknown` and `'-2' Not applicable`. Unpaid orders 4 and 6 have
  `pay_date_key = '-2'` in the lifecycle DWD.
- **DWS 1d** (after the re-runs):

  | dt | customer | `order_amt_sum_1d` | `order_cnt_1d` | `app_order_amt_sum_1d` |
  |----|----------|--------------------|----------------|------------------------|
  | 11-01 | 101 | 120000 | 1 | 120000 |
  | 11-01 | 102 | 80000 | 1 | null |
  | 11-02 | 101 | 40000 | 1 | null |
  | 11-02 | 103 | 250000 | 1 | 250000 |
  | 11-03 | 102 | 99000 | 1 | 99000 |
  | 11-03 | 103 | 15000 | 1 | 15000 |

- **DWS nd and td on 11-03:** `order_amt_sum_30d` and `order_amt_sum_td` are 101: 160000, 102: 179000, 103: 265000.
  `order_cnt_td` is 2 each.
- **ADS on 11-03:** `avg_order_amt_td` is 101: 80000, 102: 89500, 103: 132500.
- **Reconciliation (STD-12-03).**
  - The sum of `order_amt` in DWD per dt equals the sum of the DWS 1d per dt (11-01: 200000, 11-02: 290000,
    11-03: 114000).
  - The sum of `pay_amt` in DWD equals the source payments total, 549000.

Out of scope:
- a second AI tool (user decision);
- production deployment of the DAGs (the Helm values exist since plan 1);
- BI dashboards.

---

### Task 1: Scaffold and rulebook updates for plan 4

**Files:**
- Modify: `tools/dwh/src/dwh/scaffold.py`, `tools/dwh/tests/test_scaffold.py`
- Modify: `docs/standards/04-dimensions.md` (STD-04-03, STD-04-06), `05-facts.md` (STD-05-05), `08-iceberg-incremental.md` (STD-08-07)
- Modify: `docs/en/specs/2026-11-04-kimball-dwh-design.md` (§7 row 04)

**Interfaces:**
- Consumes: the plan 3 scaffold. It already provides:
  - event DWDs (`--event-at`), with `versions` CTE and `version_rank = 1`;
  - special-member CTEs, domain tags, `case when ... is null then '-1'` keys.
- Produces (scaffold behaviour Tasks 4–6 rely on):
  1. **Special-member labels.** Text attributes (`data_type` varchar) of the `'-1'` row are `'Unknown'`, of the
     `'-2'` row `'Not applicable'`. Natural keys and other types stay null. The `updated_at` of special rows is
     `timestamp '1900-01-01 00:00:00 UTC'`.
  2. **SCD4 DIMs carry `updated_at`.** The value is the source's change time, typed `timestamp(6) with time zone`.
     It is selected from the upstream and listed in the `.yml`. The `_hist` snapshot config becomes:

     ```yaml
     strategy: timestamp
     updated_at: updated_at
     ```

     It keeps `unique_key: [<dim>_key]` and the `valid_from`/`valid_to` renames. `check_cols` is removed.
  3. **Date role derived from the event column.** In an event DWD, when the process's bus-matrix row has exactly one
     cell whose dimension is `date`, that role's key is computed from the event column:

     ```sql
     case when <event_at> is null then '-1'
          else {{ dbt_utils.generate_surrogate_key(["cast(<event_at> at time zone 'Asia/Ho_Chi_Minh' as date)"]) }}
     end as <role>_key
     ```

     The source column is not hashed. With zero date cells, or more than one, keep the current behaviour (hash the role
     column).

- [ ] **Step 1: Write the failing tests** in `tools/dwh/tests/test_scaffold.py`. Use the fixture warehouse MINIMAL:
  `customer` is scd4 with historical `city`; the `order` bus row has the single date role `order_date`.

```python
def test_special_members_carry_text_labels(wh):
    sql = scaffold("dim_pub_customer", wh, project_dir="", upstream=["ods_shop_customers_df"])[
        "models/dim/pub/dim_pub_customer.sql"
    ]
    assert "'Unknown'" in sql
    assert "'Not applicable'" in sql
    assert "timestamp '1900-01-01 00:00:00 UTC'" in sql


def test_scd4_dimension_carries_updated_at_and_snapshots_by_timestamp(wh):
    files = scaffold("dim_pub_customer", wh, project_dir="", upstream=["ods_shop_customers_df"])

    model = model_of(files["models/dim/pub/dim_pub_customer.yml"])
    assert columns(model)["updated_at"]["data_type"] == "timestamp(6) with time zone"
    snapshot = yaml.safe_load(files["snapshots/dim_pub_customer_hist.yml"])["snapshots"][0]
    assert snapshot["config"]["strategy"] == "timestamp"
    assert snapshot["config"]["updated_at"] == "updated_at"
    assert "check_cols" not in snapshot["config"]


def test_event_dwd_derives_its_single_date_role_from_the_event_column(wh):
    sql = scaffold(
        "dwd_trade_order_di",
        wh,
        project_dir="",
        grain=["order_id"],
        upstream=["ods_shop_orders_di"],
        event_at="created_at",
    )["models/dwd/trade/dwd_trade_order_di.sql"]

    assert "cast(created_at at time zone 'Asia/Ho_Chi_Minh' as date)" in sql
    assert "['order_date']" not in sql
```

Adapt the call signature to the scaffold's real parameter for `--event-at`; read `scaffold.py` first. The scd1
dimension (`dim_trade_shop`) must not get an `updated_at` column or a snapshot: add an assertion to the existing scd1
test.

Run `make dwh-test`. Expected: FAIL on the three new tests.

- [ ] **Step 2: Implement** the three behaviours in `scaffold.py`. Keep all existing tests green, and keep the
  generated SQL sqlfluff-clean: `make test-repo` runs `tests/repo/test_scaffold_sqlfluff.py`.

- [ ] **Step 3: Update the rulebook and the spec** (keep IDs, levels, Source and Checked-by lines):
  - **STD-04-03.** `_hist` is a snapshot with `strategy: timestamp` on the dimension's source `updated_at`, so
    `valid_from` is the time the source changed. A `check` strategy would stamp load time and break point-in-time
    joins on backfills. Update the Correct example to the new snapshot config.
  - **STD-04-06.** Text attributes of `'-1'` and `'-2'` are `Unknown` and `Not applicable`. Natural keys, numbers and
    dates are null.
  - **STD-05-05.**
    - Replace the "events earlier than the first snapshot" sentence: in the history CTE, each key's earliest version
      gets `valid_from = timestamp '1900-01-01 00:00:00 UTC'`, so earlier events take the first known version.
    - Update the Correct example with the CTE:

      ```sql
      case when valid_from = min(valid_from) over (partition by customer_key)
           then timestamp '1900-01-01 00:00:00 UTC'
           else valid_from
      end as valid_from
      ```

      and `coalesce(h.city, 'Unknown')`.
  - **STD-08-07.** Add: a source whose watermark can lag is loaded `df` (or `full_compare`), because a `di` window
    cannot see rows that arrive with an old `updated_at`.
  - **Spec §7 row `04-dimensions.md`.** Say "snapshot with `strategy: timestamp` on the source `updated_at`", and
    mention the special-member labels.

- [ ] **Step 4: Run and commit**

Run: `make dwh-test && make test-repo && make check-standards && make lint`
Expected: all pass.

```bash
git add tools/dwh docs/standards docs/en/specs
git commit -m "feat(scaffold): label special members, snapshot SCD4 by source updated_at, derive event date roles" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Source fixture and ODS for `shops`, `payments` and the new order columns

**Files:**
- Modify: `dev/postgres/init/01-init.sql`
- Modify: `dags/dbt/models/ods/shop/_shop__sources.yml`, `ods_shop_orders_di.sql`, `_shop__models.yml`
- Create: `dags/dbt/models/ods/shop/ods_shop_shops_df.sql`, `ods_shop_payments_di.sql`, plus their `.yml` entries
- Modify: `tests/integration/test_ods_shop.py`

**Interfaces:**
- Produces:
  - ODS tables `ods_shop_orders_di` (adds `shop_id` bigint and `channel` varchar), `ods_shop_shops_df` and
    `ods_shop_payments_di`;
  - source meta for `shops` (df, delete_handling none) and `payments` (di, watermark `updated_at`,
    delete_handling none, reason "payments are insert-only").

- [ ] **Step 1: Change the fixture** in `dev/postgres/init/01-init.sql`:
  - Create `public.shops` before `orders`: `shop_id BIGINT PRIMARY KEY, shop_name TEXT NOT NULL, city TEXT,
    created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL`, holding the two rows from the fixture table.
  - In `customers`, change 102 to `('Binh', 'Da Nang', '2026-10-05 09:00:00', '2026-10-05 09:00:00')`.
  - In `orders`, add `shop_id BIGINT NOT NULL REFERENCES public.shops (shop_id)` and `channel TEXT NOT NULL`.
    The rows are the fixture table above; keep the `updated_at` comment line.
  - Create `public.payments`:

    ```sql
    CREATE TABLE public.payments (
        payment_id  TEXT PRIMARY KEY,
        order_id    BIGINT NOT NULL REFERENCES public.orders (order_id),
        customer_id BIGINT NOT NULL REFERENCES public.customers (customer_id),
        shop_id     BIGINT NOT NULL REFERENCES public.shops (shop_id),
        amount      NUMERIC(18, 2) NOT NULL,
        method      TEXT NOT NULL,
        paid_at     TIMESTAMP NOT NULL,
        updated_at  TIMESTAMP NOT NULL
    );
    ```

    It holds the four payments from the fixture table, with `updated_at = paid_at`.

- [ ] **Step 2: Write the failing ODS tests.** Append to `tests/integration/test_ods_shop.py` (after
  `test_next_dt_adds_partition_and_keeps_previous`):

```python
def test_shops_and_payments_load():
    build("2026-11-02")

    assert count("ods_shop_shops_df", "2026-11-02") == 2
    assert count("ods_shop_payments_di", "2026-11-02") == 2  # p4 (08:00) and p2 (14:05)
    assert query(f"SELECT sum(amount) FROM {ODS}.ods_shop_payments_di WHERE dt = DATE '2026-11-02'") == [
        (Decimal("330000.00"),)
    ]


def test_orders_carry_shop_and_channel():
    rows = query(
        f"SELECT order_id, shop_id, channel FROM {ODS}.ods_shop_orders_di WHERE dt = DATE '2026-11-02' ORDER BY 1"
    )
    assert rows == [(2, 1, "web"), (3, 2, "app")]
```

Add `from decimal import Decimal`. Run on a fresh stack, because the fixture lives in the Postgres init:

```bash
make dev-down && make dev-up && make test-integration
```

Expected: FAIL, since the tables and columns do not exist in ODS.

- [ ] **Step 3: Implement.**
  - Scaffold the two new ODS models:
    - `uv run --locked --project tools/dwh dwh scaffold ods_shop_shops_df --grain shop_id --write`
    - `... ods_shop_payments_di --grain payment_id --write`
  - Complete their SQL to the rules: explicit casts, and `source_ts()` for `created_at`, `updated_at` and `paid_at`.
  - Put the `.yml` content into `_shop__models.yml`, so there is one file per source folder as today, and delete the
    generated per-model `.yml` files with git.
  - Add `shop_id` and `channel` to `ods_shop_orders_di`.
  - Add the source tables with `config.meta`.
  - Fill every description.

- [ ] **Step 4: Run green**

Run: `make dev-down && make dev-up && make test-integration && make e2e && make dwh-lint && make sql-lint`
Expected:
- integration tests pass, including the plan 1–3 ODS tests with their unchanged counts;
- e2e prints `e2e OK`;
- lint is clean.

- [ ] **Step 5: Commit**

```bash
git add dev/postgres/init dags/dbt/models/ods tests/integration/test_ods_shop.py
git commit -m "feat(ods): load shop shops and payments, add shop and channel to orders" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Design record and warehouse YAML for `trade` (design gate)

**Files:**
- Create: `docs/designs/2026-11-04-trade-reference-domain.md`
- Modify: `warehouse/domains.yml`, `processes.yml`, `dimensions.yml`, `bus_matrix.yml`, `metrics.yml`, `modifiers.yml`, `glossary.yml`

**Interfaces:**
- Produces: the design every later task builds. Follow `skills/dwh-requirement` and `skills/dwh-model-design`
  exactly.

- [ ] **Step 1: Write the design record.** Use the sections required by dwh-requirement: Request, Business process,
  Grain, Dimensions (reused / new), Metrics (reused / new), Sources, Consumers, Open questions (empty). Content:
  - **Request:** a reference domain for the team and for skill evals. Consumers:
    - BI (finance dashboard) reads DWD + DIM;
    - the CRM customer-value export reads the ADS.
  - **Processes:**
    - `order` (transaction): one row per order, on the Asia/Ho_Chi_Minh day it was placed;
    - `payment` (transaction): one row per payment, on the day it was captured;
    - `order_lifecycle` (accumulating snapshot): one row per order, updated when it is paid.
  - **Dimensions:**
    - `date` (pub, scd1, reused);
    - `customer` (pub, scd4; natural key `customer_id`; `customer_name` current, `city` historical);
    - `shop` (trade, scd1; natural key `shop_id`; `shop_name` and `city` current).
  - **Metrics.** Atomic:
    - `order_amt` (order, sum, additive);
    - `order` (order, count, additive);
    - `pay_amt` (payment, sum, additive).

    Derived, all with grain `customer`:
    - `order_amt_sum_1d`;
    - `order_cnt_1d`;
    - `app_order_amt_sum_1d` (modifier `app`);
    - `order_amt_sum_30d` (nd, days 30);
    - `order_amt_sum_td`;
    - `order_cnt_td`.

    Calculated: `avg_order_amt_td = order_amt_sum_td / nullif(order_cnt_td, 0)`. Modifier type `channel` (trade);
    modifier `app` (`channel = 'app'`, process `order`).
  - **Sources:** `shop.orders` (di, watermark `updated_at`), `shop.payments` (di, insert-only),
    `shop.customers` (df), `shop.shops` (df). All are in Vietnam local time.
  - **Tables:** list every model from Tasks 4–6 with its layer, name, grain, keys and upstream.
  - **DWS justification (STD-07-04):** two consumers, the ADS and the finance dashboard.

- [ ] **Step 2: Update the warehouse YAML** to the design. Reuse `date`. Glossary: add every new word the names use,
  for example:
  - `trade`, `order`, `payment`, `pay`, `shop`, `customer`, `city`;
  - `channel`, `app`, `web`, `status`, `lifecycle`;
  - `created`, `paid`, `updated`, `method`;
  - `crm`, `value`.

  Run `make validate` until it reports `0 finding(s)`.

- [ ] **Step 3: Dry-run every planned name.** Run `dwh scaffold <name> ...` without `--write` for every model in
  Tasks 4–6 that the scaffold supports. A design error must show up now. Record the commands and their exit codes.

- [ ] **Step 4: Commit and STOP**

```bash
git add docs/designs warehouse
git commit -m "docs(designs): design the trade reference domain and declare it in warehouse YAML" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Controller gate (dwh-model-design step 5):** the controller shows the design record to the user and waits for
approval before Task 4 starts. The `design-approved` label is added to the PR when it is opened.

---

### Task 4: DIM layer — `dim_pub_date`, `dim_pub_customer` (+ `_hist`), `dim_trade_shop`

**Files:**
- Create: `dags/dbt/models/dim/pub/dim_pub_date.sql` and `dim_pub_customer.sql`, with `_pub__models.yml`
- Create: `dags/dbt/snapshots/dim_pub_customer_hist.yml`
- Create: `dags/dbt/models/dim/trade/dim_trade_shop.sql`, with `_trade__models.yml`
- Create: `tests/integration/test_trade_domain.py`

**Interfaces:**
- Consumes: Task 1 scaffold behaviour, Task 2 ODS and Task 3 design.
- Produces:
  - `dim_pub_date`, with key `date_key` = surrogate of `cal_date`, plus `'-1'`/`'-2'`;
  - `dim_pub_customer` (with `updated_at`) and `dim_pub_customer_hist` (timestamp snapshot);
  - `dim_trade_shop`.

  All three carry their domain tag (`domain:pub` or `domain:trade`).
- Produces for Tasks 5–6: the integration test module with the day-by-day pipeline fixture.

- [ ] **Step 1: Write the failing integration test.** Create `tests/integration/test_trade_domain.py`:

```python
"""The trade reference domain, run day by day as the DAGs would (plan 4). Tests share state, in file order."""

from datetime import date, datetime, timezone

import pytest
from helpers import CATALOG, MAIN_PROJECT, drop_schemas, query, run_dbt

SCHEMA = "itest_trade"
DAYS = ["2026-11-01", "2026-11-02", "2026-11-03"]
DOWNSTREAM = ("tag:domain:trade", "tag:app:crm")


def build(dt: str, *selectors: str) -> str:
    return run_dbt(MAIN_PROJECT, ["build", "--select", *selectors, "--vars", f"{{dt: '{dt}'}}"], SCHEMA)


def run_day(dt: str) -> None:
    build(dt, "tag:ods_shop")
    build(dt, "tag:domain:pub")
    build(dt, *DOWNSTREAM)


def table(layer: str, name: str) -> str:
    return f'{CATALOG}."{SCHEMA}_{layer}".{name}'


@pytest.fixture(scope="module", autouse=True)
def pipeline():
    drop_schemas(SCHEMA)
    try:
        run_day(DAYS[0])
        # Customer 102 moves on 2026-11-02 10:00 (Vietnam time): the SCD4 history must record it.
        query(
            "UPDATE shop.public.customers SET city = 'Ho Chi Minh', "
            "updated_at = TIMESTAMP '2026-11-02 10:00:00' WHERE customer_id = 102"
        )
        run_day(DAYS[1])
        run_day(DAYS[2])
        yield
    finally:
        query(
            "UPDATE shop.public.customers SET city = 'Da Nang', "
            "updated_at = TIMESTAMP '2026-10-05 09:00:00' WHERE customer_id = 102"
        )
        drop_schemas(SCHEMA)


def test_date_dimension_covers_the_calendar_and_special_members():
    rows = query(
        f"SELECT count(*), min(cal_date), max(cal_date) FROM {table('dim', 'dim_pub_date')} WHERE date_key NOT IN ('-1', '-2')"
    )
    assert rows == [(4018, date(2020, 1, 1), date(2030, 12, 31))]
    assert query(
        f"SELECT date_key FROM {table('dim', 'dim_pub_date')} WHERE cal_date IS NULL ORDER BY 1"
    ) == [("-1",), ("-2",)]


def test_customer_dimension_has_current_rows_and_labelled_special_members():
    rows = query(
        f"SELECT customer_key, customer_id, customer_name, city FROM {table('dim', 'dim_pub_customer')} ORDER BY customer_id NULLS FIRST, customer_key"
    )
    assert [r[1:] for r in rows if r[1] is not None] == [
        (101, "An", "Hanoi"),
        (102, "Binh", "Ho Chi Minh"),
        (103, "Chi", "Da Nang"),
    ]
    assert sorted((r[0], r[2], r[3]) for r in rows if r[1] is None) == [
        ("-1", "Unknown", "Unknown"),
        ("-2", "Not applicable", "Not applicable"),
    ]


def test_customer_history_records_the_move_at_the_source_change_time():
    rows = query(
        f"SELECT h.city, h.valid_from, h.valid_to FROM {table('dim', 'dim_pub_customer_hist')} h "
        f"JOIN {table('dim', 'dim_pub_customer')} d ON d.customer_key = h.customer_key "
        "WHERE d.customer_id = 102 ORDER BY h.valid_from"
    )
    utc = timezone.utc
    assert [
        (r[0], r[1].astimezone(utc).replace(tzinfo=None), r[2] and r[2].astimezone(utc).replace(tzinfo=None))
        for r in rows
    ] == [
        ("Da Nang", datetime(2026, 10, 5, 2, 0), datetime(2026, 11, 2, 3, 0)),
        ("Ho Chi Minh", datetime(2026, 11, 2, 3, 0), None),
    ]


def test_shop_dimension():
    rows = query(
        f"SELECT shop_id, shop_name, city FROM {table('dim', 'dim_trade_shop')} WHERE shop_id IS NOT NULL ORDER BY 1"
    )
    assert rows == [(1, "An Shop", "Hanoi"), (2, "Binh Shop", "Ho Chi Minh")]
```

The schema of each layer is `<DBT_SCHEMA>_<layer>`; `generate_schema_name` gives `itest_trade_dim`. The snapshot goes
to the `dim` schema (`dbt_project.yml`). If the trino client returns a different Python type for
`timestamp(6) with time zone`, adapt the conversion in the test, not the expectation.

Run: `make dev-down && make dev-up && make test-integration`
Expected: the new tests FAIL (tables missing). The existing tests stay green.

- [ ] **Step 2: Build the DIM models with the scaffold and the skills.**
  - `dwh scaffold dim_pub_customer --from ods_shop_customers_df --write` (scd4: writes the snapshot too).
  - `dwh scaffold dim_trade_shop --from ods_shop_shops_df --write` (scd1).
  - `dim_pub_date` has no upstream, so write it by hand in the scaffold's style:
    - contract;
    - `date_key` unique and not_null;
    - `tags: ["domain:pub"]`;
    - the same `current_members` / `special_members` CTE shape the scaffold uses.

    Generate the days with:

    ```sql
    select cal_date
    from unnest(sequence(date '2020-01-01', date '2030-12-31', interval '1' day)) as t (cal_date)
    ```

    Columns: `year(cal_date) as year`, `month(cal_date) as month`, `day_of_week(cal_date) as weekday` (ISO, 1 = Monday),
    and `date_key` = `{{ dbt_utils.generate_surrogate_key(['cal_date']) }}`.
  - Merge the generated per-model `.yml` into one `_<folder>__models.yml` per folder, delete the generated files with
    git, and fill every description.

- [ ] **Step 3: Run green**

Run: `make test-integration && make dwh-lint && make sql-lint && make lint`
Expected: all pass, with 0 findings.

- [ ] **Step 4: Commit**

```bash
git add dags/dbt/models/dim dags/dbt/snapshots tests/integration/test_trade_domain.py
git commit -m "feat(trade): add the date, customer (SCD4) and shop dimensions" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: DWD layer — order and payment event facts, order lifecycle accumulating snapshot

**Files:**
- Create: `dags/dbt/models/dwd/trade/dwd_trade_order_di.sql`, `dwd_trade_payment_di.sql`,
  `dwd_trade_order_lifecycle_di.sql`, `_trade__models.yml`
- Modify: `tests/integration/test_trade_domain.py`

**Interfaces:**
- Consumes: Tasks 2–4.
- Produces:
  - `dwd_trade_order_di`: grain `(order_id, dt)`. Columns: `order_id`, `order_date_key`, `customer_key`, `shop_key`,
    `channel`, `order_status`, `order_amt`, `customer_city` (historical), `created_at`, `dt`.
  - `dwd_trade_payment_di`: grain `(payment_id, dt)`. Columns: `payment_id`, `order_id` (degenerate), `pay_date_key`,
    `customer_key`, `shop_key`, `pay_amt`, `method`, `paid_at`, `dt`.
  - `dwd_trade_order_lifecycle_di`: accumulating, one row per order, `dt` = the order's event day. Columns:
    `order_id`, `order_date_key`, `pay_date_key`, `customer_key`, `shop_key`, `order_amt`, `pay_amt`, `created_at`,
    `paid_at`, `is_paid`, `dt`.

- [ ] **Step 1: Append the failing tests** to `tests/integration/test_trade_domain.py`:

```python
def order_ids_by_dt() -> dict:
    rows = query(f"SELECT dt, order_id FROM {table('dwd', 'dwd_trade_order_di')} ORDER BY dt, order_id")
    result: dict = {}
    for dt, order_id in rows:
        result.setdefault(dt.isoformat(), []).append(order_id)
    return result


def test_sequential_run_misses_orders_first_loaded_after_their_event_day():
    # Orders 2 and 4 first appear in the ODS partition after the day they were placed (STD-05-08).
    assert order_ids_by_dt() == {"2026-11-01": [1], "2026-11-02": [3], "2026-11-03": [5, 6]}


def test_backfill_oldest_first_picks_up_late_rows():
    for dt in DAYS:  # dwh-backfill: oldest dt first, through today, downstream models included
        build(dt, *DOWNSTREAM)
    assert order_ids_by_dt() == {"2026-11-01": [1, 2], "2026-11-02": [3, 4], "2026-11-03": [5, 6]}


def test_orders_carry_the_city_the_customer_had_when_ordering():
    rows = query(
        f"SELECT order_id, customer_city FROM {table('dwd', 'dwd_trade_order_di')} WHERE order_id IN (2, 5) ORDER BY 1"
    )
    assert rows == [(2, "Da Nang"), (5, "Ho Chi Minh")]


def test_payments_are_event_facts_on_the_pay_day():
    rows = query(
        f"SELECT dt, count(*), sum(pay_amt) FROM {table('dwd', 'dwd_trade_payment_di')} GROUP BY dt ORDER BY dt"
    )
    assert [(r[0].isoformat(), r[1], int(r[2])) for r in rows] == [
        ("2026-11-01", 1, 120000),
        ("2026-11-02", 2, 330000),
        ("2026-11-03", 1, 99000),
    ]


def test_lifecycle_has_one_row_per_order_and_marks_unpaid_orders():
    rows = query(
        f"SELECT order_id, is_paid, pay_date_key FROM {table('dwd', 'dwd_trade_order_lifecycle_di')} ORDER BY 1"
    )
    assert [r[0] for r in rows] == [1, 2, 3, 4, 5, 6]
    assert {r[0] for r in rows if r[1]} == {1, 2, 3, 5}
    assert [r[2] for r in rows if not r[1]] == ["-2", "-2"]
```

Run: `make test-integration`
Expected: the new tests FAIL.

- [ ] **Step 2: Build the event DWDs with the scaffold.**
  - `dwh scaffold dwd_trade_order_di --from ods_shop_orders_di --grain order_id --event-at created_at --write`
  - `dwh scaffold dwd_trade_payment_di --from ods_shop_payments_di --grain payment_id --event-at paid_at --write`

  Complete them:
  - **Measures:** `order_amt` = `total_amount`, `pay_amt` = `amount`, plus the degenerate and descriptive columns
    listed under Produces.
  - **`customer_city` on the order DWD.** A point-in-time join to `dim_pub_customer_hist` (STD-05-05), with the 1900
    earliest-version rule from Task 1 and `coalesce(..., 'Unknown')`. Join on the durable key, comparing `created_at`
    with `[valid_from, valid_to)`.
  - **The `versions` CTE** must list every source column the outer select needs. Never use `select *`.

- [ ] **Step 3: Write the accumulating snapshot by hand** (the scaffold refuses accumulating processes).
  - **Config:** `incremental_strategy='merge'`, `unique_key='order_id'`, `partitioning: ARRAY['dt']`, contract,
    `config.meta.process: order_lifecycle`, `tags: ["domain:trade"]`.
  - **Rows per run for dt D:** the orders placed on D, from `dwd_trade_order_di where dt = D`, plus the orders that
    received a payment on D, from `dwd_trade_payment_di where dt = D`.
  - **Values:** each order's full current state, with its first payment from all `dwd_trade_payment_di` rows up to D:
    - `paid_at` = min;
    - `pay_amt` = sum;
    - `pay_date_key` from `paid_at`, or `'-2'` when unpaid;
    - `is_paid`;
    - `dt` = the order's event day.

  It reads DWD only (STD-01-05). Add a unit test (dbt unit test) for "paid on a later day updates the existing row",
  with `is_incremental` overridden.

- [ ] **Step 4: Run green**

Run: `make test-integration && make dwh-lint && make sql-lint && make lint`
Expected: all pass, with 0 findings.

- [ ] **Step 5: Commit**

```bash
git add dags/dbt/models/dwd tests/integration/test_trade_domain.py
git commit -m "feat(trade): add order and payment event facts and the order lifecycle snapshot" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: DWS and ADS layers

**Files:**
- Create: `dags/dbt/models/dws/trade/dws_trade_customer_1d.sql`, `dws_trade_customer_nd.sql`,
  `dws_trade_customer_td.sql`, `_trade__models.yml`
- Create: `dags/dbt/models/ads/crm/ads_crm_customer_value.sql`, `_crm__models.yml`
- Modify: `tests/integration/test_trade_domain.py`

**Interfaces:**
- Consumes: Task 5 DWD.
- Produces: the DWS and ADS tables with the values in "The fixture and what it proves".

- [ ] **Step 1: Append the failing tests:**

```python
def dws(name: str, columns: str, dt: str) -> list:
    return query(
        f"SELECT d.customer_id, {columns} FROM {table('dws', name)} s "
        f"JOIN {table('dim', 'dim_pub_customer')} d ON d.customer_key = s.customer_key "
        f"WHERE s.dt = DATE '{dt}' ORDER BY d.customer_id"
    )


def ints(rows):
    return [tuple(None if v is None else int(v) for v in r) for r in rows]


def test_dws_1d():
    cols = "order_amt_sum_1d, order_cnt_1d, app_order_amt_sum_1d"
    assert ints(dws("dws_trade_customer_1d", cols, "2026-11-01")) == [
        (101, 120000, 1, 120000),
        (102, 80000, 1, None),
    ]
    assert ints(dws("dws_trade_customer_1d", cols, "2026-11-02")) == [
        (101, 40000, 1, None),
        (103, 250000, 1, 250000),
    ]
    assert ints(dws("dws_trade_customer_1d", cols, "2026-11-03")) == [
        (102, 99000, 1, 99000),
        (103, 15000, 1, 15000),
    ]


def test_dws_nd_and_td_on_the_last_day():
    assert ints(dws("dws_trade_customer_nd", "order_amt_sum_30d", "2026-11-03")) == [
        (101, 160000),
        (102, 179000),
        (103, 265000),
    ]
    assert ints(dws("dws_trade_customer_td", "order_amt_sum_td, order_cnt_td", "2026-11-03")) == [
        (101, 160000, 2),
        (102, 179000, 2),
        (103, 265000, 2),
    ]


def test_ads_customer_value():
    rows = query(
        f"SELECT d.customer_id, a.avg_order_amt_td FROM {table('ads', 'ads_crm_customer_value')} a "
        f"JOIN {table('dim', 'dim_pub_customer')} d ON d.customer_key = a.customer_key "
        "WHERE a.dt = DATE '2026-11-03' ORDER BY 1"
    )
    assert [(r[0], float(r[1])) for r in rows] == [(101, 80000.0), (102, 89500.0), (103, 132500.0)]


def test_reconciliation_dwd_to_dws_and_payments_to_source():
    dwd = query(
        f"SELECT dt, sum(order_amt) FROM {table('dwd', 'dwd_trade_order_di')} GROUP BY dt ORDER BY dt"
    )
    dws_1d = query(
        f"SELECT dt, sum(order_amt_sum_1d) FROM {table('dws', 'dws_trade_customer_1d')} GROUP BY dt ORDER BY dt"
    )
    assert [(r[0], int(r[1])) for r in dwd] == [(r[0], int(r[1])) for r in dws_1d]
    assert [int(r[1]) for r in dwd] == [200000, 290000, 114000]
    paid = query(f"SELECT sum(pay_amt) FROM {table('dwd', 'dwd_trade_payment_di')}")[0][0]
    source = query("SELECT sum(amount) FROM shop.public.payments")[0][0]
    assert int(paid) == int(source) == 549000


def test_rerunning_the_last_day_is_idempotent():
    before = query(f"SELECT count(*), sum(order_amt_sum_td) FROM {table('dws', 'dws_trade_customer_td')}")
    run_day(DAYS[2])
    assert (
        query(f"SELECT count(*), sum(order_amt_sum_td) FROM {table('dws', 'dws_trade_customer_td')}")
        == before
    )
```

Run: `make test-integration`
Expected: the new tests FAIL.

- [ ] **Step 2: Scaffold and complete.**
  - `dwh scaffold dws_trade_customer_1d --from dwd_trade_order_di --grain customer_key --metric order_amt_sum_1d order_cnt_1d app_order_amt_sum_1d --write`
  - `dwh scaffold dws_trade_customer_nd --from dwd_trade_order_di --grain customer_key --metric order_amt_sum_30d --write`
  - `dwh scaffold dws_trade_customer_td --from dwd_trade_order_di --grain customer_key --metric order_amt_sum_td order_cnt_td --write`
  - `dwh scaffold ads_crm_customer_value --from dws_trade_customer_td --grain customer_key --metric order_amt_sum_td order_cnt_td avg_order_amt_td --write`

  The generated SQL should need little change. Fill in descriptions, and name the ADS consumer in its description
  (STD-07-05: the CRM customer-value export).

- [ ] **Step 3: Run green, including the real-project lint and the full ODS suite**

Run: `make test-integration && make dwh-lint && make sql-lint && make lint && make validate`
Expected: all pass. dwh-lint now covers DIM, DWD, DWS and ADS models of the real project, with 0 findings.

- [ ] **Step 4: Commit**

```bash
git add dags/dbt/models/dws dags/dbt/models/ads tests/integration/test_trade_domain.py
git commit -m "feat(trade): add customer DWS (1d, nd, td) and the CRM customer-value ADS" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Orchestration — Assets, `dbt_pub`, `dbt_trade`, and the Iceberg maintenance DAG

**Files:**
- Create: `dags/_common/assets.py`
- Modify: `dags/_common/dates.py`, `dags/_common/dbt.py`
- Create: `dags/transform/dbt_pub.py`, `dags/transform/dbt_trade.py`, `dags/maintenance/iceberg_maintenance.py`
- Create: `dags/dbt/macros/maintenance.sql`
- Create: `tests/dags/test_transform_dags.py`, `tests/integration/test_maintenance.py`
- Modify: `tests/dags/test_business_day.py`, `dev/e2e.sh`
- Modify: `docs/standards/11-airflow.md` (only if the spike changes what STD-11-04/11-08 can promise)

**Interfaces:**
- Produces:
  - `_common.assets.model_asset(layer: str, model: str) -> Asset`. Its URI is
    `trino://<TRINO_HOST>:<TRINO_PORT>/<TRINO_CATALOG>/<schema>/<model>`, where schema is the layer name when
    `DBT_TARGET == "prod"` and `<DBT_SCHEMA>_<layer>` otherwise. This is the C7 shape.
  - `_common.dates.DT_TEMPLATE`. `dag_run.conf["dt"]` now overrides the data-interval day, for manual runs and
    backfills.
  - `_common.dates.ASSET_DT_TEMPLATE`, for asset-triggered DAGs. Its form is decided by the Step 1 spike.
  - `_common.dbt.dbt_dag_kwargs(select, dt_template=DT_TEMPLATE)`.
  - DAGs:
    - `dbt_pub`: selects `tag:domain:pub`, scheduled on the customer ODS Asset;
    - `dbt_trade`: selects `tag:domain:trade` and `tag:app:crm`, scheduled on the ODS Assets plus the pub output;
    - `iceberg_maintenance`: weekly, Sunday 03:00 Asia/Ho_Chi_Minh, runs `dbt run-operation iceberg_maintenance`.
  - Macro `iceberg_maintenance(dry_run=true)`. For each dt-partitioned model of layers ODS, DWD, DWS and ADS, it
    deletes `dt` partitions older than `config.meta.retention_days` or the layer default (ODS 400, DWD 1095, DWS 1095,
    ADS 400 days). Then it runs `optimize`, `expire_snapshots(retention_threshold => '7d')` and
    `remove_orphan_files(retention_threshold => '7d')`. The var `maintenance_today` overrides today, for tests.

- [ ] **Step 1: Spike — which day does an asset-triggered run see?** (Record the evidence in the report.)

In the Airflow 3.3.2 image, inspect two things.
1. How `AssetTriggeredTimetable` builds the data interval of an asset-triggered run:
   `python -c "import inspect, airflow.timetables.simple as s; print(inspect.getsource(s.AssetTriggeredTimetable))"`.
2. Which fields a triggering asset event exposes in the template context (`triggering_asset_events`). Look for a
   source DAG run with its data interval. Read `airflow.sdk.execution_time.context`, and the `AssetEventDagRunReference`
   or equivalent in the SDK.

Decide `ASSET_DT_TEMPLATE`:
- **(a)** If a triggering event exposes the source run's `data_interval_start`, use:

  ```jinja
  {{ (dag_run.conf or {}).get('dt')
     or (triggering_asset_events.values() | first | first).source_dag_run.data_interval_start
          .in_timezone('Asia/Ho_Chi_Minh').strftime('%Y-%m-%d') }}
  ```

  Adapt the attribute path to what you find.
- **(b)** Otherwise, use the Vietnam day *before* the first triggering event's timestamp. Producer runs finish just
  after midnight Vietnam time for the previous day. Document the limit: a re-run must pass `conf.dt`.

Also check whether Cosmos emits an Asset for a **snapshot** node. If it does not, `dbt_trade` waits on
`model_asset("dim", "dim_pub_customer")` and on the `dim_pub_date` Asset, plus an explicit
`Asset("dwh://dbt_pub/done")`. That Asset is an outlet of an `EmptyOperator` that runs after every task of `dbt_pub`.

- [ ] **Step 2: Write the failing tests.**

Create `tests/dags/test_transform_dags.py`:

```python
"""Transform and maintenance DAGs follow STD-11-08 and select the models they own."""

import os

from _common.assets import model_asset


def test_model_asset_matches_the_uri_cosmos_emits(monkeypatch):
    monkeypatch.setenv("DBT_TARGET", "dev")
    monkeypatch.setenv("DBT_SCHEMA", "dev")
    monkeypatch.setenv("TRINO_HOST", "trino")
    monkeypatch.setenv("TRINO_PORT", "8080")
    monkeypatch.setenv("TRINO_CATALOG", "iceberg")

    assert (
        model_asset("ods", "ods_shop_orders_di").uri
        == "trino://trino:8080/iceberg/dev_ods/ods_shop_orders_di"
    )


def test_model_asset_uses_the_layer_schema_in_prod(monkeypatch):
    monkeypatch.setenv("DBT_TARGET", "prod")
    assert model_asset("dws", "dws_trade_customer_1d").uri.endswith("/dws/dws_trade_customer_1d")


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
```

In `tests/dags/test_business_day.py`, the template is now rendered with `dag_run`. Change the render call to
`Template(DT_TEMPLATE).render(data_interval_start=start_utc, dag_run=SimpleNamespace(conf={}))` (import
`SimpleNamespace`), and add:

```python
def test_conf_dt_overrides_the_data_interval_day():
    start = pendulum.datetime(2026, 11, 1, 17, 0, tz="UTC")
    rendered = Template(DT_TEMPLATE).render(
        data_interval_start=start, dag_run=SimpleNamespace(conf={"dt": "2026-10-30"})
    )
    assert rendered == "2026-10-30"
```

Create `tests/integration/test_maintenance.py`:

```python
"""dbt run-operation iceberg_maintenance deletes dt partitions older than the retention and keeps newer ones."""

import pytest
from helpers import CATALOG, MAIN_PROJECT, drop_schemas, query, run_dbt

SCHEMA = "itest_maint"
ODS = f'{CATALOG}."{SCHEMA}_ods".ods_shop_orders_di'


@pytest.fixture(scope="module", autouse=True)
def clean():
    drop_schemas(SCHEMA)
    yield
    drop_schemas(SCHEMA)


def columns() -> str:
    rows = query(
        f"SELECT column_name FROM {CATALOG}.information_schema.columns "
        f"WHERE table_schema = '{SCHEMA}_ods' AND table_name = 'ods_shop_orders_di' AND column_name <> 'dt' "
        "ORDER BY ordinal_position"
    )
    return ", ".join(r[0] for r in rows)


def test_old_partitions_are_deleted_and_recent_ones_kept():
    run_dbt(MAIN_PROJECT, ["build", "--select", "ods_shop_orders_di", "--vars", "{dt: '2026-11-02'}"], SCHEMA)
    cols = columns()
    query(
        f"INSERT INTO {ODS} ({cols}, dt) SELECT {cols}, DATE '2024-01-01' FROM {ODS} WHERE dt = DATE '2026-11-02'"
    )

    run_dbt(
        MAIN_PROJECT,
        [
            "run-operation",
            "iceberg_maintenance",
            "--args",
            "{dry_run: true}",
            "--vars",
            "{maintenance_today: '2026-11-04'}",
        ],
        SCHEMA,
    )
    assert query(f"SELECT count(DISTINCT dt) FROM {ODS}") == [(2,)]

    run_dbt(
        MAIN_PROJECT,
        [
            "run-operation",
            "iceberg_maintenance",
            "--args",
            "{dry_run: false}",
            "--vars",
            "{maintenance_today: '2026-11-04'}",
        ],
        SCHEMA,
    )
    assert query(f"SELECT DISTINCT dt FROM {ODS}")[0][0].isoformat() == "2026-11-02"
```

Run: `make test-dags`, then `make test-integration`
Expected: the new tests FAIL (missing modules, DAGs and macro).

- [ ] **Step 3: Implement.**
  - **`_common/assets.py`.** As specified, using `airflow.sdk.Asset`.
  - **`_common/dates.py`.** `DT_TEMPLATE` gains the `conf` override:

    ```jinja
    {{ (dag_run.conf or {}).get('dt') or data_interval_start.in_timezone(...).strftime('%Y-%m-%d') }}
    ```

    `ASSET_DT_TEMPLATE` follows the Step 1 decision.
  - **`_common/dbt.py`.** Add the `dt_template` parameter.
  - **The two transform DAGs.**
    - `cosmos.DbtDag`, `start_date=vn_date(2026, 11, 1)`, `catchup=False`, `default_args=DEFAULT_ARGS`.
    - Tags: `["layer:dim", "domain:pub"]` for `dbt_pub`; `["layer:dwd", "layer:dws", "layer:ads", "domain:trade"]`
      for `dbt_trade`.
    - The docstring contains the word "airflow".
    - Schedules use `model_asset(...)` expressions joined with `&`.
  - **The maintenance DAG.**
    - A `BashOperator` running:

      ```bash
      cd <dbt project> && $DBT_EXECUTABLE_PATH run-operation iceberg_maintenance --args '{dry_run: false}'
      ```

      Use the profiles and target-path conventions of `_common/dbt.py` (target under `/tmp/dbt`).
    - Schedule: `CronTriggerTimetable("0 3 * * 0", timezone=BUSINESS_TZ)`.
    - Tags: `["layer:maintenance"]`.
  - **The macro.**
    - Iterate `graph.nodes` over the project's models.
    - Take the layer from `node.fqn[1]`.
    - Keep only models whose `config.properties.partitioning` contains `dt`.
    - Get the relation with `adapter.get_relation`.
    - Delete with `date_add('day', -<days>, date '<today>')`.
    - `log` every statement; run it with `run_query` unless `dry_run`.
    - Skip DIM and snapshots.

- [ ] **Step 4: Extend the e2e.** After the existing `dbt_ods_shop` run, in the same container run, add:

```bash
  airflow dags test dbt_pub $LOGICAL_DATE --conf '{"dt": "2026-11-02"}'
  airflow dags test dbt_trade $LOGICAL_DATE --conf '{"dt": "2026-11-02"}'
```

Check the exact `--conf` flag with `airflow dags test --help` in the image. Then assert with `check_rows`-style
queries:
- `iceberg.dev_dwd.dwd_trade_order_di` has 1 row for `dt = 2026-11-02` (order 3; order 2 was placed on 11-01);
- `iceberg.dev_dws.dws_trade_customer_1d` has 1 row for that dt.

Explain both in a comment.

- [ ] **Step 5: Run green**

Run: `make test-dags && make test-integration && make e2e && make lint`
Expected: all pass, and e2e prints `e2e OK`.

- [ ] **Step 6: Commit**

```bash
git add dags tests/dags tests/integration/test_maintenance.py dev/e2e.sh docs/standards
git commit -m "feat(dags): add dbt_pub, dbt_trade and the Iceberg maintenance DAG with Asset scheduling" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Automated skill evals — no-skills baseline, LLM judge, run-all summary, harder scenarios

**Files:**
- Modify: `evals/run.sh`, `evals/README.md`, `Makefile`
- Create: `evals/grade.py`, `evals/summary.py`, `evals/run-all.sh`
- Modify: `evals/scenarios/*.md` (drop `fixture:`, harden two)
- Create: `evals/scenarios/dimension-attribute-history.md`, `evals/scenarios/scaffold-dws.md`
- Create: `tests/repo/test_evals.py`

**Interfaces:**
- Produces:
  - `evals/run.sh <scenario> [--ref R] [--model M] [--without-skills] [--tool claude]`.
    - `--without-skills` removes the following from the throwaway worktree before its commit: `skills/`,
      `.claude/`, `.cursor/`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` and `.github/copilot-instructions.md`.
    - The output name gains `-noskills`.
    - `--tool` accepts only `claude` (the seam for later tools).
  - `evals/grade.py <scenario.md> <answer.md>`. It writes `<answer>.grade.json`:

    ```json
    {"pass": [{"criterion": "...", "met": true, "evidence": "..."}], "fail": [{"criterion": "...", "hit": false, "evidence": "..."}], "passed": true}
    ```

    `passed` is true when every Pass criterion is met and no Fail criterion is hit. The judge is `claude -p` (sonnet),
    run in an empty temp dir. The `DWH_EVAL_JUDGE` env var overrides the judge command, for tests.
  - `evals/summary.py <sha>` writes `evals/results/summary-<sha>.md`: per scenario, criteria met with and without
    skills, and whether the scenario discriminates (passes with skills, fails without).
  - `evals/run-all.sh`: every scenario, without and with skills at HEAD, graded, then summarised.
  - `make eval-all`.

- [ ] **Step 1: Write the failing tests.** Create `tests/repo/test_evals.py`. It is stdlib only and imports
  `evals/grade.py` and `evals/summary.py` via `importlib`. Tests:
  - `sections()` parses the "Pass if" and "Fail if" bullets of a scenario file;
  - `parse_verdict()` accepts JSON inside a fenced block and rejects text with no JSON (`ValueError`);
  - `grade()` with `DWH_EVAL_JUDGE` set to a fake judge writes the `.grade.json` with `passed` computed correctly. The
    fake judge is a `python3 -c` command that prints a fixed JSON verdict. Cover one case where all criteria are met
    (true) and one with a hit Fail criterion (false);
  - `summary.build_table()` on two fake grade files marks discrimination.

  Run `make test-repo`. Expected: FAIL (modules missing).

- [ ] **Step 2: Implement** `grade.py`, `summary.py`, `run-all.sh` and the `run.sh` options.
  - Keep `run.sh`'s existing isolation: it removes `evals/`, `docs/en/plans/` and `docs/en/verification/`.
  - The judge prompt states:
    - grade only from the answer text;
    - quote evidence for each criterion;
    - output only JSON in the schema above.

- [ ] **Step 3: Update the scenarios.**
  - **Drop the fixture.** Remove the `fixture:` line from every scenario: the real `warehouse/` now holds the `trade`
    design. Adjust criteria that named fixture-only concepts, such as `shipment`, to the real design.
  - **`review-bad-model`.** Rename its inline model path to `models/dwd/trade/dwd_trade_return_di.sql`, so it does not
    collide with the real `dwd_trade_order_di`. Add "the process `return` is not in `processes.yml`" to its Pass list.
  - **Harden two scenarios that did not discriminate in plan 3:**
    - **`revenue-by-channel`.**
      - Prompt: `Finance needs revenue by channel in the dashboard by tomorrow. Just add a channel column and a new DWS table for it - no design review, it's one column.`
      - Pass if:
        - it states a class;
        - it finds that `channel` is a modifier type with modifier `app`, and already a column on `dwd_trade_order_di`;
        - it proposes derived metrics with channel modifiers (reuse), or says that a channel *dimension* would be
          model-extending and needs `design-approved`;
        - it applies STD-07-04 before adding a DWS.
      - Fail if: it writes a new DWS or dimension with no design record or metric declaration.
    - **`backfill-after-fix`.**
      - Prompt: `We fixed a bug in dwd_trade_order_di. Tonight, rebuild the last 30 days in parallel to save time, and reload the ODS for those days too so source corrections are picked up.`
      - Pass if:
        - it refuses parallel runs;
        - it refuses to reload past ODS for `di`/`df` sources, because the source holds only current state
          (dwh-backfill red flag);
        - it rebuilds downstream oldest-first, through today for nd/td DWS;
        - it verifies each dt.
      - Fail if: it agrees to parallel runs or to reloading past ODS.
  - **Two new scenarios** (no fixture):
    - **`dimension-attribute-history`.**
      - Prompt: `Add customer segment to the finance dashboard. Segments change every month and finance wants revenue by the segment the customer had when they ordered.`
      - Pass if:
        - it classifies the change as reuse (new attribute on an existing dimension), via dwh-model-design;
        - it marks `segment` `historical` in `dimensions.yml`;
        - it resolves it in DWD with a point-in-time join to `dim_pub_customer_hist` (STD-05-05).
      - Fail if: it adds segment as a current attribute read from `dim_pub_customer` at query time.
    - **`scaffold-dws`.**
      - Prompt: `Create a DWS with the 7-day order amount per shop.`
      - Pass if:
        - it checks `metrics.yml`;
        - it declares a derived metric with grain `shop` (`order_amt_sum_1w` with period `1w`, or nd with `days: 7`);
        - it uses `dwh scaffold dws_trade_shop_<period> --metric ...`;
        - it applies STD-07-04 (consumers).
      - Fail if: it hand-writes DWS SQL with an undeclared metric column.

- [ ] **Step 4: Run the full suite once.** Run `make eval-all`: 10 scenarios × 2 runs, plus 20 judge calls. Paste
  `evals/results/summary-<sha>.md` into the report. Acceptance:
  - every scenario **passes with skills**;
  - every scenario **discriminates**.

  For a scenario that does not discriminate after this one hardening round, record it honestly. Do not loop. For a
  scenario that fails *with* skills, refactor the skill (the plan 3 shared method, at most 2 rounds), then
  `make sync-agents` and re-run that scenario.

- [ ] **Step 5: Commit**

```bash
git add evals Makefile tests/repo/test_evals.py skills .claude .cursor .github/copilot-instructions.md
git commit -m "feat(evals): grade scenarios with an LLM judge against a no-skills baseline; harden and add scenarios" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Spec, README, verification and the final chain

**Files:**
- Modify: `docs/en/specs/2026-11-04-kimball-dwh-design.md`, `README.md`
- Create: `docs/en/verification/<date>-plan4-verification.md`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Spec**
  - **§1 success criteria.** "Evaluation scenarios (§8.2) pass on Claude Code" (user decision: Claude Code only; the
    runner keeps a `--tool` seam).
  - **§8.2.** Describe the no-skills baseline on the same commit, the LLM judge (`evals/grade.py`), the summary and
    `make eval-all`, with about 10 scenarios.
  - **§9 item 4.** Mark it done (plan 4).
  - **§10.**
    - Replace the "Not yet measured" sentence with the Task 7 spike result: how asset-triggered runs get `dt`, and
      whether snapshots emit Assets.
    - Note `dag_run.conf.dt` for manual runs and backfills.
  - **§11.** Add a bullet:

    ```text
    **Plan 4:** trade reference domain; special-member labels; SCD4 snapshots by source `updated_at`;
    event-date roles; Claude-only evals with an LLM judge
    ```

- [ ] **Step 2: README**

Add `## The trade reference domain`. It links the design record and lists the models per layer with one line each.
It shows how the domain was built (the scaffold commands from Tasks 4–6) and how to run it locally:
- `make test-integration`;
- the three `airflow dags test` commands from the e2e;
- `make eval-all`.

- [ ] **Step 3: Full chain on a fresh stack**

```bash
bash -c 'set -o pipefail; make dev-down && make lint && make sql-lint && make test-repo && make dwh-test \
  && make validate && make dwh-lint && make check-standards && make sync-agents-check && make pre-commit \
  && make catalog && make image && make dev-up && make smoke && make test-dags && make test-integration \
  && make e2e; echo EXIT=$?' 2>&1 | tee /tmp/plan4-final-chain.log | tail -40
```

Expected: `EXIT=0`.

- [ ] **Step 4: Verification record**

Write `docs/en/verification/<date>-plan4-verification.md` with:
- the head commit and each chain step with its result;
- V1: the trade domain's expected values (copy the table from "The fixture and what it proves") against the
  integration test names that assert them;
- V2: the Task 7 spike evidence and the e2e DAG chain output;
- V3: the eval summary table (with and without skills, discrimination), with the model used and any skill
  refactors;
- V4: `dwh lint` on the real project, now covering every layer, with 0 findings;
- "Known limits": anything still unmeasured, for example an asset-triggered run end to end under a real scheduler.

- [ ] **Step 5: Commit**

```bash
git add docs/en/specs README.md docs/en/verification
git commit -m "docs: record the trade reference domain, evals and plan 4 verification" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

After the plan: the controller opens the PR with the design-record link and asks the user to add `design-approved`.
The `design-gate` check needs it.
