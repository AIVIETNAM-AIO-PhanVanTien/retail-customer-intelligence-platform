"""Batch scoring: predict churn probability for all customers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml.config import FEATURE_COLUMNS, GOLD_DIR

logger = logging.getLogger(__name__)


def batch_score(
    model: Any,
    features_df: pd.DataFrame,
    threshold: float,
    feature_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Score all customers and assign churn_flag + risk_tier.

    Parameters
    ----------
    model : Trained sklearn Pipeline (predict_proba capable).
    features_df : DataFrame with ``customer_id`` + feature columns.
    threshold : Optimal classification threshold.
    feature_columns : Feature columns to use. Defaults to ``FEATURE_COLUMNS``.

    Returns
    -------
    DataFrame with columns: customer_id, churn_probability, churn_flag, risk_tier
    """
    cols = feature_columns or FEATURE_COLUMNS
    probabilities = model.predict_proba(features_df[cols])[:, 1]

    scoring_df = pd.DataFrame(
        {
            "customer_id": features_df["customer_id"].values,
            "churn_probability": probabilities,
        }
    )
    scoring_df["churn_flag"] = (
        scoring_df["churn_probability"] >= threshold
    ).astype(int)
    scoring_df["risk_tier"] = np.select(
        [
            scoring_df["churn_probability"] >= 0.7,
            scoring_df["churn_probability"] >= 0.4,
        ],
        ["High", "Medium"],
        default="Low",
    )

    logger.info(
        "Scored %d customers — High: %d, Medium: %d, Low: %d",
        len(scoring_df),
        (scoring_df["risk_tier"] == "High").sum(),
        (scoring_df["risk_tier"] == "Medium").sum(),
        (scoring_df["risk_tier"] == "Low").sum(),
    )
    return scoring_df


def save_scores(
    scoring_df: pd.DataFrame,
    output_dir: Path | None = None,
) -> Path:
    """Write scoring results to Gold layer as Parquet."""
    out = output_dir or (GOLD_DIR / "mart_churn_scores")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "mart_churn_scores.parquet"
    scoring_df.to_parquet(path, index=False, compression="snappy")
    logger.info("Scores saved → %s (%d rows)", path, len(scoring_df))
    return path
