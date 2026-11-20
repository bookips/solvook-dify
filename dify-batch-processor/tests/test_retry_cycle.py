"""Second-round tests: axes the transient-retry implementation created.

- The poller now writes PENDING, which feeds the row back through dispatcher -> worker.
- One poller run now branches three ways on `failed` rows.
- retry_count now travels through update_datastore from the poller.

See docs/plans/2026-11-20-batch-poller-transient-retry.md, section 4.2.
"""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import shared.utils as utils

from conftest import (
    PLUGIN_COLD_START_ERROR,
    WORKFLOW_ID,
    FakeDB,
    dify_response,
    load_function,
    make_job,
)

MAX_RETRIES = 2
INPUTS = {"passageGroupId": "pg-1", "passage": "text"}


class InMemoryTable:
    """Stores rows with update_datastore's merge rule: only the columns passed are written.

    test_poller_pending_write_only_touches_retry_columns checks the real SQL follows
    the same rule, so this stand-in does not drift from it unnoticed.
    """

    def __init__(self):
        self.rows: dict[str, dict] = {}

    def update_datastore(self, unique_id, status, data=None, **_):
        row = self.rows.setdefault(unique_id, {"unique_id": unique_id})
        row["status"] = status
        row["timestamp"] = datetime.now(timezone.utc)
        for k, v in (data or {}).items():
            if k in utils._KNOWN_COLUMNS:
                row[k] = v

    def get_entities_from_datastore(self, field, value, operator="=", limit=None, key_only=False):
        assert operator == "="
        matches = [utils.EntityProxy(dict(r)) for r in self.rows.values() if r.get(field) == value]
        return matches[:limit] if limit is not None else matches


@pytest.fixture
def table():
    t = InMemoryTable()
    t.rows["j1"] = {
        "unique_id": "j1",
        "status": "PENDING",
        "workflow_id": WORKFLOW_ID,
        "workflow_run_id": None,
        "data": json.dumps(INPUTS),
        "retry_count": 0,
        "timestamp": datetime.now(timezone.utc),
    }
    return t


@pytest.fixture
def poller(monkeypatch, table):
    module = load_function("poller", monkeypatch)
    monkeypatch.setattr(module.Config, "MAX_TRANSIENT_RETRIES", MAX_RETRIES)
    module.update_datastore = table.update_datastore
    module.get_entities_from_datastore = table.get_entities_from_datastore
    return module


@pytest.fixture
def dispatcher(monkeypatch, table):
    from google.cloud import tasks_v2

    monkeypatch.setattr(tasks_v2, "CloudTasksClient", MagicMock())
    module = load_function("dispatcher", monkeypatch)
    monkeypatch.setattr(module.Config, "MAX_CONCURRENT_WORKFLOWS", 5)
    module.update_datastore = table.update_datastore
    module.get_entities_from_datastore = table.get_entities_from_datastore
    return module


def dispatch(dispatcher):
    """Run the dispatcher and return the task payloads it created."""
    dispatcher.tasks_client.create_task.reset_mock()
    dispatcher.main(None)
    return [
        json.loads(c.kwargs["task"]["http_request"]["body"])
        for c in dispatcher.tasks_client.create_task.call_args_list
    ]


def worker_starts(table, unique_id, workflow_id, run_id):
    """What worker/main.py writes after `workflow_started` (run_id None = not captured)."""
    data = {"workflow_id": workflow_id}
    if run_id:
        data["workflow_run_id"] = run_id
    table.update_datastore(unique_id, "PROCESSING", data=data)


def poll(poller, status_by_run_id):
    def fake_get(url, headers=None, timeout=None):
        return status_by_run_id[url.rsplit("/", 1)[-1]]

    poller.requests.get = MagicMock(side_effect=fake_get)
    poller.main(None)
    return poller.requests.get


def run_attempt(dispatcher, poller, table, run_id, response):
    [payload] = dispatch(dispatcher)
    assert table.rows["j1"]["status"] == "QUEUED"
    worker_starts(table, payload["unique_id"], payload["workflow_id"], run_id)
    poll(poller, {run_id: response})
    return payload


# --- requeued row goes back through dispatcher with its inputs intact ----------

def test_requeued_row_is_redispatched_with_original_inputs(dispatcher, poller, table):
    cold = dify_response("failed", PLUGIN_COLD_START_ERROR)

    first = run_attempt(dispatcher, poller, table, "run-1", cold)
    assert table.rows["j1"]["status"] == "PENDING"

    second = run_attempt(dispatcher, poller, table, "run-2", dify_response("succeeded"))

    assert second == first
    assert second["data"] == INPUTS
    assert second["workflow_id"] == WORKFLOW_ID
    assert table.rows["j1"]["status"] == "SUCCESS"
    assert table.rows["j1"]["retry_count"] == 1


def test_retry_budget_survives_dispatcher_and_worker_and_stops_at_limit(dispatcher, poller, table):
    cold = dify_response("failed", PLUGIN_COLD_START_ERROR)

    for attempt in range(1, MAX_RETRIES + 1):
        run_attempt(dispatcher, poller, table, f"run-{attempt}", cold)
        assert table.rows["j1"]["status"] == "PENDING"
        assert table.rows["j1"]["retry_count"] == attempt

    run_attempt(dispatcher, poller, table, "run-last", cold)
    assert table.rows["j1"]["status"] == "FAILED"
    assert table.rows["j1"]["retry_count"] == MAX_RETRIES
    assert dispatch(dispatcher) == []


def test_retry_without_captured_run_id_does_not_repoll_the_old_failed_run(dispatcher, poller, table):
    """If the worker misses workflow_started, the stale run id must not be polled again."""
    run_attempt(dispatcher, poller, table, "run-1", dify_response("failed", PLUGIN_COLD_START_ERROR))
    assert table.rows["j1"]["workflow_run_id"] is None

    [payload] = dispatch(dispatcher)
    worker_starts(table, payload["unique_id"], payload["workflow_id"], run_id=None)
    get = poll(poller, {})

    get.assert_not_called()
    assert table.rows["j1"]["status"] == "PROCESSING"
    assert table.rows["j1"]["retry_count"] == 1


# --- one poller run with every kind of outcome ----------------------------------

def test_single_poll_routes_each_failed_row_independently(monkeypatch):
    poller = load_function("poller", monkeypatch)
    monkeypatch.setattr(poller.Config, "MAX_TRANSIENT_RETRIES", MAX_RETRIES)
    poller.update_datastore = MagicMock()
    jobs = [
        make_job("cold", workflow_run_id="r-cold", retry_count=0),
        make_job("exhausted", workflow_run_id="r-exhausted", retry_count=MAX_RETRIES),
        make_job("other", workflow_run_id="r-other", retry_count=0),
        make_job("ok", workflow_run_id="r-ok", retry_count=1),
        make_job("running", workflow_run_id="r-running", retry_count=1),
    ]
    poller.get_entities_from_datastore = MagicMock(return_value=jobs)
    poll(poller, {
        "r-cold": dify_response("failed", PLUGIN_COLD_START_ERROR),
        "r-exhausted": dify_response("failed", PLUGIN_COLD_START_ERROR),
        "r-other": dify_response("failed", "Variable passage is required"),
        "r-ok": dify_response("succeeded"),
        "r-running": dify_response("running"),
    })

    writes = {c.args[0]: (c.args[1], c.kwargs.get("data", {})) for c in poller.update_datastore.call_args_list}
    assert set(writes) == {"cold", "exhausted", "other", "ok"}
    assert writes["cold"][0] == "PENDING" and writes["cold"][1]["retry_count"] == 1
    assert writes["exhausted"][0] == "FAILED"
    assert writes["other"][0] == "FAILED"
    assert writes["ok"][0] == "SUCCESS"


# --- the poller's PENDING write, all the way to SQL ------------------------------

def test_poller_pending_write_only_touches_retry_columns(monkeypatch):
    """Real update_datastore: retry columns are written, inputs are left as they are."""
    poller = load_function("poller", monkeypatch)
    monkeypatch.setattr(poller.Config, "MAX_TRANSIENT_RETRIES", MAX_RETRIES)
    db = FakeDB()
    monkeypatch.setattr(utils, "get_db_connection", lambda: db.conn)
    poller.update_datastore = utils.update_datastore
    poller.get_entities_from_datastore = MagicMock(return_value=[make_job("j1", workflow_run_id="r1")])

    poll(poller, {"r1": dify_response("failed", PLUGIN_COLD_START_ERROR)})

    [(sql, params)] = db.upsert_statements()
    columns = set(sql.split("(", 1)[1].split(")", 1)[0].split(", "))
    assert {"status", "retry_count", "workflow_run_id"} <= columns
    assert not columns & {"data", "workflow_id"}
    assert params["status"] == "PENDING"
    assert params["retry_count"] == 1
    assert params["workflow_run_id"] is None
