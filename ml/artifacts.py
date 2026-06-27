"""Model artifact persistence (save / load) using joblib."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib

from ml.config import ARTIFACT_DIR, FEATURE_COLUMNS

logger = logging.getLogger(__name__)


def save_model_artifacts(
    model: Any,
    threshold: float,
    metrics: dict[str, float],
    model_name: str,
    artifact_dir: Path | None = None,
    feature_stats: dict | None = None,
    score_mean_train: float | None = None,
    score_std_train: float | None = None,
) -> Path:
    """Persist trained model + metadata to disk.

    Saves:
    - ``model.joblib`` — the trained sklearn Pipeline
    - ``metadata.json`` — threshold, feature_columns, metrics, drift baseline, timestamp
    """
    out = artifact_dir or ARTIFACT_DIR
    out.mkdir(parents=True, exist_ok=True)

    # Save model
    model_path = out / "model.joblib"
    joblib.dump(model, model_path)
    logger.info("Model saved → %s", model_path)

    # Save metadata
    metadata = {
        "model_name": model_name,
        "optimal_threshold": threshold,
        "feature_columns": FEATURE_COLUMNS,
        "metrics": metrics,
        # Drift baselines — used by ml/monitoring/drift.py
        "feature_stats": feature_stats or {},
        "score_mean_train": score_mean_train,
        "score_std_train": score_std_train,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = out / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, default=str)
    logger.info("Metadata saved → %s", meta_path)

    return out


def load_model_artifacts(
    artifact_dir: Path | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Load model + metadata from disk.

    Returns
    -------
    (model, metadata_dict)
    """
    src = artifact_dir or ARTIFACT_DIR
    model_path = src / "model.joblib"
    meta_path = src / "metadata.json"

    if not model_path.exists():
        raise FileNotFoundError(f"No model found at {model_path}")

    model = joblib.load(model_path)
    logger.info("Model loaded ← %s", model_path)

    metadata: dict[str, Any] = {}
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            metadata = json.load(f)
        logger.info("Metadata loaded ← %s", meta_path)

    return model, metadata
