import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import chat_capture
import telegram_buttons
import utils


def _write_work_file(tmp_path, content=None):
    work = tmp_path / "Work Tasks.md"
    work.write_text(
        content
        or """# Work

## 🔴 Q1
- [ ] **JAMS quarterly launch** task_id::tsk_jams area:: Ops
- [ ] **Lifetime outreach** task_id::tsk_life area:: Sales

## 🟡 Q2
- [ ] **JAMS followup email** task_id::tsk_jams2 area:: Ops
"""
    )
    return work


def _apply_env(monkeypatch, tmp_path, work):
    monkeypatch.setenv("TASK_TRACKER_WORK_FILE", str(work))
    monkeypatch.setenv("TASK_TRACKER_DAILY_NOTES_DIR", str(tmp_path / "daily"))
    monkeypatch.setenv("TASK_TRACKER_DONE_LOG_DIR", str(tmp_path / "daily"))
    monkeypatch.setenv("TASK_TRACKER_LEDGER_FILE", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("STANDUP_CALENDARS", "{}")
    monkeypatch.setenv("TASK_TRACKER_CHAT_CAPTURE_NOW", "2026-07-01T12:00:00+00:00")
    monkeypatch.setattr(utils, "OBSIDIAN_WORK", work)
    monkeypatch.setattr(utils, "LEGACY_WORK", tmp_path / "missing-legacy.md")


def _events(tmp_path):
    ledger = tmp_path / "events.jsonl"
    if not ledger.exists():
        return []
    return [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]


def _event_types(tmp_path):
    return [event["event_type"] for event in _events(tmp_path)]


def test_resolve_for_confirm_single_exactish_hit(tmp_path, monkeypatch):
    work = _write_work_file(tmp_path)
    _apply_env(monkeypatch, tmp_path, work)

    payload = chat_capture.resolve_for_confirm("lifetime outreach")

    assert payload["tier"] == "single"
    assert payload["candidates"] == [
        {
            "task_id": "tsk_life",
            "title": "Lifetime outreach",
            "score": 1.0,
            "match_type": "normalized-title",
            "match_types": ["normalized-title", "token-overlap", "fuzzy"],
        }
    ]
    assert work.read_text().count("- [ ]") == 3


def test_resolve_for_confirm_ambiguous_hint_is_multi_and_capped(tmp_path, monkeypatch):
    work = _write_work_file(
        tmp_path,
        """# Work

## 🔴 Q1
- [ ] **JAMS quarterly launch** task_id::tsk_jams area:: Ops
- [ ] **JAMS followup email** task_id::tsk_jams2 area:: Ops
- [ ] **JAMS partner review** task_id::tsk_jams3 area:: Ops
- [ ] **JAMS archive cleanup** task_id::tsk_jams4 area:: Ops
""",
    )
    _apply_env(monkeypatch, tmp_path, work)

    payload = chat_capture.resolve_for_confirm("the JAMS thing")

    assert payload["tier"] == "multi"
    assert [candidate["task_id"] for candidate in payload["candidates"]] == [
        "tsk_jams",
        "tsk_jams2",
        "tsk_jams3",
    ]


def test_resolve_for_confirm_none_and_empty_catalog(tmp_path, monkeypatch):
    work = _write_work_file(tmp_path)
    _apply_env(monkeypatch, tmp_path, work)
    assert chat_capture.resolve_for_confirm("reticulate splines")["tier"] == "none"

    empty = _write_work_file(tmp_path, "# Work\n\n## 🔴 Q1\n")
    _apply_env(monkeypatch, tmp_path, empty)
    assert chat_capture.resolve_for_confirm("anything")["tier"] == "none"


def test_resolve_for_confirm_excludes_recurring_and_objective_tasks(tmp_path, monkeypatch):
    work = _write_work_file(
        tmp_path,
        """# Objectives 2026

## Objectives
- [ ] **Grow revenue** task_id::tsk_objective #Sales
  - [ ] **Lifetime outreach** task_id::tsk_life

## 🔴 Q1
- [ ] **Send weekly update** task_id::tsk_weekly recur::weekly
""",
    )
    _apply_env(monkeypatch, tmp_path, work)

    assert chat_capture.resolve_for_confirm("grow revenue")["tier"] == "none"
    assert chat_capture.resolve_for_confirm("weekly update")["tier"] == "none"
    child = chat_capture.resolve_for_confirm("lifetime outreach")
    assert child["tier"] == "single"
    assert child["candidates"][0]["task_id"] == "tsk_life"


def test_deferred_candidate_excludes_recurring_and_objective_tasks(tmp_path, monkeypatch):
    # The deferred-candidate lane uses the SAME chat-completable catalog as resolve_for_confirm, so a
    # hint matching a recurring/objective task is a miss -- never a candidate a chat tap can't complete.
    work = _write_work_file(
        tmp_path,
        """# Objectives 2026

## Objectives
- [ ] **Grow revenue** task_id::tsk_objective #Sales

## 🔴 Q1
- [ ] **Send weekly update** task_id::tsk_weekly recur::weekly
- [ ] **Lifetime outreach** task_id::tsk_life
""",
    )
    _apply_env(monkeypatch, tmp_path, work)

    recurring = chat_capture.record_deferred_candidate("weekly update", channel="telegram", message_id="m1")
    objective = chat_capture.record_deferred_candidate("grow revenue", channel="telegram", message_id="m2")
    completable = chat_capture.record_deferred_candidate("lifetime outreach", channel="telegram", message_id="m3")

    assert recurring["action"] == "miss"
    assert objective["action"] == "miss"
    assert completable["action"] == "candidate"
    assert completable["task_id"] == "tsk_life"


def test_capture_text_and_deferred_candidate_never_complete(tmp_path, monkeypatch):
    work = _write_work_file(tmp_path)
    original = work.read_text()
    _apply_env(monkeypatch, tmp_path, work)

    raw = chat_capture.capture_text(
        "finished Lifetime outreach",
        sender="sender-123",
        channel="telegram",
        message_id="msg-1",
    )
    deferred = chat_capture.record_deferred_candidate(
        "done JAMS quarterly",
        sender="sender-123",
        channel="telegram",
        message_id="msg-2",
    )

    assert raw["action"] == "candidate"
    assert raw["task_id"] == "tsk_life"
    assert deferred["action"] == "candidate"
    assert work.read_text() == original
    assert _event_types(tmp_path) == ["candidate_seen", "candidate_seen"]


def test_bare_done_task_id_string_is_a_hint_not_auto_completion(tmp_path, monkeypatch):
    work = _write_work_file(tmp_path)
    original = work.read_text()
    _apply_env(monkeypatch, tmp_path, work)

    payload = chat_capture.capture_text("done tsk_jams")

    assert payload["action"] == "miss"
    assert "completion_id" not in payload
    assert work.read_text() == original
    assert _event_types(tmp_path) == ["capture_miss"]


def test_open_tasks_for_browse_orders_by_priority_then_due_and_paginates(tmp_path, monkeypatch):
    work = _write_work_file(
        tmp_path,
        """# Work

## 🟡 Q2
- [ ] **Q2 older** task_id::tsk_q2_old 🗓️2026-06-01
- [ ] **Q2 newer** task_id::tsk_q2_new 🗓️2026-06-20

## 🔴 Q1
- [ ] **Q1 no due** task_id::tsk_q1_none
- [ ] **Q1 due** task_id::tsk_q1_due 🗓️2026-07-01

## 🟠 Q3
- [ ] **Q3 task** task_id::tsk_q3
""",
    )
    _apply_env(monkeypatch, tmp_path, work)

    page1 = chat_capture.open_tasks_for_browse(page=1, limit=3)
    page2 = chat_capture.open_tasks_for_browse(page=2, limit=3)

    assert [item["task_id"] for item in page1["items"]] == ["tsk_q1_due", "tsk_q1_none", "tsk_q2_old"]
    assert page1["has_more"] is True
    assert page1["next_page"] == 2
    assert [item["task_id"] for item in page2["items"]] == ["tsk_q2_new", "tsk_q3"]
    assert all(item["buttons"][0]["value"].startswith("tt:done:") for item in page1["items"])
    assert work.read_text().count("- [ ]") == 5


def test_open_tasks_for_browse_empty_board(tmp_path, monkeypatch):
    work = _write_work_file(tmp_path, "# Work\n\n## 🔴 Q1\n")
    _apply_env(monkeypatch, tmp_path, work)

    payload = chat_capture.open_tasks_for_browse()

    assert payload["total"] == 0
    assert payload["items"] == []
    assert payload["has_more"] is False


def test_capture_cli_refuses_personal_scope_without_mutating_personal_board(tmp_path):
    work = _write_work_file(tmp_path)
    personal = tmp_path / "Personal Tasks.md"
    personal.write_text(
        """# Personal

## 🔴 Q1
- [ ] **Lifetime outreach** task_id::tsk_life area:: Personal
"""
    )
    env = os.environ.copy()
    env["TASK_TRACKER_WORK_FILE"] = str(work)
    env["TASK_TRACKER_PERSONAL_FILE"] = str(personal)
    env["TASK_TRACKER_LEDGER_FILE"] = str(tmp_path / "events.jsonl")
    original_personal = personal.read_text()

    proc = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts" / "tasks.py"),
            "--personal",
            "capture",
            "--text",
            "finished Lifetime outreach",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "personal-capture-refused"
    assert personal.read_text() == original_personal


def test_capture_cli_rejects_retired_envelope_entrypoint(tmp_path):
    work = _write_work_file(tmp_path)
    env = os.environ.copy()
    env["TASK_TRACKER_WORK_FILE"] = str(work)
    env["TASK_TRACKER_LEDGER_FILE"] = str(tmp_path / "events.jsonl")

    proc = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts" / "tasks.py"),
            "capture",
            "--text",
            "done tsk_jams",
            "--envelope",
            "{}",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert proc.returncode != 0
    assert "--envelope" in proc.stderr
    assert "JAMS quarterly launch" in work.read_text()


def test_confirm_and_disambiguation_rows_hide_ids_in_labels():
    confirm = telegram_buttons.confirm_row("tsk_jams")
    assert [button["label"] for button in confirm] == ["✅ Yes", "Not that one"]
    assert confirm[0]["value"] == "tt:done:tsk_jams"

    rows = telegram_buttons.disambiguation_rows(
        [
            {"task_id": "tsk_jams", "title": "JAMS launch tsk_jams"},
            {"task_id": "tsk_life", "title": "Lifetime outreach"},
        ]
    )

    labels = [button["label"] for button in rows]
    assert labels == ["JAMS launch", "Lifetime outreach", "Neither"]
    assert all("tsk_" not in label for label in labels)
    assert {button["value"] for button in rows[:2]} == {"tt:done:tsk_jams", "tt:done:tsk_life"}
