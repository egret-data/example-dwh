# example-dwh — Kimball/OneData data warehouse with AI-ready development rules

- **Date:** 2026-11-04
- **Status:** Approved. Amended 2026-11-04 after plan 1 and a full reading of the Alibaba section (§11).
- **Research:** [Alibaba section digest](../research/2026-11-04-alibaba-dwh-digest.md)
- **Stack:** Apache Airflow (official Helm chart, git-sync) · dbt-trino · astronomer-cosmos · Trino · Apache Iceberg
- **Modelling reference:** Kimball dimensional modelling as operationalised by Alibaba Cloud MaxCompute
  "Build and optimize a data warehouse" (OneData):
  <https://www.alibabacloud.com/help/en/maxcompute/user-guide/overall-process>

## 1. Goal

Give a team a single repository in which anyone — a human, or any AI coding tool (Claude Code, Cursor,
Copilot, Codex, Gemini…) — can add data to the warehouse **the same Kimball/OneData way**, with:

1. A **rulebook** (standards) that defines layers, naming, dimensions, facts, metrics, incremental
   loading and SQL style.
2. A **process** (skills, in the spirit of superpowers) that walks every change from requirement to
   verified PR, with human gates where new concepts are introduced.
3. **Machine enforcement** (`dwh` CLI + CI) so that rules that can be checked are checked, independently
   of whether the AI followed the prose.

Success criteria:

- A new teammate or AI tool, given only the repo, produces a model that passes `dwh lint` and dbt tests
  on the first PR for a "reuse" change.
- No metric is defined in two places; every DWD maps to a bus-matrix cell; every DWS metric column
  traces to a declared derived metric.
- Evaluation scenarios (§8.2) pass on Claude Code and at least one other tool.

Out of scope: BI/semantic-layer serving (BI tools read the warehouse, D13, but are not configured here),
data catalog products, infrastructure provisioning of Trino / Iceberg catalog / Airflow cluster (assumed
to exist).

## 2. Decisions made

| # | Decision | Choice |
|---|----------|--------|
| D1 | Target AI tools | Multi-tool. Canonical content written once; per-tool pointer files generated. |
| D2 | Layer naming | Hybrid: Alibaba layers (ODS / DIM / DWD / DWS / ADS) as dbt model folders; Alibaba naming and metric system kept; dbt tests/contracts used for enforcement. |
| D3 | Storage | Apache Iceberg behind Trino. |
| D4 | Design metadata | YAML in repo is the source of truth; CI generates a human-readable catalogue. |
| D5 | Process strictness | By change class: *model-extending* changes need a human design gate; *reuse* changes only need PR review. |
| D6 | Repo shape | Airflow project deployed via git-sync; `gitSync.subPath = "dags"`. |
| D7 | Ingestion | Trino `INSERT … SELECT` from source catalogs, implemented as dbt ODS models. |
| D8 | Skill organisation | Phase-based skills (process only) that link to standards files (rules), loaded on demand. |
| D9 | Name | Repo `example-dwh`; CLI `dwh`. |
| D10 | Defaults | No business-segment prefix in table names; partition column is `dt` (DATE). |
| D11 | Dimension history | **SCD4 by default**: `dim_*` holds the current row per natural key; `dim_*_hist` holds every version, built from a dbt snapshot. Facts carry the **durable key** `hash(natural key)`. Historical attributes a fact needs are resolved in DWD by a point-in-time join to `_hist` and stored on the fact (§7, `04`/`05`). SCD2 with a per-version key is allowed only as a documented exception in the model `.yml`. Kimball's mini-dimension stays a separate technique for fast-changing attributes. |
| D12 | Business day | `dt` is the **Asia/Ho_Chi_Minh calendar day**. DAGs are timezone-aware; `dt` is derived from the run's data interval converted to that zone, never from the UTC `ds`; source timestamps are converted before day windows are applied (§4, `08`). |
| D13 | BI access | BI tools read the **DWD + DIM star** directly (and DWS where it exists). ADS is built only for a specific application, export or performance need, and names its consumer. |

## 3. Repository layout

```text
example-dwh/                         # git-sync clones the whole repo → /opt/airflow/dags/repo
├── dags/                            # gitSync.subPath = "dags" → Airflow dags_folder
│   ├── .airflowignore               # excludes dbt/ and non-DAG folders from parsing
│   ├── _common/                     # shared Python: Cosmos profile/config, default_args, callbacks
│   ├── sources/                     # one DAG per source system: runs dbt ODS models (tag ods_<source>)
│   │   └── dbt_ods_<source>.py
│   ├── transform/                   # one DAG per domain (ADS may get its own DAG if schedule differs)
│   │   └── dbt_<domain>.py
│   └── dbt/                         # dbt-trino project
│       ├── dbt_project.yml  packages.yml  profiles.yml   # profiles read env vars only
│       ├── models/
│       │   ├── ods/<source>/
│       │   ├── dim/<domain|pub>/
│       │   ├── dwd/<domain>/
│       │   ├── dws/<domain>/
│       │   └── ads/<app>/
│       ├── snapshots/  macros/  tests/  seeds/
├── warehouse/                       # SOURCE: design metadata (YAML + JSON Schema)
├── skills/                          # SOURCE: one SKILL.md per process phase
├── docs/
│   ├── standards/                   # SOURCE: the rulebook (English, AI- and human-facing)
│   ├── designs/                     # per-change design records produced by dwh-requirement/-model-design
│   └── en/                          # specs/, plans/, research/, verification/
├── tools/dwh/                       # `dwh` CLI (Python package)
├── evals/scenarios/                 # skill evaluation scenarios (§8.2)
├── tests/                           # pytest: DAG integrity + dwh unit tests
├── AGENTS.md                        # entry point for every AI tool
├── CLAUDE.md                        # generated: "@AGENTS.md"
├── .claude/skills/                  # generated from skills/
├── .cursor/rules/*.mdc              # generated
├── .github/copilot-instructions.md  # generated
├── .github/workflows/ci.yml
├── .github/CODEOWNERS               # warehouse/ owned by data architect(s)
├── .pre-commit-config.yaml
├── Dockerfile  requirements.txt     # Airflow + astronomer-cosmos + dbt-trino, all pinned; dbt deps baked in
└── README.md
```

Rules for this layout:

- Only `dags/` is parsed by Airflow. `warehouse/`, `skills/`, `docs/`, `tools/` are present on the pod
  (git-sync clones the whole repo) but never parsed.
- `skills/`, `docs/standards/`, `warehouse/` are the **only** sources of truth. Every per-tool file is
  generated by `dwh sync-agents`; CI fails if generated files drift (`dwh sync-agents --check`).
- `dbt_packages/` is installed at image build time (pinned), never at task runtime.
- dbt `target/` and `logs/` write to a writable temp path, because the git-sync volume is read-only.
- Cosmos uses `LoadMode.DBT_LS` with its dbt-ls cache; `manifest.json` is not committed.

## 4. Runtime architecture

```text
source catalogs (postgresql/mysql/… in Trino)
        │  dbt ODS models: INSERT … SELECT (Iceberg tables, partition dt)
        ▼
  ODS  ──►  DIM / DWD  ──►  DWS  ──►  ADS          (all Iceberg, all dbt models)
   ▲            ▲             ▲         ▲
 dbt_ods_<source> DAG     dbt_<domain> DAG(s)
   └── emits Airflow Assets ──► triggers domain DAGs

BI tools ──► DWD + DIM star (and DWS)            (D13; ADS only for a named application)
```

- **ODS ingestion (D7):** each source system is a Trino catalog declared as a dbt `source`. Each ODS
  model `ods_{source}_{table}_{di|df}` is a physical Iceberg table reading `source()`:
  - `df` (daily full): full copy into partition `dt`. For small and reference tables.
  - `di` (daily incremental): rows whose watermark (e.g. `updated_at`) falls in the `dt` day window.
  - Both replace the `dt` partition on every run: an `is_incremental()`-guarded `pre_hook` deletes
    `dt`, then the model appends (`incremental_strategy='append'`). This keeps re-runs idempotent even
    when the batch is empty (measured in plan 1, C8). The delete and the insert are two statements,
    not one transaction; a failure between them leaves `dt` empty until the retry restores it.
  - Every source table declares in its dbt source `meta`: load type (`di`/`df`), watermark column,
    source timezone, and **delete handling** (`none` | `soft_delete_flag` | `full_compare`). Hard
    deletes in a `di` source are invisible to a watermark; such tables must be `df` or `full_compare`.
- **Business day (D12):** DAGs use `timezone="Asia/Ho_Chi_Minh"` (pendulum) and pass
  `dt = data_interval_start` converted to Asia/Ho_Chi_Minh, formatted `YYYY-MM-DD`. Airflow's `ds` is
  the UTC date and is off by one day for a midnight-VN schedule, so it is never used for `dt`. A `di`
  window is `[dt 00:00, dt+1 00:00)` in Asia/Ho_Chi_Minh, compared against the source watermark after
  converting it from the source timezone. Timestamp columns (`_at`) are stored as
  `timestamp(6) with time zone`. A boundary test (a row at 23:30 and one at 00:30 VN time) proves the
  window.
- **Orchestration:** one Cosmos `DbtDag` per DAG (`LoadMode.DBT_LS`), selecting by tag. `dt` is passed
  through the dbt operator args (`--vars`). Cross-DAG dependencies use the Airflow Assets Cosmos emits
  for each model run (URI `trino://<host>:<port>/<catalog>/<schema>/<table>`; the schema differs per
  environment), not `ExternalTaskSensor`.
- **Idempotency:** re-running any task for the same `dt` produces the same result; backfill is
  re-running past `dt`s (see `dwh-backfill`).
- **Read-only code volume:** the git-sync volume is read-only. dbt `target/` and logs go to `/tmp`,
  dbt packages are baked into the image, and nothing at runtime writes into the repository (verified in
  plan 1).
- **Retention (Alibaba LIFECYCLE):** each layer has a default data retention, enforced by a maintenance
  DAG that deletes `dt` partitions older than the retention and runs Iceberg `expire_snapshots` and
  `remove_orphan_files`. Defaults: ODS 400 days; DWD 3 years; DIM current table forever, `_hist`
  forever; DWS 3 years; ADS 400 days. A model overrides its default with `meta.retention_days` in its
  `.yml`.

## 5. Design metadata (`warehouse/`)

YAML files, each validated by a JSON Schema in `warehouse/schemas/`:

| File | Contents |
|------|----------|
| `domains.yml` | Data domains: name (glossary root), description, owner. |
| `processes.yml` | Business processes: name, domain, description, fact type (transaction / periodic snapshot / accumulating snapshot), grain statement. |
| `dimensions.yml` | Conformed dimensions: name, scope (`pub` or domain), natural key, history type (`scd4` default; `scd1`, or `scd2` as a documented exception), attributes. Each attribute is marked `history: historical` (facts need the value at event time; resolved in DWD) or `current` (always read from `dim_*`). `date` is mandatory and always present as `dim_pub_date`. |
| `bus_matrix.yml` | Process × dimension matrix (which dimensions each process uses, with role names for role-playing). |
| `metrics.yml` | `atomic` (process + measure + aggregation), `derived` (atomic + period + modifiers + grain), `calculated` (formula over other metrics; a Kimball extension, Alibaba has only atomic and derived). Additivity is declared per atomic metric (`additive` / `semi_additive` with the non-additive dimension / `non_additive`). A non-additive metric (ratio, distinct count, average) is never stored as a precomputed value in DWD/DWS; its numerator and denominator are stored, and the ratio is a `calculated` metric. |
| `modifiers.yml` | Business filters (Alibaba "modifiers"): name, modifier type, SQL predicate description, applicable processes. A modifier inherits its domain from its modifier type. |
| `periods.yml` | Statistical periods, one token each, used as the DWS table and metric column suffix: `1d` (the `dt` day), `nd` (last n days; n is fixed by each derived metric, e.g. 30), `td` (all history up to and including `dt`), `1w` (last 7 days, split out of `nd` when that table gets too wide), `hh` (hourly), `mm` (minute-level). Batch DWS defaults to the `1d` / `nd` / `td` triple (Alibaba). |
| `glossary.yml` | Root words allowed in table and column names, with meaning and abbreviation. |

CI renders these plus `dbt docs` into a static catalogue (bus matrix, metric dictionary, glossary) on
merge to `main`. It is published to GitHub Pages by `.github/workflows/catalog.yml`.

## 6. Process (skills)

### 6.1 Change classification — `dwh-start`

Every data request starts here. The skill classifies the change:

| Class | Examples | Path |
|-------|----------|------|
| **Model-extending** | new domain, business process, conformed dimension or atomic metric; grain change; new source system | requirement → design → **human design approval** → implement → verify → PR |
| **Reuse** | new derived metric from an existing atomic metric, new ADS table, new dimension attribute, logic fix, bug fix | light design → implement → verify → PR |
| **Operations** | DAG fix, retry, backfill, performance | `dwh-debug` / `dwh-backfill` → PR |

When unsure, the change is classified model-extending.

### 6.2 Skill chain

Each skill is 1–2 pages: steps, stop points, red flags. Rules live in `docs/standards/` and are linked,
not copied.

1. **`dwh-requirement`** — question until business process, grain, dimensions and metrics are explicit;
   search `warehouse/*.yml` for reusable concepts *before* proposing new ones. Output:
   `docs/designs/YYYY-MM-DD-<topic>.md`.
2. **`dwh-model-design`** — update `bus_matrix.yml`, `metrics.yml`, `glossary.yml` etc.; specify each
   table (layer, name, one-sentence grain, keys, columns, sources, incremental/SCD strategy, partition).
   For model-extending changes: **stop and wait for human approval; write no SQL.**
3. **`dwh-implement`** — tests first: `dwh scaffold <model>` generates model + `.yml` with contract,
   grain tests (`unique`, `not_null`) and `relationships` to DIMs; then write SQL per the layer standard.
4. **`dwh-verify`** — run `dbt build --select <model>+` on dev, `dwh lint`, `sqlfluff lint`; check row
   counts, grain uniqueness, reconciliation to source. Record a **performance baseline** for the model
   (Trino wall time, input bytes/rows scanned, output rows, Iceberg file count and size) and, for a
   change to an existing model or any performance work, the before/after comparison (Alibaba
   "performance baseline" and "result validation"). Never claim done without real output as evidence.
5. **`dwh-review`** — checklist for AI and human reviewers: grain, layer, naming, metrics, SCD, Trino
   performance and scan cost.
6. **`dwh-debug`** — systematic debugging of dbt / Airflow / Trino failures and number discrepancies
   (trace lineage ADS → ODS).
7. **`dwh-backfill`** — safe backfill and partition re-run procedure.

### 6.3 Human design gate (D5)

- A PR that **adds** a domain, process, dimension or atomic metric to `warehouse/*.yml` must reference a
  `docs/designs/…` record and carry the label `design-approved`; CI checks both.
- `CODEOWNERS` assigns `warehouse/` to data architect(s), so their review is required.

## 7. Rulebook (`docs/standards/`)

Each file states rules as MUST / SHOULD, with a correct and an incorrect example. A rule that is
machine-checked cites its lint code (e.g. `DWH-N01`) so humans and AI refer to the same identifier.

| File | Key rules |
|------|-----------|
| `00-principles.md` | Kimball + OneData: start from business processes; declare grain first; conformed dimensions; one definition per metric; reuse before create. |
| `01-layers.md` | Role of each layer and **dependency rules**: ODS ← source; DIM/DWD ← ODS (and DIM); DWS ← DWD + DIM, or a coarser-grain DWS built on a finer existing DWS; ADS ← DWS and DIM (DWD allowed with a written reason in the model `.yml`, `meta.dwd_reason`). An accumulating snapshot reads transaction facts, not ODS. No upward reads. Only ODS may call `source()`. Dependency chains inside DIM/DWD/DWS are at most 10 models deep (Alibaba). BI reads DWD + DIM (D13). |
| `02-naming.md` | `ods_{source}_{table}_{di\|df}` · `dim_pub_{dimension}` (shared across domains) / `dim_{domain}_{dimension}` (one domain) · `dwd_{domain}_{process}_{di\|df}` · `dws_{domain}_{grain}[_{custom}]_{period}` with period one of `1d\|nd\|td\|1w\|hh\|mm` · `ads_{app}_{subject}[_{period}]` (period, when present, one of `1d\|nd\|td\|1w\|hh\|mm`). History tables add `_hist`. Column suffixes: `_id` natural ids, `_key` surrogate/durable keys, `is_` flags, `_date` dates, `_at` timestamps, `_amt` money, `_cnt` counts. Every name segment must exist in `glossary.yml`. Alibaba's slot after `dim_`/`dwd_` is the business segment; here it is `pub` or the domain (D10), and the file says so. |
| `03-domains-bus-matrix.md` | How to divide domains (by department, business process or functional module; keep them extensible) and processes; how to build the bus matrix; what counts as model-extending. |
| `04-dimensions.md` | Conformed dimensions. **SCD4 (D11):** `dim_*` = one current row per natural key, keyed by the durable key `hash(natural key)` (`dbt_utils.generate_surrogate_key`); `dim_*_hist` = all versions from a dbt snapshot with `valid_from`, `valid_to`, `is_current`. SCD1 dims are just `dim_*`. SCD2 with a per-version key only as a documented exception. Mini-dimension for fast-changing attributes. Special members, keys of the same `varchar` type as hash keys: `'-1'` unknown (natural key null or not found), `'-2'` not applicable. **Late-arriving dimensions:** a fact whose natural key is not yet in the dim still gets its durable key (hash of the natural key, so no rewrite is needed later) and the dim inserts an *inferred member* with placeholder attributes, flagged `is_inferred`, that is overwritten when the real row arrives. `dim_pub_date` is mandatory (one row per calendar day, VN calendar). DIM tables SHOULD stay ≤ 10M rows and SHOULD be a daily full-snapshot partition (Alibaba); larger ones need a written reason. Role-playing, junk dimensions; *degenerate dimension* means a transaction identifier kept on the fact with no dim table (Kimball sense). |
| `05-facts.md` | Transaction / periodic snapshot / accumulating snapshot; mandatory grain statement; one grain per table; all measures in the same unit; explicit null policy for measures; additive / semi-additive / non-additive measures, with non-additive measures stored as numerator + denominator. **Fact ↔ SCD join (D11):** facts store durable keys; an attribute marked `historical` is resolved in DWD by joining `dim_*_hist` on `durable_key` and `event_at` within `[valid_from, valid_to)`, and stored on the fact; `current` attributes are read from `dim_*` at query time. *Dimension denormalization* (Alibaba's "degenerating" DIM attributes into DWD) is allowed for frequently used attributes and is a different thing from a degenerate dimension; the file uses the two names consistently. |
| `06-metrics.md` | Atomic = process + measure + aggregation; derived = period + modifiers + atomic + grain; calculated = formula (Kimball extension). Metric column template `{modifier}_{atomic}_{agg}_{period}`, modifier optional (e.g. `app_pay_amt_sum_30d`, `pay_order_cnt_1d`). Ratios and other non-additive results are `calculated` metrics over stored numerator/denominator columns. `metrics.yml` schema. |
| `07-dws-ads.md` | DWS grain by dimension; **one statistical period per DWS table**, default triple `_1d` / `_nd` / `_td`; every DWS metric column maps to a derived metric. A DWS table is built only when it has ≥ 2 consumers or recorded performance evidence (baseline from `dwh-verify`); otherwise consumers read DWD + DIM. ADS serves one stated application need and names its consumer (D13). |
| `08-iceberg-incremental.md` | Partition by `dt` = Asia/Ho_Chi_Minh day (D12); source-timestamp conversion and the day window; idempotency; partition replacement (`pre_hook` delete + append) vs `merge`; `unique_key`; per-source **delete handling** (`none` / `soft_delete_flag` / `full_compare`); **late-arriving facts** (a re-run of the affected `dt`s, and a lookback window for `di` sources whose watermark can lag); per-layer retention (§4); Iceberg maintenance (optimize, expire snapshots, orphan files). |
| `09-dbt-conventions.md` | Materialization per layer; minimum tests per layer; contracts on DIM/DWD/DWS; tags `domain:*`, `layer:*`, `ods_<source>`; every column described. Generic test arguments nested under `arguments:` (dbt ≥ 1.11). |
| `10-trino-sql-style.md` | sqlfluff `trino` dialect; CTE style; no `SELECT *` outside ODS; filter partitions early; watch join fan-out; approximate functions (`approx_distinct`, …) only in ADS. |
| `11-airflow.md` | One DAG per source system / domain; Cosmos `DbtDag`; timezone-aware DAGs and the `dt` template (D12); Asset scheduling (env-dependent URIs); `default_args`, retries, SLA, owner and tags. A DAG file must contain the word `airflow` or the DAG processor skips it (safe mode). |
| `12-data-quality.md` | Test severities (`error` blocks, `warn` alerts); source freshness; ODS ↔ DWD row-count and amount reconciliation; inferred-member count as a monitored metric. |

The writer of the rulebook (plan 3) must read the Alibaba "Build and optimize a data warehouse" section
in full ([digest](../research/2026-11-04-alibaba-dwh-digest.md)) and cite the corresponding Alibaba page
next to each adopted rule. Rules that come from Kimball and not from Alibaba (SCD types, surrogate and
durable keys, special members, calculated metrics, `ods_`/`ads_` naming, fact ↔ SCD join) cite Kimball
instead; they are never attributed to Alibaba. Where this spec and Alibaba differ (e.g. no
business-segment prefix, D10), the spec wins and the difference is noted in the file. Inconsistencies in
the Alibaba pages listed in the digest (item 19) are not copied.

### 7.1 Agent entry point (`AGENTS.md`)

Short (≤ 150 lines): the non-negotiables (layer dependency rules, grain first, reuse before create,
never claim done without evidence), the list of skills with one-line triggers, and "before doing X read
Y" pointers into `docs/standards/`. Tools that do not auto-trigger skills (Cursor, Copilot, Codex) are
instructed to open `skills/dwh-start/SKILL.md` first for any data change.

## 8. Enforcement and verification

### 8.1 Two enforcement layers

1. **pre-commit** (local / inside the AI session): `dwh lint --changed`, `sqlfluff`, `dwh sync-agents --check`, `ruff`.
2. **GitHub Actions** (required to merge):
   - `dwh lint` — YAML ↔ dbt cross-checks. Rule families:
     - `DWH-N*` naming, including one valid period suffix per DWS table
     - `DWH-L*` layer dependencies and chain depth ≤ 10 (from `manifest.json`)
     - `DWH-M*` every DWS/ADS metric column is declared in `metrics.yml`; derived metrics resolve to an atomic metric; no precomputed non-additive column in DWD/DWS
     - `DWH-B*` every DWD maps to a bus-matrix cell
     - `DWH-T*` minimum tests per layer present
     - `DWH-D*` descriptions present
     - `DWH-S*` every source table declares load type, watermark, source timezone and delete handling; a `di` load with `none` delete handling requires a written reason
     - `DWH-Y*` warehouse YAML: JSON Schema (Y01) and cross-file consistency (Y02–Y06)
   - Design gate check (§6.3) (`dwh design-gate`, codes `DWH-G*`, workflow `design-gate.yml`).
   - `dbt build --select state:modified+ --defer` on a CI Trino schema `ci_pr_<n>`, deferring to
     production, limited to recent `dt`s.
   - pytest DAG integrity: imports, owner and tags set, no duplicate DAG ids.
   - On merge to `main`: build and publish the catalogue (§5).

`dwh` is a Python package that reads only YAML and `manifest.json` (generated by `dbt parse`), so it
needs no Trino connection. Every rule has a unit test and a failing fixture in
`tools/dwh/tests/fixtures/`.

### 8.2 Verifying the skills themselves

Skills are written test-first (superpowers:writing-skills): scenarios exist before the skill text.

- `evals/scenarios/` — about 10 scenarios with expected behaviour, including:
  - "add 7-day GMV by shop" → reuses atomic `pay_amt`, adds one derived metric, creates no new DWD;
  - "add CRM source" → stops for design approval;
  - "report needs revenue by channel" → consults the bus matrix before proposing;
  - pressure scenario ("urgent, just write the SQL") → still classifies the change first.
- Each scenario runs headless on Claude Code (`claude -p`) and one other tool (Codex or Cursor CLI);
  graded by `dwh lint` plus a checklist. Re-run on every skill change.

## 9. Delivery plan

Each step gets its own implementation plan (writing-plans), executed in order:

1. **Repo skeleton** — Airflow project, Dockerfile, dbt-trino + Cosmos wiring, `.airflowignore`, basic CI, DAG integrity tests. *Done 2026-11-04 (PR #1); capabilities recorded in `docs/en/verification/2026-11-04-plan1-capabilities.md`.*
2. **`warehouse/` + `dwh lint`** — JSON Schemas, YAML loaders, rule families N/L/M/B/T/D/S with fixtures, catalogue generation. Also carries the plan 1 follow-ups: timezone-aware `dt` (D12) with the boundary test, source `meta` for the existing ODS models, locked transitive image dependencies (constraints file), CI actions pinned to commit SHAs.
3. **Rulebook + skills** — `docs/standards/`, `skills/`, `AGENTS.md`, `dwh sync-agents`, `dwh scaffold`, pre-commit.
4. **Reference domain** — one end-to-end domain (ODS → DIM/DWD → DWS → ADS) built by following the skills; doubles as the fixture for `evals/scenarios/`.

## 10. Assumptions and open items

- Trino, an Iceberg catalog (REST/HMS/Nessie) and an Airflow cluster on the official Helm chart exist;
  this repo does not provision them.
- Verified in plan 1 against the pinned versions: dbt-trino `merge` and `snapshot` on Iceberg, partition
  replacement, Cosmos Asset events for each model run. Not yet measured: whether an event on an asset
  with no consumer DAG yet later triggers a newly added consumer (plan 4). The local stack uses an
  Iceberg JDBC catalog on Postgres; production may use REST/HMS/Nessie.
- Catalogue: GitHub Pages (plan 2).
- The reference domain (plan 4) is chosen by the team; until then examples in the rulebook use a
  generic `trade` domain (order, payment).
- Retention defaults (§4) are a starting point; the team adjusts them per legal and cost needs.

## 11. Amendment log

**2026-11-04**, after plan 1 and a full reading of the 19 Alibaba pages
([digest](../research/2026-11-04-alibaba-dwh-digest.md)), approved by the project owner:

- From Alibaba: one statistical period per DWS table and the `1d/nd/td/1w/hh/mm` suffixes (§5, `02`,
  `07`); per-layer retention (§4); chain depth ≤ 10, DWS on coarser DWS, accumulating snapshots read
  transaction facts (`01`); DIM ≤ 10M rows and daily snapshot as SHOULD (`04`); performance baseline
  and before/after validation in `dwh-verify` (§6.2).
- Naming: `dim_pub_{dim}` / `dim_{domain}_{dim}`; metric column `{modifier}_{atomic}_{agg}_{period}`;
  *dimension denormalization* (Alibaba) kept apart from *degenerate dimension* (Kimball); Kimball-only
  rules cited as Kimball (§7). D10 unchanged.
- New decisions D11 (SCD4 default), D12 (`dt` = Asia/Ho_Chi_Minh day), D13 (BI reads DWD + DIM).
- Kimball gaps closed: fact ↔ SCD join semantics; historical vs current attributes; non-additive
  measures as numerator/denominator; timezone; per-source delete handling; late-arriving facts and
  inferred members; special-member key type; mandatory `dim_pub_date`; DWS only with ≥ 2 consumers or
  performance evidence; BI access path. Lint family `DWH-S` added.
- Plan 1 facts written back: ODS partition replacement is `pre_hook` delete + append; Airflow 3
  "Assets" and Cosmos `DbtDag`; read-only code volume; dbt 1.11 `arguments:` test syntax; DAG files
  must contain the word `airflow`.
- Plan 2 review (user decision): ADS may read DIM; the ADS period suffix is optional.
- **Plan 2:** DWH-Y and DWH-G code families added; catalogue on GitHub Pages.
