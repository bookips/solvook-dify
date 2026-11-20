"""Test helpers for the Cloud Functions in this package.

Each function directory (loader/, poller/, ...) has its own top-level ``config.py``
and imports it as ``from config import Config``. Loading two functions in one pytest
session would otherwise reuse whichever ``config`` module was imported first, so
``load_function`` imports each function in isolation.

It also prevents the import from touching real infrastructure:
- ``load_dotenv`` is disabled so the developer's local ``.env`` (real secrets) is ignored.
- ``initialize_dify_api_keys`` is stubbed so no Secret Manager call is made.
"""
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent

WORKFLOW_ID = "wf-test"
API_KEY = "app-test-key"

# Real error string observed on 2026-11-20 (see docs/plans/2026-11-20-batch-poller-transient-retry.md)
PLUGIN_COLD_START_ERROR = (
    "req_id: 4a007fffb6 PluginDaemonInternalServerError: "
    "no available node, plugin runtime not found"
)


def load_function(name: str, monkeypatch):
    """Import ``<name>/main.py`` with its own ``config`` module and no external side effects."""
    import dotenv
    import shared.utils

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr(
        shared.utils, "initialize_dify_api_keys", lambda *a, **k: {WORKFLOW_ID: API_KEY}
    )

    fn_dir = str(PACKAGE_ROOT / name)
    sys.modules.pop("config", None)
    sys.path.insert(0, fn_dir)
    try:
        spec = importlib.util.spec_from_file_location(f"{name}_main", f"{fn_dir}/main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(fn_dir)
        sys.modules.pop("config", None)
    return module


def make_job(unique_id: str, *, retry_count=0, workflow_run_id="run-1", **extra):
    """A PROCESSING row as returned by get_entities_from_datastore.

    ``retry_count`` is only put in the row when not ``...``; pass ``None`` to mimic a
    row whose column value is NULL.
    """
    from shared.utils import EntityProxy

    row = {
        "unique_id": unique_id,
        "status": "PROCESSING",
        "workflow_id": WORKFLOW_ID,
        "workflow_run_id": workflow_run_id,
        "data": '{"passageGroupId": "pg-1"}',
        "timestamp": datetime.now(timezone.utc),
        "retry_count": retry_count,
    }
    row.update(extra)
    return EntityProxy(row)


def dify_response(status: str, error: str | None = None, *, omit_error: bool = False):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    body = {"id": "run-1", "status": status}
    if not omit_error:
        body["error"] = error
    resp.json.return_value = body
    return resp


class FakeDB:
    """A psycopg2 connection stand-in that records every executed statement."""

    def __init__(self, fetchone=None):
        self.executed: list[tuple[str, object]] = []
        self.cursor_obj = MagicMock()
        self.cursor_obj.execute.side_effect = lambda sql, params=None: self.executed.append((sql, params))
        self.cursor_obj.fetchone.return_value = fetchone
        self.cursor_obj.rowcount = 1  # 0 = ON CONFLICT ... WHERE skipped the update
        self.conn = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor_obj
        self.conn.cursor.return_value.__exit__.return_value = False

    def upsert_statements(self):
        return [(sql, params) for sql, params in self.executed if sql.startswith("INSERT")]


@pytest.fixture
def fake_db():
    return FakeDB()
