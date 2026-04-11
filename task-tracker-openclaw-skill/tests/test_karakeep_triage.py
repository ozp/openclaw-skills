from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import karakeep_triage


def test_get_list_by_name_accepts_wrapped_lists_payload():
    class DummyClient:
        def list_lists(self):
            return {
                "lists": [
                    {"id": "todo-1", "name": "Todo "},
                    {"id": "review-1", "name": "Review"},
                ]
            }

    result = karakeep_triage.get_list_by_name(DummyClient(), "Todo")

    assert result == {"id": "todo-1", "name": "Todo "}


def test_match_existing_task_prefers_exact_url_in_task_title():
    bookmark = {
        "id": "bm-1",
        "title": "Auto-Analyst",
        "content": {"url": "https://www.autoanalyst.ai/"},
        "note": "",
    }
    tasks = [
        {
            "title": "https://www.autoanalyst.ai/ — sistema de análise de dados relevante",
            "area": "raw-demand",
            "section": "today",
            "done": False,
            "raw_line": "- [ ] **https://www.autoanalyst.ai/ — sistema de análise de dados relevante** area:: raw-demand",
            "note_meta": [],
        },
        {
            "title": "Triage data-analysis system candidates (autoanalyst, minusx, ai-data-science-team)",
            "area": "triage",
            "section": "q2",
            "done": False,
            "raw_line": "- [ ] **Triage data-analysis system candidates (autoanalyst, minusx, ai-data-science-team)** area:: triage",
            "note_meta": [],
        },
    ]

    result = karakeep_triage.match_existing_task(bookmark, tasks=tasks)

    assert result.mode == "complement_existing"
    assert result.confidence in {"exact", "strong"}
    assert result.task["title"] == "https://www.autoanalyst.ai/ — sistema de análise de dados relevante"


def test_classify_bookmark_routes_unmatched_items_to_create_new_when_semantic_disabled(monkeypatch):
    bookmark = {
        "id": "bm-2",
        "title": "Unclear link",
        "content": {"url": "https://example.com/unclear"},
        "note": "",
    }

    monkeypatch.setattr(
        karakeep_triage,
        "read_bookmark_context",
        lambda bm: {
            "source_type": "article",
            "reader_used": "karakeep",
            "status": "partial",
            "confidence": "low",
            "reason": "thin",
            "normalized_summary": "",
            "fields": {},
            "provider_attempts": [],
        },
    )

    payload = karakeep_triage.classify_bookmark_payload(bookmark, tasks=[], semantic_enabled=False)

    assert payload["classification"]["match_mode"] == "create_new"
    assert payload["classification"]["destination_list"] == "Incorporated"
    assert payload["classification"]["new_task_title"].startswith("https://example.com/unclear")


def test_finalize_decision_biases_disagreement_to_review():
    bookmark = {
        "id": "bm-3",
        "title": "Typst",
        "content": {"url": "https://github.com/typst/typst"},
        "note": "",
    }
    matched_task = {
        "title": "Typst tooling evaluation",
        "area": "triage",
        "section": "q2",
    }
    deterministic = karakeep_triage.MatchResult(
        mode="complement_existing",
        confidence="strong",
        reason="unique_high_overlap_match",
        task=matched_task,
        score=0.91,
    )
    semantic = {
        "enabled": True,
        "status": "ok",
        "model": "modelrelay/auto-fastest",
        "reason": "semantic_result_available",
        "route": "review",
        "confidence": "high",
        "matched_task_title": None,
        "rationale": "Ambiguous relationship",
        "evidence": [],
    }
    read_payload = {
        "source_type": "repo",
        "reader_used": "github_api",
        "status": "enough",
        "confidence": "high",
        "reason": "github_repo_metadata_sufficient",
        "normalized_summary": "GitHub repo typst/typst",
    }

    classification, matched = karakeep_triage.finalize_decision(deterministic, semantic, bookmark, read_payload)

    assert classification["match_mode"] == "review"
    assert classification["destination_list"] == "Review"
    assert classification["decision_source"] == "conflict_to_review"
    assert matched is None


def test_merge_operational_note_preserves_human_lines_and_rewrites_operational_block():
    existing = "manual note\nsummary: old\ntask-ref: old-ref"
    read_payload = {
        "reader_used": "github_api",
        "status": "enough",
        "source_type": "repo",
        "normalized_summary": "A long enough repo summary",
    }

    merged = karakeep_triage.merge_operational_note(existing, "task-ref: new-ref", read_payload)

    assert "manual note" in merged
    assert "task-ref: new-ref" in merged
    assert "read-source: github_api" in merged
    assert "summary: A long enough repo summary" in merged
    assert "old-ref" not in merged
