"""ml/monitoring/store.py

Persists monitoring metrics to the gold layer as a parquet table and
optionally logs them to MLflow.

Output: data/gold/mart_monitoring/mart_monitoring.parquet
Schema:
    run_date        date       — the date this monitoring run covers
    run_id          str        — ISO timestamp of when the run executed
    metric_name     str        — e.g. "score_mean", "drift_rate"
    metric_value    float
    category        str        — "data_drift" | "model_drift"
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from ml.config import GOLD_DIR

log = logging.getLogger(__name__)

MONITORING_DIR = GOLD_DIR / "mart_monitoring"
MONITORING_PATH = MONITORING_DIR / "mart_monitoring.parquet"


def save_monitoring_metrics(
    run_date: str,
    data_drift_metrics: dict[str, float],
    model_drift_metrics: dict[str, float],
) -> pd.DataFrame:
    """Append today's metrics to the monitoring parquet table.

    Uses an append strategy (read existing + concat + overwrite) so
    the table accumulates a time series of monitoring runs.
    """
    MONITORING_DIR.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now(timezone.utc).isoformat()
    rows = []

    for metric_name, metric_value in data_drift_metrics.items():
        rows.append({
            "run_date": run_date,
            "run_id": run_id,
            "metric_name": metric_name,
            "metric_value": float(metric_value),
            "category": "data_drift",
        })

    for metric_name, metric_value in model_drift_metrics.items():
        rows.append({
            "run_date": run_date,
            "run_id": run_id,
            "metric_name": metric_name,
            "metric_value": float(metric_value),
            "category": "model_drift",
        })

    new_df = pd.DataFrame(rows)

    # Append to existing table if it exists
    if MONITORING_PATH.exists():
        existing = pd.read_parquet(MONITORING_PATH)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    combined.to_parquet(MONITORING_PATH, index=False)
    log.info(
        "Monitoring metrics saved → %s (%d rows total, %d new)",
        MONITORING_PATH,
        len(combined),
        len(new_df),
    )
    return new_df


def log_monitoring_to_mlflow(
    run_date: str,
    data_drift_metrics: dict[str, float],
    model_drift_metrics: dict[str, float],
    mlflow_client,
    experiment_name: str = "pipeline-monitoring",
) -> str:
    """Log monitoring metrics as a new MLflow run.

    Returns the MLflow run_id.
    """
    import mlflow

    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name=f"monitoring-{run_date}") as run:
        mlflow.set_tag("run_date", run_date)
        mlflow.set_tag("monitoring_type", "drift")

        all_metrics = {**data_drift_metrics, **model_drift_metrics}
        # MLflow metric names can't have certain chars — sanitise
        safe = {
            k.replace(".", "_").replace(" ", "_"): v
            for k, v in all_metrics.items()
            if isinstance(v, (int, float))
        }
        mlflow.log_metrics(safe)
        log.info("Monitoring metrics logged to MLflow run %s", run.info.run_id)
        return run.info.run_id
    
