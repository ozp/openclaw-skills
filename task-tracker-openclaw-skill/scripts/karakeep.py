#!/usr/bin/env python3
"""
karakeep.py — thin deterministic helper for the local Karakeep REST API.

Default behavior:
- Prefer environment variables:
  - KARAKEEP_API_ADDR (default: http://localhost:3030)
  - KARAKEEP_API_KEY
- Fallback to parsing /home/ozp/code/karakeep-api-guide.md for local setup only.

Commands:
  python3 karakeep.py find-url https://example.com
  python3 karakeep.py save-url https://example.com --title "Example" --note "task-ref: ..."
  python3 karakeep.py get-bookmark BOOKMARK_ID
  python3 karakeep.py update-note BOOKMARK_ID --note "..."
  python3 karakeep.py add-tags BOOKMARK_ID --tags tag1,tag2
  python3 karakeep.py assign-list BOOKMARK_ID LIST_ID
  python3 karakeep.py list-bookmarks --list-id LIST_ID
  python3 karakeep.py list-list-bookmarks LIST_ID
  python3 karakeep.py remove-list BOOKMARK_ID LIST_ID
  python3 karakeep.py list-lists
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DEFAULT_ADDR = "http://localhost:3030"
LOCAL_GUIDE = Path("/home/ozp/code/karakeep-api-guide.md")


def load_local_defaults() -> tuple[str, str | None]:
    addr = os.getenv("KARAKEEP_API_ADDR", DEFAULT_ADDR).rstrip("/")
    key = os.getenv("KARAKEEP_API_KEY")

    if key:
        return addr, key

    if LOCAL_GUIDE.exists():
        text = LOCAL_GUIDE.read_text(encoding="utf-8")
        addr_match = re.search(r"KARAKEEP_API_ADDR\s*=\s*(https?://[^\s`]+)", text)
        key_match = re.search(r"KARAKEEP_API_KEY\s*=\s*([A-Za-z0-9_\-]+)", text)
        if addr_match:
            addr = addr_match.group(1).rstrip("/")
        if key_match:
            key = key_match.group(1)

    return addr, key


class KarakeepClient:
    def __init__(self, base_addr: str, api_key: str):
        self.base_addr = base_addr.rstrip("/")
        self.api_base = f"{self.base_addr}/api/v1"
        self.api_key = api_key

    def _request(self, method: str, path: str, payload: dict | None = None):
        body = None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = Request(f"{self.api_base}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return None
                return json.loads(raw)
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Karakeep API HTTP {e.code}: {detail}") from e
        except URLError as e:
            raise RuntimeError(f"Karakeep API connection failed: {e}") from e

    def check_health(self):
        req = Request(f"{self.base_addr}/api/health", method="GET")
        with urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def find_url(self, url: str):
        return self._request("GET", f"/bookmarks/check-url?url={quote(url, safe='')}")

    def save_url(self, url: str, title: str | None = None, note: str | None = None):
        payload = {"type": "link", "url": url}
        if title:
            payload["title"] = title
        if note:
            payload["note"] = note
        return self._request("POST", "/bookmarks", payload)

    def get_bookmark(self, bookmark_id: str):
        return self._request("GET", f"/bookmarks/{bookmark_id}")

    def update_bookmark(self, bookmark_id: str, **fields):
        payload = {k: v for k, v in fields.items() if v is not None}
        return self._request("PATCH", f"/bookmarks/{bookmark_id}", payload)

    def add_tags(self, bookmark_id: str, tags: list[str]):
        payload = {
            "tags": [{"tagName": tag} for tag in tags if tag.strip()]
        }
        return self._request("POST", f"/bookmarks/{bookmark_id}/tags", payload)

    def list_lists(self):
        return self._request("GET", "/lists")

    def create_list(self, name: str, icon: str | None = None, description: str | None = None):
        payload = {"name": name}
        if icon:
            payload["icon"] = icon
        if description:
            payload["description"] = description
        return self._request("POST", "/lists", payload)

    def list_bookmarks(self, limit: int = 20, cursor: str | None = None, list_id: str | None = None):
        query = [f"limit={int(limit)}"]
        if cursor:
            query.append(f"cursor={quote(cursor, safe='')}")
        if list_id:
            query.append(f"listId={quote(list_id, safe='')}")
        return self._request("GET", f"/bookmarks?{'&'.join(query)}")

    def list_list_bookmarks(self, list_id: str):
        return self._request("GET", f"/lists/{list_id}/bookmarks")

    def add_bookmark_to_list(self, bookmark_id: str, list_id: str):
        return self._request("PUT", f"/lists/{list_id}/bookmarks/{bookmark_id}")

    def remove_bookmark_from_list(self, bookmark_id: str, list_id: str):
        return self._request("DELETE", f"/lists/{list_id}/bookmarks/{bookmark_id}")

    def assign_list(self, bookmark_id: str, list_id: str):
        return self.add_bookmark_to_list(bookmark_id, list_id)

    def search(self, query: str, limit: int = 10):
        return self._request(
            "GET",
            f"/bookmarks/search?q={quote(query, safe='')}&limit={int(limit)}"
        )

    def delete_bookmark(self, bookmark_id: str):
        return self._request("DELETE", f"/bookmarks/{bookmark_id}")


def get_client() -> KarakeepClient:
    addr, key = load_local_defaults()
    if not key:
        raise RuntimeError(
            "Karakeep API key not found. Set KARAKEEP_API_KEY or maintain /home/ozp/code/karakeep-api-guide.md."
        )
    return KarakeepClient(addr, key)


def print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_health(_args):
    print_json(get_client().check_health())


def cmd_find_url(args):
    print_json(get_client().find_url(args.url))


def cmd_save_url(args):
    print_json(get_client().save_url(args.url, title=args.title, note=args.note))


def cmd_get_bookmark(args):
    print_json(get_client().get_bookmark(args.bookmark_id))


def cmd_update_note(args):
    print_json(get_client().update_bookmark(args.bookmark_id, note=args.note, summary=args.summary))


def cmd_add_tags(args):
    tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
    print_json(get_client().add_tags(args.bookmark_id, tags))


def cmd_list_lists(_args):
    print_json(get_client().list_lists())


def cmd_create_list(args):
    print_json(get_client().create_list(args.name, icon=args.icon, description=args.description))


def cmd_list_bookmarks(args):
    print_json(get_client().list_bookmarks(limit=args.limit, cursor=args.cursor, list_id=args.list_id))


def cmd_list_list_bookmarks(args):
    print_json(get_client().list_list_bookmarks(args.list_id))


def cmd_assign_list(args):
    result = get_client().assign_list(args.bookmark_id, args.list_id)
    print_json(result if result is not None else {"ok": True})


def cmd_remove_list(args):
    result = get_client().remove_bookmark_from_list(args.bookmark_id, args.list_id)
    print_json(result if result is not None else {"ok": True})


def cmd_search(args):
    print_json(get_client().search(args.query, limit=args.limit))


def cmd_delete_bookmark(args):
    result = get_client().delete_bookmark(args.bookmark_id)
    print_json(result if result is not None else {"ok": True})


def build_parser():
    parser = argparse.ArgumentParser(description="Karakeep REST helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser("health", help="Check Karakeep health")
    p.set_defaults(func=cmd_health)

    p = subparsers.add_parser("find-url", help="Check whether a URL already exists")
    p.add_argument("url")
    p.set_defaults(func=cmd_find_url)

    p = subparsers.add_parser("save-url", help="Create bookmark from URL")
    p.add_argument("url")
    p.add_argument("--title")
    p.add_argument("--note")
    p.set_defaults(func=cmd_save_url)

    p = subparsers.add_parser("get-bookmark", help="Fetch one bookmark")
    p.add_argument("bookmark_id")
    p.set_defaults(func=cmd_get_bookmark)

    p = subparsers.add_parser("update-note", help="Update bookmark note/summary")
    p.add_argument("bookmark_id")
    p.add_argument("--note")
    p.add_argument("--summary")
    p.set_defaults(func=cmd_update_note)

    p = subparsers.add_parser("add-tags", help="Attach tags to bookmark")
    p.add_argument("bookmark_id")
    p.add_argument("--tags", required=True, help="Comma-separated tag names")
    p.set_defaults(func=cmd_add_tags)

    p = subparsers.add_parser("list-lists", help="List all bookmark lists")
    p.set_defaults(func=cmd_list_lists)

    p = subparsers.add_parser("create-list", help="Create bookmark list")
    p.add_argument("name")
    p.add_argument("--icon")
    p.add_argument("--description")
    p.set_defaults(func=cmd_create_list)

    p = subparsers.add_parser("list-bookmarks", help="List bookmarks with optional list filter")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--cursor")
    p.add_argument("--list-id")
    p.set_defaults(func=cmd_list_bookmarks)

    p = subparsers.add_parser("list-list-bookmarks", help="List bookmarks directly from one list")
    p.add_argument("list_id")
    p.set_defaults(func=cmd_list_list_bookmarks)

    p = subparsers.add_parser("assign-list", help="Assign bookmark to list")
    p.add_argument("bookmark_id")
    p.add_argument("list_id")
    p.set_defaults(func=cmd_assign_list)

    p = subparsers.add_parser("remove-list", help="Remove bookmark from list")
    p.add_argument("bookmark_id")
    p.add_argument("list_id")
    p.set_defaults(func=cmd_remove_list)

    p = subparsers.add_parser("search", help="Search bookmarks")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_search)

    p = subparsers.add_parser("delete-bookmark", help="Delete bookmark")
    p.add_argument("bookmark_id")
    p.set_defaults(func=cmd_delete_bookmark)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
