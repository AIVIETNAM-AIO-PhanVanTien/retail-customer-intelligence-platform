#!/usr/bin/env bash
# Run dbt test without locking data/retail.duckdb (e.g. when DataGrip is open).
# Copies the DuckDB file to dbt/.local_duckdb/ and runs tests against the copy.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB_SRC="$ROOT/data/retail.duckdb"
LOCAL_DIR="$ROOT/dbt/.local_duckdb"
LOCAL_DB="$LOCAL_DIR/retail.duckdb"
PROFILES="$LOCAL_DIR/profiles.yml"

if [[ ! -f "$DB_SRC" ]]; then
  echo "[ERROR] DuckDB not found: $DB_SRC"
  echo "Run first: cd dbt && dbt run --profiles-dir ."
  exit 1
fi

mkdir -p "$LOCAL_DIR"
echo "[COPY] $DB_SRC -> $LOCAL_DB"
cp "$DB_SRC" "$LOCAL_DB"

cat > "$PROFILES" <<EOF
retail_duckdb:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: '${LOCAL_DB}'
      schema: main
EOF

echo "[DBT] dbt test --profiles-dir $LOCAL_DIR"
cd "$ROOT/dbt"
dbt test --profiles-dir "$LOCAL_DIR" "$@"
