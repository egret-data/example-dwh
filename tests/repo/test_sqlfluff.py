"""sqlfluff accepts the real models and rejects `select *` outside ODS (spec §7, 10-trino-sql-style)."""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SQLFLUFF = ["uvx", "--python", "3.12", "sqlfluff==4.5.0", "lint"]


def lint(*paths: str) -> subprocess.CompletedProcess:
    return subprocess.run([*SQLFLUFF, *paths], cwd=REPO, capture_output=True, text=True, check=False)


def test_repository_models_pass():
    result = lint("dags/dbt/models")
    assert result.returncode == 0, result.stdout + result.stderr


def test_select_star_outside_ods_fails():
    target = REPO / "dags" / "dbt" / "models" / "dwd" / "zz_sqlfluff_probe.sql"
    target.write_text("select * from {{ ref('ods_shop_orders_di') }}\n")
    try:
        result = lint(str(target.relative_to(REPO)))
    finally:
        target.unlink()
    assert result.returncode == 1
    assert "AM04" in result.stdout
