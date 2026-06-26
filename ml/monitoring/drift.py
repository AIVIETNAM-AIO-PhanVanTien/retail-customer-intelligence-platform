"""ml/monitoring/drift.py

Data-drift and model-drift detection for the churn pipeline.

Data drift   — compares the current feature distribution against the
               training baseline (mean/std stored in metadata.json).
Model drift  — tracks churn score distribution shift and high-risk
               customer count over time.

All metrics are returned as plain dicts so they can be logged to
MLflow and/or written to the monitoring parquet table.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ml.config import ARTIFACT_DIR, FEATURE_COLUMNS, GOLD_DIR

log = logging.getLogger(__name__)

SCORES_PATH = GOLD_DIR / "mart_churn_scores" / "mart_churn_scores.parquet"
METADATA_PATH = ARTIFACT_DIR / "metadata.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_scores() -> pd.DataFrame:
    if not SCORES_PATH.exists():
        raise FileNotFoundError(f"Churn scores not found at {SCORES_PATH}")
    return pd.read_parquet(SCORES_PATH)


def _load_metadata() -> dict:
    if not METADATA_PATH.exists():
        raise FileNotFoundError(f"Model metadata not found at {METADATA_PATH}")
    with open(METADATA_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Data drift
# ---------------------------------------------------------------------------

def compute_data_drift(scores_df: pd.DataFrame, metadata: dict) -> dict[str, float]:
    """Compare current feature distributions against training baseline.

    Uses a simple z-score approach: for each feature, compute how many
    standard deviations the current mean is from the training mean.
    A |z| > 3 is flagged as drifted.

    Returns a flat dict of metrics suitable for MLflow logging.
    """
    baseline: dict = metadata.get("feature_stats", {})
    if not baseline:
        log.warning("No feature_stats in metadata — skipping data drift.")
        return {}

    drift_metrics: dict[str, float] = {}
    drifted_features: list[str] = []

    available = [f for f in FEATURE_COLUMNS if f in scores_df.columns and f in baseline]

    for feature in available:
        current_mean = float(scores_df[feature].mean())
        current_std = float(scores_df[feature].std())
        baseline_mean = float(baseline[feature]["mean"])
        baseline_std = float(baseline[feature]["std"])

        # z-score of current mean relative to training distribution
        z = (
            abs(current_mean - baseline_mean) / baseline_std
            if baseline_std > 0
            else 0.0
        )

        drift_metrics[f"drift_z_{feature}"] = round(z, 4)
        drift_metrics[f"current_mean_{feature}"] = round(current_mean, 4)

        if z > 3.0:
            drifted_features.append(feature)
            log.warning("Data drift detected: %s (z=%.2f)", feature, z)

    drift_metrics["n_features_checked"] = float(len(available))
    drift_metrics["n_features_drifted"] = float(len(drifted_features))
    drift_metrics["drift_rate"] = round(
        len(drifted_features) / len(available) if available else 0.0, 4
    )

    log.info(
        "Data drift: %d/%d features drifted (rate=%.2f)",
        len(drifted_features),
        len(available),
        drift_metrics["drift_rate"],
    )
    return drift_metrics


# ---------------------------------------------------------------------------
# Model drift
# ---------------------------------------------------------------------------

def compute_model_drift(scores_df: pd.DataFrame, metadata: dict) -> dict[str, float]:
    """Track churn score distribution and risk-tier counts over time.

    Compares current score distribution stats against the training-time
    baseline stored in metadata.json.
    """
    metrics: dict[str, float] = {}

    if "churn_probability" not in scores_df.columns:
        log.warning("churn_probability column missing — skipping model drift.")
        return metrics

    probs = scores_df["churn_probability"]

    # Current score distribution
    metrics["score_mean"] = round(float(probs.mean()), 4)
    metrics["score_std"] = round(float(probs.std()), 4)
    metrics["score_p25"] = round(float(probs.quantile(0.25)), 4)
    metrics["score_p50"] = round(float(probs.quantile(0.50)), 4)
    metrics["score_p75"] = round(float(probs.quantile(0.75)), 4)
    metrics["score_p90"] = round(float(probs.quantile(0.90)), 4)

    # Risk tier counts
    if "risk_tier" in scores_df.columns:
        tier_counts = scores_df["risk_tier"].value_counts()
        metrics["n_high_risk"] = float(tier_counts.get("High", 0))
        metrics["n_medium_risk"] = float(tier_counts.get("Medium", 0))
        metrics["n_low_risk"] = float(tier_counts.get("Low", 0))
        metrics["pct_high_risk"] = round(
            metrics["n_high_risk"] / len(scores_df), 4
        )

    # Drift vs training baseline
    baseline_mean = metadata.get("score_mean_train")
    baseline_std = metadata.get("score_std_train")
    if baseline_mean is not None and baseline_std is not None:
        score_z = (
            abs(metrics["score_mean"] - baseline_mean) / baseline_std
            if baseline_std > 0
            else 0.0
        )
        metrics["score_distribution_z"] = round(score_z, 4)
        if score_z > 2.0:
            log.warning(
                "Model drift detected: score mean shifted by z=%.2f", score_z
            )

    metrics["total_customers_scored"] = float(len(scores_df))
    log.info(
        "Model drift: score_mean=%.4f, pct_high_risk=%.2f%%",
        metrics["score_mean"],
        metrics.get("pct_high_risk", 0) * 100,
    )
    return metrics