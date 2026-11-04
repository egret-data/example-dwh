import os
import sys
from pathlib import Path

import pytest

# Must be set before Airflow/Cosmos are imported.
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
# The dbt ls cache lives in Airflow Variables; parse fresh in tests.
os.environ.setdefault("AIRFLOW__COSMOS__ENABLE_CACHE_DBT_LS", "False")

# The Airflow dag processor puts the dags folder on sys.path (so `_common` imports work);
# a bare pytest process does not.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dags"))

DAGS_DIR = Path(__file__).resolve().parents[2] / "dags"


@pytest.fixture(scope="session")
def dagbag():
    # Imported here, not at module top: Airflow must see the environment variables set above.
    try:
        from airflow.dag_processing.dagbag import DagBag
    except ImportError:  # older import path
        from airflow.models.dagbag import DagBag
    return DagBag(dag_folder=str(DAGS_DIR))
