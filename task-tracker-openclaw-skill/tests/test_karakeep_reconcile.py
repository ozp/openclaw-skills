from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import karakeep_links


def test_extract_bookmark_ids_uses_note_meta_and_deduplicates():
    task = {
        "title": "Example",
        "note_meta": [
            "karakeep:bm-1",
            "source:capture",
            "karakeep:bm-1",
            "karakeep:bm-2",
        ],
    }

    assert karakeep_links.extract_bookmark_ids(task) == ["bm-1", "bm-2"]


def test_inspect_task_links_reports_missing_task_ref(monkeypatch):
    monkeypatch.setattr(
        karakeep_links,
        "fetch_bookmark",
        lambda bookmark_id: ({
            "id": bookmark_id,
            "note": None,
            "content": {"url": "https://example.com"},
        }, None),
    )

    task = {
        "title": "https://example.com - Example",
        "section": "backlog",
        "done": False,
        "area": "triage",
        "note_meta": ["karakeep:bm-1"],
    }

    payload = karakeep_links.inspect_task_links(task)

    assert payload["task"]["bookmark_ids"] == ["bm-1"]
    assert payload["issues"] == [{"type": "missing_task_ref", "bookmark_id": "bm-1"}]
    assert payload["links"][0]["exists"] is True
    assert payload["links"][0]["has_backlink"] is False


def test_inspect_bookmark_links_reports_duplicate_task_link(monkeypatch):
    monkeypatch.setattr(
        karakeep_links,
        "load_linked_tasks",
        lambda personal=False: [
            {
                "title": "Task one",
                "section": "backlog",
                "done": False,
                "area": "triage",
                "note_meta": ["karakeep:bm-dup"],
                "bookmark_ids": ["bm-dup"],
            },
            {
                "title": "Task two",
                "section": "q2",
                "done": False,
                "area": "triage",
                "note_meta": ["karakeep:bm-dup"],
                "bookmark_ids": ["bm-dup"],
            },
        ],
    )
    monkeypatch.setattr(
        karakeep_links,
        "fetch_bookmark",
        lambda bookmark_id: ({
            "id": bookmark_id,
            "note": "task-ref: Work Tasks.md#task-one",
            "content": {"url": "https://example.com"},
        }, None),
    )

    payload = karakeep_links.inspect_bookmark_links("bm-dup")

    issue_types = [issue["type"] for issue in payload["issues"]]
    assert "duplicate_task_link" in issue_types
    assert len(payload["tasks"]) == 2


def test_reconcile_reports_orphan_bookmark_without_task(monkeypatch):
    monkeypatch.setattr(karakeep_links, "load_linked_tasks", lambda personal=False: [])
    monkeypatch.setattr(karakeep_links, "fetch_bookmark", lambda bookmark_id: (None, "unused"))
    monkeypatch.setattr(
        karakeep_links,
        "search_task_ref_bookmarks",
        lambda limit=100: [
            {
                "id": "bm-orphan",
                "note": "task-ref: Work Tasks.md#missing-task",
                "content": {"url": "https://example.com/orphan", "title": "Orphan"},
            }
        ],
    )

    payload = karakeep_links.reconcile()

    assert payload["summary"]["issues_total"] == 1
    assert payload["issues"][0]["type"] == "bookmark_without_task"
    assert payload["issues"][0]["bookmark_id"] == "bm-orphan"


def test_find_tasks_for_url_returns_bookmark_not_found_when_missing(monkeypatch):
    monkeypatch.setattr(karakeep_links, "find_bookmark_by_url", lambda url: None)

    payload = karakeep_links.find_tasks_for_url("https://example.com/missing")

    assert payload["bookmark"] is None
    assert payload["tasks"] == []
    assert payload["issues"] == [{"type": "bookmark_not_found", "url": "https://example.com/missing"}]
