from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import karakeep_cron_summary
import karakeep_cron_worker


def test_worker_load_state_falls_back_to_default_for_missing_file(tmp_path):
    state = karakeep_cron_worker.load_state(tmp_path / "missing.json")

    assert state["pending_successes"] == 0
    assert state["pending_results"] == []
    assert state["pending_errors"] == []


def test_summary_stays_quiet_below_threshold_without_errors():
    state = {
        "pending_successes": 4,
        "pending_results": [{"bookmark_id": "a1", "destination_list": "Incorporated", "task_action": "complemented", "decision": "complement_existing", "task_title": "Task A"}],
        "pending_errors": [],
    }

    announce, reason = karakeep_cron_summary.should_announce(state, threshold=5)

    assert announce is False
    assert reason == "quiet"


def test_summary_announces_on_threshold_and_mentions_counts():
    state = {
        "pending_successes": 5,
        "pending_results": [
            {"bookmark_id": "a1", "destination_list": "Incorporated", "task_action": "complemented", "decision": "complement_existing", "task_title": "Task A"},
            {"bookmark_id": "a2", "destination_list": "Review", "task_action": "created_review", "decision": "review", "task_title": "Task B"},
        ],
        "pending_errors": [],
    }

    announce, reason = karakeep_cron_summary.should_announce(state, threshold=5)
    message = karakeep_cron_summary.build_message(state, threshold=5, reason=reason)

    assert announce is True
    assert reason == "threshold"
    assert "Incorporated: 1" in message
    assert "Review: 1" in message
    assert "Tasks novas: 1" in message
    assert "Tasks complementadas: 1" in message


def test_summary_announces_immediately_on_error():
    state = {
        "pending_successes": 1,
        "pending_results": [],
        "pending_errors": [{"at": "2026-03-31T00:00:00+00:00", "error": "boom"}],
    }

    announce, reason = karakeep_cron_summary.should_announce(state, threshold=5)
    message = karakeep_cron_summary.build_message(state, threshold=5, reason=reason)

    assert announce is True
    assert reason == "errors"
    assert "alerta operacional" in message
    assert "boom" in message
