#!/usr/bin/env python3
"""
karakeep_wiki_enrich.py — enrich a bookmark with live data before wiki ingestion.

For repos (GitHub): fetches stars, topics, language, last commit, README excerpt via gh CLI.
For articles/docs: uses trafilatura to extract text snippet.

Usage:
  python3 karakeep_wiki_enrich.py --bookmark-json '{"id":"...","content":{"url":"...","type":"link"}}'

Output JSON:
  {
    "bookmark_id": "...",
    "url": "...",
    "source": "github | trafilatura | karakeep | failed",
    "description": "...",
    "stars": 1234,
    "topics": ["..."],
    "language": "Python",
    "last_commit": "2026-04-15",
    "readme_excerpt": "...",
    "author": "...",
    "enriched": true
  }
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


GITHUB_RE = re.compile(r"https?://github\.com/([^/]+/[^/?#]+)")
README_MAX_CHARS = 800


def _bm_url(bm: dict) -> str:
    return bm.get("url") or (bm.get("content") or {}).get("url") or ""


def _content_type(bm: dict) -> str:
    note = bm.get("note", "") or ""
    for line in note.splitlines():
        line = line.strip()
        if line.startswith("content-type:"):
            return line[len("content-type:"):].strip().lower()
    return (bm.get("content") or {}).get("type", "").lower()


def enrich_github(bookmark_id: str, url: str, repo_path: str) -> dict:
    base = {
        "bookmark_id": bookmark_id,
        "url": url,
        "source": "github",
        "description": "",
        "stars": None,
        "topics": [],
        "language": None,
        "last_commit": None,
        "readme_excerpt": "",
        "author": repo_path.split("/")[0],
        "enriched": True,
    }

    # Repo metadata via gh
    try:
        meta_raw = subprocess.run(
            ["gh", "repo", "view", repo_path,
             "--json", "description,stargazerCount,repositoryTopics,primaryLanguage,pushedAt"],
            capture_output=True, text=True, timeout=15
        )
        if meta_raw.returncode == 0 and meta_raw.stdout.strip():
            meta = json.loads(meta_raw.stdout)
            base["description"] = meta.get("description") or ""
            base["stars"] = meta.get("stargazerCount")
            base["language"] = (meta.get("primaryLanguage") or {}).get("name")
            base["last_commit"] = (meta.get("pushedAt") or "")[:10]
            topics_raw = meta.get("repositoryTopics") or []
            base["topics"] = [t.get("topic", {}).get("name", "") for t in topics_raw if t.get("topic")]
    except Exception as e:
        base["_meta_error"] = str(e)

    # README excerpt
    try:
        readme_raw = subprocess.run(
            ["gh", "repo", "view", repo_path, "--json", "readme"],
            capture_output=True, text=True, timeout=15
        )
        if readme_raw.returncode == 0 and readme_raw.stdout.strip():
            readme_data = json.loads(readme_raw.stdout)
            readme_text = readme_data.get("readme", {}).get("text", "") or ""
            # Strip markdown noise, take first meaningful chunk
            lines = [l for l in readme_text.splitlines() if l.strip() and not l.strip().startswith("#")]
            excerpt = " ".join(lines)[:README_MAX_CHARS].strip()
            base["readme_excerpt"] = excerpt
    except Exception as e:
        base["_readme_error"] = str(e)

    return base


def enrich_article(bookmark_id: str, url: str) -> dict:
    base = {
        "bookmark_id": bookmark_id,
        "url": url,
        "source": "trafilatura",
        "description": "",
        "stars": None,
        "topics": [],
        "language": None,
        "last_commit": None,
        "readme_excerpt": "",
        "author": "",
        "enriched": True,
    }
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
            if text:
                base["readme_excerpt"] = text[:README_MAX_CHARS].strip()
                base["source"] = "trafilatura"
    except ImportError:
        base["source"] = "failed"
        base["_error"] = "trafilatura not installed"
    except Exception as e:
        base["source"] = "failed"
        base["_error"] = str(e)
    return base


def enrich_bookmark(bm: dict) -> dict:
    bookmark_id = bm.get("id", "")
    url = _bm_url(bm)
    content_type = _content_type(bm)

    if not url:
        return {"bookmark_id": bookmark_id, "url": "", "enriched": False, "source": "no_url"}

    # GitHub repo
    github_match = GITHUB_RE.match(url)
    if github_match or content_type == "repo":
        if github_match:
            return enrich_github(bookmark_id, url, github_match.group(1))
        return {"bookmark_id": bookmark_id, "url": url, "enriched": False, "source": "not_github_repo"}

    # Article / docs / blog
    if content_type in ("article", "docs", "blog"):
        return enrich_article(bookmark_id, url)

    # Fallback: use what karakeep already has
    content = bm.get("content") or {}
    return {
        "bookmark_id": bookmark_id,
        "url": url,
        "source": "karakeep",
        "description": content.get("description", ""),
        "stars": None,
        "topics": [],
        "language": None,
        "last_commit": None,
        "readme_excerpt": "",
        "author": content.get("author", ""),
        "enriched": True,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bookmark-json", required=True)
    args = p.parse_args()

    bm = json.loads(args.bookmark_json)
    result = enrich_bookmark(bm)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
