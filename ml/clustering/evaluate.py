"""Clustering quality metrics and MLflow logging."""

from __future__ import annotations

import logging
from typing import Any

import mlflow
import numpy as np
from sklearn.metrics import (
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)

logger = logging.getLogger(__name__)


def evaluate_clustering(
    X_scaled: np.ndarray,
    labels: np.ndarray,
) -> dict[str, float]:
    """Compute clustering quality metrics.

    Returns
    -------
    Dict with silhouette_score, calinski_harabasz, davies_bouldin.
    Lower Davies-Bouldin is better; higher Silhouette/Calinski is better.
    """
    return {
        "silhouette_score": silhouette_score(X_scaled, labels),
        "calinski_harabasz": calinski_harabasz_score(X_scaled, labels),
        "davies_bouldin": davies_bouldin_score(X_scaled, labels),
    }


def log_clustering_to_mlflow(
    k: int,
    metrics: dict[str, float],
    cluster_labels: dict[int, str],
    cluster_sizes: dict[int, int],
    n_customers: int,
    n_features: int,
    k_search_results: list[Any] | None = None,
) -> None:
    """Log clustering experiment to the active MLflow run."""
    mlflow.log_param("k", k)
    mlflow.log_param("n_customers", n_customers)
    mlflow.log_param("n_features", n_features)
    mlflow.log_param("model_type", "KMeans")

    for name, value in metrics.items():
        mlflow.log_metric(name, value)

    # Log cluster metadata as tags
    for cid, label in cluster_labels.items():
        mlflow.set_tag(f"cluster_{cid}_name", label)
    for cid, size in cluster_sizes.items():
        mlflow.log_metric(f"cluster_{cid}_size", size)

    # Log k-search results as metrics
    if k_search_results:
        for r in k_search_results:
            mlflow.log_metric(
                f"silhouette_k{r.k}", r.silhouette
            )
            mlflow.log_metric(f"inertia_k{r.k}", r.inertia)
