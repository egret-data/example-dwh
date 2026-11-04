#!/usr/bin/env bash
# Runs dbt_ods_shop for logical date 2026-11-03 inside the Airflow image, then checks data, registered
# assets and AssetEvent rows. Its data interval is the Vietnam day 2026-11-02, so dt = 2026-11-02 while
# Airflow's UTC {{ ds }} is 2026-11-03. The orders fixture has 2 rows on 2026-11-02 and 3 on
# 2026-11-03, so the row check proves dt comes from the VN data interval (spec D12), not from ds.
set -euo pipefail
DIR="$(dirname "$0")"
COMPOSE=(docker compose -f "$DIR/compose.yml")
LOGICAL_DATE=2026-11-03
DT=2026-11-02
DAG=dbt_ods_shop
URIS=(trino://trino:8080/iceberg/dev_ods/ods_shop_orders_di
      trino://trino:8080/iceberg/dev_ods/ods_shop_customers_df)
LOG=/tmp/example-dwh-e2e.log

# DWH_TASK_RETRIES=0: a failing task fails the run now instead of waiting out 2 x 5 min retries.
# The metadata DB is SQLite inside this throwaway container, so every check runs in this one call.
"${COMPOSE[@]}" run --rm -e DWH_TASK_RETRIES=0 airflow "
  set -euo pipefail
  airflow db migrate >/dev/null
  airflow dags test $DAG $LOGICAL_DATE
  echo '--- assets'
  airflow assets list --output plain
  echo '--- asset events'
  python dev/check_asset_events.py $DAG ${URIS[*]}
" | tee "$LOG"

# Check only the registered-assets section: task logs also contain trino:// inlet lines.
ASSETS=$(sed -n '/^--- assets/,/^--- asset events/p' "$LOG")
for uri in "${URIS[@]}"; do
  grep -qF "$uri" <<<"$ASSETS" || { echo "asset not registered: $uri" >&2; exit 1; }
done

check_rows() {
  local table=$1 expected=$2 rows
  rows=$("${COMPOSE[@]}" exec -T trino trino --execute \
    "SELECT count(*) FROM iceberg.dev_ods.$table WHERE dt = DATE '$DT'")
  echo "$table dt=$DT rows: $rows"
  [ "$rows" = "\"$expected\"" ] || { echo "$table: expected $expected rows, got $rows" >&2; exit 1; }
}
echo "--- rows for dt=$DT"
check_rows ods_shop_orders_di 2
check_rows ods_shop_customers_df 3
echo "e2e OK"
