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
# DAG 1 — Daily: ingest → dbt → score → publish → monitor
# ---------------------------------------------------------------------------
with DAG(
    dag_id="retail_pipeline_daily",
    default_args=default_args,
    description="Medallion ingest → dbt → ML score → publish → monitoring (@daily)",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "medallion", "ml", "monitoring"],
    doc_md="""
## retail_pipeline_daily
 
Runs every day in dependency order:
 
| Step | Task | Notes |
|---|---|---|
| P1 | `ingest_bronze` | Incremental — skips existing month partitions |
| P2 | `clean_silver` | Incremental — skips existing month partitions |
| P3-P6 | `dbt_run` | Builds Gold star-schema + RFM mart |
| P7 | `dbt_test` | **Quality gate** — downstream tasks abort on failure |
| P9 | `score_customers` | Batch-scores all customers with latest model |
| — | `publish_scores` | Copies mart_churn_scores → serving layer (app/) |
| — | `log_monitoring` | Logs data-drift + model-drift metrics (ACM1-76) |
""",
) as daily_dag:
 
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
        bash_command="cd /opt/airflow/dbt && dbt run",
    )
 
    # Quality gate — all downstream ML tasks inherit trigger_rule="all_success"
    # so they will NOT run if this step fails.
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command="cd /opt/airflow/dbt && dbt test",
        trigger_rule="all_success",
    )
 
    score_customers = BashOperator(
        task_id="score_customers",
        bash_command="cd /opt/airflow && python3 -m ml.churn.pipeline --mode score",
        # Explicitly stated for clarity — will not run if dbt_test fails.
        trigger_rule="all_success",
    )
 
    # ACM1-75: export mart_churn_scores → serving layer
    publish_scores = BashOperator(
        task_id="publish_scores",
        bash_command="cd /opt/airflow && python3 -m scripts.export_serving_app",
    )
 
    # ACM1-76: log data-drift + model-drift metrics after every scoring run.
    # Replace the stub command with the real module path once ml/monitoring/ exists,
    # e.g. "python3 -m ml.monitoring.pipeline --run-id $(date +%Y-%m-%d)"
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
# DAG 2 — Weekly: retrain churn model (Sunday)
# ---------------------------------------------------------------------------
with DAG(
    dag_id="retail_pipeline_weekly_train",
    default_args=default_args,
    description="Weekly full retrain of the XGBoost churn model (P8)",
    schedule="0 3 * * 0",   # every Sunday at 03:00 UTC
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "ml", "training"],
    doc_md="""
## retail_pipeline_weekly_train
 
Runs every Sunday at 03:00 UTC.
 
Waits for the **daily** DAG's `dbt_test` task to have succeeded within
the same logical date window before training, ensuring the model always
trains on fresh, quality-gated Gold data.
 
| Step | Task | Notes |
|---|---|---|
| — | `wait_for_dbt_test` | ExternalTaskSensor — blocks until daily dbt_test passes |
| P8 | `train_model` | Full XGBoost retrain; QA gate AUC ≥ 0.80; logs to MLflow |
""",
) as weekly_dag:
 
    # Block until the daily DAG's dbt_test has passed on the same date.
    # allowed_states defaults to ["success"].
    wait_for_dbt_test = ExternalTaskSensor(
        task_id="wait_for_dbt_test",
        external_dag_id="retail_pipeline_daily",
        external_task_id="dbt_test",
        timeout=3600,           # wait up to 1 h before failing
        poke_interval=120,      # check every 2 min
        mode="reschedule",      # releases the worker slot while waiting
    )
 
    # P8 — full retrain; QA gate (AUC ≥ 0.80) is enforced inside the script.
    train_model = BashOperator(
        task_id="train_model",
        bash_command="cd /opt/airflow && python3 -m ml.churn.pipeline --mode train",
    )
 
    wait_for_dbt_test >> train_model
