#!/usr/bin/env bash
# Waits until Trino answers a query (max 180s).
set -euo pipefail
COMPOSE=(docker compose -f "$(dirname "$0")/compose.yml")
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T trino trino --execute "SELECT 1" >/dev/null 2>&1; then
    echo "trino ready"
    exit 0
  fi
  sleep 3
done
echo "trino not ready after 180s" >&2
exit 1
