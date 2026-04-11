#!/usr/bin/env python3
"""
read_link.py — structured bookmark reading pipeline for Karakeep triage.

Provider chain (cheap → expensive):
1. karakeep metadata
2. github api (for github.com/OWNER/REPO)
3. fetch/trafilatura
4. mcphub tool lookup (reserved; not implemented yet)
5. playwriter/browser (reserved; not implemented yet)

The module returns a normalized payload with:
- bookmark identity
- source type
- reader used
- read status: enough | partial | failed
- confidence: high | medium | low
- reason for stopping/escalating
- normalized summary and extracted fields
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).parent))

from karakeep import get_client

try:
    import trafilatura  # type: ignore
except Exception:  # pragma: no cover - runtime optional dependency path
    trafilatura = None

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) OpenClaw-Karakeep-Triage/1.0"
GENERIC_TITLES = {
    "home",
    "index",
    "untitled",
    "page not found",
    "not found",
    "loading",
    "error",
}


def clean_text(value: str | None) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    return text.strip()


def clip_text(value: str | None, limit: int = 240) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def bookmark_url(bookmark: dict) -> str:
    content = bookmark.get("content") or {}
    return clean_text(bookmark.get("url") or content.get("url") or "")


def bookmark_title(bookmark: dict) -> str:
    content = bookmark.get("content") or {}
    return clean_text(bookmark.get("title") or content.get("title") or "")


def bookmark_description(bookmark: dict) -> str:
    content = bookmark.get("content") or {}
    for key in ["description", "summary", "excerpt", "textContent"]:
        value = bookmark.get(key) or content.get(key)
        if value:
            return clean_text(value)
    return ""


def bookmark_author(bookmark: dict) -> str:
    content = bookmark.get("content") or {}
    return clean_text(bookmark.get("author") or content.get("author") or "")


def bookmark_publisher(bookmark: dict) -> str:
    content = bookmark.get("content") or {}
    return clean_text(bookmark.get("publisher") or content.get("publisher") or content.get("siteName") or "")


def bookmark_note(bookmark: dict) -> str:
    return clean_text(bookmark.get("note") or "")


def make_attempt(reader: str, status: str, confidence: str, reason: str) -> dict[str, str]:
    return {
        "reader": reader,
        "status": status,
        "confidence": confidence,
        "reason": reason,
    }


def is_generic_title(title: str, url: str = "") -> bool:
    normalized = clean_text(title).lower()
    if not normalized:
        return True
    if normalized in GENERIC_TITLES:
        return True
    if url and normalized == clean_text(url).lower():
        return True
    if len(normalized) < 8:
        return True
    return False


def detect_source_type(url: str, bookmark: dict | None = None) -> str:
    parsed = urlparse(url or "")
    host = (parsed.netloc or "").lower()
    path = parsed.path.lower()
    title = bookmark_title(bookmark or {})

    if "github.com" in host:
        return "repo"
    if any(host.endswith(domain) for domain in ["youtube.com", "youtu.be", "vimeo.com"]):
        return "video"
    if path.endswith(".pdf"):
        return "pdf"
    if any(token in host for token in ["docs.", "readthedocs", "developer."]):
        return "docs"
    if any(token in path for token in ["/docs", "/guide", "/reference", "/manual"]):
        return "docs"
    if any(token in host for token in ["blog", "medium.com", "substack.com"]):
        return "blog"
    if any(token in title.lower() for token in ["docs", "documentation", "guide", "manual"]):
        return "docs"
    if any(token in title.lower() for token in ["paper", "artigo", "study", "research"]):
        return "article"
    return "article"


def summarize_karakeep(bookmark: dict) -> str:
    parts = []
    title = bookmark_title(bookmark)
    description = bookmark_description(bookmark)
    publisher = bookmark_publisher(bookmark)
    note = bookmark_note(bookmark)

    if title and not is_generic_title(title, bookmark_url(bookmark)):
        parts.append(title)
    if description:
        parts.append(clip_text(description, 180))
    if publisher:
        parts.append(f"source: {publisher}")
    human_note = [
        line for line in note.splitlines()
        if line and not re.match(r"^(task-ref|read-source|read-status|content-type|summary):", line)
    ]
    if human_note:
        parts.append(clip_text(" ".join(human_note), 120))

    return clip_text(" — ".join(part for part in parts if part), 260)


def read_from_karakeep_metadata(bookmark: dict) -> dict[str, Any]:
    url = bookmark_url(bookmark)
    title = bookmark_title(bookmark)
    description = bookmark_description(bookmark)
    author = bookmark_author(bookmark)
    publisher = bookmark_publisher(bookmark)
    note = bookmark_note(bookmark)
    source_type = detect_source_type(url, bookmark=bookmark)

    evidence_count = sum(bool(value) for value in [description, author, publisher])
    human_note_lines = [
        line for line in note.splitlines()
        if line and not re.match(r"^(task-ref|read-source|read-status|content-type|summary):", line)
    ]

    if not is_generic_title(title, url) and (len(description) >= 100 or evidence_count >= 2):
        status = "enough"
        confidence = "high"
        reason = "karakeep_metadata_sufficient"
    elif not is_generic_title(title, url) and (description or publisher or author or human_note_lines):
        status = "partial"
        confidence = "medium"
        reason = "karakeep_metadata_partial"
    elif title or description or human_note_lines:
        status = "partial"
        confidence = "low"
        reason = "karakeep_metadata_thin"
    else:
        status = "failed"
        confidence = "low"
        reason = "karakeep_metadata_empty"

    return {
        "bookmark": {
            "id": bookmark.get("id"),
            "url": url,
            "original_title": title or url,
        },
        "source_type": source_type,
        "reader_used": "karakeep",
        "status": status,
        "confidence": confidence,
        "reason": reason,
        "normalized_summary": summarize_karakeep(bookmark),
        "fields": {
            "title": title,
            "description": clip_text(description, 240),
            "author": author,
            "publisher": publisher,
            "note": clip_text(note, 180),
        },
        "provider_attempts": [make_attempt("karakeep", status, confidence, reason)],
    }


GITHUB_REPO_RE = re.compile(r"^/([^/]+)/([^/]+)(?:/.*)?$")


def parse_github_repo(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url or "")
    if "github.com" not in (parsed.netloc or "").lower():
        return None
    match = GITHUB_REPO_RE.match(parsed.path or "")
    if not match:
        return None
    owner, repo = match.group(1), match.group(2)
    if repo.endswith(".git"):
        repo = repo[:-4]
    if owner and repo:
        return owner, repo
    return None


def github_headers(accept: str = "application/vnd.github+json") -> dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def http_get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = Request(url, headers=headers or {"User-Agent": USER_AGENT})
    with urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_text(url: str, headers: dict[str, str] | None = None) -> str:
    req = Request(url, headers=headers or {"User-Agent": USER_AGENT})
    with urlopen(req, timeout=20) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def read_from_github_api(url: str) -> dict[str, Any] | None:
    repo_ref = parse_github_repo(url)
    if not repo_ref:
        return None

    owner, repo = repo_ref
    try:
        repo_data = http_get_json(f"https://api.github.com/repos/{owner}/{repo}", headers=github_headers())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "source_type": "repo",
            "reader_used": "github_api",
            "status": "failed",
            "confidence": "low",
            "reason": f"github_api_failed:{type(exc).__name__}",
            "normalized_summary": "",
            "fields": {
                "repo": f"{owner}/{repo}",
            },
            "provider_attempts": [make_attempt("github_api", "failed", "low", f"github_api_failed:{type(exc).__name__}")],
        }

    readme_excerpt = ""
    try:
        readme_excerpt = clean_text(
            http_get_text(
                f"https://api.github.com/repos/{owner}/{repo}/readme",
                headers=github_headers("application/vnd.github.raw+json"),
            )
        )
    except Exception:
        readme_excerpt = ""

    description = clean_text(repo_data.get("description"))
    topics = repo_data.get("topics") or []
    language = clean_text(repo_data.get("language"))
    stars = repo_data.get("stargazers_count")
    archived = bool(repo_data.get("archived"))
    is_fork = bool(repo_data.get("fork"))
    site_name = clean_text(repo_data.get("owner", {}).get("login"))

    enough_signal = bool(description or readme_excerpt or topics or language)
    confidence = "high" if enough_signal else "medium"
    status = "enough" if enough_signal else "partial"
    reason = "github_repo_metadata_sufficient" if enough_signal else "github_repo_metadata_partial"

    summary_parts = [f"GitHub repo {owner}/{repo}"]
    if description:
        summary_parts.append(description)
    if language:
        summary_parts.append(f"language: {language}")
    if topics:
        summary_parts.append("topics: " + ", ".join(topics[:5]))
    if readme_excerpt:
        summary_parts.append(clip_text(readme_excerpt, 180))

    return {
        "source_type": "repo",
        "reader_used": "github_api",
        "status": status,
        "confidence": confidence,
        "reason": reason,
        "normalized_summary": clip_text(" — ".join(summary_parts), 280),
        "fields": {
            "repo": f"{owner}/{repo}",
            "description": clip_text(description, 240),
            "primary_language": language,
            "topics": topics[:8],
            "stars": stars,
            "archived": archived,
            "fork": is_fork,
            "site_name": site_name,
            "readme_excerpt": clip_text(readme_excerpt, 240),
        },
        "provider_attempts": [make_attempt("github_api", status, confidence, reason)],
    }


META_PATTERNS = {
    "title": [
        re.compile(r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)[\"']", re.I),
        re.compile(r"<title>(.*?)</title>", re.I | re.S),
    ],
    "description": [
        re.compile(r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"']([^\"']+)[\"']", re.I),
        re.compile(r"<meta[^>]+property=[\"']og:description[\"'][^>]+content=[\"']([^\"']+)[\"']", re.I),
    ],
    "author": [
        re.compile(r"<meta[^>]+name=[\"']author[\"'][^>]+content=[\"']([^\"']+)[\"']", re.I),
    ],
    "site_name": [
        re.compile(r"<meta[^>]+property=[\"']og:site_name[\"'][^>]+content=[\"']([^\"']+)[\"']", re.I),
    ],
}


def extract_html_meta(html: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for key, patterns in META_PATTERNS.items():
        for pattern in patterns:
            match = pattern.search(html)
            if match:
                meta[key] = clean_text(re.sub(r"<[^>]+>", " ", match.group(1)))
                break
    return meta


def read_from_fetch(url: str) -> dict[str, Any]:
    try:
        html = http_get_text(url, headers={"User-Agent": USER_AGENT})
    except (HTTPError, URLError, TimeoutError) as exc:
        return {
            "source_type": detect_source_type(url),
            "reader_used": "fetch_fetch",
            "status": "failed",
            "confidence": "low",
            "reason": f"fetch_failed:{type(exc).__name__}",
            "normalized_summary": "",
            "fields": {"title": "", "site_name": "", "author": "", "excerpt": "", "markdown_excerpt": "", "word_count_estimate": 0},
            "provider_attempts": [make_attempt("fetch_fetch", "failed", "low", f"fetch_failed:{type(exc).__name__}")],
        }

    meta = extract_html_meta(html)
    markdown_excerpt = ""
    if trafilatura is not None:
        try:
            markdown_excerpt = clean_text(
                trafilatura.extract(
                    html,
                    output_format="markdown",
                    include_comments=False,
                    include_tables=False,
                    include_links=False,
                )
                or ""
            )
        except Exception:
            markdown_excerpt = ""

    excerpt = meta.get("description") or markdown_excerpt
    word_count_estimate = len((markdown_excerpt or excerpt or "").split())
    source_type = detect_source_type(url)

    if meta.get("title") and (len(markdown_excerpt) >= 240 or len(excerpt) >= 140):
        status = "enough"
        confidence = "high"
        reason = "fetch_content_sufficient"
    elif meta.get("title") or excerpt:
        status = "partial"
        confidence = "medium" if excerpt else "low"
        reason = "fetch_content_partial"
    else:
        status = "failed"
        confidence = "low"
        reason = "fetch_content_empty"

    summary_parts = []
    if meta.get("title"):
        summary_parts.append(meta["title"])
    if meta.get("site_name"):
        summary_parts.append(f"source: {meta['site_name']}")
    if excerpt:
        summary_parts.append(clip_text(excerpt, 180))

    return {
        "source_type": source_type,
        "reader_used": "trafilatura" if markdown_excerpt else "fetch_fetch",
        "status": status,
        "confidence": confidence,
        "reason": reason,
        "normalized_summary": clip_text(" — ".join(summary_parts), 280),
        "fields": {
            "title": clean_text(meta.get("title")),
            "site_name": clean_text(meta.get("site_name")),
            "author": clean_text(meta.get("author")),
            "excerpt": clip_text(excerpt, 220),
            "markdown_excerpt": clip_text(markdown_excerpt, 220),
            "word_count_estimate": word_count_estimate,
        },
        "provider_attempts": [make_attempt("trafilatura" if markdown_excerpt else "fetch_fetch", status, confidence, reason)],
    }


def append_attempts(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    combined = dict(extra)
    combined_attempts = list(base.get("provider_attempts") or []) + list(extra.get("provider_attempts") or [])
    combined["provider_attempts"] = combined_attempts
    if "bookmark" not in combined and "bookmark" in base:
        combined["bookmark"] = base["bookmark"]
    return combined


def read_bookmark_context(bookmark: dict) -> dict[str, Any]:
    initial = read_from_karakeep_metadata(bookmark)
    url = initial["bookmark"]["url"]

    if initial["status"] == "enough":
        return initial

    github_result = read_from_github_api(url)
    if github_result is not None:
        combined = append_attempts(initial, github_result)
        combined["bookmark"] = initial["bookmark"]
        if github_result["status"] == "enough":
            return combined
        initial = combined

    fetch_result = read_from_fetch(url)
    combined = append_attempts(initial, fetch_result)
    combined["bookmark"] = initial["bookmark"]
    if fetch_result["status"] == "enough":
        return combined

    # Reserved layers: keep explicit attempt records even before implementation.
    combined["provider_attempts"] = list(combined.get("provider_attempts") or []) + [
        make_attempt("mcphub_tool", "failed", "low", "reserved_not_implemented"),
        make_attempt("playwriter", "failed", "low", "reserved_not_implemented"),
    ]

    if combined.get("status") != "enough":
        combined["status"] = fetch_result.get("status") or initial.get("status") or "failed"
        combined["confidence"] = fetch_result.get("confidence") or initial.get("confidence") or "low"
        combined["reason"] = fetch_result.get("reason") or initial.get("reason") or "reader_chain_incomplete"
        combined["reader_used"] = fetch_result.get("reader_used") or initial.get("reader_used")
        combined["source_type"] = fetch_result.get("source_type") or initial.get("source_type")
        combined["normalized_summary"] = fetch_result.get("normalized_summary") or initial.get("normalized_summary")
        combined["fields"] = fetch_result.get("fields") or initial.get("fields")

    return combined


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_read_bookmark(args) -> None:
    bookmark = get_client().get_bookmark(args.bookmark_id)
    if not isinstance(bookmark, dict):
        raise RuntimeError(f"bookmark not found: {args.bookmark_id}")
    print_json(read_bookmark_context(bookmark))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read one bookmark through the read-link provider chain")
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_bookmark = subparsers.add_parser("read-bookmark", help="Read one bookmark by id")
    read_bookmark.add_argument("--bookmark-id", required=True)
    read_bookmark.set_defaults(func=cmd_read_bookmark)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
