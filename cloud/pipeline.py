"""Refresh the warehouse: load new S3 files into Snowflake, then rebuild and test the dbt models.

    python -m cloud.pipeline              # run once
    python -m cloud.pipeline --every 5    # keep running every 5 minutes (Ctrl+C to stop)

Settings come from .env (see .env.example); dbt authenticates as the key-pair service user.
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime

from cloud import config
from cloud.config import PRIVATE_KEY_FILE, REPO_ROOT
from cloud.setup import load, log


def dbt_build(sf: config.SnowflakeSettings) -> bool:
    from dbt.cli.main import dbtRunner

    os.environ.update({
        "SNOWFLAKE_ACCOUNT": sf.account or "",
        "SNOWFLAKE_USER": sf.service_user,
        "SNOWFLAKE_PRIVATE_KEY_PATH": str(PRIVATE_KEY_FILE),
        "SNOWFLAKE_ROLE": sf.role,
        "SNOWFLAKE_WAREHOUSE": sf.warehouse,
        "SNOWFLAKE_DATABASE": sf.database,
    })
    result = dbtRunner().invoke([
        "build", "--project-dir", str(REPO_ROOT / "traffic"),
        "--profiles-dir", str(REPO_ROOT / "traffic" / "profiles"), "--quiet",
    ])
    return result.success


def run_once(sf: config.SnowflakeSettings) -> bool:
    started = time.monotonic()
    load(sf)
    ok = dbt_build(sf)
    log(f"dbt build {'passed' if ok else 'FAILED'} ({time.monotonic() - started:.0f}s)")
    return ok


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--every", type=float, metavar="MINUTES", help="repeat on this interval")
    args = p.parse_args()
    _, sf = config.load()
    if not sf.account:
        raise SystemExit("Set SNOWFLAKE_ACCOUNT in .env (and run python -m cloud.setup all first).")

    if not args.every:
        return 0 if run_once(sf) else 1
    while True:
        log(f"run at {datetime.now():%H:%M:%S}")
        try:
            run_once(sf)
        except Exception as exc:  # keep the schedule alive; the next run retries
            log(f"run failed: {exc}")
        time.sleep(args.every * 60)


if __name__ == "__main__":
    raise SystemExit(main())
