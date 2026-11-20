"""Poller: re-queue workflow runs that failed because plugins were not ready yet.

See docs/plans/2026-11-20-batch-poller-transient-retry.md, section 4.1.
"""
from unittest.mock import MagicMock

import pytest

from conftest import (
    PLUGIN_COLD_START_ERROR,
    dify_response,
    load_function,
    make_job,
)

MAX_RETRIES = 2


@pytest.fixture
def poller(monkeypatch):
    module = load_function("poller", monkeypatch)
    monkeypatch.setattr(module.Config, "MAX_TRANSIENT_RETRIES", MAX_RETRIES, raising=False)
    module.update_datastore = MagicMock()
    return module


def run_poller(poller, jobs, responses):
    """Run poller.main once. ``responses`` maps unique_id -> mocked Dify response."""
    poller.get_entities_from_datastore = MagicMock(return_value=jobs)
    by_run_url = {}
    for job in jobs:
        by_run_url[job.get("workflow_run_id")] = responses[job.key.name]

    def fake_get(url, headers=None, timeout=None):
        run_id = url.rsplit("/", 1)[-1]
        return by_run_url[run_id]

    poller.requests.get = MagicMock(side_effect=fake_get)
    poller.main(None)
    return {c.args[0]: c for c in poller.update_datastore.call_args_list}


def written(call):
    """(status, data) passed to update_datastore."""
    status = call.args[1]
    data = call.kwargs.get("data") if "data" in call.kwargs else (call.args[2] if len(call.args) > 2 else None)
    return status, data or {}


# --- 1, 2, 4: retryable failures are re-queued -----------------------------

def test_cold_start_failure_is_requeued_as_pending(poller):
    calls = run_poller(
        poller,
        [make_job("j1", retry_count=0)],
        {"j1": dify_response("failed", PLUGIN_COLD_START_ERROR)},
    )

    status, data = written(calls["j1"])
    assert status == "PENDING"
    assert data["retry_count"] == 1
    assert "workflow_run_id" in data and data["workflow_run_id"] is None
    assert PLUGIN_COLD_START_ERROR in data["message"]


def test_last_allowed_retry_is_still_requeued(poller):
    calls = run_poller(
        poller,
        [make_job("j1", retry_count=MAX_RETRIES - 1)],
        {"j1": dify_response("failed", PLUGIN_COLD_START_ERROR)},
    )

    status, data = written(calls["j1"])
    assert status == "PENDING"
    assert data["retry_count"] == MAX_RETRIES


def test_null_retry_count_is_treated_as_zero(poller):
    calls = run_poller(
        poller,
        [make_job("j1", retry_count=None)],
        {"j1": dify_response("failed", PLUGIN_COLD_START_ERROR)},
    )

    status, data = written(calls["j1"])
    assert status == "PENDING"
    assert data["retry_count"] == 1


def test_missing_retry_count_key_is_treated_as_zero(poller):
    job = make_job("j1")
    del job._data["retry_count"]
    calls = run_poller(poller, [job], {"j1": dify_response("failed", PLUGIN_COLD_START_ERROR)})

    status, data = written(calls["j1"])
    assert status == "PENDING"
    assert data["retry_count"] == 1


@pytest.mark.parametrize(
    "error",
    [
        "no available node",
        "plugin runtime not found",
        "PluginDaemonInternalServerError: no available node, plugin runtime not found",
    ],
)
def test_each_allowlisted_marker_is_retryable_on_its_own(poller, error):
    calls = run_poller(poller, [make_job("j1")], {"j1": dify_response("failed", error)})
    assert written(calls["j1"])[0] == "PENDING"


# --- 3, 5: non-retryable or exhausted failures stay FAILED -----------------

def test_retry_limit_reached_marks_failed(poller):
    calls = run_poller(
        poller,
        [make_job("j1", retry_count=MAX_RETRIES)],
        {"j1": dify_response("failed", PLUGIN_COLD_START_ERROR)},
    )

    status, data = written(calls["j1"])
    assert status == "FAILED"
    assert data["message"] == PLUGIN_COLD_START_ERROR


@pytest.mark.parametrize(
    "error",
    [
        "Variable passage is required",
        "PluginDaemonInternalServerError: something else",
        "",
    ],
)
def test_other_failures_are_failed_immediately(poller, error):
    calls = run_poller(poller, [make_job("j1")], {"j1": dify_response("failed", error)})

    status, data = written(calls["j1"])
    assert status == "FAILED"
    assert "retry_count" not in data


def test_failure_with_null_error_is_failed_with_default_message(poller):
    calls = run_poller(poller, [make_job("j1")], {"j1": dify_response("failed", None)})
    assert written(calls["j1"])[0] == "FAILED"
    assert written(calls["j1"])[1]["message"] == "Dify workflow failed."


def test_failure_without_error_key_is_failed_with_default_message(poller):
    calls = run_poller(poller, [make_job("j1")], {"j1": dify_response("failed", omit_error=True)})
    assert written(calls["j1"])[0] == "FAILED"
    assert written(calls["j1"])[1]["message"] == "Dify workflow failed."


# --- retry limit configuration (default / disabled) -------------------------

def test_retries_disabled_when_limit_is_zero(poller, monkeypatch):
    monkeypatch.setattr(poller.Config, "MAX_TRANSIENT_RETRIES", 0, raising=False)
    calls = run_poller(
        poller,
        [make_job("j1", retry_count=0)],
        {"j1": dify_response("failed", PLUGIN_COLD_START_ERROR)},
    )
    assert written(calls["j1"])[0] == "FAILED"


def test_max_transient_retries_defaults_to_two(monkeypatch):
    monkeypatch.delenv("MAX_TRANSIENT_RETRIES", raising=False)
    poller = load_function("poller", monkeypatch)
    assert poller.Config.MAX_TRANSIENT_RETRIES == 2


def test_max_transient_retries_reads_env(monkeypatch):
    monkeypatch.setenv("MAX_TRANSIENT_RETRIES", "0")
    poller = load_function("poller", monkeypatch)
    assert poller.Config.MAX_TRANSIENT_RETRIES == 0


# --- 6, 7: existing behaviour is unchanged -----------------------------------

@pytest.mark.parametrize("status", ["succeeded", "partial-succeeded"])
def test_success_statuses_mark_success(poller, status):
    calls = run_poller(poller, [make_job("j1")], {"j1": dify_response(status)})
    assert written(calls["j1"])[0] == "SUCCESS"


def test_running_job_is_left_untouched(poller):
    calls = run_poller(poller, [make_job("j1")], {"j1": dify_response("running")})
    assert calls == {}
