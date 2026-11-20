"""retry_count must reach the SQL. Unknown keys are dropped silently by both writers.

See docs/plans/2026-11-20-batch-poller-transient-retry.md, section 4.1 (#8, #9).
"""
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
