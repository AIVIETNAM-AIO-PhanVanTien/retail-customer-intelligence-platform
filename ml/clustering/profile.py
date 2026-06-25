"""Cluster profiling: compute feature statistics and assign labels."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ml.config import FEATURE_COLUMNS

logger = logging.getLogger(__name__)


def build_cluster_profiles(
    features_df: pd.DataFrame,
    labels: np.ndarray,
    feature_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Compute mean feature values and relative deviation per cluster.

    Returns a DataFrame with one row per cluster containing:
    - raw mean of each feature
    - ``cluster_size``, ``cluster_pct``
    """
    cols = feature_columns or FEATURE_COLUMNS
    df = features_df[cols].copy()
    df["cluster"] = labels

    overall_mean = df[cols].mean()
    profiles = df.groupby("cluster")[cols].mean()

    # Relative deviation from overall mean (%)
    relative = (profiles - overall_mean) / overall_mean.replace(0, np.nan) * 100
    relative = relative.add_suffix("_rel_pct")

    # Cluster sizes
    sizes = df.groupby("cluster").size().rename("cluster_size")
    pcts = (sizes / len(df) * 100).rename("cluster_pct")

    return profiles.join(relative).join(sizes).join(pcts)


def assign_cluster_labels(profiles: pd.DataFrame) -> dict[int, str]:
    """Assign human-readable labels based on dominant feature patterns.

    Examines the relative deviation of key behavioral indicators
    to determine the most descriptive name for each cluster.
    """
    labels: dict[int, str] = {}

    for cluster_id, row in profiles.iterrows():
        label = _classify_cluster(row)
        labels[int(cluster_id)] = label
        logger.info("Cluster %d → %s", cluster_id, label)

    # Resolve duplicates by appending cluster id
    seen: dict[str, int] = {}
    for cid, name in sorted(labels.items()):
        if name in seen:
            prev_id = seen[name]
            labels[prev_id] = f"{name} A"
            labels[cid] = f"{name} B"
        seen[name] = cid

    return labels


def _classify_cluster(row: pd.Series) -> str:
    """Rule-based classification of a single cluster profile."""

    def rel(feat: str) -> float:
        col = f"{feat}_rel_pct"
        return float(row.get(col, 0.0))

    # High-value + active
    if rel("monetary") > 50 and rel("frequency") > 30 and rel("recency_days") < -20:
        return "High-Value Active"

    # High-value + declining (high monetary but negative trend)
    if rel("monetary") > 30 and rel("monetary_trend") < -30:
        return "Declining Premium"

    # Dormant — high recency, low frequency
    if rel("recency_days") > 50 and rel("frequency") < -20:
        return "Dormant"

    # One-time / new buyers — low tenure, low frequency
    if rel("tenure_days") < -30 and rel("frequency") < -20:
        return "New / One-Time Buyers"

    # Frequent budget shoppers — high frequency, low monetary
    if rel("frequency") > 20 and rel("monetary") < -20:
        return "Frequent Budget Shoppers"

    # At-risk — high cancellation or return rates
    if rel("cancellation_rate") > 50 or rel("return_quantity_rate") > 50:
        return "High-Return / Problematic"

    # Low-engagement — below average across the board
    if rel("monetary") < -30 and rel("frequency") < -30:
        return "Low-Engagement"

    return "Average Regulars"
