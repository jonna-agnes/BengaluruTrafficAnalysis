"""Settings for cloud provisioning, read from the repo-root .env (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KEY_DIR = REPO_ROOT / "keys"                        # gitignored
PRIVATE_KEY_FILE = KEY_DIR / "snowflake_svc.p8"     # Snowflake service-user private key


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(REPO_ROOT / ".env")


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) and value.strip() else default


@dataclass(frozen=True)
class AwsSettings:
    profile: str | None
    expected_account_id: str | None  # guard: refuse to touch any other AWS account
    region: str
    bucket: str | None  # None -> derived from account id once known
    role_name: str
    policy_name: str

    def bucket_name(self, account_id: str) -> str:
        return self.bucket or f"bengaluru-traffic-{account_id}-{self.region}"


@dataclass(frozen=True)
class SnowflakeSettings:
    account: str | None
    admin_user: str | None
    admin_password: str | None
    admin_authenticator: str | None
    admin_passcode: str | None
    database: str
    warehouse: str
    role: str
    service_user: str
    integration: str
    resource_monitor: str
    monthly_credit_quota: int
    timezone: str


def load() -> tuple[AwsSettings, SnowflakeSettings]:
    _load_dotenv()
    aws = AwsSettings(
        profile=_env("AWS_PROFILE", "jo-cli"),
        expected_account_id=_env("TRAFFIC_AWS_ACCOUNT_ID", "879352492139"),
        region=_env("AWS_REGION", "ap-south-1"),
        bucket=_env("TRAFFIC_S3_BUCKET"),
        role_name=_env("TRAFFIC_SNOWFLAKE_IAM_ROLE", "traffic-snowflake-s3-read"),
        policy_name=_env("TRAFFIC_SNOWFLAKE_IAM_POLICY", "traffic-snowflake-s3-read"),
    )
    sf = SnowflakeSettings(
        account=_env("SNOWFLAKE_ACCOUNT"),
        admin_user=_env("SNOWFLAKE_ADMIN_USER"),
        admin_password=_env("SNOWFLAKE_ADMIN_PASSWORD"),
        admin_authenticator=_env("SNOWFLAKE_ADMIN_AUTHENTICATOR"),
        admin_passcode=_env("SNOWFLAKE_ADMIN_PASSCODE"),
        database=_env("SNOWFLAKE_DATABASE", "TRAFFIC").upper(),
        warehouse=_env("SNOWFLAKE_WAREHOUSE", "TRAFFIC_WH").upper(),
        role=_env("SNOWFLAKE_ROLE", "TRAFFIC_ROLE").upper(),
        service_user=_env("SNOWFLAKE_USER", "TRAFFIC_SVC").upper(),
        integration=_env("SNOWFLAKE_STORAGE_INTEGRATION", "TRAFFIC_S3_INT").upper(),
        resource_monitor=_env("SNOWFLAKE_RESOURCE_MONITOR", "TRAFFIC_MONITOR").upper(),
        monthly_credit_quota=int(_env("SNOWFLAKE_MONTHLY_CREDIT_QUOTA", "20")),
        timezone=_env("TRAFFIC_TIMEZONE", "Asia/Kolkata"),
    )
    return aws, sf
