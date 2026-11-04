"""Cosmos configuration shared by every dbt DAG."""

import os
from pathlib import Path

from cosmos import ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import InvocationMode, LoadMode, TestIndirectSelection

from _common.dates import DT_TEMPLATE

# Not resolve(): git-sync swaps a symlink; keep the stable /opt/airflow/dags/repo path.
DAGS_DIR = Path(__file__).absolute().parent.parent
DBT_PROJECT_DIR = DAGS_DIR / "dbt"
DBT_EXECUTABLE = os.environ.get("DBT_EXECUTABLE_PATH", "/opt/dbt-venv/bin/dbt")
DBT_TARGET = os.environ.get("DBT_TARGET", "dev")


def dbt_dag_kwargs(select: list[str], dt_template: str = DT_TEMPLATE) -> dict:
    """Keyword arguments for cosmos.DbtDag / DbtTaskGroup running the models matched by `select`.

    `dt_template` renders the business day: DT_TEMPLATE for cron DAGs, ASSET_DT_TEMPLATE for DAGs
    scheduled on Assets.
    """
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
            # Cosmos runs `dbt test --select <model>`. With dbt's default (eager) that also picks the
            # relationships tests of downstream models whose tables a later DAG builds, and they fail with
            # "table not found". buildable keeps a test only when every model it touches is selected or
            # upstream of it.
            test_indirect_selection=TestIndirectSelection.BUILDABLE,
        ),
        "render_config": RenderConfig(
            load_method=LoadMode.DBT_LS,
            select=select,
            dbt_executable_path=DBT_EXECUTABLE,
            invocation_mode=InvocationMode.SUBPROCESS,
        ),
        # Passed to run time only (templated), so `dbt ls` at parse time never renders it.
        "operator_args": {
            "vars": {"dt": dt_template},
            # Cosmos reads the Asset outlets from run_results.json under DBT_TARGET_PATH. The image sets one
            # path for the whole container, so concurrent tasks read each other's results and emit events for
            # the wrong Asset (measured with a live scheduler). One directory per task keeps them apart.
            "env": {"DBT_TARGET_PATH": "/tmp/dbt/target/{{ ti.task_id }}"},
        },
    }
