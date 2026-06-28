"""Export dbt serving tables (DuckDB) to Parquet or CSV for Power BI / Fabric.

Power BI Desktop has a *native* Parquet connector (no ODBC driver needed).
Microsoft Fabric Lakehouse / OneLake supports CSV upload directly.

Re-run this after each `dbt run` / ML pipeline run to refresh the files.

Usage (from repo root)::

    # Parquet — default, for Power BI Desktop
    python scripts/export_powerbi.py

    # CSV — for Microsoft Fabric import
    python scripts/export_powerbi.py --format csv

    # Explicit parquet
    python scripts/export_powerbi.py --format parquet

Output:
    data/powerbi/<table>.parquet   (Parquet mode)
    data/fabric/<table>.csv        (CSV mode)

Both directories are gitignored — local only.

Tables exported
---------------
From DuckDB (dbt marts + star schema):
  dim_date, dim_customer, dim_product, dim_country
  fact_transactions
  mart_rfm, mart_kpi_monthly, mart_features

From Gold Parquet (ML pipeline outputs — not materialized in DuckDB):
  mart_churn_scores    — churn probability + risk tier per customer
  mart_monitoring      — model/data drift metrics over time
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "retail.duckdb"
GOLD_DIR = ROOT / "data" / "gold"

# Tables served from DuckDB (dbt materializations)
DUCKDB_TABLES = [
    "dim_date",
    "dim_customer",
    "dim_product",
    "dim_country",
    "fact_transactions",
    "mart_rfm",
    "mart_kpi_monthly",
    "mart_features",  # excluded from CSV/Fabric export — ML input only, not for BI
]

# Tables excluded from CSV (Fabric) export — too ML-specific for BI dashboards
CSV_EXCLUDE = {"mart_features", "mart_monitoring"}

# ML pipeline outputs — stored as Parquet in data/gold/, not in DuckDB.
# Registered as temporary views so the same COPY logic applies to all tables.
GOLD_PARQUET_VIEWS = {
    "mart_churn_scores": GOLD_DIR / "mart_churn_scores" / "mart_churn_scores.parquet",
    "mart_monitoring": GOLD_DIR / "mart_monitoring" / "mart_monitoring.parquet",
}

ALL_TABLES = DUCKDB_TABLES + list(GOLD_PARQUET_VIEWS)

_OUT_DIR = {
    "parquet": ROOT / "data" / "powerbi",
    "csv": ROOT / "data" / "fabric",
}

_COPY_FMT = {
    "parquet": "FORMAT PARQUET",
    "csv": "FORMAT CSV, HEADER true",
}

_EXT = {"parquet": ".parquet", "csv": ".csv"}

_DONE_MSG = {
    "parquet": "Open Power BI Desktop -> Get Data -> Parquet -> pick a file in {out}",
    "csv": (
        "Upload the CSV files from {out} into your Microsoft Fabric Lakehouse.\n"
        "Then apply fabric/semantic_model/ TMDL to set up relationships and measures."
    ),
}


def _register_gold_views(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Register available Gold parquet files as temporary DuckDB views. Returns skipped names."""
    skipped = []
    for view_name, parquet_path in GOLD_PARQUET_VIEWS.items():
        if parquet_path.exists():
            con.execute(
                f"CREATE OR REPLACE VIEW {view_name} AS "
                f"SELECT * FROM read_parquet('{parquet_path.as_posix()}')"
            )
        else:
            skipped.append(view_name)
    return skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Export DuckDB tables for BI tools.")
    parser.add_argument(
        "--format",
        choices=["parquet", "csv"],
        default="parquet",
        help="Output format: 'parquet' (Power BI, default) or 'csv' (Microsoft Fabric).",
    )
    args = parser.parse_args()
    fmt: str = args.format

    if not DB.exists():
        raise SystemExit(f"DuckDB not found: {DB}\nRun `dbt run` first.")

    out_dir = _OUT_DIR[fmt]
    out_dir.mkdir(parents=True, exist_ok=True)

    # In-memory connection so CREATE VIEW (for gold parquets) is allowed;
    # retail.duckdb is attached read-only and queried with the retail.main prefix.
    con = duckdb.connect()
    con.execute(f"ATTACH '{DB.as_posix()}' AS retail (READ_ONLY)")

    skipped = _register_gold_views(con)
    exclude = skipped + (list(CSV_EXCLUDE) if fmt == "csv" else [])
    export_tables = [t for t in ALL_TABLES if t not in exclude]

    print(f"Format : {fmt.upper()}")
    print(f"Output : {out_dir}")
    print(f"Tables : {len(export_tables)}" + (f"  (skipped: {skipped})" if skipped else ""))
    print()

    for t in export_tables:
        out_file = out_dir / f"{t}{_EXT[fmt]}"
        # Gold views live in the in-memory db; duckdb tables need the retail.main prefix.
        ref = t if t in GOLD_PARQUET_VIEWS else f"retail.main.{t}"
        con.execute(f"COPY {ref} TO '{out_file.as_posix()}' ({_COPY_FMT[fmt]})")
        n = con.execute(f"SELECT COUNT(*) FROM {ref}").fetchone()[0]
        src = "(gold)" if t in GOLD_PARQUET_VIEWS else "(duckdb)"
        print(f"  {t:26s} {n:>8,} rows  {src}  ->  {out_file.name}")

    print(f"\nDone. {_DONE_MSG[fmt].format(out=out_dir)}")


if __name__ == "__main__":
    main()
