#!/usr/bin/env python3
"""
karakeep_links.py — deterministic lookup/reconciliation for task ↔ bookmark links.

Phase 2 scope:
- read task → bookmark links from `note:: karakeep:BOOKMARK_ID`
- find linked task(s) by bookmark id or URL
- inspect bookmark/backlink status for one task
- reconcile the current board in dry-run mode

This script is intentionally conservative:
- no autonomous repair
- no mass mutation
- reports first, fixes later

Examples:
  python3 karakeep_links.py link-status --task "open-terminal"
  python3 karakeep_links.py link-status --bookmark-id y6lp0vgax9nk1mxd0w0oasxl
  python3 karakeep_links.py find-task --url https://github.com/open-webui/open-terminal
  python3 karakeep_links.py reconcile --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from capture import slugify_task_ref
from karakeep import get_client
from utils import load_tasks

TASK_REF_PREFIX = "task-ref:"
TASK_REF_PATTERN = re.compile(r"task-ref:\s*([^\n]+)", re.IGNORECASE)


def extract_bookmark_ids(task: dict) -> list[str]:
    values = task.get("note_meta") or ([] if not task.get("note") else [task.get("note")])
    ids: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.startswith("karakeep:"):
            continue
        bookmark_id = value.split(":", 1)[1].strip()
        if bookmark_id and bookmark_id not in seen:
            ids.append(bookmark_id)
            seen.add(bookmark_id)
    return ids


def expected_task_ref(task: dict) -> str:
    return f"task-ref: Work Tasks.md#{slugify_task_ref(task.get('title', ''))}"


def extract_task_ref(note: str | None) -> str | None:
    if not note:
        return None
    match = TASK_REF_PATTERN.search(note)
    return f"task-ref: {match.group(1).strip()}" if match else None


def bookmark_url(bookmark: dict | None) -> str | None:
    if not isinstance(bookmark, dict):
        return None
    content = bookmark.get("content") or {}
    return content.get("url")


def bookmark_title(bookmark: dict | None) -> str | None:
    if not isinstance(bookmark, dict):
        return None
    return bookmark.get("title") or (bookmark.get("content") or {}).get("title")


def summarize_task(task: dict) -> dict:
    return {
        "title": task.get("title"),
        "section": task.get("section"),
        "done": bool(task.get("done")),
        "area": task.get("area"),
        "bookmark_ids": extract_bookmark_ids(task),
        "expected_task_ref": expected_task_ref(task),
    }


def summarize_bookmark(bookmark: dict | None) -> dict | None:
    if not isinstance(bookmark, dict):
        return None
    return {
        "id": bookmark.get("id"),
        "title": bookmark_title(bookmark),
        "url": bookmark_url(bookmark),
        "note": bookmark.get("note"),
        "task_ref": extract_task_ref(bookmark.get("note")),
    }


def load_all_tasks(personal: bool = False) -> list[dict]:
    _, tasks_data = load_tasks(personal)
    return tasks_data.get("all", [])


def load_linked_tasks(personal: bool = False) -> list[dict]:
    linked = []
    for task in load_all_tasks(personal):
        bookmark_ids = extract_bookmark_ids(task)
        if bookmark_ids:
            linked.append({**task, "bookmark_ids": bookmark_ids})
    return linked


def find_task_by_query(query: str, personal: bool = False) -> dict:
    tasks = load_all_tasks(personal)
    q = query.strip().lower()
    matches = [task for task in tasks if q in (task.get("title") or "").lower()]
    if not matches:
        raise ValueError(f"no task matches: {query}")
    if len(matches) > 1:
        raise ValueError(f"multiple tasks match: {query}")
    return matches[0]


def build_bookmark_index(tasks: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = defaultdict(list)
    for task in tasks:
        for bookmark_id in task.get("bookmark_ids", extract_bookmark_ids(task)):
            index[bookmark_id].append(task)
    return dict(index)


def fetch_bookmark(bookmark_id: str) -> tuple[dict | None, str | None]:
    client = get_client()
    try:
        return client.get_bookmark(bookmark_id), None
    except RuntimeError as exc:
        return None, str(exc)


def find_bookmark_by_url(url: str) -> dict | None:
    client = get_client()
    result = client.find_url(url)
    if not isinstance(result, dict):
        return None

    bookmark_id = result.get("id") or result.get("bookmarkId")
    if bookmark_id:
        try:
            return client.get_bookmark(bookmark_id)
        except RuntimeError:
            return {"id": bookmark_id}

    bookmarks = result.get("bookmarks")
    if isinstance(bookmarks, list) and bookmarks:
        first = bookmarks[0]
        first_id = first.get("id") or first.get("bookmarkId")
        if first_id and "content" not in first:
            try:
                return client.get_bookmark(first_id)
            except RuntimeError:
                return {"id": first_id}
        return first

    return None


def inspect_task_links(task: dict) -> dict:
    bookmark_ids = extract_bookmark_ids(task)
    task_summary = summarize_task(task)
    issues: list[dict] = []
    links: list[dict] = []

    for bookmark_id in bookmark_ids:
        bookmark, error = fetch_bookmark(bookmark_id)
        if error:
            issues.append({
                "type": "missing_bookmark",
                "bookmark_id": bookmark_id,
                "error": error,
            })
            links.append({
                "bookmark_id": bookmark_id,
                "exists": False,
                "error": error,
            })
            continue

        task_ref = extract_task_ref(bookmark.get("note"))
        expected_ref = task_summary["expected_task_ref"]
        has_backlink = bool(task_ref)
        backlink_matches = task_ref == expected_ref

        if not has_backlink:
            issues.append({
                "type": "missing_task_ref",
                "bookmark_id": bookmark_id,
            })
        elif not backlink_matches:
            issues.append({
                "type": "mismatched_task_ref",
                "bookmark_id": bookmark_id,
                "expected": expected_ref,
                "actual": task_ref,
            })

        links.append({
            "bookmark_id": bookmark_id,
            "exists": True,
            "bookmark": summarize_bookmark(bookmark),
            "has_backlink": has_backlink,
            "backlink_matches": backlink_matches,
        })

    return {
        "task": task_summary,
        "links": links,
        "issues": issues,
    }


def inspect_bookmark_links(bookmark_id: str, personal: bool = False) -> dict:
    linked_tasks = load_linked_tasks(personal)
    index = build_bookmark_index(linked_tasks)
    bookmark, error = fetch_bookmark(bookmark_id)
    if error:
        raise RuntimeError(error)

    tasks = index.get(bookmark_id, [])
    bookmark_summary = summarize_bookmark(bookmark)
    issues: list[dict] = []
    task_ref = extract_task_ref(bookmark.get("note"))

    if not tasks:
        issues.append({
            "type": "bookmark_without_task",
            "bookmark_id": bookmark_id,
            "task_ref": task_ref,
        })
    if len(tasks) > 1:
        issues.append({
            "type": "duplicate_task_link",
            "bookmark_id": bookmark_id,
            "task_titles": [task.get("title") for task in tasks],
        })

    for task in tasks:
        expected_ref = expected_task_ref(task)
        if task_ref and task_ref != expected_ref:
            issues.append({
                "type": "mismatched_task_ref",
                "bookmark_id": bookmark_id,
                "task_title": task.get("title"),
                "expected": expected_ref,
                "actual": task_ref,
            })
        if not task_ref:
            issues.append({
                "type": "missing_task_ref",
                "bookmark_id": bookmark_id,
                "task_title": task.get("title"),
            })

    return {
        "bookmark": bookmark_summary,
        "tasks": [summarize_task(task) for task in tasks],
        "issues": issues,
    }


def find_tasks_for_url(url: str, personal: bool = False) -> dict:
    bookmark = find_bookmark_by_url(url)
    if not bookmark or not bookmark.get("id"):
        return {
            "url": url,
            "bookmark": None,
            "tasks": [],
            "issues": [{"type": "bookmark_not_found", "url": url}],
        }

    inspection = inspect_bookmark_links(bookmark["id"], personal)
    return {
        "url": url,
        "bookmark": inspection["bookmark"],
        "tasks": inspection["tasks"],
        "issues": inspection["issues"],
    }


def search_task_ref_bookmarks(limit: int = 100) -> list[dict]:
    client = get_client()
    try:
        result = client.search("task-ref:", limit=limit)
    except RuntimeError:
        return []
    bookmarks = result.get("bookmarks") if isinstance(result, dict) else []
    if not isinstance(bookmarks, list):
        return []
    return [bookmark for bookmark in bookmarks if extract_task_ref(bookmark.get("note"))]


def reconcile(personal: bool = False, limit: int = 100) -> dict:
    linked_tasks = load_linked_tasks(personal)
    bookmark_index = build_bookmark_index(linked_tasks)
    issues: list[dict] = []
    checked_links: list[dict] = []

    for bookmark_id, tasks in sorted(bookmark_index.items()):
        if len(tasks) > 1:
            issues.append({
                "type": "duplicate_task_link",
                "bookmark_id": bookmark_id,
                "task_titles": [task.get("title") for task in tasks],
            })

        bookmark, error = fetch_bookmark(bookmark_id)
        if error:
            issues.append({
                "type": "missing_bookmark",
                "bookmark_id": bookmark_id,
                "task_titles": [task.get("title") for task in tasks],
                "error": error,
            })
            checked_links.append({
                "bookmark_id": bookmark_id,
                "task_titles": [task.get("title") for task in tasks],
                "exists": False,
                "error": error,
            })
            continue

        task_ref = extract_task_ref(bookmark.get("note"))
        expected_refs = {expected_task_ref(task) for task in tasks}

        if not task_ref:
            issues.append({
                "type": "missing_task_ref",
                "bookmark_id": bookmark_id,
                "task_titles": [task.get("title") for task in tasks],
            })
        elif task_ref not in expected_refs:
            issues.append({
                "type": "mismatched_task_ref",
                "bookmark_id": bookmark_id,
                "task_titles": [task.get("title") for task in tasks],
                "expected_any_of": sorted(expected_refs),
                "actual": task_ref,
            })

        checked_links.append({
            "bookmark_id": bookmark_id,
            "task_titles": [task.get("title") for task in tasks],
            "exists": True,
            "task_ref": task_ref,
            "bookmark": summarize_bookmark(bookmark),
        })

    task_ref_bookmarks = search_task_ref_bookmarks(limit=limit)
    for bookmark in task_ref_bookmarks:
        bookmark_id = bookmark.get("id")
        if not bookmark_id or bookmark_id in bookmark_index:
            continue
        issues.append({
            "type": "bookmark_without_task",
            "bookmark_id": bookmark_id,
            "task_ref": extract_task_ref(bookmark.get("note")),
            "url": bookmark_url(bookmark),
            "title": bookmark_title(bookmark),
        })

    issue_counts: dict[str, int] = defaultdict(int)
    for issue in issues:
        issue_counts[issue["type"]] += 1

    return {
        "summary": {
            "linked_tasks": len(linked_tasks),
            "linked_bookmarks": len(bookmark_index),
            "checked_task_ref_bookmarks": len(task_ref_bookmarks),
            "issue_counts": dict(sorted(issue_counts.items())),
            "issues_total": len(issues),
        },
        "issues": issues,
        "checked_links": checked_links,
    }


def print_json(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def print_human_status(payload: dict) -> None:
    if "task" in payload:
        task = payload["task"]
        print(f"Task: {task['title']}")
        print(f"Section: {task['section']} | Area: {task.get('area') or '-'}")
        print(f"Bookmarks: {', '.join(task['bookmark_ids']) or '-'}")
        print(f"Expected backlink: {task['expected_task_ref']}")
        print()
        for link in payload.get("links", []):
            print(f"- Bookmark {link['bookmark_id']}: {'OK' if link.get('exists') else 'MISSING'}")
            if link.get("bookmark"):
                print(f"  URL: {link['bookmark'].get('url') or '-'}")
                print(f"  Task ref: {link['bookmark'].get('task_ref') or '-'}")
            if link.get("exists"):
                print(f"  Backlink present: {'yes' if link.get('has_backlink') else 'no'}")
                print(f"  Backlink matches: {'yes' if link.get('backlink_matches') else 'no'}")
        if payload.get("issues"):
            print("\nIssues:")
            for issue in payload["issues"]:
                print(f"- {issue['type']}: {json.dumps(issue, ensure_ascii=False)}")
        return

    if "bookmark" in payload and "tasks" in payload:
        bookmark = payload["bookmark"]
        print(f"Bookmark: {bookmark.get('id')}")
        print(f"URL: {bookmark.get('url') or '-'}")
        print(f"Task ref: {bookmark.get('task_ref') or '-'}")
        print("Linked tasks:")
        if payload["tasks"]:
            for task in payload["tasks"]:
                print(f"- {task['title']}")
        else:
            print("- none")
        if payload.get("issues"):
            print("\nIssues:")
            for issue in payload["issues"]:
                print(f"- {issue['type']}: {json.dumps(issue, ensure_ascii=False)}")
        return

    if "summary" in payload:
        summary = payload["summary"]
        print("Karakeep reconcile (dry-run)")
        print(f"- linked tasks: {summary['linked_tasks']}")
        print(f"- linked bookmarks: {summary['linked_bookmarks']}")
        print(f"- task-ref bookmarks checked: {summary['checked_task_ref_bookmarks']}")
        print(f"- issues total: {summary['issues_total']}")
        if summary["issue_counts"]:
            print("- issue counts:")
            for kind, count in summary["issue_counts"].items():
                print(f"  - {kind}: {count}")
        if payload.get("issues"):
            print("\nIssues:")
            for issue in payload["issues"]:
                print(f"- {issue['type']}: {json.dumps(issue, ensure_ascii=False)}")
        return

    print_json(payload)


def cmd_link_status(args) -> None:
    if args.task:
        task = find_task_by_query(args.task, personal=args.personal)
        payload = inspect_task_links(task)
    elif args.bookmark_id:
        payload = inspect_bookmark_links(args.bookmark_id, personal=args.personal)
    elif args.url:
        payload = find_tasks_for_url(args.url, personal=args.personal)
    else:
        raise ValueError("one of --task, --bookmark-id, or --url is required")

    if args.json:
        print_json(payload)
    else:
        print_human_status(payload)


def cmd_find_task(args) -> None:
    if args.bookmark_id:
        payload = inspect_bookmark_links(args.bookmark_id, personal=args.personal)
    elif args.url:
        payload = find_tasks_for_url(args.url, personal=args.personal)
    else:
        raise ValueError("one of --bookmark-id or --url is required")

    if args.json:
        print_json(payload)
    else:
        print_human_status(payload)


def cmd_reconcile(args) -> None:
    payload = reconcile(personal=args.personal, limit=args.limit)
    payload["mode"] = "dry-run"
    if args.json:
        print_json(payload)
    else:
        print_human_status(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Task ↔ Karakeep lookup and reconciliation")
    parser.add_argument("--personal", action="store_true", help="Use personal tasks file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    link_status = subparsers.add_parser("link-status", help="Inspect link status for one task, bookmark, or URL")
    target = link_status.add_mutually_exclusive_group(required=True)
    target.add_argument("--task", help="Task title query")
    target.add_argument("--bookmark-id", help="Bookmark id")
    target.add_argument("--url", help="Bookmark URL")
    link_status.add_argument("--json", action="store_true", help="JSON output")
    link_status.set_defaults(func=cmd_link_status)

    find_task = subparsers.add_parser("find-task", help="Find task(s) by bookmark id or URL")
    target = find_task.add_mutually_exclusive_group(required=True)
    target.add_argument("--bookmark-id", help="Bookmark id")
    target.add_argument("--url", help="Bookmark URL")
    find_task.add_argument("--json", action="store_true", help="JSON output")
    find_task.set_defaults(func=cmd_find_task)

    reconcile_parser = subparsers.add_parser("reconcile", help="Report simple link inconsistencies")
    reconcile_parser.add_argument("--dry-run", action="store_true", help="Accepted for explicitness; reconciliation is read-only in Phase 2")
    reconcile_parser.add_argument("--limit", type=int, default=100, help="Max task-ref bookmarks to scan in Karakeep search")
    reconcile_parser.add_argument("--json", action="store_true", help="JSON output")
    reconcile_parser.set_defaults(func=cmd_reconcile)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (RuntimeError, ValueError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
