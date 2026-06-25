"""K-Means training: optimal k selection and model fitting."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from ml.config import CLUSTERING_K_RANGE, RANDOM_STATE

logger = logging.getLogger(__name__)


@dataclass
class KSearchResult:
    """Metrics for one candidate k value."""

    k: int
    inertia: float
    silhouette: float


def find_optimal_k(
    X_scaled: np.ndarray,
    k_range: range | None = None,
) -> list[KSearchResult]:
    """Evaluate K-Means for each k and return quality metrics.

    Parameters
    ----------
    X_scaled : Preprocessed (scaled) feature matrix.
    k_range : Range of k values to try. Defaults to ``CLUSTERING_K_RANGE``.

    Returns
    -------
    List of ``KSearchResult`` sorted by k (ascending).
    """
    ks = k_range or CLUSTERING_K_RANGE
    results: list[KSearchResult] = []

    for k in ks:
        km = KMeans(
            n_clusters=k,
            random_state=RANDOM_STATE,
            n_init=10,
            max_iter=300,
        )
        labels = km.fit_predict(X_scaled)
        sil = silhouette_score(X_scaled, labels)
        results.append(KSearchResult(k=k, inertia=km.inertia_, silhouette=sil))
        logger.info("k=%d  inertia=%.1f  silhouette=%.4f", k, km.inertia_, sil)

    return results


def select_best_k(results: list[KSearchResult]) -> int:
    """Pick k with the highest silhouette score."""
    best = max(results, key=lambda r: r.silhouette)
    logger.info(
        "Selected k=%d (silhouette=%.4f)", best.k, best.silhouette
    )
    return best.k


def train_kmeans(
    X_scaled: np.ndarray,
    k: int,
) -> tuple[KMeans, np.ndarray]:
    """Fit final K-Means model with the chosen k.

    Returns
    -------
    (fitted_model, cluster_labels)
    """
    model = KMeans(
        n_clusters=k,
        random_state=RANDOM_STATE,
        n_init=10,
        max_iter=300,
    )
    labels = model.fit_predict(X_scaled)

    sizes = np.bincount(labels)
    for i, s in enumerate(sizes):
        logger.info("Cluster %d: %d customers (%.1f%%)", i, s, s / len(labels) * 100)

    return model, labels
