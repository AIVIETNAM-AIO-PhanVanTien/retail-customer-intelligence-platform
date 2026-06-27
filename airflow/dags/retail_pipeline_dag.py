from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.sensors.external_task import ExternalTaskSensor

# ---------------------------------------------------------------------------
# Shared defaults
# ---------------------------------------------------------------------------
default_args = {
    "owner": "pipeline",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

# ---------------------------------------------------------------------------
# DAG 1 — Monthly: ingest → dbt → score → publish → monitor
# ---------------------------------------------------------------------------
with DAG(
    dag_id="retail_pipeline_monthly",
    default_args=default_args,
    description="Medallion ingest → dbt → ML score → publish → monitoring (@monthly)",
    schedule="@monthly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "medallion", "ml", "monitoring"],
    doc_md="""
## retail_pipeline_monthly

Runs on the 1st of each month in dependency order:

| Step | Task | Notes |
|---|---|---|
| P1 | `ingest_bronze` | Incremental — skips existing month partitions |
| P2 | `clean_silver` | Incremental — skips existing month partitions |
| P3-P6 | `dbt_run` | Builds Gold star-schema + RFM mart |
| P7 | `dbt_test` | **Quality gate** — downstream tasks abort on failure |
| P9 | `score_customers` | Batch-scores all customers with latest model |
| — | `publish_scores` | Copies mart_churn_scores → serving layer (app/) |
| P10 | `log_monitoring` | Logs data-drift + model-drift metrics (PSI ≥ 0.20 = alert) |
""",
) as monthly_dag:

    ingest_bronze = BashOperator(
        task_id="ingest_bronze",
        bash_command="cd /opt/airflow && python3 -m src.etl.bronze_ingest --all",
    )

    clean_silver = BashOperator(
        task_id="clean_silver",
        bash_command="cd /opt/airflow && python3 -m src.etl.silver_transform --all",
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command="dbt run --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt --target prod --vars '{silver_dir: /opt/airflow/data/silver, bronze_dir: /opt/airflow/data/bronze}'",
    )

    # Quality gate — all downstream ML tasks inherit trigger_rule="all_success"
    # so they will NOT run if this step fails.
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command="dbt test --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt --target prod --vars '{silver_dir: /opt/airflow/data/silver, bronze_dir: /opt/airflow/data/bronze}'",
        trigger_rule="all_success",
    )

    score_customers = BashOperator(
        task_id="score_customers",
        bash_command="cd /opt/airflow && python3 -m ml.churn.pipeline --mode score",
        trigger_rule="all_success",
    )

    publish_scores = BashOperator(
        task_id="publish_scores",
        bash_command="cd /opt/airflow && python3 -m scripts.export_serving_app",
    )

    # ACM1-76: log data-drift + model-drift metrics after every scoring run.
    # PSI > 0.20 triggers a drift alert logged to MLflow (pipeline-monitoring experiment).
    log_monitoring = BashOperator(
        task_id="log_monitoring",
        bash_command=(
            "cd /opt/airflow && "
            "python3 -m ml.monitoring.pipeline "
            "--run-id $(date +%Y-%m-%d)"
        ),
    )

    # ── dependency chain ──────────────────────────────────────────────────
    (
        ingest_bronze
        >> clean_silver
        >> dbt_run
        >> dbt_test
        >> score_customers
        >> publish_scores
        >> log_monitoring
    )


# ---------------------------------------------------------------------------
# DAG 2 — Monthly: retrain churn model (runs after DAG 1 completes)
# ---------------------------------------------------------------------------
with DAG(
    dag_id="retail_pipeline_monthly_train",
    default_args=default_args,
    description="Monthly full retrain of the XGBoost churn model (P8)",
    schedule="@monthly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "ml", "training"],
    doc_md="""
## retail_pipeline_monthly_train

Runs on the 1st of each month after `retail_pipeline_monthly` completes.

Waits for the monthly DAG's `dbt_test` task to have succeeded before
training, ensuring the model always trains on fresh, quality-gated Gold data.

| Step | Task | Notes |
|---|---|---|
| — | `wait_for_dbt_test` | ExternalTaskSensor — blocks until monthly dbt_test passes |
| P8 | `train_model` | Full XGBoost retrain; QA gate AUC ≥ 0.80; logs to MLflow |
""",
) as monthly_train_dag:

    # Block until the monthly DAG's dbt_test has passed on the same logical date.
    wait_for_dbt_test = ExternalTaskSensor(
        task_id="wait_for_dbt_test",
        external_dag_id="retail_pipeline_monthly",
        external_task_id="dbt_test",
        timeout=7200,           # wait up to 2 h before failing
        poke_interval=120,      # check every 2 min
        mode="reschedule",      # releases the worker slot while waiting
    )

    # P8 — full retrain; QA gate (AUC ≥ 0.80) is enforced inside the script.
    train_model = BashOperator(
        task_id="train_model",
        bash_command="cd /opt/airflow && python3 -m ml.churn.pipeline --mode train",
    )

    # P8b — K-Means clustering; runs after fresh Gold data (independent of churn model).
    cluster_customers = BashOperator(
        task_id="cluster_customers",
        bash_command="cd /opt/airflow && python3 -m ml.clustering.pipeline",
    )

    wait_for_dbt_test >> train_model >> cluster_customers


# ---------------------------------------------------------------------------
# DAG 3 — Full Load: wipe all layers and rebuild from scratch (manual trigger)
# ---------------------------------------------------------------------------
with DAG(
    dag_id="retail_pipeline_full_load",
    default_args=default_args,
    description="Full rebuild — wipe Bronze/Silver/Gold and reload from raw CSV (manual trigger only)",
    schedule=None,              # manual trigger only via Airflow UI / CLI
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "full-load", "medallion", "ml"],
    doc_md="""
## retail_pipeline_full_load

**Manual trigger only** — use when you need a clean rebuild from scratch
(e.g. schema change, date-shift recalibration, or full reprocess after a bug fix).

> ⚠️ This DAG **deletes** all existing Bronze, Silver, and Gold data before reloading.
> Do not trigger unless a full reprocess is intentional.

| Step | Task | Notes |
|---|---|---|
| — | `wipe_bronze_silver` | Deletes `data/bronze/` and `data/silver/` partition folders |
| — | `wipe_gold` | Deletes `data/gold/` and `data/retail.duckdb` |
| P1 | `ingest_bronze` | Full ingest from raw CSV — all months |
| P2 | `clean_silver` | Full transform — all months |
| P3-P6 | `dbt_run` | Rebuild Gold star-schema + RFM mart |
| P7 | `dbt_test` | Quality gate |
| P8 | `train_model` | Full retrain on fresh Gold data |
| P9 | `score_customers` | Batch-score all customers with new model |
| — | `publish_scores` | Export scores → serving layer (app/) |
| P10 | `log_monitoring` | Reset monitoring baseline + log initial snapshot |
""",
) as full_load_dag:

    # Wipe Bronze + Silver partitions (keep raw CSV)
    wipe_bronze_silver = BashOperator(
        task_id="wipe_bronze_silver",
        bash_command=(
            "cd /opt/airflow && "
            "rm -rf data/bronze/year_month=* data/silver/year_month=* "
            "data/bronze/_ingestion_log.csv data/silver/_quality_log.jsonl"
        ),
    )

    # Wipe Gold layer (DuckDB + parquet marts)
    wipe_gold = BashOperator(
        task_id="wipe_gold",
        bash_command=(
            "cd /opt/airflow && "
            "rm -rf data/gold/ data/retail.duckdb data/monitoring/"
        ),
    )

    ingest_bronze_full = BashOperator(
        task_id="ingest_bronze",
        bash_command="cd /opt/airflow && python3 -m src.etl.bronze_ingest --all",
    )

    clean_silver_full = BashOperator(
        task_id="clean_silver",
        bash_command="cd /opt/airflow && python3 -m src.etl.silver_transform --all",
    )

    dbt_run_full = BashOperator(
        task_id="dbt_run",
        bash_command="dbt run --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt --target prod --vars '{silver_dir: /opt/airflow/data/silver, bronze_dir: /opt/airflow/data/bronze}'",
    )

    dbt_test_full = BashOperator(
        task_id="dbt_test",
        bash_command="dbt test --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt --target prod --vars '{silver_dir: /opt/airflow/data/silver, bronze_dir: /opt/airflow/data/bronze}'",
        trigger_rule="all_success",
    )

    train_model_full = BashOperator(
        task_id="train_model",
        bash_command="cd /opt/airflow && python3 -m ml.churn.pipeline --mode train",
        trigger_rule="all_success",
    )

    cluster_customers_full = BashOperator(
        task_id="cluster_customers",
        bash_command="cd /opt/airflow && python3 -m ml.clustering.pipeline",
    )

    score_customers_full = BashOperator(
        task_id="score_customers",
        bash_command="cd /opt/airflow && python3 -m ml.churn.pipeline --mode score",
    )

    publish_scores_full = BashOperator(
        task_id="publish_scores",
        bash_command="cd /opt/airflow && python3 -m scripts.export_serving_app",
    )

    log_monitoring_full = BashOperator(
        task_id="log_monitoring",
        bash_command=(
            "cd /opt/airflow && "
            "python3 -m ml.monitoring.pipeline "
            "--run-id $(date +%Y-%m-%d)"
        ),
    )

    # ── dependency chain ──────────────────────────────────────────────────
    # train_model and cluster_customers run in parallel after dbt_test.
    (
        [wipe_bronze_silver, wipe_gold]
        >> ingest_bronze_full
        >> clean_silver_full
        >> dbt_run_full
        >> dbt_test_full
        >> [train_model_full, cluster_customers_full]
    )
    (
        train_model_full
        >> score_customers_full
        >> publish_scores_full
        >> log_monitoring_full
    )
