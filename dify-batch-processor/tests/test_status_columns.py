"""retry_count must reach the SQL. Unknown keys are dropped silently by both writers.

See docs/plans/2026-11-20-batch-poller-transient-retry.md, section 4.1 (#8, #9).
"""
from datetime import datetime, timezone

import pytest
import shared.utils as utils

from conftest import FakeDB


def test_update_datastore_writes_retry_count(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(utils, "get_db_connection", lambda: db.conn)

    utils.update_datastore("j1", "PENDING", data={"retry_count": 1, "workflow_run_id": None})

    [(sql, params)] = db.upsert_statements()
    assert "retry_count" in sql.split("VALUES")[0]
    assert "retry_count = EXCLUDED.retry_count" in sql
    assert params["retry_count"] == 1


def test_update_datastore_without_retry_count_leaves_column_alone(monkeypatch):
    """dispatcher (QUEUED) and worker (PROCESSING) must not reset the counter."""
    db = FakeDB()
    monkeypatch.setattr(utils, "get_db_connection", lambda: db.conn)

    utils.update_datastore("j1", "QUEUED")

    [(sql, _)] = db.upsert_statements()
    assert "retry_count" not in sql


def test_check_and_upsert_status_writes_retry_count():
    db = FakeDB(fetchone=("FAILED",))

    upserted, current = utils.check_and_upsert_status(
        db.conn, "j1", "PENDING", data={"workflow_id": "wf", "data": "{}", "retry_count": 0}
    )

    assert (upserted, current) == (True, "FAILED")
    [(sql, params)] = db.upsert_statements()
    columns = sql.split("(", 1)[1].split(")", 1)[0].split(", ")
    assert "retry_count" in columns
    assert params[columns.index("retry_count")] == 0
    assert "retry_count = EXCLUDED.retry_count" in sql


# --- conditional write (expect=) ---------------------------------------------
# The poller writes from a snapshot it read earlier. Since the retry lets a row go
# PROCESSING -> PENDING -> PROCESSING, a stale snapshot could overwrite a newer run.
# expect= makes the write apply only while the row still matches the snapshot.

SNAPSHOT_TS = datetime(2026, 11, 20, 2, 17, 6, 123456, tzinfo=timezone.utc)


def test_update_datastore_with_expect_adds_null_safe_where(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(utils, "get_db_connection", lambda: db.conn)

    applied = utils.update_datastore(
        "j1", "PENDING", data={"retry_count": 1},
        expect={"status": "PROCESSING", "timestamp": SNAPSHOT_TS},
    )

    assert applied is True
    [(sql, params)] = db.upsert_statements()
    where = sql.split(" WHERE ", 1)[1]
    assert "batch_process_status.status IS NOT DISTINCT FROM %(expect_status)s" in where
    assert "batch_process_status.timestamp IS NOT DISTINCT FROM %(expect_timestamp)s" in where
    assert " AND " in where
    assert params["expect_status"] == "PROCESSING"
    assert params["expect_timestamp"] == SNAPSHOT_TS


def test_update_datastore_expect_null_timestamp_can_still_match(monkeypatch):
    """`timestamp = NULL` is never true; a row with a NULL timestamp would be stuck forever."""
    db = FakeDB()
    monkeypatch.setattr(utils, "get_db_connection", lambda: db.conn)

    utils.update_datastore("j1", "FAILED", expect={"status": "PROCESSING", "timestamp": None})

    [(sql, params)] = db.upsert_statements()
    assert "= %(expect_timestamp)s" not in sql
    assert "IS NOT DISTINCT FROM %(expect_timestamp)s" in sql
    assert params["expect_timestamp"] is None


def test_update_datastore_reports_skipped_conditional_write(monkeypatch):
    db = FakeDB()
    db.cursor_obj.rowcount = 0
    monkeypatch.setattr(utils, "get_db_connection", lambda: db.conn)

    applied = utils.update_datastore(
        "j1", "PENDING", expect={"status": "PROCESSING", "timestamp": SNAPSHOT_TS}
    )

    assert applied is False


def test_update_datastore_reports_db_error_as_not_applied(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(utils, "get_db_connection", boom)
    assert utils.update_datastore("j1", "QUEUED") is False


def test_update_datastore_without_expect_is_unconditional(monkeypatch):
    """dispatcher, worker and loader keep writing unconditionally."""
    db = FakeDB()
    monkeypatch.setattr(utils, "get_db_connection", lambda: db.conn)

    assert utils.update_datastore("j1", "QUEUED") is True

    [(sql, params)] = db.upsert_statements()
    assert " WHERE " not in sql
    assert not any(k.startswith("expect_") for k in params)


def test_update_datastore_rejects_unknown_expect_column(monkeypatch):
    monkeypatch.setattr(utils, "get_db_connection", lambda: FakeDB().conn)
    with pytest.raises(ValueError):
        utils.update_datastore("j1", "PENDING", expect={"status; DROP TABLE x": "PROCESSING"})


# --- the two column lists cannot drift apart --------------------------------

@pytest.mark.parametrize(
    "column", sorted(utils._KNOWN_COLUMNS - {"unique_id", "status", "timestamp"})
)
def test_check_and_upsert_status_writes_every_known_column(column):
    db = FakeDB(fetchone=None)

    utils.check_and_upsert_status(db.conn, "j1", "PENDING", data={column: "v"})

    [(sql, _)] = db.upsert_statements()
    columns = sql.split("(", 1)[1].split(")", 1)[0].split(", ")
    assert column in columns
