#!/usr/bin/env bash
# Runs dbt_ods_shop for 2026-11-03 inside the Airflow image, then checks data and emitted assets.
set -euo pipefail
DIR="$(dirname "$0")"
COMPOSE=(docker compose -f "$DIR/compose.yml")

# DWH_TASK_RETRIES=0: a failing task fails the run now instead of waiting out 2 x 5 min retries.
"${COMPOSE[@]}" run --rm -e DWH_TASK_RETRIES=0 airflow "
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

# Check only the emitted-assets section: task logs also contain trino:// inlet lines.
LOG=/tmp/example-dwh-e2e.log
ASSETS=$(sed -n '/^--- assets/,/^--- rows/p' "$LOG")
for uri in trino://trino:8080/iceberg/dev_ods/ods_shop_orders_di \
           trino://trino:8080/iceberg/dev_ods/ods_shop_customers_df; do
  grep -qF "$uri" <<<"$ASSETS" || { echo "asset not emitted: $uri" >&2; exit 1; }
done
echo "e2e OK"
