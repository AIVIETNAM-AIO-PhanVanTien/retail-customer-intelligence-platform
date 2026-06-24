"""Export the trained churn model into the serving ``app/`` folder.

Produces a self-contained bundle the Streamlit Space (and HuggingFace)
needs at runtime:

    app/model/model.pkl        — sklearn Pipeline (imputer + XGBoost)
    app/model/metadata.json    — threshold, feature list, score summary
    app/data/customers.parquet — scored customer base for the demo

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from ml.config import FEATURE_COLUMNS, PROJECT_ROOT

logger = logging.getLogger(__name__)

APP_DIR = PROJECT_ROOT / "app"
DUCKDB_PATH = PROJECT_ROOT / "data" / "retail.duckdb"


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

    # 2. Scored customer base
    df = _load_customer_features()
    proba = model.predict_proba(df[FEATURE_COLUMNS])[:, 1]
    df["churn_probability"] = proba
    df.to_parquet(out / "data" / "customers.parquet", index=False)
    logger.info(
        "Serving customers → %s (%d rows)",
        out / "data" / "customers.parquet",
        len(df),
    )

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
