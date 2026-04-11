from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import read_link


def test_read_from_karakeep_metadata_marks_rich_metadata_as_enough():
    bookmark = {
        "id": "bm-rich",
        "url": "https://example.com/article",
        "title": "Useful article about task routing",
        "description": "This article explains how to classify incoming links, compare them against existing queues, and route them safely with explicit fallback policies.",
        "author": "Example Author",
        "publisher": "Example Docs",
        "note": "human context",
    }

    payload = read_link.read_from_karakeep_metadata(bookmark)

    assert payload["status"] == "enough"
    assert payload["reader_used"] == "karakeep"
    assert payload["confidence"] == "high"


def test_parse_github_repo_extracts_owner_and_repo():
    assert read_link.parse_github_repo("https://github.com/open-webui/open-terminal") == ("open-webui", "open-terminal")
    assert read_link.parse_github_repo("https://example.com/foo/bar") is None


def test_read_bookmark_context_falls_back_when_initial_metadata_is_thin(monkeypatch):
    bookmark = {
        "id": "bm-thin",
        "url": "https://example.com/docs/page",
        "title": "Page Not Found",
        "description": "",
        "note": "",
    }

    def fake_fetch(url):
        return {
            "source_type": "docs",
            "reader_used": "fetch_fetch",
            "status": "enough",
            "confidence": "high",
            "reason": "fetch_content_sufficient",
            "normalized_summary": "Fetched docs summary",
            "fields": {"title": "Docs page"},
            "provider_attempts": [read_link.make_attempt("fetch_fetch", "enough", "high", "fetch_content_sufficient")],
        }

    monkeypatch.setattr(read_link, "read_from_fetch", fake_fetch)
    monkeypatch.setattr(read_link, "read_from_github_api", lambda url: None)

    payload = read_link.read_bookmark_context(bookmark)

    assert payload["reader_used"] == "fetch_fetch"
    assert payload["status"] == "enough"
    assert len(payload["provider_attempts"]) >= 2
