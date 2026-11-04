# example-dwh — Kimball/OneData data warehouse with AI-ready development rules

- **Date:** 2026-11-04
- **Status:** Approved in brainstorming, pending written-spec review
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

Out of scope: BI/semantic-layer serving, data catalog products, infrastructure provisioning of Trino /
Iceberg catalog / Airflow cluster (assumed to exist).

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
│   └── en/specs/                    # specs like this one
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
   └── emits Airflow Datasets ──► triggers domain DAGs
```

- **ODS ingestion (D7):** each source system is a Trino catalog declared as a dbt `source`. Each ODS
  model `ods_{source}_{table}_{di|df}` is a physical Iceberg table reading `source()`:
  - `df` (daily full): full copy into partition `dt`. For small and reference tables.
  - `di` (daily incremental): rows whose watermark (e.g. `updated_at`) falls in `dt`, written with
    `incremental_strategy='merge'` (by key) or partition replacement.
- **Orchestration:** one Cosmos `DbtTaskGroup` per DAG, selecting by tag. Variable `dt` is passed from
  the Airflow logical date (`--vars '{"dt": "{{ ds }}"}'`). Cross-DAG dependencies use Airflow Datasets
  emitted by Cosmos, not `ExternalTaskSensor`.
- **Idempotency:** re-running any task for the same `dt` produces the same result; backfill is
  re-running past `dt`s (see `dwh-backfill`).

## 5. Design metadata (`warehouse/`)

YAML files, each validated by a JSON Schema in `warehouse/schemas/`:

| File | Contents |
|------|----------|
| `domains.yml` | Data domains: name (glossary root), description, owner. |
| `processes.yml` | Business processes: name, domain, description, fact type (transaction / periodic snapshot / accumulating snapshot), grain statement. |
| `dimensions.yml` | Conformed dimensions: name, scope (`pub` or domain), natural key, SCD type, attributes. |
| `bus_matrix.yml` | Process × dimension matrix (which dimensions each process uses, with role names for role-playing). |
| `metrics.yml` | `atomic` (process + measure + aggregation), `derived` (atomic + period + modifiers + grain), `calculated` (formula over other metrics). |
| `modifiers.yml` | Business filters (Alibaba "modifiers"): name, SQL predicate description, applicable processes. |
| `periods.yml` | Statistical periods: `1d`, `7d`, `30d`, `nd`, `td` (to date), `1h`, … |
| `glossary.yml` | Root words allowed in table and column names, with meaning and abbreviation. |

CI renders these plus `dbt docs` into a static catalogue (bus matrix, metric dictionary, glossary) on
merge to `main`. Publishing target (GitHub Pages or internal host) is chosen during implementation of
plan 2.

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
   counts, grain uniqueness, reconciliation to source. Never claim done without real output as evidence.
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
| `01-layers.md` | Role of each layer and **dependency rules**: ODS ← source; DIM/DWD ← ODS (and DIM); DWS ← DWD + DIM; ADS ← DWS (DWD allowed with a written reason in the model `.yml`). No upward reads. Only ODS may call `source()`. |
| `02-naming.md` | `ods_{source}_{table}_{di\|df}` · `dim_{pub\|domain}_{dimension}` · `dwd_{domain}_{process}_{di\|df}` · `dws_{domain}_{grain}_{custom}_{1d\|nd\|td}` · `ads_{app}_{subject}_{period}`. Column suffixes: `_id`/`_key` keys, `is_` flags, `_date` dates, `_at` timestamps, `_amt` money, `_cnt` counts. Every name segment must exist in `glossary.yml`. |
| `03-domains-bus-matrix.md` | How to divide domains and processes; how to build the bus matrix; what counts as model-extending. |
| `04-dimensions.md` | Conformed dimensions; hash surrogate keys (`dbt_utils.generate_surrogate_key`); unknown member `-1`; SCD1 as `df`; SCD2 via dbt snapshot → `dim_*` with `valid_from`, `valid_to`, `is_current`; role-playing, junk, degenerate dimensions. |
| `05-facts.md` | Transaction / periodic snapshot / accumulating snapshot; mandatory grain statement; additive / semi-additive / non-additive measures; degenerating frequently used DIM attributes into DWD (Alibaba practice) and its limits. |
| `06-metrics.md` | Atomic = process + measure; derived = period + modifiers + atomic + grain; calculated = formula. Column name `{modifier}_{atomic}_{period}` (e.g. `app_pay_amt_30d`). `metrics.yml` schema. |
| `07-dws-ads.md` | DWS grain by dimension; every DWS metric column maps to a derived metric. ADS serves one stated need and names its consumer. |
| `08-iceberg-incremental.md` | Partition by `dt`; `dt` var from Airflow; idempotency; `merge` vs partition replacement; late-arriving data; `unique_key`; Iceberg maintenance (optimize, expire snapshots). |
| `09-dbt-conventions.md` | Materialization per layer; minimum tests per layer; contracts on DIM/DWD/DWS; tags `domain:*`, `layer:*`, `ods_<source>`; every column described. |
| `10-trino-sql-style.md` | sqlfluff `trino` dialect; CTE style; no `SELECT *` outside ODS; filter partitions early; watch join fan-out; approximate functions (`approx_distinct`, …) only in ADS. |
| `11-airflow.md` | One DAG per source system / domain; Cosmos `DbtTaskGroup`; Dataset scheduling; `default_args`, retries, SLA, owner and tags. |
| `12-data-quality.md` | Test severities (`error` blocks, `warn` alerts); source freshness; ODS ↔ DWD row-count and amount reconciliation. |

The writer of the rulebook (plan 3) must read the Alibaba "Build and optimize a data warehouse" section
in full and cite the corresponding Alibaba page next to each adopted rule. Where this spec and Alibaba
differ (e.g. no business-segment prefix, D10), the spec wins and the difference is noted in the file.

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
     - `DWH-N*` naming
     - `DWH-L*` layer dependencies (from `manifest.json`)
     - `DWH-M*` every DWS/ADS metric column is declared in `metrics.yml`; derived metrics resolve to an atomic metric
     - `DWH-B*` every DWD maps to a bus-matrix cell
     - `DWH-T*` minimum tests per layer present
     - `DWH-D*` descriptions present
   - Design gate check (§6.3).
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

1. **Repo skeleton** — Airflow project, Dockerfile, dbt-trino + Cosmos wiring, `.airflowignore`, basic CI, DAG integrity tests.
2. **`warehouse/` + `dwh lint`** — JSON Schemas, YAML loaders, rule families N/L/M/B/T/D with fixtures, catalogue generation.
3. **Rulebook + skills** — `docs/standards/`, `skills/`, `AGENTS.md`, `dwh sync-agents`, `dwh scaffold`, pre-commit.
4. **Reference domain** — one end-to-end domain (ODS → DIM/DWD → DWS → ADS) built by following the skills; doubles as the fixture for `evals/scenarios/`.

## 10. Assumptions and open items

- Trino, an Iceberg catalog (REST/HMS/Nessie) and an Airflow cluster on the official Helm chart exist;
  this repo does not provision them.
- dbt-trino `merge` on Iceberg and Cosmos Dataset emission are verified against the pinned versions in
  plan 1 before the standards depend on them.
- Catalogue publishing target is decided in plan 2.
- The reference domain (plan 4) is chosen by the team; until then examples in the rulebook use a
  generic `trade` domain (order, payment).
