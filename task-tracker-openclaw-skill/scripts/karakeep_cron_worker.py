#!/usr/bin/env python3
"""
karakeep_cron_worker.py — process at most one Karakeep inbox item and persist batch state.

Intended for scheduled/background runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from karakeep_triage import (  # noqa: E402
    DEFAULT_SEMANTIC_MODEL,
    TODO_LIST_NAME,
    get_bookmarks_for_list,
    get_client,
    route_bookmark,
)

DEFAULT_STATE_FILE = Path("/home/ozp/clawd/agents/karakeep/memory/cron-state.json")
MAX_STORED_RESULTS = 20
MAX_STORED_ERRORS = 10


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "pending_successes": 0,
        "pending_results": [],
        "pending_errors": [],
        "last_run_at": None,
        "last_processed_at": None,
        "last_summary_at": None,
    }


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_state()
    state = default_state()
    state.update(data if isinstance(data, dict) else {})
    if not isinstance(state.get("pending_results"), list):
        state["pending_results"] = []
    if not isinstance(state.get("pending_errors"), list):
        state["pending_errors"] = []
    if not isinstance(state.get("pending_successes"), int):
        state["pending_successes"] = 0
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summarize_task(payload: dict[str, Any]) -> tuple[str | None, str]:
    classification = payload.get("classification") or {}
    matched_task = classification.get("matched_task") or {}

    if classification.get("match_mode") == "complement_existing":
        return matched_task.get("title"), "complemented"
    if classification.get("match_mode") == "create_new":
        return classification.get("new_task_title"), "created"
    return classification.get("review_task_title"), "created_review"


def build_result_entry(payload: dict[str, Any]) -> dict[str, Any]:
    bookmark = payload.get("bookmark") or {}
    classification = payload.get("classification") or {}
    task_title, task_action = summarize_task(payload)
    return {
        "processed_at": utc_now(),
        "bookmark_id": bookmark.get("id"),
        "url": bookmark.get("url") or (bookmark.get("content") or {}).get("url"),
        "title": bookmark.get("title") or (bookmark.get("content") or {}).get("title"),
        "decision": classification.get("match_mode"),
        "destination_list": classification.get("destination_list"),
        "reason": classification.get("reason"),
        "task_title": task_title,
        "task_action": task_action,
        "read_source": (payload.get("read_link") or {}).get("reader_used"),
        "read_status": (payload.get("read_link") or {}).get("status"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Process one Karakeep inbox item and persist cron state")
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--list-name", default=TODO_LIST_NAME)
    parser.add_argument("--model", default=DEFAULT_SEMANTIC_MODEL)
    parser.add_argument("--deterministic-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    state_path = Path(args.state_file)
    state = load_state(state_path)
    state["last_run_at"] = utc_now()

    try:
        client = get_client()
        bookmarks = get_bookmarks_for_list(client, args.list_name, limit=1)
        if not bookmarks:
            save_state(state_path, state)
            print(json.dumps({"status": "noop", "reason": "empty_inbox", "state_file": str(state_path)}, ensure_ascii=False, indent=2))
            return

        bookmark = bookmarks[0]
        payload = route_bookmark(
            bookmark["id"],
            apply=True,
            semantic_enabled=not args.deterministic_only,
            model=args.model,
        )
        entry = build_result_entry(payload)
        state["pending_successes"] += 1
        state["pending_results"] = (state.get("pending_results") or []) + [entry]
        state["pending_results"] = state["pending_results"][-MAX_STORED_RESULTS:]
        state["last_processed_at"] = entry["processed_at"]
        save_state(state_path, state)
        print(json.dumps({"status": "processed", "entry": entry, "state_file": str(state_path)}, ensure_ascii=False, indent=2))
    except Exception as exc:
        error_entry = {
            "at": utc_now(),
            "error": str(exc),
            "list_name": args.list_name,
        }
        state["pending_errors"] = (state.get("pending_errors") or []) + [error_entry]
        state["pending_errors"] = state["pending_errors"][-MAX_STORED_ERRORS:]
        save_state(state_path, state)
        print(json.dumps({"status": "error", "error": error_entry, "state_file": str(state_path)}, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
