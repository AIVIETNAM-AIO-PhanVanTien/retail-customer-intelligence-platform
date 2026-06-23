from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "pipeline",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="retail_pipeline",
    default_args=default_args,
    description="Ingest -> Clean -> dbt run -> dbt test",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "medallion"],
    doc_md="""
    ## Retail Pipeline DAG
    Automates the full medallion pipeline:
    - **ingest_bronze**: loads raw CSV into Bronze parquet files
    - **clean_silver**: cleans and deduplicates into Silver layer
    - **dbt_run**: builds Gold star schema + RFM mart via dbt
    - **dbt_test**: runs the dbt data-quality test suite across all models
    """,
) as dag:

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

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command="cd /opt/airflow/dbt && dbt test",
        trigger_rule="all_success",
    )

    train_model = BashOperator(
        task_id="train_model",
        bash_command="cd /opt/airflow && python3 -m ml.churn.pipeline --mode train",
    )

    score_customers = BashOperator(
        task_id="score_customers",
        bash_command="cd /opt/airflow && python3 -m ml.churn.pipeline --mode score",
    )

    ingest_bronze >> clean_silver >> dbt_run >> dbt_test >> train_model >> score_customers
    