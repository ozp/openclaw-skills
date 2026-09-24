#!/usr/bin/env python3
"""
migrate_backlog_to_mc.py — migrate existing backlog items from Work Tasks.md to Mission Control boards.

Parses backlog items with `note:: karakeep:*` metadata and creates MC tasks
via the same routing logic used by the karakeep triage pipeline.

Usage:
  python3 migrate_backlog_to_mc.py --dry-run          # preview what would be migrated
  python3 migrate_backlog_to_mc.py --apply             # create tasks in MC
  python3 migrate_backlog_to_mc.py --apply --yes       # skip confirmation prompt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# Reuse MC constants from karakeep_triage
sys.path.insert(0, str(Path(__file__).parent))

from karakeep_triage import (
    MC_BASE_URL,
    MC_ENV_FILE,
    MC_INBOX_BOARD_ID,
    MC_AREA_BOARD_MAP,
    get_mc_token,
    mc_api_call,
    read_env_key,
)


WORK_TASKS_FILE = Path("/home/ozp/clawd/tasks/Work Tasks.md")

# Regex to parse backlog items
# Format: - [ ] **URL — TITLE** area:: X type:: Y estimate:: Z note:: karakeep:ID [note:: karakeep:ID2]
BACKLOG_PATTERN = re.compile(
    r"-\s+\[\s*\]\s+\*\*(.+?)\*\*\s+"
    r"area::\s*(\S+)\s+"
    r"type::\s*(\S+)\s+"
    r"estimate::\s*(\S+)\s+"
    r"(.+)"
)

KARAKEEP_NOTE_PATTERN = re.compile(r"note::\s*karakeep:([a-z0-9]+)")


def parse_backlog_items(content: str) -> list[dict]:
    """Parse all backlog items with karakeep metadata from Work Tasks.md."""
    items = []
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("- [ ] **"):
            continue
        match = BACKLOG_PATTERN.match(line)
        if not match:
            continue

        title_block = match.group(1).strip()
        area = match.group(2).strip()
        task_type = match.group(3).strip()
        estimate = match.group(4).strip()
        notes_str = match.group(5).strip()

        # Extract karakeep IDs
        karakeep_ids = KARAKEEP_NOTE_PATTERN.findall(notes_str)
        if not karakeep_ids:
            continue

        # Parse title and URL from title_block
        # Format: "URL — TITLE" or just "URL" or "TITLE"
        url = ""
        display_title = title_block
        if " — " in title_block:
            parts = title_block.split(" — ", 1)
            url = parts[0].strip()
            display_title = parts[1].strip()
        elif title_block.startswith("http"):
            url = title_block
            display_title = title_block
        else:
            display_title = title_block

        items.append({
            "title_block": title_block,
            "url": url,
            "display_title": display_title,
            "area": area,
            "task_type": task_type,
            "estimate": estimate,
            "karakeep_ids": karakeep_ids,
            "line": line,
        })

    return items


def route_area_to_board(area: str) -> tuple[str, str]:
    """Route an area to an MC board. Returns (board_id, board_name)."""
    if area in MC_AREA_BOARD_MAP:
        board_id = MC_AREA_BOARD_MAP[area]
    else:
        board_id = MC_INBOX_BOARD_ID

    board_names = {
        MC_INBOX_BOARD_ID: "External Triage",
        "40851a1e-fe67-460c-889f-eba0d8649b1a": "Agent Architecture",
        "ee065313-414e-4113-83c1-2b3eb3f30d8e": "Governance & Gates",
        "76f10c1e-6f4e-4d42-b2dc-d5cc1fe6c926": "Models & Cost",
        "0f302d65-dd09-4fd3-848f-8989636d9334": "Infrastructure Baseline",
        "78fad92f-6aa2-446f-9120-f30c70ce9cd7": "Knowledge & RAG",
        "7aa5ee71-938f-4b61-9e61-603a731b2753": "Integrations",
        "2df94061-0c2b-4e7e-8a64-4e3a2b3591eb": "UNIP Operations",
        "7478d357-f8da-4426-8343-464eb602ff9b": "Prompts & Docs",
        "ab429505-87ff-4373-9991-8ff066f82d00": "Experimental",
    }
    return board_id, board_names.get(board_id, board_id)


def check_existing_mc_task(board_id: str, bookmark_id: str, token: str) -> dict | None:
    """Check if an MC task already exists for this bookmark."""
    import_source = f"karakeep:{bookmark_id}"
    try:
        result = mc_api_call("GET", f"/api/v1/boards/{board_id}/tasks?limit=100", token)
        items = result if isinstance(result, list) else result.get("items", result.get("tasks", []))
        for task in items:
            cfv = task.get("custom_field_values", {})
            if cfv.get("import_source") == import_source:
                return task
    except Exception:
        pass
    return None


def create_migrated_mc_task(item: dict, token: str, primary_karakeep_id: str) -> dict:
    """Create a single MC task from a parsed backlog item."""
    board_id, board_name = route_area_to_board(item["area"])

    task_title = item["title_block"]
    description_parts = [
        f"Source URL: {item['url']}" if item["url"] else "",
        f"Migrated from local Work Tasks.md backlog on 2026-04-11.",
        f"Original area: {item['area']}",
        f"Karakeep ID: {primary_karakeep_id}",
    ]
    description = "\n\n".join(p for p in description_parts if p)

    body = {
        "title": task_title,
        "description": description,
        "status": "inbox",
        "priority": "low",
        "custom_field_values": {
            "area": item["area"],
            "estimate": item["estimate"],
            "type": item["task_type"],
            "import_source": f"karakeep:{primary_karakeep_id}",
        },
    }

    # Check for existing task first
    existing = check_existing_mc_task(board_id, primary_karakeep_id, token)
    if existing:
        return {
            "status": "duplicate",
            "task_id": existing.get("id"),
            "board_id": board_id,
            "board_name": board_name,
            "title": task_title[:80],
        }

    try:
        result = mc_api_call("POST", f"/api/v1/boards/{board_id}/tasks", token, body)
        return {
            "status": "created",
            "task_id": result.get("id"),
            "board_id": board_id,
            "board_name": board_name,
            "title": task_title[:80],
        }
    except Exception as exc:
        return {
            "status": "error",
            "title": task_title[:80],
            "error": f"{type(exc).__name__}:{exc}",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate backlog items to Mission Control")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating tasks")
    parser.add_argument("--apply", action="store_true", help="Create tasks in MC")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    parser.add_argument("--tasks-file", default=str(WORK_TASKS_FILE), help="Path to Work Tasks.md")
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        args.dry_run = True

    content = Path(args.tasks_file).read_text(encoding="utf-8")
    items = parse_backlog_items(content)

    if not items:
        print("No backlog items with karakeep metadata found.")
        return

    # Group by board for summary
    board_counts: dict[str, int] = {}
    for item in items:
        _, board_name = route_area_to_board(item["area"])
        board_counts[board_name] = board_counts.get(board_name, 0) + 1

    print(f"Found {len(items)} backlog items with karakeep metadata.")
    print(f"\nRouting preview:")
    for board_name, count in sorted(board_counts.items(), key=lambda x: -x[1]):
        print(f"  {board_name}: {count} items")

    if args.dry_run:
        print(f"\n--- DRY RUN ---")
        print("Run with --apply to create tasks in Mission Control.")
        # Show first 5 as sample
        print(f"\nSample items (first 5):")
        for item in items[:5]:
            _, board_name = route_area_to_board(item["area"])
            kk_id = item["karakeep_ids"][0]
            print(f"  [{item['area']}] → {board_name} | {item['title_block'][:80]} | karakeep:{kk_id}")
        if len(items) > 5:
            print(f"  ... and {len(items) - 5} more")
        return

    # Apply mode
    token = get_mc_token()
    if not token:
        print("ERROR: MC token not found. Check backend/.env for LOCAL_AUTH_TOKEN.")
        sys.exit(1)

    if not args.yes:
        print(f"\nWill create {len(items)} tasks in Mission Control.")
        response = input("Proceed? [y/N] ").strip().lower()
        if response not in ("y", "yes"):
            print("Aborted.")
            return

    results = {"created": 0, "duplicate": 0, "error": 0}
    errors = []

    for i, item in enumerate(items):
        primary_id = item["karakeep_ids"][0]
        result = create_migrated_mc_task(item, token, primary_id)
        status = result.get("status", "error")
        results[status] = results.get(status, 0) + 1

        if status == "error":
            errors.append(result)

        if (i + 1) % 10 == 0 or i == len(items) - 1:
            print(f"  Progress: {i + 1}/{len(items)} | created={results['created']} dup={results['duplicate']} err={results['error']}")

    print(f"\n--- MIGRATION COMPLETE ---")
    print(f"  Created: {results['created']}")
    print(f"  Duplicates (skipped): {results['duplicate']}")
    print(f"  Errors: {results['error']}")

    if errors:
        print(f"\nErrors:")
        for err in errors[:10]:
            print(f"  {err.get('title', '?')}: {err.get('error', 'unknown')}")


if __name__ == "__main__":
    main()
