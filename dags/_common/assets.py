"""Airflow Assets for dbt models, shaped like the ones Cosmos emits (plan 1, capability C7)."""

import os

from airflow.sdk import Asset


def model_asset(layer: str, model: str) -> Asset:
    """The Asset Cosmos emits for `model` of `layer`: `trino://<host>:<port>/<catalog>/<schema>/<model>`.

    The schema follows generate_schema_name: the bare layer in prod, `<DBT_SCHEMA>_<layer>` elsewhere. It is
    read from the environment at call time, so a dev DAG never consumes a prod event.
    """
    host = os.environ.get("TRINO_HOST", "localhost")
    port = os.environ.get("TRINO_PORT", "8080")
    catalog = os.environ.get("TRINO_CATALOG", "iceberg")
    if os.environ.get("DBT_TARGET", "dev") == "prod":
        schema = layer
    else:
        schema = f"{os.environ.get('DBT_SCHEMA', 'dev')}_{layer}"
    return Asset(f"trino://{host}:{port}/{catalog}/{schema}/{model}")
