-- Snowflake objects for the Bengaluru traffic pipeline.
-- Rendered and executed by `python -m cloud.setup snowflake` (the double-brace placeholders
-- are filled from .env). Idempotent: safe to re-run. To run it by hand in a Snowsight
-- worksheet as ACCOUNTADMIN, print a filled-in copy with `python -m cloud.setup render-sql`.

-------------------------------------------------------------------------------
-- 1. Account-level objects (ACCOUNTADMIN)
-------------------------------------------------------------------------------
USE ROLE ACCOUNTADMIN;

CREATE ROLE IF NOT EXISTS {{ ROLE }} COMMENT = 'Traffic pipeline: loads RAW data and runs dbt';
GRANT ROLE {{ ROLE }} TO ROLE SYSADMIN;

-- Cost guardrail: every pipeline run resumes the warehouse.
CREATE RESOURCE MONITOR IF NOT EXISTS {{ RESOURCE_MONITOR }}
  WITH CREDIT_QUOTA = {{ CREDIT_QUOTA }} FREQUENCY = MONTHLY START_TIMESTAMP = IMMEDIATELY
  TRIGGERS ON 80 PERCENT DO NOTIFY
           ON 100 PERCENT DO SUSPEND
           ON 110 PERCENT DO SUSPEND_IMMEDIATE;
ALTER RESOURCE MONITOR {{ RESOURCE_MONITOR }} SET CREDIT_QUOTA = {{ CREDIT_QUOTA }};

CREATE WAREHOUSE IF NOT EXISTS {{ WAREHOUSE }}
  WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Traffic pipeline COPY INTO + dbt';
ALTER WAREHOUSE {{ WAREHOUSE }} SET RESOURCE_MONITOR = {{ RESOURCE_MONITOR }};
GRANT USAGE, OPERATE ON WAREHOUSE {{ WAREHOUSE }} TO ROLE {{ ROLE }};

-- S3 access through an IAM role (no AWS keys stored in Snowflake).
-- IF NOT EXISTS + ALTER keeps the integration's external ID stable across re-runs.
CREATE STORAGE INTEGRATION IF NOT EXISTS {{ INTEGRATION }}
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  ENABLED = TRUE
  STORAGE_AWS_ROLE_ARN = '{{ AWS_ROLE_ARN }}'
  STORAGE_ALLOWED_LOCATIONS = ('s3://{{ BUCKET }}/raw/', 's3://{{ BUCKET }}/aggregated/');
ALTER STORAGE INTEGRATION {{ INTEGRATION }} SET
  STORAGE_AWS_ROLE_ARN = '{{ AWS_ROLE_ARN }}'
  STORAGE_ALLOWED_LOCATIONS = ('s3://{{ BUCKET }}/raw/', 's3://{{ BUCKET }}/aggregated/');
GRANT USAGE ON INTEGRATION {{ INTEGRATION }} TO ROLE {{ ROLE }};

CREATE DATABASE IF NOT EXISTS {{ DATABASE }};
GRANT OWNERSHIP ON DATABASE {{ DATABASE }} TO ROLE {{ ROLE }} COPY CURRENT GRANTS;

-- Service user for the pipeline + dbt: key-pair auth (TYPE = SERVICE cannot use passwords).
CREATE USER IF NOT EXISTS {{ SERVICE_USER }}
  TYPE = SERVICE
  DEFAULT_ROLE = {{ ROLE }}
  DEFAULT_WAREHOUSE = {{ WAREHOUSE }}
  DEFAULT_NAMESPACE = {{ DATABASE }}.RAW
  COMMENT = 'Traffic pipeline service user (load + dbt)';
ALTER USER {{ SERVICE_USER }} SET
  RSA_PUBLIC_KEY = '{{ RSA_PUBLIC_KEY }}'
  DEFAULT_ROLE = {{ ROLE }}
  DEFAULT_WAREHOUSE = {{ WAREHOUSE }}
  -- Parquet timestamps are UTC instants; load/display them in Bengaluru time so
  -- TO_DATE(event_ts) gives the local calendar day (same as the DuckDB target).
  TIMEZONE = '{{ TIMEZONE }}';
GRANT ROLE {{ ROLE }} TO USER {{ SERVICE_USER }};
GRANT ROLE {{ ROLE }} TO USER {{ ADMIN_USER }};

-------------------------------------------------------------------------------
-- 2. Database objects (owned by the pipeline role)
-------------------------------------------------------------------------------
USE ROLE {{ ROLE }};
USE WAREHOUSE {{ WAREHOUSE }};
USE DATABASE {{ DATABASE }};
ALTER SESSION SET TIMEZONE = '{{ TIMEZONE }}';

CREATE SCHEMA IF NOT EXISTS RAW;
CREATE SCHEMA IF NOT EXISTS AGGREGATED;

CREATE FILE FORMAT IF NOT EXISTS RAW.PARQUET_FORMAT
  TYPE = PARQUET USE_LOGICAL_TYPE = TRUE USE_VECTORIZED_SCANNER = TRUE;
CREATE FILE FORMAT IF NOT EXISTS AGGREGATED.PARQUET_FORMAT
  TYPE = PARQUET USE_LOGICAL_TYPE = TRUE USE_VECTORIZED_SCANNER = TRUE;

-- Paths written by pyspark_transformation/trans.py
CREATE OR REPLACE STAGE RAW.TRAFFIC_RAW_STAGE
  STORAGE_INTEGRATION = {{ INTEGRATION }}
  URL = 's3://{{ BUCKET }}/raw/traffic_events/'
  FILE_FORMAT = RAW.PARQUET_FORMAT;
CREATE OR REPLACE STAGE AGGREGATED.TRAFFIC_AGG_STAGE
  STORAGE_INTEGRATION = {{ INTEGRATION }}
  URL = 's3://{{ BUCKET }}/aggregated/5min/'
  FILE_FORMAT = AGGREGATED.PARQUET_FORMAT;

-- Columns match the Spark output schemas; _SOURCE_FILE/_LOADED_AT are filled by
-- COPY INTO ... INCLUDE_METADATA in cloud/setup.py.
CREATE TABLE IF NOT EXISTS RAW.RAW_TRAFFIC_DATA (
  EVENT_ID                  VARCHAR,
  EVENT_TIMESTAMP           VARCHAR,
  EVENT_TS                  TIMESTAMP_TZ,
  AREA                      VARCHAR,
  ROAD_SEGMENT_ID           VARCHAR,
  ROAD_NAME                 VARCHAR,
  LATITUDE                  FLOAT,
  LONGITUDE                 FLOAT,
  VEHICLE_COUNT             NUMBER(10,0),
  AVG_SPEED_KMPH            FLOAT,
  OCCUPANCY_PCT             FLOAT,
  CONGESTION_LEVEL          VARCHAR,
  WEATHER                   VARCHAR,
  INCIDENT_TYPE             VARCHAR,
  INCIDENT_DURATION_MINUTES NUMBER(10,0),
  IS_WEEKEND                BOOLEAN,
  HOUR_OF_DAY               NUMBER(2,0),
  DAY_OF_WEEK               VARCHAR,
  DATA_SOURCE               VARCHAR,
  GENERATED_AT              VARCHAR,
  ANOMALY_TYPE              VARCHAR,
  _SOURCE_FILE              VARCHAR,
  _LOADED_AT                TIMESTAMP_LTZ
);

CREATE TABLE IF NOT EXISTS AGGREGATED.TRAFFIC_METRICS_5MIN (
  WINDOW_START          TIMESTAMP_TZ,
  WINDOW_END            TIMESTAMP_TZ,
  AREA                  VARCHAR,
  ROAD_SEGMENT_ID       VARCHAR,
  ROAD_NAME             VARCHAR,
  TOTAL_EVENTS          NUMBER(18,0),
  AVG_VEHICLE_COUNT     FLOAT,
  AVG_SPEED_KMPH        FLOAT,
  AVG_OCCUPANCY_PCT     FLOAT,
  PEAK_CONGESTION_LEVEL VARCHAR,
  _SOURCE_FILE          VARCHAR,
  _LOADED_AT            TIMESTAMP_LTZ
);
