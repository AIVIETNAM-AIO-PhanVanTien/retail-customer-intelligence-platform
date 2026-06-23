"""Export dbt serving tables (DuckDB) to Parquet for Power BI.

Power BI Desktop has a *native* Parquet connector, so this path needs NO
DuckDB ODBC driver install — easiest for first-time Power BI users.

Re-run this after each `dbt run` to refresh the Parquet files, then click
"Refresh" in Power BI Desktop to pull the new numbers.

Usage (from repo root)::

    python scripts/export_powerbi.py

Output: data/powerbi/<table>.parquet  (data/ is gitignored — local only)
"""
from __future__ import annotations

import sys
from pathlib import Path
import duckdb

# Windows consoles often default to a legacy codepage (cp1252/cp1258) that
# can't print this repo's Vietnamese path — force UTF-8 so output never crashes.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "retail.duckdb"
OUT = ROOT / "data" / "powerbi"

# Serving tables only (the dbt marts + star-schema dims/fact). Views
# (stg/int) are excluded — Power BI consumes the presentation marts.
TABLES = [
    "dim_date",
    "dim_customer",
    "dim_product",
    "dim_country",
    "fact_transactions",
    "mart_rfm",
    "mart_kpi_monthly",
    "mart_features",
]


def main() -> None:
    if not DB.exists():
        raise SystemExit(f"DuckDB not found: {DB}\nRun `dbt run` first.")

    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)

    print(f"Exporting {len(TABLES)} tables -> {OUT}\n")
    for t in TABLES:
        out_file = OUT / f"{t}.parquet"
        con.execute(f"COPY {t} TO '{out_file.as_posix()}' (FORMAT PARQUET)")
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:22s} {n:>8,} rows  ->  {out_file.name}")

    print(f"\nDone. Open Power BI Desktop -> Get Data -> Parquet -> pick a file in {OUT}")


if __name__ == "__main__":
    main()
