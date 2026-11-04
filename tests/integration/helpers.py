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
    # The trino client returns rows as lists; the helper's contract is list[tuple].
    return [tuple(row) for row in cur.fetchall()]


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
