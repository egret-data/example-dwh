# Plan 1 — Repo skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A runnable Airflow + dbt-trino + Cosmos project on Iceberg that loads one source system into ODS end-to-end, with a local dev stack, DAG integrity tests, capability checks, and CI.

**Architecture:** The repo is an Airflow project cloned by git-sync (`subPath: dags`). The dbt project lives in `dags/dbt/` and runs through Cosmos `DbtDag` using a dbt executable from a separate virtualenv baked into the image. A docker-compose dev stack (Postgres as source + Iceberg JDBC catalog, RustFS as S3, Trino) mirrors production paths; the Airflow container mounts the repo at the same path git-sync uses.

**Tech Stack:** Apache Airflow 3.3.2 (Python 3.12) · astronomer-cosmos 1.16.0 · dbt-core 1.11.16 · dbt-trino 1.11.0 · dbt_utils 1.4.1 · Trino 483 · Apache Iceberg (JDBC catalog on Postgres) · RustFS 1.0.1 · Postgres 17.6 · pytest 9.2.0 · ruff 0.17.3 · official Airflow Helm chart 1.22.0.

**Spec:** `docs/en/specs/2026-11-04-kimball-dwh-design.md` (§3, §4, §8.1 partially, §9 step 1, §10).

## Global Constraints

- Repo root: `/Users/1pro-l4r8/Documents/github/example-dwh`. All paths below are relative to it.
- Airflow `dags_folder` = `<repo>/dags` (git-sync `subPath: "dags"`); the repo is mounted/cloned at `/opt/airflow/dags/repo`.
- dbt project at `dags/dbt/`, profile name `example_dwh`, project name `example_dwh`.
- dbt runs from `/opt/dbt-venv/bin/dbt` (separate venv), never from the Airflow interpreter. Cosmos uses `InvocationMode.SUBPROCESS` and `LoadMode.DBT_LS`.
- dbt packages are installed at image build into `/opt/dbt_packages`; never at task runtime (`install_dbt_deps=False`).
- dbt `target/` and logs go to `/tmp/dbt/...` (git-sync volume is read-only).
- `profiles.yml` reads only environment variables; no secrets in the repo. Dev-stack credentials (`dwh`/`dwhsecret`) are local-only.
- Layers are dbt folders `models/{ods,dim,dwd,dws,ads}`; schemas: `prod` → `ods`, `dim`, …; other targets → `<DBT_SCHEMA>_ods`, …
- Partition column `dt` (DATE); `dt` is passed from Airflow as `{{ ds }}`.
- ODS naming: `ods_{source}_{table}_{di|df}`; tag `ods_<source>` on every ODS model of a source.
- Pin every version exactly as in Tech Stack. Python code passes `ruff check` and `ruff format --check` (ruff 0.17.3, line length 110).
- Commits follow Conventional Commits and end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Work on branch `feat/plan1-repo-skeleton`, not `main`.
- Destructive test cleanup only touches schemas named exactly `itest` / `itest_cap` or starting with `itest_` / `itest_cap_`, filtered in Python (never SQL `LIKE`, where `_` is a wildcard).

## File map

| Path | Responsibility | Task |
|------|----------------|------|
| `.gitignore`, `.editorconfig`, `pyproject.toml`, `Makefile` | repo hygiene, ruff config, task runner | 1 (Makefile grows in 2–6) |
| `dev/compose.yml` | local stack: postgres, rustfs, rustfs-init, trino, airflow (tools profile) | 1 (airflow service in 2) |
| `dev/postgres/init/01-init.sql` | source DB `shop` with fixture rows + `iceberg_catalog` DB | 1 |
| `dev/trino/catalog/{iceberg,shop}.properties` | Trino catalogs | 1 |
| `dev/wait-for-trino.sh`, `dev/smoke.sql`, `dev/smoke.sh` | readiness + Iceberg/MERGE smoke | 1 |
| `Dockerfile`, `requirements.txt`, `requirements-dbt.txt` | image: Airflow + Cosmos, dbt venv, baked dbt packages | 2 |
| `dags/dbt/{dbt_project.yml,packages.yml,package-lock.yml,profiles.yml}` | dbt project config | 2 |
| `dags/dbt/macros/{generate_schema_name.sql,get_dt.sql}` | schema naming per layer, `dt` var | 2 |
| `dags/dbt/models/{dim,dwd,dws,ads}/.gitkeep` | layer folders | 2 |
| `dags/dbt/models/ods/shop/*` | source + two ODS models + tests | 3 |
| `tests/integration/{conftest.py,test_ods_shop.py}` | ODS idempotency against the dev stack | 3 |
| `tests/integration/dbt_capabilities/**`, `tests/integration/test_capabilities.py` | merge + SCD2 snapshot capability checks | 4 |
| `dags/.airflowignore`, `dags/_common/{__init__,defaults,dbt}.py`, `dags/sources/dbt_ods_shop.py` | Cosmos wiring + ODS DAG | 5 |
| `tests/dags/{conftest.py,test_dag_integrity.py}` | DAG integrity | 5 |
| `dev/e2e.sh`, `docs/en/verification/2026-11-04-plan1-capabilities.md` | Airflow end-to-end run + recorded results | 6 |
| `.github/workflows/ci.yml`, `deploy/helm/values.example.yaml`, `README.md` | CI, git-sync deployment example, docs | 7 |

---

### Task 1: Local dev stack (Postgres source, RustFS, Trino + Iceberg)

**Files:**
- Create: `.gitignore`, `.editorconfig`, `pyproject.toml`, `Makefile`
- Create: `dev/compose.yml`, `dev/postgres/init/01-init.sql`, `dev/trino/catalog/iceberg.properties`, `dev/trino/catalog/shop.properties`
- Create: `dev/wait-for-trino.sh`, `dev/smoke.sql`, `dev/smoke.sh`

**Interfaces:**
- Produces: compose project `example-dwh`; services `postgres`, `rustfs`, `rustfs-init`, `trino` (in-network `trino:8080`, host `localhost:28080`); Trino catalogs `iceberg` (Iceberg, warehouse `s3://warehouse/`) and `shop` (Postgres DB `shop`, schema `public`, tables `orders`, `customers`); make targets `dev-up`, `dev-down`, `smoke`, `lint`, `fmt`.
- Fixture data contract (later tasks assert on it): `orders` rows updated on 2026-11-01 = 1, 2026-11-02 = 2, 2026-11-03 = 3 (6 total); `customers` = 3 rows.

- [ ] **Step 1: Create the branch and repo hygiene files**

```bash
cd /Users/1pro-l4r8/Documents/github/example-dwh
git checkout -b feat/plan1-repo-skeleton
```

`.gitignore`:

```gitignore
__pycache__/
*.pyc
.venv/
.env
.pytest_cache/
.ruff_cache/
dags/dbt/target/
dags/dbt/dbt_packages/
dags/dbt/logs/
logs/
```

`.editorconfig`:

```ini
root = true

[*]
end_of_line = lf
insert_final_newline = true
charset = utf-8
indent_style = space
indent_size = 4

[*.{yml,yaml,sql,md,json}]
indent_size = 2

[Makefile]
indent_style = tab
```

`pyproject.toml`:

```toml
[project]
name = "example-dwh"
version = "0.1.0"
requires-python = ">=3.12"

[tool.ruff]
target-version = "py312"
line-length = 110
src = ["dags", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]

[tool.ruff.lint.isort]
known-first-party = ["_common"]
```

- [ ] **Step 2: Write the Postgres init script**

`dev/postgres/init/01-init.sql`:

```sql
-- Local dev only. Source system "shop" + the database backing the Iceberg JDBC catalog.
CREATE DATABASE shop;
CREATE DATABASE iceberg_catalog;

\connect shop

CREATE TABLE public.customers (
    customer_id   BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    city          TEXT,
    created_at    TIMESTAMP NOT NULL,
    updated_at    TIMESTAMP NOT NULL
);

INSERT INTO public.customers VALUES
    (101, 'An',   'Hanoi',       '2026-10-01 08:00:00', '2026-10-01 08:00:00'),
    (102, 'Binh', 'Ho Chi Minh', '2026-10-05 09:00:00', '2026-11-02 10:00:00'),
    (103, 'Chi',  'Da Nang',     '2026-10-09 10:00:00', '2026-10-09 10:00:00');

CREATE TABLE public.orders (
    order_id     BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL REFERENCES public.customers (customer_id),
    order_status TEXT NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    created_at   TIMESTAMP NOT NULL,
    updated_at   TIMESTAMP NOT NULL
);

-- updated_at per day: 2026-11-01 -> 1 row, 2026-11-02 -> 2 rows, 2026-11-03 -> 3 rows.
INSERT INTO public.orders VALUES
    (1, 101, 'paid',      120000.00, '2026-11-01 09:00:00', '2026-11-01 09:30:00'),
    (2, 102, 'shipped',    80000.00, '2026-11-01 11:00:00', '2026-11-02 08:00:00'),
    (3, 103, 'paid',      250000.00, '2026-11-02 14:00:00', '2026-11-02 14:05:00'),
    (4, 101, 'cancelled',  40000.00, '2026-11-02 20:00:00', '2026-11-03 07:00:00'),
    (5, 102, 'paid',       99000.00, '2026-11-03 10:00:00', '2026-11-03 10:01:00'),
    (6, 103, 'created',    15000.00, '2026-11-03 23:00:00', '2026-11-03 23:59:59');
```

- [ ] **Step 3: Write the Trino catalogs**

`dev/trino/catalog/iceberg.properties`:

```properties
connector.name=iceberg
iceberg.catalog.type=jdbc
iceberg.jdbc-catalog.catalog-name=dwh
iceberg.jdbc-catalog.driver-class=org.postgresql.Driver
iceberg.jdbc-catalog.connection-url=jdbc:postgresql://postgres:5432/iceberg_catalog
iceberg.jdbc-catalog.connection-user=dwh
iceberg.jdbc-catalog.connection-password=dwhsecret
iceberg.jdbc-catalog.default-warehouse-dir=s3://warehouse/
fs.native-s3.enabled=true
s3.endpoint=http://rustfs:9000
s3.region=us-east-1
s3.path-style-access=true
s3.aws-access-key=dwh
s3.aws-secret-key=dwhsecret
```

`dev/trino/catalog/shop.properties`:

```properties
connector.name=postgresql
connection-url=jdbc:postgresql://postgres:5432/shop
connection-user=dwh
connection-password=dwhsecret
```

- [ ] **Step 4: Write the compose file**

`dev/compose.yml`:

```yaml
# Local dev stack. Credentials here are for this stack only.
name: example-dwh

services:
  postgres:
    image: postgres:17.6
    environment:
      POSTGRES_USER: dwh
      POSTGRES_PASSWORD: dwhsecret
      POSTGRES_DB: dwh
    ports:
      - "25432:5432"
    volumes:
      - ./postgres/init:/docker-entrypoint-initdb.d:ro
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dwh -d shop"]
      interval: 3s
      timeout: 3s
      retries: 40

  rustfs:
    image: rustfs/rustfs:1.0.1
    environment:
      RUSTFS_ACCESS_KEY: dwh
      RUSTFS_SECRET_KEY: dwhsecret
    ports:
      - "29000:9000"
    volumes:
      - rustfsdata:/data
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:9000/health || exit 1"]
      interval: 3s
      timeout: 3s
      retries: 40

  rustfs-init:
    image: amazon/aws-cli:2.37.9
    depends_on:
      rustfs: { condition: service_healthy }
    restart: "no"
    environment:
      AWS_ACCESS_KEY_ID: dwh
      AWS_SECRET_ACCESS_KEY: dwhsecret
      AWS_DEFAULT_REGION: us-east-1
      AWS_ENDPOINT_URL: http://rustfs:9000
    entrypoint: ["/bin/sh", "-c"]
    command:
      - aws s3api head-bucket --bucket warehouse 2>/dev/null || aws s3api create-bucket --bucket warehouse

  trino:
    image: trinodb/trino:483
    depends_on:
      postgres: { condition: service_healthy }
      rustfs-init: { condition: service_completed_successfully }
    ports:
      - "28080:8080"
    volumes:
      - ./trino/catalog:/etc/trino/catalog:ro

volumes:
  pgdata:
  rustfsdata:
```

- [ ] **Step 5: Write the readiness and smoke scripts**

`dev/wait-for-trino.sh`:

```bash
#!/usr/bin/env bash
# Waits until Trino answers a query (max 180s).
set -euo pipefail
COMPOSE=(docker compose -f "$(dirname "$0")/compose.yml")
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T trino trino --execute "SELECT 1" >/dev/null 2>&1; then
    echo "trino ready"
    exit 0
  fi
  sleep 3
done
echo "trino not ready after 180s" >&2
exit 1
```

`dev/smoke.sql`:

```sql
CREATE SCHEMA IF NOT EXISTS iceberg.smoke;
DROP TABLE IF EXISTS iceberg.smoke.t;
CREATE TABLE iceberg.smoke.t (id BIGINT, v VARCHAR, dt DATE) WITH (partitioning = ARRAY['dt']);
INSERT INTO iceberg.smoke.t VALUES (1, 'a', DATE '2026-11-01'), (2, 'b', DATE '2026-11-01');
MERGE INTO iceberg.smoke.t t
USING (VALUES (BIGINT '2', 'b2', DATE '2026-11-02'), (BIGINT '3', 'c', DATE '2026-11-02')) AS s (id, v, dt)
  ON t.id = s.id
WHEN MATCHED THEN UPDATE SET v = s.v, dt = s.dt
WHEN NOT MATCHED THEN INSERT (id, v, dt) VALUES (s.id, s.v, s.dt);
SELECT id, v, dt FROM iceberg.smoke.t ORDER BY id;
SELECT count(*) FROM shop.public.orders;
DROP TABLE iceberg.smoke.t;
DROP SCHEMA iceberg.smoke;
```

`dev/smoke.sh`:

```bash
#!/usr/bin/env bash
# Proves: Iceberg JDBC catalog + S3 writes, partitioned table, MERGE, and the shop source catalog.
set -euo pipefail
DIR="$(dirname "$0")"
docker compose -f "$DIR/compose.yml" exec -T trino trino --execute "$(cat "$DIR/smoke.sql")"
```

```bash
chmod +x dev/wait-for-trino.sh dev/smoke.sh
```

- [ ] **Step 6: Write the Makefile**

`Makefile`:

```makefile
COMPOSE := docker compose -f dev/compose.yml

.PHONY: dev-up dev-down smoke lint fmt

dev-up:
	$(COMPOSE) up -d trino
	./dev/wait-for-trino.sh

dev-down:
	$(COMPOSE) down -v

smoke:
	./dev/smoke.sh

lint:
	uvx ruff@0.17.3 check .
	uvx ruff@0.17.3 format --check .

fmt:
	uvx ruff@0.17.3 check --fix .
	uvx ruff@0.17.3 format .
```

- [ ] **Step 7: Bring the stack up and run the smoke test**

Run: `make dev-up && make smoke`

Expected stdout ends with exactly:

```text
"1","a","2026-11-01"
"2","b2","2026-11-02"
"3","c","2026-11-02"
"6"
```

If Trino fails to start, run `docker compose -f dev/compose.yml logs trino | tail -50` and fix the catalog file it names before continuing.

- [ ] **Step 8: Commit**

```bash
git add .gitignore .editorconfig pyproject.toml Makefile dev/
git commit -m "chore: add local dev stack with Trino, Iceberg JDBC catalog and RustFS

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: dbt project skeleton and the Airflow/dbt image

**Files:**
- Create: `requirements.txt`, `requirements-dbt.txt`, `Dockerfile`
- Create: `dags/dbt/dbt_project.yml`, `dags/dbt/packages.yml`, `dags/dbt/package-lock.yml` (generated), `dags/dbt/profiles.yml`
- Create: `dags/dbt/macros/generate_schema_name.sql`, `dags/dbt/macros/get_dt.sql`
- Create: `dags/dbt/models/{dim,dwd,dws,ads}/.gitkeep`, `dags/dbt/{snapshots,tests,seeds}/.gitkeep`
- Modify: `dev/compose.yml` (add `airflow` service), `Makefile` (add `image`, `dbt-parse`)

**Interfaces:**
- Consumes: Task 1 stack (`trino:8080`, catalog `iceberg`).
- Produces: image `example-dwh-airflow:dev` (target `dev`, adds pytest to both interpreters) and target `prod`; env in image `DBT_EXECUTABLE_PATH=/opt/dbt-venv/bin/dbt`, `DBT_PACKAGES_INSTALL_PATH=/opt/dbt_packages`, `DBT_TARGET_PATH=/tmp/dbt/target`, `DBT_LOG_PATH=/tmp/dbt/logs`; compose service `airflow` (profile `tools`, repo mounted at `/opt/airflow/dags/repo`, entrypoint `bash -c`); dbt macro `get_dt()` → `'YYYY-MM-DD'` string; dbt env contract `DBT_TARGET` (`dev`|`ci`|`prod`), `DBT_SCHEMA`, `TRINO_HOST`, `TRINO_PORT`, `TRINO_USER`, `TRINO_CATALOG`, `TRINO_HTTP_SCHEME`, `TRINO_AUTH_METHOD`, `TRINO_PASSWORD`.

- [ ] **Step 1: Write the dbt project config**

`dags/dbt/dbt_project.yml`:

```yaml
name: example_dwh
version: "0.1.0"
config-version: 2
profile: example_dwh

model-paths: ["models"]
macro-paths: ["macros"]
snapshot-paths: ["snapshots"]
test-paths: ["tests"]
seed-paths: ["seeds"]
# Packages are baked into the image (git-sync volume is read-only).
packages-install-path: "{{ env_var('DBT_PACKAGES_INSTALL_PATH', 'dbt_packages') }}"

models:
  example_dwh:
    +on_schema_change: fail
    ods:
      +schema: ods
      +materialized: incremental
      +tags: ["layer:ods"]
      shop:
        +tags: ["ods_shop"]
    dim:
      +schema: dim
      +materialized: table
      +tags: ["layer:dim"]
    dwd:
      +schema: dwd
      +materialized: incremental
      +tags: ["layer:dwd"]
    dws:
      +schema: dws
      +materialized: incremental
      +tags: ["layer:dws"]
    ads:
      +schema: ads
      +materialized: table
      +tags: ["layer:ads"]
```

`dags/dbt/packages.yml`:

```yaml
packages:
  - package: dbt-labs/dbt_utils
    version: 1.4.1
```

`dags/dbt/profiles.yml`:

```yaml
# Environment variables only. No secrets in this file.
example_dwh:
  target: "{{ env_var('DBT_TARGET', 'dev') }}"
  outputs:
    dev: &trino
      type: trino
      method: "{{ env_var('TRINO_AUTH_METHOD', 'none') }}"
      user: "{{ env_var('TRINO_USER', 'dbt') }}"
      password: "{{ env_var('TRINO_PASSWORD', '') }}"
      host: "{{ env_var('TRINO_HOST', 'localhost') }}"
      port: "{{ env_var('TRINO_PORT', '8080') | as_number }}"
      http_scheme: "{{ env_var('TRINO_HTTP_SCHEME', 'http') }}"
      database: "{{ env_var('TRINO_CATALOG', 'iceberg') }}"
      schema: "{{ env_var('DBT_SCHEMA', 'dev') }}"
      threads: 4
    ci: *trino
    prod: *trino
```

- [ ] **Step 2: Write the macros**

`dags/dbt/macros/generate_schema_name.sql`:

```sql
{#
  prod: layer schema as-is (ods, dim, dwd, dws, ads).
  other targets: <target.schema>_<layer>, e.g. dev_viet_ods, ci_pr_12_ods.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- if custom_schema_name is none -%}
    {{ target.schema }}
  {%- elif target.name == 'prod' -%}
    {{ custom_schema_name | trim }}
  {%- else -%}
    {{ target.schema }}_{{ custom_schema_name | trim }}
  {%- endif -%}
{%- endmacro %}
```

`dags/dbt/macros/get_dt.sql`:

```sql
{#
  The partition date being processed, as 'YYYY-MM-DD'.
  Airflow passes --vars '{dt: <ds>}'. Default: yesterday (for manual dev runs).
  Validated only at execution time, because `dbt ls`/parse render with placeholder values.
#}
{% macro get_dt() -%}
  {%- set default_dt = (modules.datetime.date.today() - modules.datetime.timedelta(days=1)).isoformat() -%}
  {%- set dt = var('dt', default_dt) | string -%}
  {%- if execute -%}
    {%- do modules.datetime.date.fromisoformat(dt) -%}
  {%- endif -%}
  {{- return(dt) -}}
{%- endmacro %}
```

```bash
mkdir -p dags/dbt/models/{dim,dwd,dws,ads} dags/dbt/{snapshots,tests,seeds}
touch dags/dbt/models/{dim,dwd,dws,ads}/.gitkeep dags/dbt/{snapshots,tests,seeds}/.gitkeep
```

- [ ] **Step 3: Generate `package-lock.yml` with the pinned dbt**

Run:

```bash
docker run --rm -v "$PWD/dags/dbt:/w" -w /w python:3.12-slim sh -c \
  "pip install -q dbt-core==1.11.16 dbt-trino==1.11.0 && dbt deps && rm -rf dbt_packages"
cat dags/dbt/package-lock.yml
```

Expected: `package-lock.yml` lists `dbt-labs/dbt_utils` version `1.4.1` with a `sha1_hash`.

- [ ] **Step 4: Write requirements and the Dockerfile**

`requirements.txt` (installed into the Airflow interpreter):

```text
apache-airflow==3.3.2
astronomer-cosmos==1.16.0
```

`requirements-dbt.txt` (installed into `/opt/dbt-venv`):

```text
dbt-core==1.11.16
dbt-trino==1.11.0
```

`Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1
FROM apache/airflow:3.3.2-python3.12 AS base

USER root
RUN python -m venv /opt/dbt-venv \
    && mkdir -p /opt/dbt_packages /tmp/dbt \
    && chown -R airflow: /opt/dbt-venv /opt/dbt_packages /tmp/dbt
USER airflow

# Airflow side: pinning apache-airflow stops pip from up/downgrading the base install.
COPY --chown=airflow requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# dbt side: separate venv so dbt and Airflow never share dependency pins.
COPY --chown=airflow requirements-dbt.txt /tmp/requirements-dbt.txt
RUN /opt/dbt-venv/bin/pip install --no-cache-dir -r /tmp/requirements-dbt.txt

ENV DBT_EXECUTABLE_PATH=/opt/dbt-venv/bin/dbt \
    DBT_PACKAGES_INSTALL_PATH=/opt/dbt_packages \
    DBT_TARGET_PATH=/tmp/dbt/target \
    DBT_LOG_PATH=/tmp/dbt/logs

# Bake dbt packages; git-sync delivers models but never runs `dbt deps`.
COPY --chown=airflow dags/dbt/dbt_project.yml dags/dbt/packages.yml dags/dbt/package-lock.yml /tmp/dbt-deps/
RUN cd /tmp/dbt-deps && /opt/dbt-venv/bin/dbt deps && rm -rf /tmp/dbt-deps

FROM base AS dev
RUN pip install --no-cache-dir pytest==9.2.0 \
    && /opt/dbt-venv/bin/pip install --no-cache-dir pytest==9.2.0

FROM base AS prod
```

- [ ] **Step 5: Add the `airflow` tools service to compose**

Append under `services:` in `dev/compose.yml` (before `volumes:`):

```yaml
  airflow:
    image: example-dwh-airflow:dev
    profiles: ["tools"]
    depends_on:
      trino: { condition: service_started }
    environment:
      AIRFLOW__CORE__DAGS_FOLDER: /opt/airflow/dags/repo/dags
      AIRFLOW__CORE__LOAD_EXAMPLES: "False"
      DBT_PROFILES_DIR: /opt/airflow/dags/repo/dags/dbt
      DBT_TARGET: dev
      DBT_SCHEMA: dev
      TRINO_HOST: trino
      TRINO_PORT: "8080"
      TRINO_USER: dbt
      TRINO_CATALOG: iceberg
    # Same path the Helm chart's git-sync uses.
    volumes:
      - ..:/opt/airflow/dags/repo
    working_dir: /opt/airflow/dags/repo
    entrypoint: ["/bin/bash", "-c"]
```

- [ ] **Step 6: Add make targets**

Add to `Makefile` (extend the `.PHONY` line with `image dbt-parse`):

```makefile
RUN := $(COMPOSE) run --rm airflow

image:
	docker build --target dev -t example-dwh-airflow:dev .

dbt-parse:
	$(RUN) 'cd dags/dbt && $$DBT_EXECUTABLE_PATH parse'
```

- [ ] **Step 7: Build the image and verify both interpreters**

Run:

```bash
make image
docker run --rm --entrypoint /opt/dbt-venv/bin/dbt example-dwh-airflow:dev --version
docker run --rm --entrypoint python example-dwh-airflow:dev -c "import airflow, cosmos; print(airflow.__version__, cosmos.__version__)"
docker run --rm --entrypoint ls example-dwh-airflow:dev /opt/dbt_packages
```

Expected: dbt `--version` shows `installed: 1.11.16` and plugin `trino: 1.11.0`; second command prints `3.3.2 1.16.0`; third prints `dbt_utils`.

- [ ] **Step 8: Verify dbt parses with baked packages and schema naming works**

Run: `make dbt-parse`
Expected: exits 0 (output contains no `Compilation Error`).

Run (stack from Task 1 must be up): `docker compose -f dev/compose.yml run --rm airflow 'cd dags/dbt && $DBT_EXECUTABLE_PATH debug'`
Expected: `All checks passed!` (dbt connects to `trino:8080`, catalog `iceberg`).

- [ ] **Step 9: Commit**

```bash
git add Dockerfile requirements.txt requirements-dbt.txt dags/dbt dev/compose.yml Makefile
git commit -m "feat: add dbt-trino project skeleton and Airflow/Cosmos image

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: ODS models for source `shop` with idempotency tests

**Files:**
- Create: `tests/integration/conftest.py`, `tests/integration/test_ods_shop.py`
- Create: `dags/dbt/models/ods/shop/_shop__sources.yml`, `dags/dbt/models/ods/shop/_shop__models.yml`
- Create: `dags/dbt/models/ods/shop/ods_shop_orders_di.sql`, `dags/dbt/models/ods/shop/ods_shop_customers_df.sql`
- Modify: `Makefile` (add `test-integration`)

**Interfaces:**
- Consumes: Task 1 fixture data contract; Task 2 macros `get_dt()`, `generate_schema_name`; env contract.
- Produces: models `ods_shop_orders_di` (rows whose `updated_at` falls on `dt`, partitioned by `dt`) and `ods_shop_customers_df` (full copy per `dt`), both `incremental_strategy='delete+insert'` with `unique_key=['dt']` (= partition replacement); test helpers in `tests/integration/conftest.py`: `MAIN_PROJECT: Path`, `CATALOG = "iceberg"`, `query(sql) -> list[tuple]`, `run_dbt(project_dir: Path, args: list[str], schema: str) -> str`, `drop_schemas(prefix: str) -> None`.

- [ ] **Step 1: Write the integration test helpers**

`tests/integration/conftest.py`:

```python
"""Helpers for tests that run dbt against the local dev stack.

Run with the dbt venv interpreter (it has pytest + the trino client):
    /opt/dbt-venv/bin/python -m pytest tests/integration
"""

import os
import subprocess
from pathlib import Path

import trino

REPO = Path(__file__).resolve().parents[2]
MAIN_PROJECT = REPO / "dags" / "dbt"
CATALOG = "iceberg"
DBT = os.environ.get("DBT_EXECUTABLE_PATH", "/opt/dbt-venv/bin/dbt")


def query(sql: str) -> list[tuple]:
    conn = trino.dbapi.connect(
        host=os.environ.get("TRINO_HOST", "localhost"),
        port=int(os.environ.get("TRINO_PORT", "8080")),
        user="itest",
        catalog=CATALOG,
    )
    cur = conn.cursor()
    cur.execute(sql)
    return cur.fetchall()


def run_dbt(project_dir: Path, args: list[str], schema: str) -> str:
    env = {
        **os.environ,
        "DBT_TARGET": "dev",
        "DBT_SCHEMA": schema,
        "DBT_PROFILES_DIR": str(MAIN_PROJECT),
        # One target dir per project so partial-parse state never mixes projects.
        "DBT_TARGET_PATH": f"/tmp/dbt/target-{project_dir.name}",
    }
    result = subprocess.run(
        [DBT, *args, "--project-dir", str(project_dir)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def drop_schemas(prefix: str) -> None:
    """Drop schema `prefix` and schemas starting with `prefix_`. Filters in Python, never with LIKE."""
    schemas = [row[0] for row in query(f"SELECT schema_name FROM {CATALOG}.information_schema.schemata")]
    for schema in schemas:
        if schema != prefix and not schema.startswith(prefix + "_"):
            continue
        tables = query(
            f"SELECT table_name, table_type FROM {CATALOG}.information_schema.tables "
            f"WHERE table_schema = '{schema}'"
        )
        for name, table_type in tables:
            kind = "VIEW" if table_type == "VIEW" else "TABLE"
            query(f'DROP {kind} IF EXISTS {CATALOG}."{schema}"."{name}"')
        query(f'DROP SCHEMA IF EXISTS {CATALOG}."{schema}"')
```

- [ ] **Step 2: Write the failing tests**

`tests/integration/test_ods_shop.py`:

```python
"""ODS load for source `shop`: partition replacement by dt, idempotent re-runs.

Tests run in file order and share state: each builds on the previous load.
"""

from datetime import date

import pytest
from conftest import CATALOG, MAIN_PROJECT, drop_schemas, query, run_dbt

SCHEMA = "itest"
ODS = f'{CATALOG}."{SCHEMA}_ods"'


def build(dt: str) -> None:
    run_dbt(MAIN_PROJECT, ["build", "--select", "tag:ods_shop", "--vars", f"{{dt: '{dt}'}}"], SCHEMA)


def count(table: str, dt: str | None = None) -> int:
    where = f" WHERE dt = DATE '{dt}'" if dt else ""
    return query(f"SELECT count(*) FROM {ODS}.{table}{where}")[0][0]


@pytest.fixture(scope="module", autouse=True)
def clean():
    drop_schemas(SCHEMA)
    yield
    drop_schemas(SCHEMA)


def test_di_loads_only_rows_updated_on_dt():
    build("2026-11-02")
    assert count("ods_shop_orders_di", "2026-11-02") == 2
    assert count("ods_shop_orders_di") == 2


def test_df_loads_full_copy_into_dt():
    assert count("ods_shop_customers_df", "2026-11-02") == 3


def test_rerun_same_dt_is_idempotent():
    build("2026-11-02")
    assert count("ods_shop_orders_di") == 2
    assert count("ods_shop_customers_df") == 3


def test_next_dt_adds_partition_and_keeps_previous():
    build("2026-11-03")
    assert count("ods_shop_orders_di", "2026-11-03") == 3
    assert count("ods_shop_orders_di", "2026-11-02") == 2
    dts = query(f"SELECT DISTINCT dt FROM {ODS}.ods_shop_customers_df ORDER BY dt")
    assert dts == [(date(2026, 11, 2),), (date(2026, 11, 3),)]
```

Add to `Makefile` (extend `.PHONY` with `test-integration`):

```makefile
test-integration:
	$(RUN) "/opt/dbt-venv/bin/python -m pytest tests/integration -v"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `make test-integration`
Expected: FAIL — dbt reports `The selection criterion 'tag:ods_shop' does not match any enabled nodes` (assertion message shows dbt output).

- [ ] **Step 4: Write the source and models**

`dags/dbt/models/ods/shop/_shop__sources.yml`:

```yaml
version: 2

sources:
  - name: shop
    description: Shop OLTP database (Trino catalog `shop`, Postgres connector).
    database: shop
    schema: public
    tables:
      - name: orders
        description: One row per order; updated in place.
      - name: customers
        description: One row per customer; updated in place.
```

`dags/dbt/models/ods/shop/ods_shop_orders_di.sql`:

```sql
{{
  config(
    incremental_strategy='delete+insert',
    unique_key=['dt'],
    properties={"partitioning": "ARRAY['dt']"}
  )
}}

{% set dt = get_dt() %}

select
    cast(order_id as bigint)            as order_id,
    cast(customer_id as bigint)         as customer_id,
    cast(order_status as varchar)       as order_status,
    cast(total_amount as decimal(18, 2)) as total_amount,
    cast(created_at as timestamp(6))    as created_at,
    cast(updated_at as timestamp(6))    as updated_at,
    date '{{ dt }}'                     as dt
from {{ source('shop', 'orders') }}
where updated_at >= timestamp '{{ dt }} 00:00:00'
  and updated_at < timestamp '{{ dt }} 00:00:00' + interval '1' day
```

`dags/dbt/models/ods/shop/ods_shop_customers_df.sql`:

```sql
{{
  config(
    incremental_strategy='delete+insert',
    unique_key=['dt'],
    properties={"partitioning": "ARRAY['dt']"}
  )
}}

{% set dt = get_dt() %}

select
    cast(customer_id as bigint)      as customer_id,
    cast(customer_name as varchar)   as customer_name,
    cast(city as varchar)            as city,
    cast(created_at as timestamp(6)) as created_at,
    cast(updated_at as timestamp(6)) as updated_at,
    date '{{ dt }}'                  as dt
from {{ source('shop', 'customers') }}
```

`dags/dbt/models/ods/shop/_shop__models.yml`:

```yaml
version: 2

models:
  - name: ods_shop_orders_di
    description: "Daily increment of shop.orders: rows whose updated_at falls on dt. Grain: one row per order per dt."
    columns:
      - name: order_id
        description: Order id from the source.
        data_tests: [not_null]
      - name: dt
        description: Partition date (the day the row changed).
        data_tests: [not_null]
    data_tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [order_id, dt]

  - name: ods_shop_customers_df
    description: "Daily full copy of shop.customers. Grain: one row per customer per dt."
    columns:
      - name: customer_id
        description: Customer id from the source.
        data_tests: [not_null]
      - name: dt
        description: Partition date (snapshot day).
        data_tests: [not_null]
    data_tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [customer_id, dt]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `make test-integration`
Expected: `4 passed`.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add dags/dbt/models/ods tests/integration Makefile
git commit -m "feat: load shop source into ODS with partition replacement by dt

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Capability checks — dbt-trino merge and SCD2 snapshot on Iceberg

Spec §10 requires proving these before the standards (plan 3) depend on them.

**Files:**
- Create: `tests/integration/dbt_capabilities/dbt_project.yml`
- Create: `tests/integration/dbt_capabilities/models/chk_merge.sql`, `tests/integration/dbt_capabilities/models/chk_scd2_src.sql`
- Create: `tests/integration/dbt_capabilities/snapshots/chk_scd2.yml`
- Create: `tests/integration/test_capabilities.py`

**Interfaces:**
- Consumes: `run_dbt`, `query`, `drop_schemas`, `CATALOG` from `tests/integration/conftest.py` (Task 3).
- Produces: a standalone dbt project `dbt_capabilities` (profile `example_dwh`, var `batch` ∈ {1, 2}) used only by tests.

- [ ] **Step 1: Write the failing tests**

`tests/integration/test_capabilities.py`:

```python
"""Prove dbt-trino features the standards rely on: incremental merge and check-strategy snapshots."""

from datetime import date
from pathlib import Path

import pytest
from conftest import CATALOG, drop_schemas, query, run_dbt

PROJECT = Path(__file__).resolve().parent / "dbt_capabilities"
SCHEMA = "itest_cap"


def dbt(args: list[str], batch: int) -> None:
    run_dbt(PROJECT, [*args, "--vars", f"{{batch: {batch}}}"], SCHEMA)


@pytest.fixture(scope="module", autouse=True)
def clean():
    drop_schemas(SCHEMA)
    yield
    drop_schemas(SCHEMA)


def test_merge_updates_matched_rows_inserts_new_and_moves_partition():
    dbt(["run", "--select", "chk_merge"], batch=1)
    dbt(["run", "--select", "chk_merge"], batch=2)

    rows = query(f'SELECT id, v, dt FROM {CATALOG}."{SCHEMA}".chk_merge ORDER BY id')

    assert rows == [
        (1, "a", date(2026, 11, 1)),
        (2, "b2", date(2026, 11, 2)),
        (3, "c", date(2026, 11, 2)),
    ]


def test_check_snapshot_closes_changed_row_and_opens_new_version():
    dbt(["run", "--select", "chk_scd2_src"], batch=1)
    dbt(["snapshot"], batch=1)
    dbt(["run", "--select", "chk_scd2_src"], batch=2)
    dbt(["snapshot"], batch=2)

    rows = query(
        f"SELECT id, v, dbt_valid_to IS NULL AS is_current "
        f'FROM {CATALOG}."{SCHEMA}".chk_scd2 ORDER BY id, dbt_valid_from'
    )

    assert rows == [(1, "a", False), (1, "a2", True), (2, "b", True)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `make test-integration`
Expected: the 4 ODS tests pass; the 2 capability tests FAIL because `dbt_capabilities/dbt_project.yml` does not exist (`No dbt_project.yml found`).

- [ ] **Step 3: Write the capability project**

`tests/integration/dbt_capabilities/dbt_project.yml`:

```yaml
name: dbt_capabilities
version: "0.1.0"
config-version: 2
profile: example_dwh
model-paths: ["models"]
snapshot-paths: ["snapshots"]
```

`tests/integration/dbt_capabilities/models/chk_merge.sql`:

```sql
{{
  config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='id',
    properties={"partitioning": "ARRAY['dt']"}
  )
}}

select cast(id as bigint) as id, cast(v as varchar) as v, dt
from (
{% if var('batch') | int == 1 %}
    values (1, 'a', date '2026-11-01'), (2, 'b', date '2026-11-01')
{% else %}
    values (2, 'b2', date '2026-11-02'), (3, 'c', date '2026-11-02')
{% endif %}
) as t (id, v, dt)
```

`tests/integration/dbt_capabilities/models/chk_scd2_src.sql`:

```sql
{{ config(materialized='table') }}

select cast(id as bigint) as id, cast(v as varchar) as v
from (
{% if var('batch') | int == 1 %}
    values (1, 'a'), (2, 'b')
{% else %}
    values (1, 'a2'), (2, 'b')
{% endif %}
) as t (id, v)
```

`tests/integration/dbt_capabilities/snapshots/chk_scd2.yml`:

```yaml
snapshots:
  - name: chk_scd2
    relation: ref('chk_scd2_src')
    config:
      unique_key: id
      strategy: check
      check_cols: ["v"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `make test-integration`
Expected: `6 passed`.

If a capability test fails, do not change the assertion. Record the failing output in the verification record (Task 6) and stop: report to the user, because the spec's incremental/SCD standards depend on it.

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add tests/integration
git commit -m "test: prove dbt-trino merge and SCD2 snapshots on Iceberg

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Cosmos wiring, the ODS DAG and DAG integrity tests

**Files:**
- Create: `tests/dags/conftest.py`, `tests/dags/test_dag_integrity.py`
- Create: `dags/.airflowignore`, `dags/_common/__init__.py`, `dags/_common/defaults.py`, `dags/_common/dbt.py`
- Create: `dags/sources/dbt_ods_shop.py`
- Modify: `Makefile` (add `test-dags`)

**Interfaces:**
- Consumes: dbt project at `dags/dbt` (Tasks 2–3), image env `DBT_EXECUTABLE_PATH`, `DBT_TARGET`.
- Produces:
  - `_common.defaults.DEFAULT_ARGS: dict` (owner `data-eng`, retries 2, retry_delay 5 min)
  - `_common.dbt.DBT_PROJECT_DIR: Path`
  - `_common.dbt.dbt_dag_kwargs(select: list[str]) -> dict` — keyword args for `cosmos.DbtDag` / `DbtTaskGroup`: `project_config`, `profile_config`, `execution_config`, `render_config`, `operator_args` (with `vars={"dt": "{{ ds }}"}`)
  - DAG `dbt_ods_shop` (`@daily`, start 2026-11-01, no catchup, tags `layer:ods`, `source:shop`)

- [ ] **Step 1: Write the failing DAG integrity tests**

`tests/dags/conftest.py`:

```python
import os

# Must be set before Airflow/Cosmos are imported.
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
# The dbt ls cache lives in Airflow Variables; parse fresh in tests.
os.environ.setdefault("AIRFLOW__COSMOS__ENABLE_CACHE_DBT_LS", "False")
```

`tests/dags/test_dag_integrity.py`:

```python
"""Every DAG in dags/ imports cleanly and follows the minimum conventions."""

from pathlib import Path

import pytest

try:
    from airflow.dag_processing.dagbag import DagBag
except ImportError:  # older import path
    from airflow.models.dagbag import DagBag

DAGS_DIR = Path(__file__).resolve().parents[2] / "dags"


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR), include_examples=False)


def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}


def test_every_dag_has_a_real_owner_and_tags(dagbag):
    assert dagbag.dags, "no DAGs found"
    for dag_id, dag in dagbag.dags.items():
        assert dag.owner not in ("", "airflow"), f"{dag_id} has no owner"
        assert dag.tags, f"{dag_id} has no tags"


def test_ods_shop_dag_renders_only_shop_ods_models(dagbag):
    dag = dagbag.get_dag("dbt_ods_shop")

    assert dag is not None
    task_ids = set(dag.task_ids)
    assert any("ods_shop_orders_di" in t for t in task_ids)
    assert any("ods_shop_customers_df" in t for t in task_ids)
    assert all("ods_shop" in t for t in task_ids), task_ids
```

Add to `Makefile` (extend `.PHONY` with `test-dags`):

```makefile
test-dags:
	$(RUN) "airflow db migrate >/dev/null && python -m pytest tests/dags -v"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `make test-dags`
Expected: FAIL — `test_every_dag_has_a_real_owner_and_tags` fails with `no DAGs found`; `test_ods_shop_dag_renders_only_shop_ods_models` fails with `assert None is not None`.

- [ ] **Step 3: Write the Cosmos wiring and the DAG**

`dags/.airflowignore`:

```text
dbt/
_common/
```

`dags/_common/__init__.py`: empty file.

`dags/_common/defaults.py`:

```python
from datetime import timedelta

DEFAULT_ARGS = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}
```

`dags/_common/dbt.py`:

```python
"""Cosmos configuration shared by every dbt DAG."""

import os
from pathlib import Path

from cosmos import ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import InvocationMode, LoadMode

# Not resolve(): git-sync swaps a symlink; keep the stable /opt/airflow/dags/repo path.
DAGS_DIR = Path(__file__).absolute().parent.parent
DBT_PROJECT_DIR = DAGS_DIR / "dbt"
DBT_EXECUTABLE = os.environ.get("DBT_EXECUTABLE_PATH", "/opt/dbt-venv/bin/dbt")
DBT_TARGET = os.environ.get("DBT_TARGET", "dev")


def dbt_dag_kwargs(select: list[str]) -> dict:
    """Keyword arguments for cosmos.DbtDag / DbtTaskGroup running the models matched by `select`."""
    return {
        "project_config": ProjectConfig(
            dbt_project_path=DBT_PROJECT_DIR,
            install_dbt_deps=False,  # packages are baked into the image
        ),
        "profile_config": ProfileConfig(
            profile_name="example_dwh",
            target_name=DBT_TARGET,
            profiles_yml_filepath=DBT_PROJECT_DIR / "profiles.yml",
        ),
        "execution_config": ExecutionConfig(
            dbt_executable_path=DBT_EXECUTABLE,
            invocation_mode=InvocationMode.SUBPROCESS,
        ),
        "render_config": RenderConfig(
            load_method=LoadMode.DBT_LS,
            select=select,
            dbt_executable_path=DBT_EXECUTABLE,
            invocation_mode=InvocationMode.SUBPROCESS,
        ),
        # Passed to run time only (templated), so `dbt ls` at parse time never sees "{{ ds }}".
        "operator_args": {"vars": {"dt": "{{ ds }}"}},
    }
```

`dags/sources/dbt_ods_shop.py`:

```python
"""Load source system `shop` into ODS (Iceberg) for the logical date."""

from datetime import datetime

from _common.dbt import dbt_dag_kwargs
from _common.defaults import DEFAULT_ARGS
from cosmos import DbtDag

dbt_ods_shop = DbtDag(
    dag_id="dbt_ods_shop",
    schedule="@daily",
    start_date=datetime(2026, 11, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["layer:ods", "source:shop"],
    **dbt_dag_kwargs(select=["tag:ods_shop"]),
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `make test-dags`
Expected: `3 passed`.

- [ ] **Step 5: Lint and commit**

```bash
make fmt && make lint
git add dags/.airflowignore dags/_common dags/sources tests/dags Makefile
git commit -m "feat: run shop ODS models from Airflow via Cosmos

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: End-to-end Airflow run, asset emission, and the verification record

**Files:**
- Create: `dev/e2e.sh`
- Create: `docs/en/verification/2026-11-04-plan1-capabilities.md`
- Modify: `Makefile` (add `e2e`)

**Interfaces:**
- Consumes: DAG `dbt_ods_shop` (Task 5), dev stack (Task 1).
- Produces: `make e2e` (exit 0 = DAG run succeeded, dt partition loaded, Cosmos emitted `trino://` assets); the verification record that plan 3 cites.

- [ ] **Step 1: Write the e2e script**

`dev/e2e.sh`:

```bash
#!/usr/bin/env bash
# Runs dbt_ods_shop for 2026-11-03 inside the Airflow image, then checks data and emitted assets.
set -euo pipefail
DIR="$(dirname "$0")"
COMPOSE=(docker compose -f "$DIR/compose.yml")

"${COMPOSE[@]}" run --rm airflow "
  set -euo pipefail
  airflow db migrate >/dev/null
  airflow dags test dbt_ods_shop 2026-11-03
  echo '--- assets'
  airflow assets list --output plain
" | tee /tmp/example-dwh-e2e.log

echo '--- rows for dt=2026-11-03'
ROWS=$("${COMPOSE[@]}" exec -T trino trino --execute \
  "SELECT count(*) FROM iceberg.dev_ods.ods_shop_orders_di WHERE dt = DATE '2026-11-03'")
echo "$ROWS"
[ "$ROWS" = '"3"' ] || { echo "expected 3 rows, got $ROWS" >&2; exit 1; }

grep -q 'trino://' /tmp/example-dwh-e2e.log || { echo "no trino:// assets emitted" >&2; exit 1; }
echo "e2e OK"
```

```bash
chmod +x dev/e2e.sh
```

Add to `Makefile` (extend `.PHONY` with `e2e`):

```makefile
e2e:
	./dev/e2e.sh
```

- [ ] **Step 2: Run it**

Run: `make e2e`
Expected: Airflow log shows both `ods_shop_*` run tasks and their test tasks in state `success`; `--- assets` section lists URIs starting with `trino://trino:8080/`; script ends with `e2e OK`.

If the data check passes but the asset check fails, record it in Step 3 as FAIL with the `airflow assets list` output and stop: report to the user, because spec §4 schedules domain DAGs on Cosmos-emitted assets.

- [ ] **Step 3: Write the verification record with the measured results**

`docs/en/verification/2026-11-04-plan1-capabilities.md` — fill every `Result` cell with PASS/FAIL and paste the real output lines; do not write PASS for a check that was not run:

````markdown
# Plan 1 — platform capability verification

Measured on: <date of the run>, commit <git rev-parse --short HEAD>.

| Component | Version |
|-----------|---------|
| Airflow | 3.3.2 (python 3.12) |
| astronomer-cosmos | 1.16.0 |
| dbt-core / dbt-trino | 1.11.16 / 1.11.0 |
| Trino | 483 |
| Iceberg catalog | JDBC (Postgres 17.6), storage RustFS 1.0.1 |

| # | Capability (spec ref) | How measured | Result | Evidence |
|---|-----------------------|--------------|--------|----------|
| C1 | Iceberg partitioned table + Trino MERGE (§4) | `make smoke` | | |
| C2 | ODS `delete+insert` by `dt` is idempotent (§4) | `make test-integration` → `test_ods_shop.py` | | |
| C3 | dbt-trino `merge` incremental on Iceberg (§10) | `test_capabilities.py::test_merge_*` | | |
| C4 | dbt snapshot (check strategy) on Iceberg (§10, standards 04) | `test_capabilities.py::test_check_snapshot_*` | | |
| C5 | Cosmos `DBT_LS` render with separate dbt venv | `make test-dags` | | |
| C6 | Airflow run loads partition for `{{ ds }}` | `make e2e` row check | | |
| C7 | Cosmos emits `trino://` assets (§4, §10) | `make e2e` assets section | | |

## Asset URIs observed

```text
<paste the trino:// lines from the --- assets section>
```

## Consequences for later plans

<one line per FAIL: what in the spec must change; or "None — all capabilities passed.">
````

- [ ] **Step 4: Commit**

```bash
git add dev/e2e.sh Makefile docs/en/verification
git commit -m "test: verify Airflow end-to-end ODS run and Cosmos asset emission

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: CI, git-sync deployment example, README

**Files:**
- Create: `.github/workflows/ci.yml`, `deploy/helm/values.example.yaml`, `README.md`

**Interfaces:**
- Consumes: make targets `lint`, `image`, `dev-up`, `smoke`, `test-dags`, `test-integration`, `e2e`, `dev-down`.
- Produces: required CI checks `lint` and `stack`; Helm values contract for plan-independent deployment.

- [ ] **Step 1: Write the CI workflow**

`.github/workflows/ci.yml`:

```yaml
name: ci

on:
  pull_request:
  push:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: make lint

  stack:
    runs-on: ubuntu-24.04
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v4
      - run: make image
      - run: make dev-up
      - run: make smoke
      - run: make test-dags
      - run: make test-integration
      - run: make e2e
      - name: Stack logs on failure
        if: failure()
        run: docker compose -f dev/compose.yml logs --no-color --tail=200
      - name: Tear down
        if: always()
        run: make dev-down
```

- [ ] **Step 2: Write the Helm values example**

`deploy/helm/values.example.yaml`:

```yaml
# Example values for the official Airflow Helm chart 1.22.0 (https://airflow.apache.org).
# Replace registry, repo URL and secret names with your own.
airflowVersion: "3.3.2"
images:
  airflow:
    repository: registry.example.com/example-dwh/airflow   # built from Dockerfile, target `prod`
    tag: "0.1.0"

dags:
  persistence:
    enabled: false
  gitSync:
    enabled: true
    repo: https://github.com/example-org/example-dwh.git
    branch: main
    rev: HEAD
    depth: 1
    subPath: "dags"        # dags_folder = /opt/airflow/dags/repo/dags
    period: 60s

config:
  core:
    load_examples: "False"

env:
  - name: DBT_TARGET
    value: prod
  - name: TRINO_HOST
    value: trino.trino.svc.cluster.local
  - name: TRINO_PORT
    value: "8443"
  - name: TRINO_HTTP_SCHEME
    value: https
  - name: TRINO_CATALOG
    value: iceberg
  - name: TRINO_AUTH_METHOD
    value: ldap

# TRINO_USER and TRINO_PASSWORD come from a Kubernetes Secret.
extraEnvFrom: |
  - secretRef:
      name: example-dwh-trino
```

- [ ] **Step 3: Validate the Helm values render git-sync with the right subPath**

Run:

```bash
helm repo add apache-airflow https://airflow.apache.org >/dev/null 2>&1 || true
helm repo update apache-airflow >/dev/null
helm template dwh apache-airflow/airflow --version 1.22.0 -f deploy/helm/values.example.yaml \
  | grep -E "AIRFLOW__CORE__DAGS_FOLDER|/opt/airflow/dags/repo/dags" | sort -u
```

Expected: at least one line containing `/opt/airflow/dags/repo/dags`.

- [ ] **Step 4: Write the README**

`README.md`:

````markdown
# example-dwh

Kimball/OneData data warehouse on Airflow + dbt-trino + Iceberg.
Design: [docs/en/specs/2026-11-04-kimball-dwh-design.md](docs/en/specs/2026-11-04-kimball-dwh-design.md).

## Layout

| Path | What |
|------|------|
| `dags/` | Airflow dags_folder (git-sync `subPath: dags`) |
| `dags/dbt/` | dbt-trino project; models by layer `ods/ dim/ dwd/ dws/ ads/` |
| `dags/_common/` | shared Cosmos config and default args |
| `dags/sources/` | one DAG per source system (ODS) |
| `dev/` | local stack: Postgres (source + Iceberg JDBC catalog), RustFS, Trino |
| `tests/dags/` | DAG integrity tests (Airflow interpreter) |
| `tests/integration/` | dbt runs against the local stack (dbt venv interpreter) |
| `deploy/helm/` | example values for the official Airflow chart with git-sync |

## Local development

Requires Docker and [uv](https://docs.astral.sh/uv/).

```bash
make image             # build example-dwh-airflow:dev
make dev-up            # start Postgres, RustFS, Trino (Trino on localhost:28080)
make smoke             # Iceberg + MERGE + source catalog smoke test
make test-dags         # DAG integrity
make test-integration  # ODS idempotency + dbt capability checks
make e2e               # run dbt_ods_shop in Airflow for 2026-11-03
make dev-down          # stop and delete volumes
```

Ad-hoc dbt inside the image:

```bash
docker compose -f dev/compose.yml run --rm airflow \
  'cd dags/dbt && $DBT_EXECUTABLE_PATH build --select tag:ods_shop --vars "{dt: 2026-11-02}"'
```

## How it runs in production

- git-sync clones this repo to `/opt/airflow/dags/repo`; Airflow parses only `dags/`.
- dbt runs from `/opt/dbt-venv` inside the image; dbt packages are baked in at build time.
  **Changing `dags/dbt/packages.yml` requires a new image.**
- Every dbt run receives `dt = {{ ds }}`; each model replaces or merges only its `dt` partition, so re-runs are safe.
````

- [ ] **Step 5: Run the full local CI sequence**

Run: `make lint && make dev-down && make image && make dev-up && make smoke && make test-dags && make test-integration && make e2e`
Expected: every step exits 0; last line `e2e OK`.

- [ ] **Step 6: Commit**

```bash
git add .github deploy README.md
git commit -m "ci: add lint and stack workflow, git-sync Helm example and README

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Not in this plan (later plans)

- `warehouse/` YAML, JSON Schemas, `dwh` CLI and lint rules → plan 2.
- `docs/standards/`, `skills/`, `AGENTS.md`, `dwh sync-agents`, sqlfluff, pre-commit → plan 3.
- DIM/DWD/DWS/ADS models, domain DAGs scheduled on assets, `dbt build --defer` in CI → plan 4.
````
