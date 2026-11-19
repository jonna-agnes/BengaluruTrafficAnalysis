"""Provision / inspect / tear down the cloud side of the traffic pipeline.

    python -m cloud.setup aws          # S3 bucket + IAM role Snowflake uses to read it
    python -m cloud.setup snowflake    # warehouse, DB, schemas, tables, stages, service user;
                                       # then links the Snowflake integration to the IAM role
    python -m cloud.setup all          # both, in order
    python -m cloud.setup load         # COPY INTO from S3 now (what the Airflow DAG does every 5 min)
    python -m cloud.setup status       # what exists, file/row counts
    python -m cloud.setup teardown --yes

Everything is idempotent. Settings come from the repo-root .env (see .env.example).
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import time
from pathlib import Path

from cloud import config
from cloud.config import AIRFLOW_DIR, CONTAINER_KEY_PATH, KEY_DIR, PRIVATE_KEY_FILE, REPO_ROOT

SQL_TEMPLATE = Path(__file__).parent / "snowflake" / "setup.sql"
STATE_FILE = Path(__file__).parent / ".state.json"  # gitignored; remembers Snowflake's IAM identity


# --------------------------------------------------------------------------- helpers
def log(msg: str) -> None:
    print(f"[cloud] {msg}", flush=True)


def load_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def upsert_env(path: Path, values: dict[str, str], only_if_missing: set[str] = frozenset()) -> None:
    """Set KEY=VALUE lines in a .env file, keeping every other line as is."""
    lines = path.read_text().splitlines() if path.exists() else []
    seen = set()
    for i, line in enumerate(lines):
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)", line)
        if m and m.group(1) in values:
            key, current = m.group(1), m.group(2).strip()
            seen.add(key)
            if key in only_if_missing and current:
                continue
            lines[i] = f"{key}={values[key]}"
    lines += [f"{k}={v}" for k, v in values.items() if k not in seen]
    path.write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- AWS
def aws_session(aws: config.AwsSettings):
    import boto3

    session = boto3.Session(profile_name=aws.profile, region_name=aws.region)
    account_id = session.client("sts").get_caller_identity()["Account"]
    if aws.expected_account_id and account_id != aws.expected_account_id:
        sys.exit(f"Refusing to continue: profile {aws.profile!r} is AWS account {account_id}, "
                 f"expected {aws.expected_account_id} (TRAFFIC_AWS_ACCOUNT_ID).")
    return session, account_id


def read_policy(bucket: str) -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion"],
             "Resource": [f"arn:aws:s3:::{bucket}/raw/*", f"arn:aws:s3:::{bucket}/aggregated/*"]},
            {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
             "Resource": f"arn:aws:s3:::{bucket}",
             "Condition": {"StringLike": {"s3:prefix": ["raw/*", "aggregated/*"]}}},
        ],
    }


def trust_policy(account_id: str, state: dict) -> dict:
    # Before Snowflake exists, trust only our own account (with an unguessable external id);
    # `snowflake` swaps in Snowflake's IAM user + external id from DESC INTEGRATION.
    principal = state.get("snowflake_iam_user_arn") or f"arn:aws:iam::{account_id}:root"
    external_id = state.get("snowflake_external_id") or state.setdefault("placeholder_external_id", secrets.token_hex(16))
    return {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"AWS": principal}, "Action": "sts:AssumeRole",
                       "Condition": {"StringEquals": {"sts:ExternalId": external_id}}}],
    }


def setup_aws(aws: config.AwsSettings) -> tuple[str, str]:
    session, account_id = aws_session(aws)
    bucket = aws.bucket_name(account_id)
    s3, iam = session.client("s3"), session.client("iam")
    log(f"AWS account {account_id}, region {aws.region}, bucket {bucket}")

    existing = {b["Name"] for b in s3.list_buckets()["Buckets"]}
    if bucket not in existing:
        kwargs = {"Bucket": bucket}
        if aws.region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": aws.region}
        s3.create_bucket(**kwargs)
        log("created bucket")
    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={
        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}, "BucketKeyEnabled": True}]})
    s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [{"Key": "project", "Value": "bengaluru-traffic"}]})

    state = load_state()
    trust = json.dumps(trust_policy(account_id, state))
    try:
        role_arn = iam.get_role(RoleName=aws.role_name)["Role"]["Arn"]
        iam.update_assume_role_policy(RoleName=aws.role_name, PolicyDocument=trust)
    except iam.exceptions.NoSuchEntityException:
        role_arn = iam.create_role(RoleName=aws.role_name, AssumeRolePolicyDocument=trust,
                                   Description="Snowflake storage integration: read traffic Parquet from S3",
                                   Tags=[{"Key": "project", "Value": "bengaluru-traffic"}])["Role"]["Arn"]
        log(f"created IAM role {role_arn}")
    iam.put_role_policy(RoleName=aws.role_name, PolicyName=aws.policy_name,
                        PolicyDocument=json.dumps(read_policy(bucket)))

    state.update(bucket=bucket, role_arn=role_arn, account_id=account_id, region=aws.region)
    save_state(state)
    upsert_env(REPO_ROOT / ".env", {"TRAFFIC_S3_BUCKET": bucket, "AWS_PROFILE": aws.profile or "",
                                    "AWS_REGION": aws.region})
    log(f"AWS ready: s3://{bucket}  role {role_arn}")
    return bucket, role_arn


# --------------------------------------------------------------------------- Snowflake
def ensure_key_pair() -> str:
    """Create an RSA key pair for the service user; return the public key body."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    KEY_DIR.mkdir(parents=True, exist_ok=True)
    if PRIVATE_KEY_FILE.exists():
        key = serialization.load_pem_private_key(PRIVATE_KEY_FILE.read_bytes(), password=None)
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        PRIVATE_KEY_FILE.write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        log(f"generated service-user key {PRIVATE_KEY_FILE}")
    pem = key.public_key().public_bytes(serialization.Encoding.PEM,
                                        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return "".join(l for l in pem.splitlines() if "-----" not in l)


def admin_connection(sf: config.SnowflakeSettings):
    import snowflake.connector

    missing = [n for n, v in [("SNOWFLAKE_ACCOUNT", sf.account), ("SNOWFLAKE_ADMIN_USER", sf.admin_user)] if not v]
    if missing:
        sys.exit(f"Set {', '.join(missing)} in .env (an ACCOUNTADMIN login) to provision Snowflake.")
    kwargs = {"account": sf.account, "user": sf.admin_user, "role": "ACCOUNTADMIN",
              "session_parameters": {"QUERY_TAG": "traffic-cloud-setup"}}
    if sf.admin_password:
        kwargs["password"] = sf.admin_password
    if sf.admin_authenticator:
        kwargs["authenticator"] = sf.admin_authenticator
    if sf.admin_passcode:
        kwargs["passcode"] = sf.admin_passcode
    return snowflake.connector.connect(**kwargs)


def render_sql(sf: config.SnowflakeSettings, bucket: str, role_arn: str, public_key: str) -> str:
    values = {
        "ROLE": sf.role, "WAREHOUSE": sf.warehouse, "DATABASE": sf.database, "SERVICE_USER": sf.service_user,
        "INTEGRATION": sf.integration, "RESOURCE_MONITOR": sf.resource_monitor,
        "CREDIT_QUOTA": str(sf.monthly_credit_quota), "TIMEZONE": sf.timezone, "BUCKET": bucket,
        "AWS_ROLE_ARN": role_arn, "RSA_PUBLIC_KEY": public_key, "ADMIN_USER": (sf.admin_user or "").upper(),
    }
    sql = re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: values[m.group(1)], SQL_TEMPLATE.read_text())
    return sql


def setup_snowflake(aws: config.AwsSettings, sf: config.SnowflakeSettings) -> None:
    state = load_state()
    if "role_arn" not in state:
        log("AWS not provisioned yet, running it first")
        setup_aws(aws)
        state = load_state()
    public_key = ensure_key_pair()

    with admin_connection(sf) as conn:
        log(f"connected to Snowflake account {sf.account} as {sf.admin_user}")
        for cur in conn.execute_string(render_sql(sf, state["bucket"], state["role_arn"], public_key)):
            cur.close()
        log("Snowflake objects created")

        desc = {r[0]: r[2] for r in conn.cursor().execute(f"DESC STORAGE INTEGRATION {sf.integration}")}
        state["snowflake_iam_user_arn"] = desc["STORAGE_AWS_IAM_USER_ARN"]
        state["snowflake_external_id"] = desc["STORAGE_AWS_EXTERNAL_ID"]
        save_state(state)

        session, account_id = aws_session(aws)
        session.client("iam").update_assume_role_policy(
            RoleName=aws.role_name, PolicyDocument=json.dumps(trust_policy(account_id, state)))
        log("IAM role now trusts the Snowflake integration")

        # IAM changes take a few seconds to propagate.
        cur = conn.cursor()
        cur.execute(f"USE ROLE {sf.role}")
        cur.execute(f"USE DATABASE {sf.database}")
        for attempt in range(12):
            try:
                cur.execute("LIST @RAW.TRAFFIC_RAW_STAGE")
                log(f"stage access OK ({len(cur.fetchall())} files visible in raw stage)")
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 11:
                    raise
                log(f"waiting for IAM propagation ({exc.__class__.__name__})")
                time.sleep(10)

    write_airflow_env(sf)
    log("Snowflake ready. Next: cd airflow && docker compose up -d --build")


def write_airflow_env(sf: config.SnowflakeSettings) -> None:
    from cryptography.fernet import Fernet

    env_file = AIRFLOW_DIR / ".env"
    upsert_env(env_file, {
        "SNOWFLAKE_ACCOUNT": sf.account or "", "SNOWFLAKE_USER": sf.service_user,
        "SNOWFLAKE_PRIVATE_KEY_PATH": CONTAINER_KEY_PATH, "SNOWFLAKE_DATABASE": sf.database,
        "SNOWFLAKE_SCHEMA": "RAW", "SNOWFLAKE_WAREHOUSE": sf.warehouse, "SNOWFLAKE_ROLE": sf.role,
    })
    upsert_env(env_file, {
        "AIRFLOW_UID": "50000",
        "AIRFLOW_FERNET_KEY": Fernet.generate_key().decode(),
        "AIRFLOW_API_SECRET_KEY": secrets.token_urlsafe(32),
    }, only_if_missing={"AIRFLOW_UID", "AIRFLOW_FERNET_KEY", "AIRFLOW_API_SECRET_KEY"})
    log(f"wrote {env_file}")


# --------------------------------------------------------------------------- load (same COPY as the DAG)
COPY_SQL = (
    "COPY INTO {table} FROM @{stage} PATTERN = '.*[.]parquet' "
    "MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE "
    "INCLUDE_METADATA = (_SOURCE_FILE = METADATA$FILENAME, _LOADED_AT = METADATA$START_SCAN_TIME) "
    "ON_ERROR = 'CONTINUE'"
)


def service_connection(sf: config.SnowflakeSettings):
    """Connect as the key-pair service user (what Airflow and dbt use)."""
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(PRIVATE_KEY_FILE.read_bytes(), password=None)
    der = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    return snowflake.connector.connect(account=sf.account, user=sf.service_user, private_key=der,
                                       role=sf.role, warehouse=sf.warehouse, database=sf.database)


def load(sf: config.SnowflakeSettings) -> None:
    """Run the Airflow DAG's COPY INTO by hand (S3 stages -> RAW / AGGREGATED)."""
    with service_connection(sf) as conn:
        cur = conn.cursor()
        for table, stage in (("RAW.RAW_TRAFFIC_DATA", "RAW.TRAFFIC_RAW_STAGE"),
                             ("AGGREGATED.TRAFFIC_METRICS_5MIN", "AGGREGATED.TRAFFIC_AGG_STAGE")):
            rows = cur.execute(COPY_SQL.format(table=table, stage=stage)).fetchall()
            loaded = sum(r[3] for r in rows if len(r) > 3 and isinstance(r[3], int))
            total = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            log(f"{table}: loaded {loaded:,} new rows from {len(rows)} file(s); table now {total:,} rows")


# --------------------------------------------------------------------------- status / teardown
def status(aws: config.AwsSettings, sf: config.SnowflakeSettings) -> None:
    session, account_id = aws_session(aws)
    bucket = aws.bucket_name(account_id)
    s3 = session.client("s3")
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for prefix in ("raw/traffic_events/", "aggregated/5min/"):
            n = size = 0
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    if obj["Key"].endswith(".parquet"):
                        n, size = n + 1, size + obj["Size"]
            log(f"s3://{bucket}/{prefix}: {n} parquet files, {size / 1e6:.1f} MB")
    except s3.exceptions.NoSuchBucket:
        log(f"bucket {bucket} does not exist (run: python -m cloud.setup aws)")
    if sf.account and sf.admin_user:
        with admin_connection(sf) as conn:
            cur = conn.cursor()
            for table in ("RAW.RAW_TRAFFIC_DATA", "AGGREGATED.TRAFFIC_METRICS_5MIN", "MARTS.FACT_TRAFFIC_EVENTS"):
                try:
                    n = cur.execute(f"SELECT COUNT(*) FROM {sf.database}.{table}").fetchone()[0]
                    log(f"Snowflake {table}: {n:,} rows")
                except Exception as exc:  # noqa: BLE001
                    log(f"Snowflake {table}: {exc.__class__.__name__}")
    else:
        log("Snowflake: not configured (SNOWFLAKE_ACCOUNT / SNOWFLAKE_ADMIN_USER unset)")


def teardown(aws: config.AwsSettings, sf: config.SnowflakeSettings) -> None:
    if sf.account and sf.admin_user:
        with admin_connection(sf) as conn:
            for stmt in (f"DROP DATABASE IF EXISTS {sf.database}", f"DROP WAREHOUSE IF EXISTS {sf.warehouse}",
                         f"DROP STORAGE INTEGRATION IF EXISTS {sf.integration}",
                         f"DROP USER IF EXISTS {sf.service_user}", f"DROP ROLE IF EXISTS {sf.role}",
                         f"DROP RESOURCE MONITOR IF EXISTS {sf.resource_monitor}"):
                conn.cursor().execute(stmt)
                log(stmt)
    session, account_id = aws_session(aws)
    bucket = aws.bucket_name(account_id)
    s3 = session.resource("s3")
    try:
        s3.Bucket(bucket).objects.all().delete()
        s3.Bucket(bucket).delete()
        log(f"deleted bucket {bucket}")
    except Exception as exc:  # noqa: BLE001
        log(f"bucket: {exc}")
    iam = session.client("iam")
    try:
        iam.delete_role_policy(RoleName=aws.role_name, PolicyName=aws.policy_name)
        iam.delete_role(RoleName=aws.role_name)
        log(f"deleted IAM role {aws.role_name}")
    except iam.exceptions.NoSuchEntityException:
        pass
    STATE_FILE.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["aws", "snowflake", "all", "load", "status", "teardown", "render-sql"])
    parser.add_argument("--yes", action="store_true", help="confirm teardown")
    args = parser.parse_args()
    aws, sf = config.load()

    if args.command == "aws":
        setup_aws(aws)
    elif args.command in ("snowflake", "all"):
        if args.command == "all":
            setup_aws(aws)
        setup_snowflake(aws, sf)
    elif args.command == "load":
        load(sf)
    elif args.command == "status":
        status(aws, sf)
    elif args.command == "render-sql":  # for pasting into a Snowsight worksheet by hand
        state = load_state()
        print(render_sql(sf, state.get("bucket", "<bucket>"), state.get("role_arn", "<role-arn>"), ensure_key_pair()))
    elif args.command == "teardown":
        if not args.yes:
            sys.exit("teardown deletes the bucket, IAM role and Snowflake objects; re-run with --yes")
        teardown(aws, sf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
