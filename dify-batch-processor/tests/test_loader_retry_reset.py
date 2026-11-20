"""Loader: queuing a row again from the sheet starts a fresh retry budget.

See docs/plans/2026-11-20-batch-poller-transient-retry.md, section 3.4.
"""
from unittest.mock import MagicMock

import pytest

from conftest import FakeDB, load_function


@pytest.fixture
def loader(monkeypatch):
    module = load_function("loader", monkeypatch)
    monkeypatch.setattr(
        module.Config,
        "DIFY_WORKFLOW_IDS_BY_CURRICULUM_AND_CONTENT_CATEGORY",
        {"high": {"본문분석": "wf-analysis", "워크북": "wf-workbook"}},
    )
    module.get_gcp_credentials = MagicMock(return_value=None)
    module.get_sheets_service = MagicMock()
    return module


def sheet_row(category: str, force: str = "FALSE"):
    return [
        {"curriculum": "high"},
        {"content_category": category},
        {"passageGroupId": "pg-1"},
        {"passageId": "p-1"},
        {"passage": "text"},
        {"interpretation": "해석"},
        {"env": "prod"},
        {"force_creation": force},
        {"target": "TRUE"},
    ]


@pytest.mark.parametrize("force", ["FALSE", "TRUE"])
def test_every_upsert_resets_retry_count(loader, force):
    loader.stream_structured_sheet_data = MagicMock(
        return_value=iter([(2, sheet_row("본문분석,워크북", force))])
    )
    db = FakeDB()
    loader.get_db_connection = MagicMock(return_value=db.conn)
    loader.check_and_upsert_status = MagicMock(return_value=(True, "FAILED"))

    loader.main(None)

    assert loader.check_and_upsert_status.call_count == 2
    for call in loader.check_and_upsert_status.call_args_list:
        assert call.kwargs["data"]["retry_count"] == 0


def test_failed_row_requeued_from_sheet_writes_zero_retry_count(loader):
    """End to end through the real check_and_upsert_status: the SQL resets the column."""
    loader.stream_structured_sheet_data = MagicMock(
        return_value=iter([(2, sheet_row("본문분석"))])
    )
    db = FakeDB(fetchone=("FAILED",))
    loader.get_db_connection = MagicMock(return_value=db.conn)

    loader.main(None)

    [(sql, params)] = db.upsert_statements()
    columns = sql.split("(", 1)[1].split(")", 1)[0].split(", ")
    assert "retry_count" in columns
    assert params[columns.index("retry_count")] == 0
