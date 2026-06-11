"""Bronze layer: ingest raw CSV into partitioned Parquet.

Reads the single online_retail_listing.csv (semicolon-delimited, European
decimals), normalises columns to snake_case, shifts dates to ~2026 so
recency/churn windows are meaningful, and writes hive-style Parquet
partitions keyed by shifted ``year_month``.

Date synthesis happens here (not in Silver) so all downstream layers
work with 2024-2026 dates from the start.

Processing order
----------------
``ingest_all()`` starts from the **most recent** month and iterates
backward so that the freshest data is committed first.

Usage::

    # single month (shifted key)
    python -m src.etl.bronze_ingest --month 2026-05

    # all months, newest first
    python -m src.etl.bronze_ingest --all
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ── Constants ────────────────────────────────────────────────────────────
RAW_PATH: Path = Path("data/raw/online_retail_listing.csv")
XLSX_PATH: Path = Path("data/raw/uci_original/online_retail_II.xlsx")
BRONZE_DIR: Path = Path("data/bronze")

# Date-shift: rebase max(original_date) ≈ today
# Original xlsx max date is 2011-12-09 (CSV was truncated to 2011-12-04)
REFERENCE_DATE_OLD = pd.Timestamp("2011-12-09")  # max date in original UCI dataset
REFERENCE_DATE_NEW = pd.Timestamp("2026-06-10")  # today
DATE_SHIFT_DAYS = (REFERENCE_DATE_NEW - REFERENCE_DATE_OLD).days  # 5 295

# ── PyArrow schema (explicit, not inferred) ──────────────────────────────
BRONZE_SCHEMA = pa.schema(
    [
        pa.field("invoice", pa.string()),
        pa.field("stock_code", pa.string()),
        pa.field("description", pa.string()),
        pa.field("quantity", pa.float64()),
        pa.field("invoice_date", pa.timestamp("us")),          # shifted
        pa.field("original_invoice_date", pa.timestamp("us")),  # original for audit
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
    """Scan the raw data and return shifted YYYY-MM strings, **newest first**."""
    df = _read_raw_file(raw_path, columns=["InvoiceDate"])
    dates = pd.to_datetime(
        df["InvoiceDate"].astype(str).str.strip(), format="mixed", dayfirst=True
    )
    shifted = dates + pd.Timedelta(days=DATE_SHIFT_DAYS)
    months = sorted(shifted.dt.to_period("M").unique(), reverse=True)
    return [str(m) for m in months]


def _read_raw_file(
    raw_path: Path,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Read raw CSV or XLSX. Supports both data sources."""
    usecols = columns if columns else None
    if raw_path.suffix.lower() == ".xlsx":
        df1 = pd.read_excel(raw_path, sheet_name=0, usecols=usecols)
        df2 = pd.read_excel(raw_path, sheet_name=1, usecols=usecols)
        df = pd.concat([df1, df2], ignore_index=True)
    else:
        df = pd.read_csv(
            raw_path, sep=";", usecols=usecols,
            dtype=str, encoding="ISO-8859-1",
        )
    return df


def _load_raw_all(raw_path: Path = RAW_PATH) -> pd.DataFrame:
    """Read the full raw data **once** (CSV or XLSX)."""
    if raw_path.suffix.lower() == ".xlsx":
        df = _read_raw_file(raw_path)
    else:
        df = pd.read_csv(
            raw_path, sep=";", dtype=str, encoding="ISO-8859-1",
        )
        df.columns = df.columns.str.strip()
    return df


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to snake_case, derive typed fields, shift dates."""
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

    # Parse original date
    df["invoice_date"] = df["invoice_date"].astype(str).str.strip()
    original = pd.to_datetime(df["invoice_date"], format="mixed", dayfirst=True, errors="coerce")
    df["original_invoice_date"] = original

    # Shift to ~2026
    df["invoice_date"] = original + pd.Timedelta(days=DATE_SHIFT_DAYS)

    # Types — handle both CSV (comma decimals) and XLSX (already numeric)
    if df["price"].dtype == object:
        df["quantity"] = pd.to_numeric(
            df["quantity"].astype(str).str.replace(",", "."), errors="coerce"
        )
        df["price"] = pd.to_numeric(
            df["price"].astype(str).str.replace(",", "."), errors="coerce"
        )
    else:
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
        df["price"] = pd.to_numeric(df["price"], errors="coerce")

    # customer_id → string (NaN → empty string)
    df["customer_id"] = (
        df["customer_id"].fillna("").astype(str).str.strip()
    )

    # Strip whitespace + upper-case stock_code to avoid case-sensitivity splits
    df["stock_code"] = df["stock_code"].fillna("").astype(str).str.strip().str.upper()
    for col in ("description", "country", "invoice"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()

    # Cancellation flag: invoice starts with 'C'
    df["is_cancellation"] = df["invoice"].str.startswith("C", na=False)

    # Drop helper columns if present
    for col in ("_parsed_date", "_ym"):
        if col in df.columns:
            df.drop(columns=[col], inplace=True)

    return df


# ── Main ingest ──────────────────────────────────────────────────────────
def ingest(year_month: str, raw_path: Path = RAW_PATH) -> None:
    """Ingest one month from the raw CSV into Bronze Parquet."""
    if already_ingested(year_month):
        print(f"[SKIP] Bronze {year_month} already exists.")
        return

    print(f"[INGEST] Loading raw data for {year_month} ...")
    df_raw = _load_raw_all(raw_path)
    df = normalize_columns(df_raw)

    # Filter to the requested shifted month
    df["_ym"] = df["invoice_date"].dt.to_period("M").astype(str)
    month_df = df[df["_ym"] == year_month].copy()
    month_df.drop(columns=["_ym"], inplace=True)

    if month_df.empty:
        print(f"[WARN] No rows found for {year_month}. Skipping.")
        return

    month_df["ingested_at"] = pd.Timestamp(datetime.now(timezone.utc))

    # Write partition
    part_dir = BRONZE_DIR / f"year_month={year_month}"
    part_dir.mkdir(parents=True, exist_ok=True)

    table = pa.Table.from_pandas(
        month_df[BRONZE_SCHEMA.names], schema=BRONZE_SCHEMA
    )
    pq.write_table(table, part_dir / "data.parquet", compression="snappy")

    # Audit log
    log_path = BRONZE_DIR / "_ingestion_log.csv"
    log_row = {
        "year_month": year_month,
        "row_count": len(month_df),
        "cancellation_count": int(month_df["is_cancellation"].sum()),
        "null_customer_count": int((month_df["customer_id"] == "").sum()),
        "min_invoice_date": str(month_df["invoice_date"].min()),
        "max_invoice_date": str(month_df["invoice_date"].max()),
        "unique_countries": int(month_df["country"].nunique()),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "source_file": raw_path.name,
    }
    log_df = pd.DataFrame([log_row])
    log_df.to_csv(
        log_path, mode="a", header=not log_path.exists(), index=False
    )
    print(
        f"[DONE] Bronze {year_month}: {len(month_df)} rows "
        f"({int(month_df['is_cancellation'].sum())} cancellations) -> {part_dir}"
    )


def ingest_all(raw_path: Path = RAW_PATH) -> list[str]:
    """Ingest **all** months, starting from the newest and iterating backward.

    Reads the CSV **once**, normalises once, then slices by shifted month.
    """
    months = _discover_months(raw_path)
    print(f"[DISCOVER] {len(months)} months found "
          f"({months[0]} ... {months[-1]}), processing newest-first.")

    # Load and normalise once
    print("[INGEST] Loading raw CSV ...")
    df_raw = _load_raw_all(raw_path)
    df = normalize_columns(df_raw)
    df["_ym"] = df["invoice_date"].dt.to_period("M").astype(str)

    processed: list[str] = []
    for ym in months:
        if already_ingested(ym):
            print(f"[SKIP] Bronze {ym} already exists.")
            processed.append(ym)
            continue

        month_df = df[df["_ym"] == ym].copy()
        month_df.drop(columns=["_ym"], inplace=True)

        if month_df.empty:
            continue

        month_df["ingested_at"] = pd.Timestamp(datetime.now(timezone.utc))

        part_dir = BRONZE_DIR / f"year_month={ym}"
        part_dir.mkdir(parents=True, exist_ok=True)

        table = pa.Table.from_pandas(
            month_df[BRONZE_SCHEMA.names], schema=BRONZE_SCHEMA
        )
        pq.write_table(table, part_dir / "data.parquet", compression="snappy")

        # Audit log
        log_path = BRONZE_DIR / "_ingestion_log.csv"
        log_row = {
            "year_month": ym,
            "row_count": len(month_df),
            "cancellation_count": int(month_df["is_cancellation"].sum()),
            "null_customer_count": int((month_df["customer_id"] == "").sum()),
            "min_invoice_date": str(month_df["invoice_date"].min()),
            "max_invoice_date": str(month_df["invoice_date"].max()),
            "unique_countries": int(month_df["country"].nunique()),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "source_file": raw_path.name,
        }
        log_df = pd.DataFrame([log_row])
        log_df.to_csv(
            log_path, mode="a", header=not log_path.exists(), index=False
        )
        print(
            f"[DONE] Bronze {ym}: {len(month_df)} rows "
            f"({int(month_df['is_cancellation'].sum())} cancellations) -> {part_dir}"
        )
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
