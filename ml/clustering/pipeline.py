"""Clustering pipeline — CLI entry point.

Usage::

    python -m ml.clustering.pipeline
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import joblib
import mlflow
import numpy as np
import pandas as pd

from ml.config import (
    CLUSTERING_ARTIFACT_DIR,
    FEATURE_COLUMNS,
    GOLD_DIR,
    MLFLOW_CLUSTERING_EXPERIMENT,
    MLFLOW_TRACKING_URI,
)
from ml.clustering.evaluate import evaluate_clustering, log_clustering_to_mlflow
from ml.clustering.preprocessing import build_clustering_preprocessor
from ml.clustering.profile import assign_cluster_labels, build_cluster_profiles
from ml.clustering.train import find_optimal_k, select_best_k, train_kmeans
from ml.features import build_feature_matrix

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _save_clustering_artifacts(
    model: object,
    preprocessor: object,
    k: int,
    metrics: dict[str, float],
    cluster_labels: dict[int, str],
    artifact_dir: Path | None = None,
) -> Path:
    """Persist clustering model + preprocessor + metadata."""
    out = artifact_dir or CLUSTERING_ARTIFACT_DIR
    out.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, out / "model.joblib")
    joblib.dump(preprocessor, out / "preprocessor.joblib")
    logger.info("Model + preprocessor saved → %s", out)

    metadata = {
        "model_type": "KMeans",
        "k": k,
        "feature_columns": FEATURE_COLUMNS,
        "cluster_labels": {str(k): v for k, v in cluster_labels.items()},
        "metrics": metrics,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(out / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, default=str)

    return out


def _save_cluster_output(
    customer_ids: pd.Series,
    labels: np.ndarray,
    cluster_labels: dict[int, str],
    output_dir: Path | None = None,
) -> Path:
    """Write cluster assignments to Gold layer as Parquet."""
    out = output_dir or (GOLD_DIR / "mart_customer_clusters")
    out.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame({
        "customer_id": customer_ids.values,
        "cluster_id": labels,
        "cluster_name": [cluster_labels[c] for c in labels],
    })

    path = out / "mart_customer_clusters.parquet"
    df.to_parquet(path, index=False, compression="snappy")
    logger.info("Cluster assignments saved → %s (%d rows)", path, len(df))
    return path


def run_clustering_pipeline() -> None:
    """Full clustering pipeline: features → scale → find k → fit → profile → save."""
    logger.info("=" * 60)
    logger.info("CLUSTERING PIPELINE START")
    logger.info("=" * 60)

    # 1. Build features (score mode — all customers, no churn label)
    logger.info("[1/6] Building feature matrix (score mode)...")
    features_df = build_feature_matrix(mode="score")
    X = features_df[FEATURE_COLUMNS].copy()
    logger.info("Feature matrix: %d customers × %d features", len(X), X.shape[1])

    # 2. Preprocess (impute + log1p skewed + scale)
    logger.info("[2/6] Preprocessing (impute → log1p → scale)...")
    preprocessor = build_clustering_preprocessor()
    X_scaled = preprocessor.fit_transform(X)

    # 3. Find optimal k
    logger.info("[3/6] Searching optimal k (Elbow + Silhouette)...")
    k_results = find_optimal_k(X_scaled)
    best_k = select_best_k(k_results)

    # 4. Train final model
    logger.info("[4/6] Training K-Means (k=%d)...", best_k)
    model, labels = train_kmeans(X_scaled, best_k)

    # 5. Profile clusters + assign labels
    logger.info("[5/6] Profiling clusters...")
    profiles = build_cluster_profiles(features_df, labels)
    cluster_labels = assign_cluster_labels(profiles)
    cluster_sizes = dict(zip(*np.unique(labels, return_counts=True)))

    # 6. Evaluate + save
    logger.info("[6/6] Evaluating + saving artifacts...")
    metrics = evaluate_clustering(X_scaled, labels)

    # MLflow logging
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_CLUSTERING_EXPERIMENT)

    with mlflow.start_run(run_name="kmeans-clustering"):
        log_clustering_to_mlflow(
            k=best_k,
            metrics=metrics,
            cluster_labels=cluster_labels,
            cluster_sizes={int(k): int(v) for k, v in cluster_sizes.items()},
            n_customers=len(features_df),
            n_features=len(FEATURE_COLUMNS),
            k_search_results=k_results,
        )

        # Save model artifacts
        _save_clustering_artifacts(
            model=model,
            preprocessor=preprocessor,
            k=best_k,
            metrics=metrics,
            cluster_labels=cluster_labels,
        )

        # Save cluster profile as CSV artifact for MLflow
        profiles_path = CLUSTERING_ARTIFACT_DIR / "cluster_profiles.csv"
        CLUSTERING_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        profiles.to_csv(profiles_path)
        mlflow.log_artifact(str(profiles_path))

    # Save Gold output
    _save_cluster_output(
        customer_ids=features_df["customer_id"],
        labels=labels,
        cluster_labels=cluster_labels,
    )

    logger.info("=" * 60)
    logger.info(
        "CLUSTERING PIPELINE DONE — k=%d  silhouette=%.4f",
        best_k,
        metrics["silhouette_score"],
    )
    for cid, name in sorted(cluster_labels.items()):
        logger.info("  Cluster %d: %s (%d customers)", cid, name, cluster_sizes[cid])
    logger.info("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="ML Customer Clustering Pipeline")
    parser.parse_args()
    run_clustering_pipeline()


if __name__ == "__main__":
    main()
