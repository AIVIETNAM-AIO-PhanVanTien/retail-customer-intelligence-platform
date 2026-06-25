"""SHAP explainability for the churn XGBoost model.

Computes SHAP values on the held-out test set to explain which features
drive churn predictions — both globally (across all customers) and locally
(per individual customer).

Artifacts produced:
    ml/artifacts/shap/shap_values.npy         — (n_test, n_features) matrix
    ml/artifacts/shap/global_importance.csv    — mean |SHAP| per feature
    ml/artifacts/shap/expected_value.json      — base value (average model output)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd
import shap

from ml.config import ARTIFACT_DIR, FEATURE_COLUMNS

logger = logging.getLogger(__name__)

SHAP_ARTIFACT_DIR = ARTIFACT_DIR / "shap"


def compute_shap_values(
    pipeline: Any,
    X_test: pd.DataFrame,
    feature_names: list[str] | None = None,
) -> dict[str, Any]:
    """Compute SHAP values for the XGBoost step of the sklearn Pipeline.

    Uses ``shap.TreeExplainer`` which is exact and fast for tree models.
    The preprocessor (median imputer) is applied first so SHAP sees the
    same transformed data the model sees, but we keep original feature
    names for interpretability.

    Parameters
    ----------
    pipeline : Trained sklearn Pipeline with steps ``preprocess`` + ``model``.
    X_test : Raw test features (before preprocessing).
    feature_names : Feature column names. Defaults to ``FEATURE_COLUMNS``.

    Returns
    -------
    dict with keys:
        shap_values  — np.ndarray (n_samples, n_features)
        expected_value — float (base value / average model output)
        feature_names — list[str]
    """
    names = feature_names or FEATURE_COLUMNS

    preprocessor = pipeline.named_steps["preprocess"]
    xgb_model = pipeline.named_steps["model"]

    X_processed = preprocessor.transform(X_test[names])

    explainer = shap.TreeExplainer(xgb_model)
    shap_values = explainer.shap_values(X_processed)

    expected_value = float(explainer.expected_value)

    logger.info(
        "SHAP computed: %d samples × %d features, expected_value=%.4f",
        shap_values.shape[0],
        shap_values.shape[1],
        expected_value,
    )

    return {
        "shap_values": shap_values,
        "expected_value": expected_value,
        "feature_names": names,
    }


def global_shap_importance(
    shap_data: dict[str, Any],
) -> pd.DataFrame:
    """Compute global feature importance as mean |SHAP| per feature.

    Returns a DataFrame sorted by importance (descending) with columns:
        feature, mean_abs_shap
    """
    sv = shap_data["shap_values"]
    names = shap_data["feature_names"]

    mean_abs = np.abs(sv).mean(axis=0)

    importance = (
        pd.DataFrame({"feature": names, "mean_abs_shap": mean_abs})
        .sort_values("mean_abs_shap", ascending=False)
        .reset_index(drop=True)
    )
    return importance


def save_shap_artifacts(
    shap_data: dict[str, Any],
    artifact_dir: Path | None = None,
) -> Path:
    """Persist SHAP artifacts to disk.

    Saves:
        shap_values.npy         — raw SHAP value matrix
        global_importance.csv   — ranked mean |SHAP| table
        expected_value.json     — base value for waterfall calculations
    """
    out = artifact_dir or SHAP_ARTIFACT_DIR
    out.mkdir(parents=True, exist_ok=True)

    np.save(out / "shap_values.npy", shap_data["shap_values"])

    importance = global_shap_importance(shap_data)
    importance.to_csv(out / "global_importance.csv", index=False)

    with open(out / "expected_value.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "expected_value": shap_data["expected_value"],
                "n_samples": int(shap_data["shap_values"].shape[0]),
                "n_features": int(shap_data["shap_values"].shape[1]),
            },
            f,
            indent=2,
        )

    logger.info("SHAP artifacts saved → %s", out)
    return out


def log_shap_to_mlflow(
    shap_data: dict[str, Any],
    X_test: pd.DataFrame,
    feature_names: list[str] | None = None,
) -> None:
    """Log SHAP summary bar plot and importance CSV to the active MLflow run.

    Expects an active ``mlflow.start_run()`` context from ``pipeline.py``.
    """
    names = feature_names or FEATURE_COLUMNS
    sv = shap_data["shap_values"]

    importance = global_shap_importance(shap_data)

    # Log top feature importances as MLflow metrics
    for _, row in importance.head(10).iterrows():
        metric_key = f"shap_{row['feature']}"
        mlflow.log_metric(metric_key, float(row["mean_abs_shap"]))

    # Generate and log summary bar plot
    fig, ax = plt.subplots(figsize=(10, 8))
    top = importance.head(15)
    ax.barh(
        top["feature"][::-1],
        top["mean_abs_shap"][::-1],
        color="#1f77b4",
    )
    ax.set_xlabel("Mean |SHAP value|")
    ax.set_title("Global Feature Importance (SHAP)")
    fig.tight_layout()

    plot_path = SHAP_ARTIFACT_DIR / "shap_summary_bar.png"
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    mlflow.log_artifact(str(plot_path), artifact_path="shap")
    mlflow.log_artifact(
        str(SHAP_ARTIFACT_DIR / "global_importance.csv"),
        artifact_path="shap",
    )

    logger.info("SHAP artifacts logged to MLflow")
