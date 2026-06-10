"""Gold layer: star schema + RFM mart (ACM1-31, ACM1-36).

Loads all Silver partitions, builds a Kimball star schema
(dim_customer, dim_product, dim_date, dim_country, fact_transactions)
and an RFM mart with quintile scoring and segment labels.

Usage::

    python -m src.etl.gold_build
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ── Constants ────────────────────────────────────────────────────────────
SILVER_DIR: Path = Path("data/silver")
GOLD_DIR: Path = Path("data/gold")
SEED: int = 42

# ── RFM segment lookup  (r_score, f_score) → segment label ──────────────
SEGMENT_MAP: dict[tuple[int, int], str] = {
    # Champions  (high R, high F)
    (5, 5): "Champions",
    (5, 4): "Champions",
    (4, 5): "Champions",
    (4, 4): "Loyal Customers",
    # Loyal / Potential
    (3, 5): "Loyal Customers",
    (3, 4): "Potential Loyalists",
    (4, 3): "Loyal Customers",
    (3, 3): "Potential Loyalists",
    # New / Promising
    (5, 1): "New Customers",
    (5, 2): "Promising",
    (4, 1): "Promising",
    (4, 2): "Need Attention",
    # At Risk
    (2, 5): "Cannot Lose Them",
    (2, 4): "At Risk",
    (2, 3): "At Risk",
    (3, 2): "Need Attention",
    (3, 1): "About to Sleep",
    # Hibernating / Lost
    (1, 5): "Cannot Lose Them",
    (1, 4): "Cannot Lose Them",
    (1, 3): "Hibernating",
    (1, 2): "Hibernating",
    (1, 1): "Lost",
    (2, 2): "At Risk",
    (2, 1): "About to Sleep",
}

VALID_SEGMENTS = sorted(set(SEGMENT_MAP.values()))


# ── Load Silver ──────────────────────────────────────────────────────────
def load_all_silver() -> pd.DataFrame:
    """Concatenate all Silver partitions into a single DataFrame."""
    partitions = sorted(SILVER_DIR.glob("year_month=*/data_silver.parquet"))
    if not partitions:
        raise FileNotFoundError(f"No Silver partitions found in {SILVER_DIR}")

    frames = []
    for p in partitions:
        df = pq.ParquetFile(p).read().to_pandas()
        ym = p.parent.name.split("=")[1]
        df["_source_year_month"] = ym
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    print(f"[GOLD] Loaded {len(combined)} rows from {len(partitions)} Silver partitions")
    return combined


# ── Dimension builders ──────────────────────────────────────────────────
def build_dim_date(df: pd.DataFrame) -> pd.DataFrame:
    """Build dim_date from unique invoice_date values."""
    dates = pd.to_datetime(df["invoice_date"]).dt.date.unique()
    dates = sorted(dates)

    rows = []
    for i, d in enumerate(dates, start=1):
        dt = pd.Timestamp(d)
        rows.append(
            {
                "date_sk": i,
                "date": d,
                "year": dt.year,
                "month": dt.month,
                "week": int(dt.isocalendar()[1]),
                "day_of_week": dt.weekday(),
                "quarter": (dt.month - 1) // 3 + 1,
            }
        )
    dim = pd.DataFrame(rows)
    print(f"  dim_date: {len(dim)} rows")
    return dim


def build_dim_customer(df: pd.DataFrame) -> pd.DataFrame:
    """Build dim_customer with an 'Unknown' row for empty customer_ids (FK fix)."""
    # Create an 'Unknown' customer row (sk = 0) so fact rows with empty
    # customer_id get a valid FK instead of NaN.
    rows = [{"customer_sk": 0, "customer_id": "", "first_seen_date": pd.NaT, "segment": "Unknown"}]

    valid = df[df["customer_id"] != ""].copy()
    agg = (
        valid.groupby("customer_id")
        .agg(first_seen_date=("invoice_date", "min"))
        .reset_index()
    )
    agg["customer_sk"] = range(1, len(agg) + 1)
    agg["segment"] = "UNKNOWN"
    rows.extend(agg[["customer_sk", "customer_id", "first_seen_date", "segment"]].to_dict("records"))

    dim = pd.DataFrame(rows)
    print(f"  dim_customer: {len(dim)} rows (incl. Unknown sk=0)")
    return dim


def build_dim_product(df: pd.DataFrame) -> pd.DataFrame:
    """Build dim_product from unique stock_code (already upper-cased in Bronze)."""
    pairs = (
        df[["stock_code", "description"]]
        .drop_duplicates(subset=["stock_code"])
        .sort_values("stock_code")
        .reset_index(drop=True)
    )
    pairs["product_sk"] = range(1, len(pairs) + 1)
    dim = pairs[["product_sk", "stock_code", "description"]]
    print(f"  dim_product: {len(dim)} rows")
    return dim


def build_dim_country(df: pd.DataFrame) -> pd.DataFrame:
    """Build dim_country from unique country values."""
    countries = sorted(df["country"].unique())
    dim = pd.DataFrame(
        {
            "country_sk": range(1, len(countries) + 1),
            "country_name": countries,
        }
    )
    print(f"  dim_country: {len(dim)} rows")
    return dim


# ── Fact builder ────────────────────────────────────────────────────────
def build_fact_transactions(
    df: pd.DataFrame,
    dim_customer: pd.DataFrame,
    dim_product: pd.DataFrame,
    dim_country: pd.DataFrame,
    dim_date: pd.DataFrame,
) -> pd.DataFrame:
    """Build fact_transactions by joining surrogate keys from dimensions."""
    cust_map = dict(zip(dim_customer["customer_id"], dim_customer["customer_sk"]))
    prod_map = dict(zip(dim_product["stock_code"], dim_product["product_sk"]))
    cntry_map = dict(zip(dim_country["country_name"], dim_country["country_sk"]))

    date_map = {
        str(d): sk
        for sk, d in zip(dim_date["date_sk"], dim_date["date"])
    }

    fact = df.copy()
    fact["transaction_sk"] = range(1, len(fact) + 1)

    fact["customer_sk"] = fact["customer_id"].map(cust_map)
    fact["product_sk"] = fact["stock_code"].map(prod_map)
    fact["country_sk"] = fact["country"].map(cntry_map)
    fact["date_sk"] = pd.to_datetime(fact["invoice_date"]).dt.date.astype(str).map(
        date_map
    )

    out_cols = [
        "transaction_sk",
        "customer_sk",
        "product_sk",
        "country_sk",
        "date_sk",
        "quantity",
        "price",
        "line_amount",
    ]
    null_fk = int(fact["customer_sk"].isna().sum())
    print(f"  fact_transactions: {len(fact)} rows (customer_sk null: {null_fk})")
    return fact[out_cols]


# ── RFM mart ─────────────────────────────────────────────────────────────
def build_rfm_mart(df: pd.DataFrame) -> pd.DataFrame:
    """Build RFM mart with quintile scores and segment labels.

    Filters: only non-cancellation rows with valid customer_id AND
    only positive line_amount invoices for both frequency and monetary.
    """
    mask = (df["customer_id"] != "") & (~df["is_cancellation"])
    valid = df[mask].copy()

    # Only keep rows with positive line_amount for both F and M consistency
    valid = valid[valid["line_amount"] > 0].copy()

    reference_date = valid["invoice_date"].max()

    rfm = (
        valid.groupby("customer_id")
        .agg(
            last_purchase=("invoice_date", "max"),
            frequency=("invoice", "nunique"),
            monetary=("line_amount", "sum"),
        )
        .reset_index()
    )

    rfm["recency_days"] = (reference_date - rfm["last_purchase"]).dt.days

    # Quintile scoring (1-5)
    n = len(rfm)
    rfm["r_score"] = pd.qcut(
        rfm["recency_days"].rank(method="first"),
        q=min(n, 5),
        labels=list(range(min(n, 5), 0, -1)),
        duplicates="drop",
    ).astype(int)
    rfm["f_score"] = pd.qcut(
        rfm["frequency"].rank(method="first"),
        q=min(n, 5),
        labels=list(range(1, min(n, 5) + 1)),
        duplicates="drop",
    ).astype(int)
    rfm["m_score"] = pd.qcut(
        rfm["monetary"].rank(method="first"),
        q=min(n, 5),
        labels=list(range(1, min(n, 5) + 1)),
        duplicates="drop",
    ).astype(int)

    # Segment assignment via (r_score, f_score) lookup
    def _segment(row: pd.Series) -> str:
        return SEGMENT_MAP.get(
            (int(row["r_score"]), int(row["f_score"])), "Need Attention"
        )

    rfm["segment"] = rfm.apply(_segment, axis=1)

    out_cols = [
        "customer_id",
        "recency_days",
        "frequency",
        "monetary",
        "r_score",
        "f_score",
        "m_score",
        "segment",
    ]
    print(f"  mart_rfm: {len(rfm)} customers, "
          f"segments: {rfm['segment'].value_counts().to_dict()}")
    return rfm[out_cols]


def enrich_dim_customer_with_segment(
    dim_customer: pd.DataFrame, rfm: pd.DataFrame
) -> pd.DataFrame:
    """Fill segment in dim_customer from the RFM mart."""
    seg_map = dict(zip(rfm["customer_id"], rfm["segment"]))
    dim_customer["segment"] = (
        dim_customer["customer_id"]
        .map(seg_map)
        .fillna(dim_customer["segment"])  # keep 'Unknown' for sk=0
    )
    return dim_customer


# ── Write helpers ───────────────────────────────────────────────────────
def _write_table(df: pd.DataFrame, name: str, gold_dir: Path) -> None:
    """Write a Gold table as snappy-compressed Parquet."""
    out_dir = gold_dir / name
    out_dir.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df)
    pq.write_table(table, out_dir / f"{name}.parquet", compression="snappy")
    print(f"  Written {name}: {len(df)} rows -> {out_dir}")


def write_build_log(
    n_silver: int,
    dim_customer: pd.DataFrame,
    dim_product: pd.DataFrame,
    dim_country: pd.DataFrame,
    dim_date: pd.DataFrame,
    fact: pd.DataFrame,
    rfm: pd.DataFrame,
) -> None:
    """Write _build_log.json audit."""
    log = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "silver_rows": n_silver,
        "dim_customer_rows": len(dim_customer),
        "dim_product_rows": len(dim_product),
        "dim_country_rows": len(dim_country),
        "dim_date_rows": len(dim_date),
        "fact_transactions_rows": len(fact),
        "fact_null_customer_sk": int(fact["customer_sk"].isna().sum()),
        "mart_rfm_customers": len(rfm),
        "rfm_segments": rfm["segment"].value_counts().to_dict(),
    }
    out = GOLD_DIR / "_build_log.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, default=str)
    print(f"  Written _build_log.json -> {out}")


# ── Orchestrator ────────────────────────────────────────────────────────
def build() -> None:
    """Build the full Gold layer: star schema + RFM mart."""
    if (GOLD_DIR / "fact_transactions").exists():
        print("[SKIP] Gold already built. Delete data/gold/ to rebuild.")
        return

    print("[GOLD] Building star schema + RFM mart ...\n")

    df = load_all_silver()
    n_silver = len(df)

    # Dimensions
    dim_date = build_dim_date(df)
    dim_customer = build_dim_customer(df)
    dim_product = build_dim_product(df)
    dim_country = build_dim_country(df)

    # Fact
    fact = build_fact_transactions(df, dim_customer, dim_product, dim_country, dim_date)

    # RFM
    rfm = build_rfm_mart(df)

    # Enrich customer dimension with segment
    dim_customer = enrich_dim_customer_with_segment(dim_customer, rfm)

    # Write all tables
    _write_table(dim_date, "dim_date", GOLD_DIR)
    _write_table(dim_customer, "dim_customer", GOLD_DIR)
    _write_table(dim_product, "dim_product", GOLD_DIR)
    _write_table(dim_country, "dim_country", GOLD_DIR)
    _write_table(fact, "fact_transactions", GOLD_DIR)
    _write_table(rfm, "mart_rfm", GOLD_DIR)

    # Audit
    write_build_log(n_silver, dim_customer, dim_product, dim_country, dim_date, fact, rfm)

    print(f"\n[GOLD DONE] Star schema + RFM mart built successfully.")


# ── CLI ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    build()
