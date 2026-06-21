"""Feature engineering: Silver transactions → customer feature matrix.

Supports two modes:
- ``train``: computes features + churn labels (needs evaluation period data).
- ``score``: computes features only (no churn label; for batch prediction).
"""

from __future__ import annotations

import glob
from datetime import timedelta

import numpy as np
import pandas as pd
from scipy.stats import linregress

from ml.config import (
    EVALUATION_WINDOW_DAYS,
    FEATURE_COLUMNS,
    RANDOM_STATE,
    SILVER_DIR,
)


# Data loading
def load_silver_transactions(
    silver_dir: str | None = None,
    sample_frac: float | None = None,
) -> pd.DataFrame:
    """Load and concatenate all Silver partitions into one DataFrame."""
    pattern = str(silver_dir or SILVER_DIR) + "/year_month=*/data_silver.parquet"
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No silver parquet files found at: {pattern}"
        )

    frame = pd.concat(
        (pd.read_parquet(p) for p in files), ignore_index=True
    )
    frame["invoice_date"] = pd.to_datetime(frame["invoice_date"])
    frame["customer_id"] = frame["customer_id"].astype("string")

    if sample_frac:
        frame = frame.sample(
            frac=sample_frac, random_state=RANDOM_STATE
        ).reset_index(drop=True)

    return frame


# Churn label engineering
def create_churn_labels(
    df: pd.DataFrame,
    observation_end: pd.Timestamp,
) -> pd.DataFrame:
    """Create binary churn labels (1 = churned, 0 = retained).

    A customer is labelled *churned* when they have zero valid purchases
    in the evaluation period (everything after ``observation_end``).
    """
    observation_customers = (
        df.loc[
            (df["invoice_date"] <= observation_end)
            & df["customer_id"].notna()
            & (df["customer_id"].str.strip() != ""),
            "customer_id",
        ]
        .drop_duplicates()
        .sort_values()
    )

    evaluation_purchases = df.loc[
        (df["invoice_date"] > observation_end)
        & (~df["is_cancellation"])
        & df["customer_id"].notna()
        & (df["customer_id"].str.strip() != ""),
        "customer_id",
    ].drop_duplicates()

    labels = pd.DataFrame({"customer_id": observation_customers})
    labels["churn"] = (
        (~labels["customer_id"].isin(evaluation_purchases)).astype(int)
    )
    return labels


# Utility helpers
def safe_divide(
    numerator: pd.Series,
    denominator: pd.Series,
    default: float = 0.0,
) -> pd.Series:
    """Element-wise division that replaces inf/NaN with *default*."""
    result = numerator / denominator.replace(0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan).fillna(default)


def _monthly_slope(customer_monthly: pd.DataFrame) -> float:
    """Compute linear-regression slope of monthly revenue."""
    if len(customer_monthly) < 2:
        return 0.0
    x = customer_monthly["month_index"].to_numpy(dtype=float)
    y = customer_monthly["line_amount"].to_numpy(dtype=float)
    x = x - x.min()
    if np.allclose(y, y[0]):
        return 0.0
    return float(linregress(x, y).slope)


# Core feature builder
def build_customer_features(
    transactions: pd.DataFrame,
    observation_end: pd.Timestamp,
) -> pd.DataFrame:
    """Build a customer-level feature matrix from raw transactions.

    Only uses data up to ``observation_end`` (inclusive).
    Returns one row per ``customer_id`` with all ``FEATURE_COLUMNS``.
    """
    # Observation window only, remove anonymous rows
    obs = transactions.loc[
        (transactions["invoice_date"] <= observation_end)
        & transactions["customer_id"].notna()
        & (transactions["customer_id"].str.strip() != "")
    ].copy()
    valid = obs.loc[~obs["is_cancellation"]].copy()

    if obs.empty or valid.empty:
        raise ValueError(
            "Observation period has no customer transactions."
        )

    valid["price_quantity"] = valid["price"] * valid["quantity"]

    # Core RFM aggregation
    rfm = valid.groupby("customer_id").agg(
        last_purchase_date=("invoice_date", "max"),
        first_purchase_date=("invoice_date", "min"),
        frequency=("invoice", "nunique"),
        monetary=("line_amount", "sum"),
        total_quantity=("quantity", "sum"),
        unique_products=("stock_code", "nunique"),
        price_quantity_sum=("price_quantity", "sum"),
    )
    rfm["recency_days"] = (observation_end - rfm["last_purchase_date"]).dt.days
    rfm["tenure_days"] = (
        rfm["last_purchase_date"] - rfm["first_purchase_date"]
    ).dt.days
    rfm["days_since_first_purchase"] = (
        observation_end - rfm["first_purchase_date"]
    ).dt.days
    rfm["avg_order_value"] = safe_divide(rfm["monetary"], rfm["frequency"])
    rfm["avg_basket_size"] = safe_divide(
        rfm["total_quantity"], rfm["frequency"]
    )
    rfm["avg_unit_price"] = safe_divide(
        rfm["price_quantity_sum"], rfm["total_quantity"]
    )
    rfm["is_one_time_buyer"] = (rfm["frequency"] == 1).astype(int)

    # Inter-purchase gap features
    invoice_dates = (
        valid.groupby(["customer_id", "invoice"], as_index=False)
        .agg(invoice_date=("invoice_date", "min"))
        .sort_values(["customer_id", "invoice_date"])
    )
    invoice_dates["gap_days"] = (
        invoice_dates.groupby("customer_id")["invoice_date"]
        .diff()
        .dt.total_seconds()
        / 86_400
    )
    gap_features = invoice_dates.groupby("customer_id")["gap_days"].agg(
        avg_days_between_orders="mean",
        std_days_between_orders="std",
    )

    invoice_dates["is_weekend"] = (
        invoice_dates["invoice_date"].dt.dayofweek.isin([5, 6]).astype(int)
    )
    weekend_ratio = (
        invoice_dates.groupby("customer_id")["is_weekend"]
        .mean()
        .rename("weekend_purchase_ratio")
    )

    # Cancellation and return features
    invoice_counts = (
        obs.groupby("customer_id")["invoice"].nunique().rename("invoice_count")
    )
    cancellation_invoices = (
        obs.loc[obs["is_cancellation"]]
        .groupby("customer_id")["invoice"]
        .nunique()
        .rename("cancellation_invoice_count")
    )
    cancellation_rate = safe_divide(
        cancellation_invoices.reindex(invoice_counts.index).fillna(0),
        invoice_counts,
    ).rename("cancellation_rate")

    qty_positive = (
        obs.loc[obs["quantity"] > 0]
        .groupby("customer_id")["quantity"]
        .sum()
        .rename("qty_positive")
    )
    qty_negative = (
        obs.loc[obs["quantity"] < 0]
        .groupby("customer_id")["quantity"]
        .sum()
        .abs()
        .rename("qty_returned")
    )
    return_quantity_rate = safe_divide(
        qty_negative.reindex(invoice_counts.index).fillna(0),
        qty_positive.reindex(invoice_counts.index).fillna(0),
    ).rename("return_quantity_rate")

    # Per-invoice value features
    invoice_values = valid.groupby(
        ["customer_id", "invoice"], as_index=False
    ).agg(invoice_value=("line_amount", "sum"))
    order_value_features = invoice_values.groupby("customer_id")[
        "invoice_value"
    ].agg(
        max_single_order_value="max",
        min_single_order_value="min",
    )

    # Monetary trend (linear slope on monthly revenue)
    monthly = valid.assign(
        month_index=valid["invoice_date"].dt.year * 12
        + valid["invoice_date"].dt.month
    )
    monthly = monthly.groupby(
        ["customer_id", "month_index"], as_index=False
    )["line_amount"].sum()
    monetary_trend = (
        monthly.groupby("customer_id")
        .apply(_monthly_slope, include_groups=False)
        .rename("monetary_trend")
    )

    # Time-windowed features (30d / 90d / 180d)
    obs_30d = obs.loc[
        obs["invoice_date"] >= observation_end - pd.Timedelta(days=30)
    ]
    valid_30d = obs_30d.loc[~obs_30d["is_cancellation"]]
    freq_30d = (
        valid_30d.groupby("customer_id")["invoice"]
        .nunique()
        .rename("frequency_last_30d")
    )

    obs_90d = obs.loc[
        obs["invoice_date"] >= observation_end - pd.Timedelta(days=90)
    ]
    valid_90d = obs_90d.loc[~obs_90d["is_cancellation"]]
    freq_90d = (
        valid_90d.groupby("customer_id")["invoice"]
        .nunique()
        .rename("frequency_last_90d")
    )
    monetary_90d = (
        valid_90d.groupby("customer_id")["line_amount"]
        .sum()
        .rename("monetary_last_90d")
    )

    obs_180d = obs.loc[
        obs["invoice_date"] >= observation_end - pd.Timedelta(days=180)
    ]
    valid_180d = obs_180d.loc[~obs_180d["is_cancellation"]]
    freq_180d = (
        valid_180d.groupby("customer_id")["invoice"]
        .nunique()
        .rename("frequency_last_180d")
    )

    # Product diversity in last 90d
    unique_products_90d = (
        valid_90d.groupby("customer_id")["stock_code"]
        .nunique()
        .rename("unique_products_90d")
    )

    # Monetary acceleration (2nd-half vs 1st-half spending)
    obs_min_date = valid["invoice_date"].min()
    mid_point = obs_min_date + (observation_end - obs_min_date) / 2
    monetary_first_half = (
        valid.loc[valid["invoice_date"] < mid_point]
        .groupby("customer_id")["line_amount"]
        .sum()
        .rename("monetary_first_half")
    )
    monetary_second_half = (
        valid.loc[valid["invoice_date"] >= mid_point]
        .groupby("customer_id")["line_amount"]
        .sum()
        .rename("monetary_second_half")
    )

    is_uk = (
        obs.groupby("customer_id")["country"]
        .first()
        .apply(lambda x: 1 if x == "United Kingdom" else 0)
        .rename("is_uk")
    )

    # Assemble base feature matrix
    features = (
        rfm.join(gap_features)
        .join(cancellation_rate)
        .join(return_quantity_rate)
        .join(weekend_ratio)
        .join(order_value_features)
        .join(monetary_trend)
        .join(freq_30d)
        .join(freq_90d)
        .join(monetary_90d)
        .join(freq_180d)
        .join(unique_products_90d)
        .join(monetary_first_half)
        .join(monetary_second_half)
        .join(is_uk)
        .reset_index()
    )

    # Fill missing windowed features (customers absent in a window = 0)
    fill_zero_cols = [
        "frequency_last_30d",
        "frequency_last_90d",
        "monetary_last_90d",
        "frequency_last_180d",
        "unique_products_90d",
        "monetary_first_half",
        "monetary_second_half",
        "is_uk",
        "monetary_trend",
        "cancellation_rate",
        "return_quantity_rate",
        "weekend_purchase_ratio",
        "std_days_between_orders",
    ]
    for col in fill_zero_cols:
        if col in features.columns:
            features[col] = features[col].fillna(0)

    # avg_days_between_orders: NaN for one-time buyers → use recency_days
    features["avg_days_between_orders"] = features[
        "avg_days_between_orders"
    ].fillna(features["recency_days"])

    # Derived ratio features
    features["ratio_frequency_90d"] = safe_divide(
        features["frequency_last_90d"], features["frequency"]
    )
    features["velocity_ratio_180d"] = safe_divide(
        features["frequency_last_180d"], features["frequency"]
    )
    features["spending_recency_ratio"] = safe_divide(
        features["monetary_last_90d"], features["monetary"]
    )
    features["velocity_ratio_30d_90d"] = safe_divide(
        features["frequency_last_30d"],
        features["frequency_last_90d"].add(1),
    )
    features["overdue_ratio"] = safe_divide(
        features["recency_days"], features["avg_days_between_orders"]
    ).clip(upper=10.0)
    features["purchase_regularity"] = safe_divide(
        features["std_days_between_orders"],
        features["avg_days_between_orders"],
    ).clip(upper=5.0)
    features["recency_one_time"] = (
        features["recency_days"] * features["is_one_time_buyer"]
    )
    features["product_diversity_trend"] = safe_divide(
        features["unique_products_90d"], features["unique_products"]
    )
    features["monetary_acceleration"] = safe_divide(
        features["monetary_second_half"],
        features["monetary_first_half"].add(1),
    ).clip(upper=20.0)

    return features[["customer_id", *FEATURE_COLUMNS]]


# High-level orchestrator
def build_feature_matrix(
    silver_df: pd.DataFrame | None = None,
    observation_end: pd.Timestamp | None = None,
    mode: str = "train",
) -> pd.DataFrame:
    """Build the full feature matrix.

    Parameters
    ----------
    silver_df : Pre-loaded Silver DataFrame. Loaded from disk if *None*.
    observation_end : Cutoff date. Auto-computed if *None*.
    mode : ``"train"`` → returns features + ``churn`` column.
           ``"score"`` → returns features only (no label).

    Returns
    -------
    DataFrame with ``customer_id``, feature columns, and optionally ``churn``.
    """
    if silver_df is None:
        silver_df = load_silver_transactions()

    max_date = silver_df["invoice_date"].max()

    if mode == "train":
        if observation_end is None:
            observation_end = max_date - timedelta(
                days=EVALUATION_WINDOW_DAYS
            )
        features = build_customer_features(silver_df, observation_end)
        labels = create_churn_labels(silver_df, observation_end)
        return features.merge(labels, on="customer_id", how="inner")

    # score mode — use all available data as observation
    if observation_end is None:
        observation_end = max_date
    features = build_customer_features(silver_df, observation_end)
    return features
