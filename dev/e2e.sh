#!/usr/bin/env bash
# Runs dbt_ods_shop, dbt_pub and dbt_trade for logical date 2026-11-03 inside the Airflow image, then checks
# data, registered assets and AssetEvent rows. Its data interval is the Vietnam day 2026-11-02, so dt = 2026-11-02 while
# Airflow's UTC {{ ds }} is 2026-11-03. The orders fixture has 2 rows on 2026-11-02 and 3 on
# 2026-11-03, so the row check proves dt comes from the VN data interval (spec D12), not from ds.
# dbt_pub and dbt_trade are asset-scheduled, so `dags test` (which triggers no assets) gets the day from
# --conf '{"dt": ...}' instead.
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
  airflow dags test dbt_pub $LOGICAL_DATE --conf '{\"dt\": \"$DT\"}'
  airflow dags test dbt_trade $LOGICAL_DATE --conf '{\"dt\": \"$DT\"}'
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
    "SELECT count(*) FROM iceberg.dev_$table WHERE dt = DATE '$DT'")
  echo "$table dt=$DT rows: $rows"
  [ "$rows" = "\"$expected\"" ] || { echo "$table: expected $expected rows, got $rows" >&2; exit 1; }
}
echo "--- rows for dt=$DT"
check_rows ods.ods_shop_orders_di 2
check_rows ods.ods_shop_customers_df 3
# Order 3 is the only order placed on 2026-11-02 (Vietnam time); order 2 was placed on 2026-11-01. So the
# DWD holds one row for the day, and the customer DWS holds one row: the customer who placed order 3.
check_rows dwd.dwd_trade_order_di 1
check_rows dws.dws_trade_customer_1d 1
echo "e2e OK"
