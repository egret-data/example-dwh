#!/usr/bin/env bash
# Runs dbt_ods_shop for 2026-11-03 inside the Airflow image, then checks data and emitted assets.
set -euo pipefail
DIR="$(dirname "$0")"
COMPOSE=(docker compose -f "$DIR/compose.yml")

"${COMPOSE[@]}" run --rm airflow "
  set -euo pipefail
  airflow db migrate >/dev/null
  airflow dags test dbt_ods_shop 2026-11-03
  echo '--- assets'
  airflow assets list --output plain
" | tee /tmp/example-dwh-e2e.log

echo '--- rows for dt=2026-11-03'
ROWS=$("${COMPOSE[@]}" exec -T trino trino --execute \
  "SELECT count(*) FROM iceberg.dev_ods.ods_shop_orders_di WHERE dt = DATE '2026-11-03'")
echo "$ROWS"
[ "$ROWS" = '"3"' ] || { echo "expected 3 rows, got $ROWS" >&2; exit 1; }

grep -q 'trino://' /tmp/example-dwh-e2e.log || { echo "no trino:// assets emitted" >&2; exit 1; }
echo "e2e OK"
