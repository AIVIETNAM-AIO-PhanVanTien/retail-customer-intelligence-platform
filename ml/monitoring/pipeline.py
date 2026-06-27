"""ml/monitoring/pipeline.py — CLI entry point.

Usage::

    python -m ml.monitoring.pipeline --run-id 2026-06-26

Computes data-drift and model-drift metrics for the given run date,
saves them to data/gold/mart_monitoring/mart_monitoring.parquet, and
logs them to MLflow under the 'pipeline-monitoring' experiment.
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

import mlflow

from ml.config import MLFLOW_TRACKING_URI
from ml.monitoring.drift import (
    compute_data_drift,
    compute_model_drift,
    _load_metadata,
    _load_scores,
)
from ml.monitoring.store import log_monitoring_to_mlflow, save_monitoring_metrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
log = logging.getLogger(__name__)

MLFLOW_MONITORING_EXPERIMENT = "pipeline-monitoring"


def run(run_date: str) -> None:
    log.info("=" * 60)
    log.info("MONITORING PIPELINE START — %s", run_date)
    log.info("=" * 60)

    # ── 1. Load inputs ────────────────────────────────────────────
    log.info("[1/4] Loading churn scores and model metadata...")
    scores_df = _load_scores()
    metadata = _load_metadata()
    log.info("Scores: %d rows | Metadata loaded", len(scores_df))

    # ── 2. Data drift ─────────────────────────────────────────────
    log.info("[2/4] Computing data drift...")
    data_drift = compute_data_drift(scores_df, metadata)
    log.info(
        "Data drift: %d features checked, %d drifted (rate=%.2f)",
        int(data_drift.get("n_features_checked", 0)),
        int(data_drift.get("n_features_drifted", 0)),
        data_drift.get("drift_rate", 0.0),
    )

    # ── 3. Model drift ────────────────────────────────────────────
    log.info("[3/4] Computing model drift...")
    model_drift = compute_model_drift(scores_df, metadata)
    log.info(
        "Model drift: score_mean=%.4f, pct_high_risk=%.2f%%",
        model_drift.get("score_mean", 0.0),
        model_drift.get("pct_high_risk", 0.0) * 100,
    )

    # ── 4. Persist metrics ────────────────────────────────────────
    log.info("[4/4] Saving metrics to parquet + MLflow...")
    save_monitoring_metrics(run_date, data_drift, model_drift)

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    log_monitoring_to_mlflow(
        run_date=run_date,
        data_drift_metrics=data_drift,
        model_drift_metrics=model_drift,
        mlflow_client=None,
        experiment_name=MLFLOW_MONITORING_EXPERIMENT,
    )

    log.info("=" * 60)
    log.info("MONITORING PIPELINE DONE — %s", run_date)
    log.info("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitoring pipeline")
    parser.add_argument(
        "--run-id",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="Run date label (default: today, YYYY-MM-DD)",
    )
    args = parser.parse_args()
    run(run_date=args.run_id)


if __name__ == "__main__":
    main()
