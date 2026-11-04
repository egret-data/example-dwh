#!/usr/bin/env bash
# Proves: Iceberg JDBC catalog + S3 writes, partitioned table, MERGE, and the shop source catalog.
set -euo pipefail
DIR="$(dirname "$0")"
docker compose -f "$DIR/compose.yml" exec -T trino trino --execute "$(cat "$DIR/smoke.sql")"
