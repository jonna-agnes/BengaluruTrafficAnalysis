FROM apache/airflow:3.1.0-python3.12

# Snowflake provider, pinned to Airflow's tested constraints
RUN pip install --no-cache-dir "apache-airflow==3.1.0" apache-airflow-providers-snowflake \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.1.0/constraints-3.12.txt"

# dbt in its own virtualenv so its dependencies never clash with Airflow's
RUN python -m venv /opt/airflow/dbt-venv \
 && /opt/airflow/dbt-venv/bin/pip install --no-cache-dir "dbt-core~=1.12.0" "dbt-snowflake~=1.12.0"
