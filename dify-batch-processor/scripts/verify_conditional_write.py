#!/usr/bin/env python3
"""Check update_datastore(expect=...) against a real PostgreSQL. Leaves no trace.

The unit tests only check the SQL text and a mocked rowcount. This script runs the
real shared.utils code against a real server to confirm what the poller relies on:

- a guarded upsert whose WHERE is false updates nothing and reports rowcount 0
- a timestamp read back through get_entities_from_datastore matches exactly
- IS NOT DISTINCT FROM lets a NULL timestamp match
- retry_count is written by both writers

Safety (all three apply; any one is enough to protect the real table):
1. Every statement runs against a session-local TEMP copy of batch_process_status
   (CREATE TEMP TABLE ... LIKE). The script aborts unless the name resolves to it.
2. After the temp table is created the session is READ ONLY. PostgreSQL still
   allows writes to temporary tables, but any write to a real table fails.
3. Everything after setup is rolled back, and the temp table disappears when the
   connection closes.

It works whether or not retry_count has been added to the real table yet: the temp
copy gets the column if it is missing.

Usage (from dify-batch-processor/, with the proxy running: ./scripts/cloud-sql-proxy.sh):
    DB_HOST=localhost DB_PORT=15432 poetry run python scripts/verify_conditional_write.py

DB_DATABASE, DB_USERNAME and DB_PASSWORD are read from the environment or .env.
Exit code 0 = every check passed.
"""
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import shared.utils as utils  # noqa: E402

TABLE = utils.TABLE_NAME
PROCESSING = "PROCESSING"


class _SharedConnection:
    """Hands the one test connection to shared.utils; commit/close become no-ops."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *a, **k):
        return self._conn.cursor(*a, **k)

    def commit(self):
        pass

    def close(self):
        pass


class _ErrorRecorder(logging.Handler):
    """update_datastore logs and swallows DB errors; a swallowed error must not pass as 'skipped'."""

    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.records = []

    def emit(self, record):
        self.records.append(record)


failures: list[str] = []


def check(name, condition, detail=""):
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def setup_temp_table(conn):
    with conn.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE {TABLE} (LIKE public.{TABLE} INCLUDING ALL)")
        cur.execute(
            f"ALTER TABLE pg_temp.{TABLE} ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0"
        )
        cur.execute(
            "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.oid = %s::regclass",
            (TABLE,),
        )
        schema = cur.fetchone()[0]
        cur.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = %s AND column_name = 'retry_count'",
            (TABLE,),
        )
        real_has_column = cur.fetchone() is not None
    conn.commit()  # commits only the temp table DDL
    if not schema.startswith("pg_temp"):
        sys.exit(f"ABORT: '{TABLE}' resolves to schema '{schema}', not the temp copy.")
    print(f"Using temp table in {schema}.")
    print(f"Real table public.{TABLE} has retry_count: {'yes' if real_has_column else 'NO (apply scripts/sql/2026-11-20-add-retry-count.sql before deploying)'}")

    with conn.cursor() as cur:
        cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    conn.commit()


def snapshot(unique_id):
    """Read the row exactly as the poller does (get_entities_from_datastore, status=PROCESSING)."""
    [entity] = [e for e in utils.get_entities_from_datastore("status", PROCESSING) if e.key.name == unique_id]
    return entity


def row(conn, unique_id):
    """Current row contents (direct read)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT * FROM {TABLE} WHERE unique_id = %s", (unique_id,))
        return dict(cur.fetchone())


def seed(conn, unique_id, *, status=PROCESSING, run_id="run-1", retry_count=0, ts="now"):
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO {TABLE} (unique_id, status, workflow_id, workflow_run_id, data, retry_count, timestamp) "
            "VALUES (%s, %s, 'wf', %s, '{}', %s, " + ("NOW()" if ts == "now" else "NULL") + ")",
            (unique_id, status, run_id, retry_count),
        )


def run_checks(conn):
    errors = _ErrorRecorder()
    logging.getLogger().addHandler(errors)

    print("\n1. Guarded write on the row version that was read -> applied")
    seed(conn, "c1")
    snap = snapshot("c1")
    applied = utils.update_datastore(
        "c1", "PENDING", data={"workflow_run_id": None, "retry_count": 1},
        expect={"status": PROCESSING, "timestamp": snap.get("timestamp")},
    )
    after = row(conn, "c1")
    check("returns True", applied is True)
    check("status is PENDING", after.get("status") == "PENDING", after.get("status"))
    check("retry_count is 1", after.get("retry_count") == 1, after.get("retry_count"))
    check("workflow_run_id is NULL", after.get("workflow_run_id") is None)
    check("data/workflow_id untouched", after.get("data") == "{}" and after.get("workflow_id") == "wf")
    check("timestamp read back is tz-aware", snap.get("timestamp").tzinfo is not None)

    print("\n2. Stale snapshot (row re-dispatched since) -> skipped, row unchanged")
    seed(conn, "c2")
    stale = snapshot("c2")
    with conn.cursor() as cur:  # what dispatcher + worker do in between
        cur.execute(
            f"UPDATE {TABLE} SET workflow_run_id = 'run-2', timestamp = timestamp + interval '1 second' WHERE unique_id = 'c2'"
        )
    before = row(conn, "c2")
    applied = utils.update_datastore(
        "c2", "PENDING", data={"workflow_run_id": None, "retry_count": 1},
        expect={"status": PROCESSING, "timestamp": stale.get("timestamp")},
    )
    after = row(conn, "c2")
    check("returns False", applied is False)
    check("row unchanged", after == before)

    print("\n3. Status changed since read -> skipped")
    seed(conn, "c3")
    snap = snapshot("c3")
    with conn.cursor() as cur:
        cur.execute(f"UPDATE {TABLE} SET status = 'SUCCESS' WHERE unique_id = 'c3'")
    applied = utils.update_datastore(
        "c3", "FAILED", expect={"status": PROCESSING, "timestamp": snap.get("timestamp")}
    )
    check("returns False", applied is False)
    check("status still SUCCESS", row(conn, "c3").get("status") == "SUCCESS")

    print("\n4. Row with NULL timestamp -> expect timestamp=None matches")
    seed(conn, "c4", ts=None)
    snap = snapshot("c4")
    applied = utils.update_datastore(
        "c4", "FAILED", expect={"status": PROCESSING, "timestamp": snap.get("timestamp")}
    )
    check("snapshot timestamp is None", snap.get("timestamp") is None)
    check("returns True", applied is True)
    check("status is FAILED", row(conn, "c4").get("status") == "FAILED")

    print("\n5. Timestamp off by 1 microsecond -> skipped (exact match, no rounding)")
    seed(conn, "c5")
    snap = snapshot("c5")
    applied = utils.update_datastore(
        "c5", "FAILED",
        expect={"status": PROCESSING, "timestamp": snap.get("timestamp") + timedelta(microseconds=1)},
    )
    check("returns False", applied is False)

    print("\n6. Unguarded write (dispatcher/worker/loader path) -> applied as before")
    seed(conn, "c6", status="PENDING", run_id=None, retry_count=2)
    applied = utils.update_datastore("c6", "QUEUED")
    after = row(conn, "c6")
    check("returns True", applied is True)
    check("status is QUEUED", after.get("status") == "QUEUED")
    check("retry_count kept at 2", after.get("retry_count") == 2, after.get("retry_count"))

    print("\n7. Loader re-queue of a FAILED row resets retry_count")
    seed(conn, "c7", status="FAILED", retry_count=2)
    upserted, current = utils.check_and_upsert_status(
        conn, "c7", "PENDING", data={"data": "{}", "workflow_id": "wf", "retry_count": 0}
    )
    after = row(conn, "c7")
    check("upserted from FAILED", (upserted, current) == (True, "FAILED"), (upserted, current))
    check("retry_count reset to 0", after.get("retry_count") == 0, after.get("retry_count"))

    print("\n8. New row without retry_count gets the column default 0")
    utils.update_datastore("c8", "PENDING", data={"workflow_id": "wf", "data": "{}"})
    check("retry_count is 0", row(conn, "c8").get("retry_count") == 0)

    print("\n9. Read-only guard really protects the real table")
    with conn.cursor() as cur:
        cur.execute("SAVEPOINT ro_probe")
        try:
            cur.execute(f"UPDATE public.{TABLE} SET status = status WHERE false")
            blocked = False
        except psycopg2.errors.ReadOnlySqlTransaction:
            blocked = True
        cur.execute("ROLLBACK TO SAVEPOINT ro_probe")
    check("write to public table is rejected", blocked)

    logging.getLogger().removeHandler(errors)
    check("no database errors were swallowed", not errors.records,
          "; ".join(r.getMessage() for r in errors.records))


def main():
    conn = psycopg2.connect(
        host=utils.os.getenv("DB_HOST"),
        port=utils.os.getenv("DB_PORT", "5432"),
        user=utils.os.getenv("DB_USERNAME"),
        password=utils.os.getenv("DB_PASSWORD"),
        dbname=utils.os.getenv("DB_DATABASE"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW server_version")
            print(f"PostgreSQL {cur.fetchone()[0]}")
        setup_temp_table(conn)
        utils.get_db_connection = lambda: _SharedConnection(conn)
        run_checks(conn)
    finally:
        conn.rollback()
        conn.close()

    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{len(failures)} CHECK(S) FAILED: ' + ', '.join(failures)}")
    print("Rolled back; temp table dropped with the session. Nothing was written to the real table.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="    %(levelname)s: %(message)s")
    main()
