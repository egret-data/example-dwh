import os
import sys
from pathlib import Path

# Must be set before Airflow/Cosmos are imported.
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
# The dbt ls cache lives in Airflow Variables; parse fresh in tests.
os.environ.setdefault("AIRFLOW__COSMOS__ENABLE_CACHE_DBT_LS", "False")

# The Airflow dag processor puts the dags folder on sys.path (so `_common` imports work);
# a bare pytest process does not.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dags"))
