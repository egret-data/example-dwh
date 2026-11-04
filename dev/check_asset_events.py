"""Fail unless the Airflow metadata DB holds an AssetEvent from DAG `dag_id` for every given asset URI.

Usage (inside the Airflow image, after `airflow dags test`):
    python dev/check_asset_events.py <dag_id> <uri> [<uri> ...]
"""

import sys

from airflow.models.asset import AssetEvent, AssetModel
from airflow.utils.session import create_session
from sqlalchemy import select


def main(dag_id: str, uris: list[str]) -> int:
    with create_session() as session:
        rows = session.execute(
            select(AssetModel.uri, AssetEvent.source_task_id, AssetEvent.source_run_id)
            .join(AssetModel, AssetEvent.asset_id == AssetModel.id)
            .where(AssetEvent.source_dag_id == dag_id)
            .order_by(AssetEvent.id)
        ).all()
    for uri, task_id, run_id in rows:
        print(f"asset_event uri={uri} source_task_id={task_id} source_run_id={run_id}")
    missing = sorted(set(uris) - {row[0] for row in rows})
    for uri in missing:
        print(f"no asset event for {uri}", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
