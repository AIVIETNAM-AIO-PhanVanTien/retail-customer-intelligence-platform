"""Silver layer: clean, dedup, validate (ACM1-30).

Reads Bronze Parquet partitions, applies cleaning rules, runs quality
checks, and writes validated Silver Parquet.

Date synthesis is now in Bronze. Silver only cleans and validates.

Processing order
----------------
``process_all()`` iterates **newest month first**.

Usage::

    # single month
    python -m src.etl.silver_transform --month 2026-05

    # all months, newest first
    python -m src.etl.silver_transform --all
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.utils.data_quality_check import TabularDataQuality

# ── Constants ────────────────────────────────────────────────────────────
BRONZE_DIR: Path = Path("data/bronze")
SILVER_DIR: Path = Path("data/silver")

# ── PyArrow schema ───────────────────────────────────────────────────────
SILVER_SCHEMA = pa.schema(
    [
        pa.field("invoice", pa.string()),
        pa.field("stock_code", pa.string()),
        pa.field("description", pa.string()),
        pa.field("quantity", pa.float64()),
        pa.field("price", pa.float64()),
        pa.field("customer_id", pa.string()),
        pa.field("country", pa.string()),
        pa.field("is_cancellation", pa.bool_()),
        pa.field("line_amount", pa.float64()),
        pa.field("invoice_date", pa.timestamp("us")),
        pa.field("original_invoice_date", pa.timestamp("us")),
        pa.field("invoice_year", pa.int32()),
        pa.field("invoice_month", pa.int32()),
        pa.field("invoice_day", pa.int32()),
        pa.field("invoice_quarter", pa.int32()),
        pa.field("invoice_day_of_week", pa.int32()),
        pa.field("invoice_week", pa.int32()),
        pa.field("year_month", pa.string()),
    ]
)


# ── Step 1: Cleaning ────────────────────────────────────────────────────
def load_bronze(year_month: str) -> pd.DataFrame:
    """Load one Bronze partition."""
    path = BRONZE_DIR / f"year_month={year_month}" / "data.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Bronze partition not found: {path}")
    df = pq.ParquetFile(path).read().to_pandas()
    print(f"  Loaded {len(df)} rows from Bronze {year_month}")
    return df


def run_cleaning(df: pd.DataFrame) -> pd.DataFrame:
    """Clean: type enforcement, dedup, strip, compute line_amount, filter noise."""
    initial = len(df)

    # Type enforcement
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce")
    df["is_cancellation"] = df["is_cancellation"].astype(bool)

    # Strip whitespace on text columns
    for col in ("description", "stock_code", "country", "invoice"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()

    # Replace empty description with "UNKNOWN"
    df.loc[df["description"] == "", "description"] = "UNKNOWN"

    # Deduplicate on all columns
    before_dedup = len(df)
    df = df.drop_duplicates().copy()  # .copy() avoids SettingWithCopyWarning
    print(f"  Dedup: {before_dedup - len(df)} duplicates removed")

    # Compute line_amount
    df["line_amount"] = df["quantity"] * df["price"]

    # ── Noise filter (business rules) ──
    # Non-cancellation rows with price <= 0 are adjustments/bad-debt/junk
    noise_mask = (~df["is_cancellation"]) & (df["price"] <= 0)
    n_noise = int(noise_mask.sum())
    if n_noise > 0:
        df = df[~noise_mask].copy()
        print(f"  Filtered {n_noise} non-cancellation rows with price <= 0")

    print(f"  Cleaning: {initial} -> {len(df)} rows")
    return df.reset_index(drop=True)


# ── Step 2: Derived calendar columns ────────────────────────────────────
def run_derive_calendar(df: pd.DataFrame) -> pd.DataFrame:
    """Add calendar derived columns from the (already-shifted) invoice_date."""
    dt = df["invoice_date"].dt
    df["invoice_year"] = dt.year.astype("int32")
    df["invoice_month"] = dt.month.astype("int32")
    df["invoice_day"] = dt.day.astype("int32")
    df["invoice_quarter"] = dt.quarter.astype("int32")
    df["invoice_day_of_week"] = dt.dayofweek.astype(np.int32)  # 0=Mon
    df["invoice_week"] = dt.isocalendar().week.astype(np.int32)
    df["year_month"] = dt.strftime("%Y-%m").astype(str)
    return df


# ── Step 3: Quality check ───────────────────────────────────────────────
def run_quality_check(df: pd.DataFrame, year_month: str) -> tuple[pd.DataFrame, dict]:
    """Run TabularDataQuality checks and build a report dict."""
    dq = TabularDataQuality(df)
    metrics = dq.run_all_checks()

    report: dict = {
        "year_month": year_month,
        "initial_rows": len(df),
        "final_rows": len(df),
        "quality_metrics": metrics,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    return df, report


# ── Write helpers ───────────────────────────────────────────────────────
def write_silver_partition(df: pd.DataFrame, year_month: str) -> None:
    """Write Silver Parquet with explicit schema."""
    part_dir = SILVER_DIR / f"year_month={year_month}"
    part_dir.mkdir(parents=True, exist_ok=True)

    cols = [f.name for f in SILVER_SCHEMA]
    sub = df[cols].copy()
    # Force all string columns to plain str
    for col in sub.select_dtypes(include=["category", "object"]).columns:
        sub[col] = sub[col].astype(str)
    table = pa.Table.from_pandas(sub, schema=SILVER_SCHEMA)
    pq.write_table(table, part_dir / "data_silver.parquet", compression="snappy")
    print(f"  Written {len(df)} rows -> {part_dir / 'data_silver.parquet'}")


def write_quality_report(report: dict, year_month: str) -> None:
    """Write per-partition quality JSON and append to cumulative JSONL log."""
    qr_path = SILVER_DIR / f"year_month={year_month}" / "quality_report.json"
    qr_path.parent.mkdir(parents=True, exist_ok=True)
    with open(qr_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    log_path = SILVER_DIR / "_quality_log.jsonl"
    summary = {k: v for k, v in report.items() if k != "quality_metrics"}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, default=str) + "\n")


# ── Orchestrator ────────────────────────────────────────────────────────
def process(year_month: str) -> None:
    """Full Silver pipeline for one month."""
    out_path = SILVER_DIR / f"year_month={year_month}" / "data_silver.parquet"
    if out_path.exists():
        print(f"[SKIP] Silver {year_month} already exists.")
        return

    print(f"[SILVER] Processing {year_month} ...")
    df = load_bronze(year_month)
    df = run_cleaning(df)
    df = run_derive_calendar(df)
    df, report = run_quality_check(df, year_month)
    write_silver_partition(df, year_month)
    write_quality_report(report, year_month)
    print(f"[DONE] Silver {year_month}: {len(df)} rows\n")


def process_all() -> list[str]:
    """Process all Silver partitions, **newest month first**."""
    if not BRONZE_DIR.exists():
        print("[ERROR] No Bronze data found.")
        return []

    months: list[str] = sorted(
        [
            p.name.split("=")[1]
            for p in BRONZE_DIR.iterdir()
            if p.is_dir() and p.name.startswith("year_month=")
        ],
        reverse=True,
    )
    print(f"[SILVER-ALL] {len(months)} Bronze partitions, newest-first: "
          f"{months[0]} ... {months[-1]}")
    processed: list[str] = []
    for ym in months:
        process(ym)
        processed.append(ym)
    return processed


# ── CLI ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Silver transform")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--month", help="Process a single month (YYYY-MM)")
    group.add_argument(
        "--all",
        action="store_true",
        dest="process_all_months",
        help="Process all months, newest first",
    )
    args = parser.parse_args()

    if args.process_all_months:
        process_all()
    else:
        process(args.month)
