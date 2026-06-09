"""Bronze layer: ingest raw CSV into partitioned Parquet (ACM1-29).

Reads the single online_retail_listing.csv (semicolon-delimited, European
decimals), normalises columns to snake_case, flags cancellations, and writes
hive-style Parquet partitions keyed by ``year_month``.

Processing order
----------------
When calling ``ingest_all()`` the pipeline starts from the **most recent**
month and iterates backward so that the freshest data is committed first --
if the run fails partway through, you already have the latest partitions.

Usage::

    # single month
    python -m src.etl.bronze_ingest --month 2010-06

    # all months, newest first
    python -m src.etl.bronze_ingest --all
"""

from __future__ import annotations

import argparse
from datetime import datetime, UTC
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ── Constants ────────────────────────────────────────────────────────────
RAW_PATH: Path = Path("data/raw/online_retail_listing.csv")
BRONZE_DIR: Path = Path("data/bronze")
SEED: int = 42

# ── PyArrow schema (explicit, not inferred) ──────────────────────────────
BRONZE_SCHEMA = pa.schema(
    [
        pa.field("invoice", pa.string()),
        pa.field("stock_code", pa.string()),
        pa.field("description", pa.string()),
        pa.field("quantity", pa.float64()),
        pa.field("invoice_date", pa.timestamp("us")),
        pa.field("price", pa.float64()),
        pa.field("customer_id", pa.string()),
        pa.field("country", pa.string()),
        pa.field("is_cancellation", pa.bool_()),
        pa.field("ingested_at", pa.timestamp("us")),
    ]
)


# ── Helpers ──────────────────────────────────────────────────────────────
def already_ingested(year_month: str) -> bool:
    """Return True if the Bronze partition for *year_month* already exists."""
    return (BRONZE_DIR / f"year_month={year_month}" / "data.parquet").exists()


def _discover_months(raw_path: Path = RAW_PATH) -> list[str]:
    """Scan the raw CSV and return all unique YYYY-MM strings, **newest first**."""
    # Read only the InvoiceDate column to keep it fast
    df = pd.read_csv(
        raw_path,
        sep=";",
        usecols=["InvoiceDate"],
        dtype=str,
        encoding="ISO-8859-1",  # handles mixed £ encodings
    )
    # Parse dd.mm.yyyy HH:MM  (some rows have single-digit day/month)
    dates = pd.to_datetime(df["InvoiceDate"].str.strip(), format="mixed", dayfirst=True)
    months = sorted(dates.dt.to_period("M").unique(), reverse=True)
    return [str(m) for m in months]


def _load_raw_month(raw_path: Path, year_month: str) -> pd.DataFrame:
    """Read the full CSV and return only rows for *year_month*."""
    df = pd.read_csv(
        raw_path,
        sep=";",
        dtype=str,           # read all as str; decimal="," mangles values with dtype=str
        encoding="ISO-8859-1",  # handles mixed £ encodings (standalone \xa3 + UTF-8 \xc2\xa3)
    )
    # Strip column whitespace
    df.columns = df.columns.str.strip()

    # Parse InvoiceDate
    df["_parsed_date"] = pd.to_datetime(
        df["InvoiceDate"].str.strip(), format="mixed", dayfirst=True
    )
    df["_ym"] = df["_parsed_date"].dt.to_period("M").astype(str)
    month_df = df[df["_ym"] == year_month].copy()
    month_df.drop(columns=["_ym"], inplace=True)
    return month_df


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to snake_case and derive typed fields."""
    rename_map = {
        "Invoice": "invoice",
        "StockCode": "stock_code",
        "Description": "description",
        "Quantity": "quantity",
        "InvoiceDate": "invoice_date",
        "Price": "price",
        "Customer ID": "customer_id",
        "Country": "country",
    }
    df = df.rename(columns=rename_map)

    # Types
    df["invoice_date"] = pd.to_datetime(
        df["_parsed_date"], errors="coerce"
    )
    # European decimal comma → dot before numeric conversion
    df["quantity"] = pd.to_numeric(
        df["quantity"].str.replace(",", "."), errors="coerce"
    )
    df["price"] = pd.to_numeric(
        df["price"].str.replace(",", "."), errors="coerce"
    )

    # customer_id → string (NaN → empty string)
    df["customer_id"] = (
        df["customer_id"].fillna("").astype(str).str.strip()
    )

    # Strip whitespace on text columns
    for col in ("description", "stock_code", "country", "invoice"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()

    # Cancellation flag: invoice starts with 'C'
    df["is_cancellation"] = df["invoice"].str.startswith("C", na=False)

    # Drop helper column
    if "_parsed_date" in df.columns:
        df.drop(columns=["_parsed_date"], inplace=True)

    return df


# ── Main ingest ──────────────────────────────────────────────────────────
def ingest(year_month: str, raw_path: Path = RAW_PATH) -> None:
    """Ingest one month from the raw CSV into Bronze Parquet."""
    if already_ingested(year_month):
        print(f"[SKIP] Bronze {year_month} already exists.")
        return

    print(f"[INGEST] Loading raw data for {year_month} …")
    df_raw = _load_raw_month(raw_path, year_month)
    if df_raw.empty:
        print(f"[WARN] No rows found for {year_month}. Skipping.")
        return

    df = normalize_columns(df_raw)
    df["ingested_at"] = pd.Timestamp(datetime.now(UTC))

    # Write partition
    part_dir = BRONZE_DIR / f"year_month={year_month}"
    part_dir.mkdir(parents=True, exist_ok=True)

    table = pa.Table.from_pandas(df[BRONZE_SCHEMA.names], schema=BRONZE_SCHEMA)
    pq.write_table(table, part_dir / "data.parquet", compression="snappy")

    # Audit log
    log_path = BRONZE_DIR / "_ingestion_log.csv"
    log_row = {
        "year_month": year_month,
        "row_count": len(df),
        "cancellation_count": int(df["is_cancellation"].sum()),
        "null_customer_count": int((df["customer_id"] == "").sum()),
        "min_invoice_date": str(df["invoice_date"].min()),
        "max_invoice_date": str(df["invoice_date"].max()),
        "unique_countries": int(df["country"].nunique()),
        "ingested_at": datetime.now(UTC).isoformat(),
        "source_file": raw_path.name,
    }
    log_df = pd.DataFrame([log_row])
    log_df.to_csv(
        log_path, mode="a", header=not log_path.exists(), index=False
    )
    print(
        f"[DONE] Bronze {year_month}: {len(df)} rows "
        f"({int(df['is_cancellation'].sum())} cancellations) → {part_dir}"
    )


def ingest_all(raw_path: Path = RAW_PATH) -> list[str]:
    """Ingest **all** months, starting from the newest and iterating backward.

    Returns the list of months that were actually processed (skips already
    ingested partitions).
    """
    months = _discover_months(raw_path)
    print(f"[DISCOVER] {len(months)} months found "
          f"({months[0]} … {months[-1]}), processing newest-first.")
    processed: list[str] = []
    for ym in months:
        ingest(ym, raw_path)
        processed.append(ym)
    return processed


# ── CLI ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bronze ingestion")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--month", help="Ingest a single month (YYYY-MM)")
    group.add_argument(
        "--all",
        action="store_true",
        dest="ingest_all_months",
        help="Ingest all months, newest first",
    )
    args = parser.parse_args()

    if args.ingest_all_months:
        ingest_all()
    else:
        ingest(args.month)
