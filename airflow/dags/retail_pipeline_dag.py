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
    description="Ingest -> Clean -> dbt run -> dbt test -> publish Gold",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "medallion"],
) as dag:

    ingest_bronze = BashOperator(
        task_id="ingest_bronze",
        bash_command="cd /opt/airflow && python3 src/etl/bronze_ingest.py --all",
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
    )

    ingest_bronze >> clean_silver >> dbt_run >> dbt_test