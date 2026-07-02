#!/usr/bin/env python3
"""
karakeep_wiki_writer.py — write a karakeep bookmark as a wiki entry.

Usage:
  python3 karakeep_wiki_writer.py write --bookmark-json '{"id":"...","url":"..."}' --category agent-tooling/frameworks.md
  python3 karakeep_wiki_writer.py check-dedup BOOKMARK_ID
  python3 karakeep_wiki_writer.py update-stats

Outputs JSON to stdout with result and any errors.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

VAULT = Path("/home/ozp/obsidian-wiki-vault")
REFERENCES = VAULT / "references"
MANIFEST = REFERENCES / "wiki-manifest.json"
INDEX = REFERENCES / "_index.md"

def resolve_category_path(key: str) -> Path:
    return REFERENCES / key


def ensure_category_file(key: str, title: str | None = None) -> Path:
    """Create category file and parent dirs if they don't exist. Returns path."""
    path = resolve_category_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        heading = title or key.replace("/", " / ").replace(".md", "").replace("-", " ").title()
        path.write_text(f"# {heading}\n\n", encoding="utf-8")
        _register_category_in_index(key, heading)
    return path


def _register_category_in_index(key: str, title: str):
    """Add a new category row to _index.md if not already present."""
    if not INDEX.exists():
        return
    text = INDEX.read_text(encoding="utf-8")
    if key in text:
        return
    new_row = f"| {title} | [{key}]({key}) | 0 | — |"
    # Insert before the closing of the categories table (first blank line after the header row)
    lines = text.splitlines()
    insert_at = None
    in_table = False
    for i, line in enumerate(lines):
        if "| Category" in line:
            in_table = True
        if in_table and line.strip() == "":
            insert_at = i
            break
    if insert_at is not None:
        lines.insert(insert_at, new_row)
        INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"schema": "karakeep.wiki_manifest.v1", "entries": {}}


def save_manifest(manifest: dict):
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def is_duplicate(bookmark_id: str, manifest: dict) -> bool:
    return bookmark_id in manifest.get("entries", {})


def extract_user_hint(note: str) -> str | None:
    """Extract user-hint line from karakeep note field."""
    if not note:
        return None
    for line in note.splitlines():
        line = line.strip()
        if line.startswith("user-hint:"):
            return line[len("user-hint:"):].strip()
    return None


def extract_content_type(note: str) -> str | None:
    if not note:
        return None
    for line in note.splitlines():
        line = line.strip()
        if line.startswith("content-type:"):
            return line[len("content-type:"):].strip()
    return None


def _bm_url(bm: dict) -> str:
    return bm.get("url") or (bm.get("content") or {}).get("url") or ""


def _tag_names(bm: dict) -> list[str]:
    raw = bm.get("tags") or []
    names = []
    for t in raw:
        if isinstance(t, dict):
            name = t.get("name", "").strip()
        else:
            name = str(t).strip()
        if name:
            names.append(name)
    return names


def format_entry(bm: dict, enrichment: dict | None = None) -> str:
    """Format a bookmark as a wiki entry block."""
    url = _bm_url(bm)
    title = bm.get("title") or (bm.get("content") or {}).get("title") or url or "Untitled"
    note = bm.get("note", "") or ""
    tags = _tag_names(bm)
    bookmark_id = bm.get("id", "")
    content_type = extract_content_type(note) or (bm.get("content") or {}).get("type", "") or bm.get("content_type", "")
    user_hint = extract_user_hint(note)
    today = date.today().isoformat()

    tag_str = ", ".join(sorted(set(tags))) if tags else "—"

    lines = [f"### [{title}]({url})"]
    lines.append(f"- **Tipo:** {content_type or '—'}")
    if user_hint:
        lines.append(f"- **Nota:** {user_hint}")

    # Enrichment fields (from GitHub API or trafilatura)
    if enrichment and enrichment.get("enriched"):
        parts = []
        if enrichment.get("description"):
            parts.append(enrichment["description"])
        if enrichment.get("stars") is not None:
            parts.append(f"⭐ {enrichment['stars']}")
        if enrichment.get("language"):
            parts.append(enrichment["language"])
        if enrichment.get("last_commit"):
            parts.append(f"último commit: {enrichment['last_commit']}")
        if parts:
            lines.append(f"- **Sobre:** {' · '.join(parts)}")
        if enrichment.get("topics"):
            lines.append(f"- **Tópicos:** {', '.join(enrichment['topics'])}")
        if enrichment.get("readme_excerpt"):
            excerpt = enrichment["readme_excerpt"][:300].replace("\n", " ")
            lines.append(f"- **Resumo:** {excerpt}")

    lines.append(f"- **Tags:** {tag_str}")
    lines.append(f"- **ID:** `karakeep:{bookmark_id}`")
    lines.append(f"- **Data:** {today}")
    lines.append("")

    return "\n".join(lines)


def write_entry(bm: dict, category_key: str, category_title: str | None = None, enrichment: dict | None = None) -> dict:
    bookmark_id = bm.get("id", "")
    if not bookmark_id:
        return {"ok": False, "error": "bookmark has no id"}

    manifest = load_manifest()
    if is_duplicate(bookmark_id, manifest):
        existing = manifest["entries"][bookmark_id]
        return {"ok": False, "duplicate": True, "existing": existing}

    target_file = ensure_category_file(category_key, title=category_title)

    entry = format_entry(bm, enrichment=enrichment)

    current = target_file.read_text(encoding="utf-8")
    target_file.write_text(current + "\n" + entry, encoding="utf-8")

    manifest["entries"][bookmark_id] = {
        "file": category_key,
        "url": _bm_url(bm),
        "title": bm.get("title", "") or (bm.get("content") or {}).get("title", ""),
        "written_at": date.today().isoformat(),
    }
    save_manifest(manifest)

    update_index_stats(manifest)

    return {
        "ok": True,
        "bookmark_id": bookmark_id,
        "file": category_key,
        "wiki_ref": f"references/{category_key}",
    }


def update_index_stats(manifest: dict):
    """Update entry counts in _index.md."""
    if not INDEX.exists():
        return

    entries = manifest.get("entries", {})
    total = len(entries)

    counts: dict[str, int] = {}
    for e in entries.values():
        f = e.get("file", "")
        counts[f] = counts.get(f, 0) + 1

    text = INDEX.read_text(encoding="utf-8")

    # Update total entries line
    text = re.sub(
        r"(\*\*Total entries:\*\* )\d+",
        f"\\g<1>{total}",
        text,
    )

    # Update last ingest date
    today = date.today().isoformat()
    text = re.sub(
        r"(\*\*Last ingest:\*\* ).*",
        f"\\g<1>{today}",
        text,
    )

    # Update per-category entry counts in the table.
    # Match rows like: | Title | [path/file.md](path/file.md) | N | ... |
    lines = []
    for line in text.splitlines():
        updated = line
        m = re.match(r"^(\|\s*.+?\s*\|\s*\[[^\]]+\]\(([^)]+)\)\s*\|\s*)(\d+)(\s*\|.*)$", line)
        if m:
            cat_key = m.group(2)
            if cat_key in counts:
                updated = f"{m.group(1)}{counts[cat_key]}{m.group(4)}"
        lines.append(updated)
    text = "\n".join(lines) + "\n"

    INDEX.write_text(text, encoding="utf-8")


def cmd_write(args):
    bm = json.loads(args.bookmark_json)
    enrichment = json.loads(args.enrichment_json) if args.enrichment_json else None
    result = write_entry(bm, args.category, category_title=getattr(args, "category_title", None), enrichment=enrichment)
    print(json.dumps(result, ensure_ascii=False))


def cmd_check_dedup(args):
    manifest = load_manifest()
    dup = is_duplicate(args.bookmark_id, manifest)
    result = {"bookmark_id": args.bookmark_id, "duplicate": dup}
    if dup:
        result["existing"] = manifest["entries"][args.bookmark_id]
    print(json.dumps(result, ensure_ascii=False))


def cmd_update_stats(args):
    manifest = load_manifest()
    update_index_stats(manifest)
    print(json.dumps({"ok": True, "total": len(manifest.get("entries", {}))}))


def main():
    p = argparse.ArgumentParser(description="Write karakeep bookmarks to wiki")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write", help="Write entry to wiki file")
    w.add_argument("--bookmark-json", required=True, help="JSON string of bookmark object")
    w.add_argument("--category", required=True, help="Category key, e.g. mcp/servers.md")
    w.add_argument("--category-title", default=None, help="Human-readable title for new categories")
    w.add_argument("--enrichment-json", default=None, help="JSON string of enrichment data from karakeep_wiki_enrich.py")
    w.set_defaults(func=cmd_write)

    d = sub.add_parser("check-dedup", help="Check if bookmark already in wiki")
    d.add_argument("bookmark_id")
    d.set_defaults(func=cmd_check_dedup)

    s = sub.add_parser("update-stats", help="Recompute _index.md stats")
    s.set_defaults(func=cmd_update_stats)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
