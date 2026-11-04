"""Cosmos configuration shared by every dbt DAG."""

import os
from pathlib import Path

from cosmos import ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import InvocationMode, LoadMode

from _common.dates import DT_TEMPLATE

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
        # Passed to run time only (templated), so `dbt ls` at parse time never renders it.
        "operator_args": {"vars": {"dt": DT_TEMPLATE}},
    }
