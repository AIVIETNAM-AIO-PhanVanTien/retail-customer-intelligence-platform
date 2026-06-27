"""Export the trained churn model into the serving ``app/`` folder.

Produces a self-contained bundle the Streamlit Space (and HuggingFace)
needs at runtime:

    app/model/model.pkl              — sklearn Pipeline (imputer + XGBoost)
    app/model/metadata.json          — threshold, feature list, score summary
    app/data/customers.parquet       — scored customer base (churn + cluster)
    app/data/cluster_profiles.parquet — cluster profile stats per cluster
    app/data/monitoring.parquet      — model/data drift monitoring history

Two entry points:

* ``export_serving_bundle(...)`` — called from the training pipeline with the
  freshly trained model (so every ``mlflow run`` refreshes ``app/``).
* ``python -m scripts.export_serving_app`` — standalone refresh that loads the
  last saved artifacts (``ml/artifacts/``) and rebuilds the bundle.
"""

from __future__ import annotations

import json
import logging
import pickle
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import joblib
import numpy as np
import pandas as pd

from ml.config import CLUSTERING_ARTIFACT_DIR, FEATURE_COLUMNS, GOLD_DIR, PROJECT_ROOT

logger = logging.getLogger(__name__)

APP_DIR = PROJECT_ROOT / "app"
DUCKDB_PATH = PROJECT_ROOT / "data" / "retail.duckdb"
MONITORING_PARQUET = GOLD_DIR / "mart_monitoring" / "mart_monitoring.parquet"


def _load_customer_features() -> pd.DataFrame:
    """Read the feature matrix + RFM segment for every customer from DuckDB."""
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        feat = con.execute("SELECT * FROM main.mart_features").fetchdf()
        rfm = con.execute(
            "SELECT customer_id, segment FROM main.mart_rfm"
        ).fetchdf()
    finally:
        con.close()
    return feat.merge(rfm, on="customer_id", how="left")


def _assign_clusters(df: pd.DataFrame) -> pd.DataFrame:
    """Load the clustering model and assign cluster_id + cluster_name to df."""
    model_path = CLUSTERING_ARTIFACT_DIR / "model.joblib"
    preprocessor_path = CLUSTERING_ARTIFACT_DIR / "preprocessor.joblib"
    meta_path = CLUSTERING_ARTIFACT_DIR / "metadata.json"

    if not model_path.exists():
        logger.warning("Clustering model not found at %s — skipping cluster assignment", model_path)
        return df

    km = joblib.load(model_path)
    preprocessor = joblib.load(preprocessor_path)

    with open(meta_path, encoding="utf-8") as fh:
        cluster_meta = json.load(fh)

    cluster_labels: dict[str, str] = cluster_meta.get("cluster_labels", {})
    cluster_features: list[str] = cluster_meta.get("feature_columns", FEATURE_COLUMNS)

    X = df[cluster_features].copy()
    X_scaled = preprocessor.transform(X)
    labels = km.predict(X_scaled)

    df = df.copy()
    df["cluster_id"] = labels
    df["cluster_name"] = [cluster_labels.get(str(c), f"Cluster {c}") for c in labels]
    logger.info("Cluster assignment done — %d customers across %d clusters", len(df), len(cluster_labels))
    return df


def _export_cluster_profiles(app_dir: Path) -> None:
    """Copy cluster_profiles.csv from artifacts into app/data as parquet."""
    profiles_csv = CLUSTERING_ARTIFACT_DIR / "cluster_profiles.csv"
    meta_path = CLUSTERING_ARTIFACT_DIR / "metadata.json"

    if not profiles_csv.exists():
        logger.warning("cluster_profiles.csv not found — skipping")
        return

    profiles = pd.read_csv(profiles_csv, index_col=0)
    profiles.index.name = "cluster_id"
    profiles = profiles.reset_index()

    with open(meta_path, encoding="utf-8") as fh:
        cluster_meta = json.load(fh)
    cluster_labels: dict[str, str] = cluster_meta.get("cluster_labels", {})
    profiles["cluster_name"] = profiles["cluster_id"].astype(str).map(cluster_labels).fillna("Unknown")

    out_path = app_dir / "data" / "cluster_profiles.parquet"
    profiles.to_parquet(out_path, index=False)
    logger.info("Cluster profiles → %s (%d clusters)", out_path, len(profiles))


def _export_monitoring(app_dir: Path) -> None:
    """Copy the monitoring parquet into app/data/."""
    if not MONITORING_PARQUET.exists():
        logger.warning("Monitoring parquet not found at %s — skipping", MONITORING_PARQUET)
        return

    out_path = app_dir / "data" / "monitoring.parquet"
    shutil.copy2(MONITORING_PARQUET, out_path)
    logger.info("Monitoring data → %s", out_path)


def export_serving_bundle(
    model: Any,
    threshold: float,
    metrics: dict[str, float] | None = None,
    *,
    model_name: str = "churn-xgboost",
    run_id: str | None = None,
    app_dir: Path | None = None,
) -> Path:
    """Write model.pkl + metadata.json + customers.parquet into ``app/``.

    Parameters
    ----------
    model : Trained sklearn Pipeline (``predict_proba`` capable).
    threshold : Decision threshold for the churn flag.
    metrics : Optional test metrics to embed in metadata.
    model_name : Label stored in metadata.
    run_id : Optional MLflow run id for traceability.
    app_dir : Target serving folder. Defaults to ``<repo>/app``.
    """
    out = app_dir or APP_DIR
    (out / "model").mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(parents=True, exist_ok=True)

    # 1. Model
    with open(out / "model" / "model.pkl", "wb") as fh:
        pickle.dump(model, fh)
    logger.info("Serving model → %s", out / "model" / "model.pkl")

    # 2. Scored customer base (churn + cluster)
    df = _load_customer_features()
    proba = model.predict_proba(df[FEATURE_COLUMNS])[:, 1]
    df["churn_probability"] = proba
    df = _assign_clusters(df)
    df.to_parquet(out / "data" / "customers.parquet", index=False)
    logger.info(
        "Serving customers → %s (%d rows)",
        out / "data" / "customers.parquet",
        len(df),
    )

    # 2b. Cluster profiles + monitoring
    _export_cluster_profiles(out)
    _export_monitoring(out)

    # 3. Metadata
    meta = {
        "model_name": model_name,
        "model_type": "XGBClassifier (sklearn Pipeline)",
        "optimal_threshold": float(threshold),
        "risk_tiers": {"High": 0.7, "Medium": 0.4, "Low": 0.0},
        "feature_columns": FEATURE_COLUMNS,
        "n_features": len(FEATURE_COLUMNS),
        "n_customers": int(len(df)),
        "metrics": metrics or {},
        "score_summary": {
            "min": float(proba.min()),
            "p25": float(np.percentile(proba, 25)),
            "median": float(np.median(proba)),
            "p75": float(np.percentile(proba, 75)),
            "max": float(proba.max()),
            "mean": float(proba.mean()),
            "pct_high_risk": float((proba >= 0.7).mean()),
            "pct_churn_flag": float((proba >= threshold).mean()),
        },
        "source_run_id": run_id or "n/a",
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(out / "model" / "metadata.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    logger.info("Serving metadata → %s", out / "model" / "metadata.json")

    return out


def main() -> None:
    """Standalone refresh from the last saved training artifacts."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
    from ml.artifacts import load_model_artifacts

    model, metadata = load_model_artifacts()
    threshold = float(metadata.get("optimal_threshold", 0.5))
    export_serving_bundle(
        model=model,
        threshold=threshold,
        metrics=metadata.get("metrics", {}),
        model_name=metadata.get("model_name", "churn-xgboost"),
    )
    logger.info("Serving bundle refreshed → %s", APP_DIR)


if __name__ == "__main__":
    main()
