import os
from datetime import timedelta

DEFAULT_ARGS = {
    "owner": "data-eng",
    # DWH_TASK_RETRIES exists only so dev/e2e.sh can fail fast (set to 0); deployments leave it unset.
    "retries": int(os.environ.get("DWH_TASK_RETRIES", "2")),
    "retry_delay": timedelta(minutes=5),
}
