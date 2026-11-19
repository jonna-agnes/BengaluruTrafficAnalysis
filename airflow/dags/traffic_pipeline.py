"""Every 5 minutes: load new Parquet files from S3 into Snowflake, then rebuild and test the dbt models."""
from datetime import datetime, timedelta

from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag

# Snowflake's load history makes these idempotent: files already loaded are skipped.
COPY_SQL = """
COPY INTO {table} FROM @{stage}
  PATTERN = '.*[.]parquet'
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  INCLUDE_METADATA = (_SOURCE_FILE = METADATA$FILENAME, _LOADED_AT = METADATA$START_SCAN_TIME)
  ON_ERROR = 'CONTINUE'
"""

DBT = "/opt/airflow/dbt-venv/bin/dbt"
DBT_ARGS = "--project-dir /opt/airflow/traffic --profiles-dir /opt/airflow/dbt_profiles"


@dag(
    dag_id="traffic_load_and_model",
    schedule="*/5 * * * *",
    start_date=datetime(2026, 7, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
    tags=["traffic", "snowflake", "dbt"],
    doc_md=__doc__,
)
def traffic_load_and_model():
    load_events = SQLExecuteQueryOperator(
        task_id="load_events",
        conn_id="snowflake_traffic",
        sql=COPY_SQL.format(table="RAW.RAW_TRAFFIC_DATA", stage="RAW.TRAFFIC_RAW_STAGE"),
    )
    load_windows = SQLExecuteQueryOperator(
        task_id="load_5min_windows",
        conn_id="snowflake_traffic",
        sql=COPY_SQL.format(table="AGGREGATED.TRAFFIC_METRICS_5MIN", stage="AGGREGATED.TRAFFIC_AGG_STAGE"),
    )
    dbt_build = BashOperator(task_id="dbt_build", bash_command=f"{DBT} build {DBT_ARGS}")

    [load_events, load_windows] >> dbt_build


traffic_load_and_model()
