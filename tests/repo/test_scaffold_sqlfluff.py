"""`dwh scaffold` output passes the sqlfluff style rules (spec §6.2, §7)."""

import shutil
import subprocess
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROBE = "zz_scaffold_probe"
GENERATE = textwrap.dedent(
    """
    import sys, tempfile
    from pathlib import Path
    sys.path.insert(0, "tools/dwh/tests")
    from fixtures.warehouse import write_warehouse
    from dwh.scaffold import scaffold
    from dwh.warehouse import load_warehouse

    wh = load_warehouse(write_warehouse(Path(tempfile.mkdtemp()) / "warehouse"))
    cases = [
        ("ods_shop_orders_di", {"grain": ["order_id"]}),
        ("dim_pub_customer", {"upstream": ["ods_shop_customers_df"]}),
        ("dwd_trade_order_di", {"grain": ["order_id"], "upstream": ["ods_shop_orders_di"]}),
        ("dws_trade_customer_1d", {"grain": ["customer_key"], "upstream": ["dwd_trade_order_di"],
                                   "metrics": ["order_amt_sum_1d", "order_cnt_1d"]}),
        ("dws_trade_customer_nd", {"grain": ["customer_key"], "upstream": ["dwd_trade_order_di"],
                                   "metrics": ["app_order_amt_sum_30d"]}),
        ("ads_bi_customer_daily", {"grain": ["customer_key"], "upstream": ["dws_trade_customer_1d"],
                                   "metrics": ["order_amt_sum_1d", "avg_order_amt_1d"]}),
    ]
    for name, kwargs in cases:
        for path, text in scaffold(name, wh, project_dir="", **kwargs).items():
            if path.endswith(".sql"):
                print("\\0".join([path, text]), end="\\1")
    """
)


def test_scaffolded_sql_passes_sqlfluff():
    generated = subprocess.run(
        ["uv", "run", "--locked", "--project", "tools/dwh", "python", "-"],
        input=GENERATE,
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    models = REPO / "dags" / "dbt" / "models"
    folders = set()
    try:
        for entry in filter(None, generated.split("\1")):
            path, text = entry.split("\0", 1)
            relative = Path(path)  # models/<layer>/<folder>/<name>.sql
            folder = models / relative.parts[1] / PROBE
            folder.mkdir(parents=True, exist_ok=True)
            (folder / relative.name).write_text(text)
            folders.add(folder)
        assert len(folders) == 5  # ods, dim, dwd, dws, ads
        result = subprocess.run(
            [
                "uvx",
                "--python",
                "3.12",
                "sqlfluff==4.5.0",
                "lint",
                *sorted(str(f.relative_to(REPO)) for f in folders),
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        for folder in folders:
            shutil.rmtree(folder, ignore_errors=True)
