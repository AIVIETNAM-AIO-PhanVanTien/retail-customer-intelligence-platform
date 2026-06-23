"""Model evaluation, QA gate check, and threshold optimisation."""

from __future__ import annotations

import logging
from typing import Any
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)

from ml.config import QA_AUC_GATE

logger = logging.getLogger(__name__)


def evaluate_model(
    model: Any,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> dict[str, float]:
    """Compute all evaluation metrics for a single model."""
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    return {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision_churn": precision_score(
            y_test, y_pred, pos_label=1, zero_division=0
        ),
        "recall_churn": recall_score(
            y_test, y_pred, pos_label=1, zero_division=0
        ),
        "f1_churn": f1_score(
            y_test, y_pred, pos_label=1, zero_division=0
        ),
        "auc_roc": roc_auc_score(y_test, y_proba),
    }



def find_optimal_threshold(
    model: Any,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> tuple[float, dict[str, float]]:
    """Find the threshold that maximises F1-score on the test set.

    Returns
    -------
    (optimal_threshold, metrics_at_threshold)
    """
    y_proba = model.predict_proba(X_test)[:, 1]
    precisions, recalls, thresholds = precision_recall_curve(y_test, y_proba)

    f1_scores = (
        2
        * precisions[:-1]
        * recalls[:-1]
        / np.clip(precisions[:-1] + recalls[:-1], 1e-12, None)
    )
    optimal_idx = int(np.nanargmax(f1_scores)) if len(f1_scores) else 0
    optimal_threshold = (
        float(thresholds[optimal_idx]) if len(thresholds) else 0.5
    )

    y_pred_opt = (y_proba >= optimal_threshold).astype(int)
    metrics = {
        "threshold": optimal_threshold,
        "precision_churn": precision_score(
            y_test, y_pred_opt, pos_label=1, zero_division=0
        ),
        "recall_churn": recall_score(
            y_test, y_pred_opt, pos_label=1, zero_division=0
        ),
        "f1_churn": f1_score(
            y_test, y_pred_opt, pos_label=1, zero_division=0
        ),
    }

    logger.info(
        "Optimal threshold: %.3f (F1=%.4f)",
        optimal_threshold,
        metrics["f1_churn"],
    )
    return optimal_threshold, metrics


def log_evaluation_to_mlflow(
    model_name: str,
    test_metrics: dict[str, float],
    optimal_threshold: float,
    threshold_metrics: dict[str, float],
) -> None:
    """Log test-set evaluation metrics to the active MLflow run."""
    mlflow.log_metric("test_auc_roc", test_metrics["auc_roc"])
    mlflow.log_metric("test_accuracy", test_metrics["accuracy"])
    mlflow.log_metric("test_precision_churn", test_metrics["precision_churn"])
    mlflow.log_metric("test_recall_churn", test_metrics["recall_churn"])
    mlflow.log_metric("test_f1_churn", test_metrics["f1_churn"])
    mlflow.log_metric("optimal_threshold", optimal_threshold)
    mlflow.log_metric("opt_f1_churn", threshold_metrics["f1_churn"])
    mlflow.set_tag("best_model", model_name)
    mlflow.set_tag("qa_gate_passed", str(test_metrics["auc_roc"] >= QA_AUC_GATE))
