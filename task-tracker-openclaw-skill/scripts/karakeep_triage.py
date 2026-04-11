#!/usr/bin/env python3
"""
karakeep_triage.py — bounded inbox review and routing for Karakeep Phase 3 / Option 2.

Current behavior:
- inspect a small inbox slice from Karakeep list `Todo`
- run `read-link` before classification
- compute deterministic baseline routing
- compute semantic/model-assisted recommendation through LiteLLM/ModelRelay
- keep deterministic fallback and bias disagreements toward Review
- move bookmarks out of `Todo` into `Incorporated` or `Review`
- keep mutation narrow and explicit (`--apply` required)

Commands:
  python3 karakeep_triage.py review-inbox --limit 5
  python3 karakeep_triage.py classify-bookmark --bookmark-id BOOKMARK_ID
  python3 karakeep_triage.py route-item --bookmark-id BOOKMARK_ID --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).parent))

from capture import TASKS_SCRIPT, detect_area, slugify_task_ref
from karakeep import get_client
from karakeep_links import extract_bookmark_ids
from read_link import clip_text, read_bookmark_context
from utils import get_tasks_file, load_tasks

TODO_LIST_NAME = "Todo"
INCORPORATED_LIST_NAME = "Incorporated"
REVIEW_LIST_NAME = "Review"
DEFAULT_LIMIT = 5
DEFAULT_LITELLM_BASE_URL = "http://localhost:4000/v1"
DEFAULT_SEMANTIC_MODEL = "modelrelay/auto-fastest"
LITELLM_ENV_FILE = Path("/home/ozp/.config/env/.env")

# --- Mission Control integration ---
MC_BASE_URL = "http://localhost:8001"
MC_ENV_FILE = Path("/home/ozp/code/openclaw-mission-control/backend/.env")
MC_INBOX_BOARD_ID = "ba06d446-93ce-484a-85eb-9a18ca1104d1"  # External Triage
MC_HIGH_CONFIDENCE_THRESHOLD = "high"

# area → MC board ID mapping
MC_AREA_BOARD_MAP: dict[str, str] = {
    "triage": "ba06d446-93ce-484a-85eb-9a18ca1104d1",       # External Triage
    "agents": "40851a1e-fe67-460c-889f-eba0d8649b1a",       # Agent Architecture
    "security": "ee065313-414e-4113-83c1-2b3eb3f30d8e",     # Governance & Gates
    "models": "76f10c1e-6f4e-4d42-b2dc-d5cc1fe6c926",       # Models & Cost
    "openclaw": "0f302d65-dd09-4fd3-848f-8989636d9334",     # Infrastructure Baseline
    "backup": "0f302d65-dd09-4fd3-848f-8989636d9334",       # Infrastructure Baseline
    "bibliography": "78fad92f-6aa2-446f-9120-f30c70ce9cd7", # Knowledge & RAG
    "knowledge-pipeline": "78fad92f-6aa2-446f-9120-f30c70ce9cd7",  # Knowledge & RAG
    "parsing": "78fad92f-6aa2-446f-9120-f30c70ce9cd7",     # Knowledge & RAG
    "rag": "78fad92f-6aa2-446f-9120-f30c70ce9cd7",         # Knowledge & RAG
    "governance": "ee065313-414e-4113-83c1-2b3eb3f30d8e",   # Governance & Gates
    "planning": "ab429505-87ff-4373-9991-8ff066f82d00",     # Experimental
    "claude-code": "40851a1e-fe67-460c-889f-eba0d8649b1a",  # Agent Architecture
    "integrations": "7aa5ee71-938f-4b61-9e61-603a731b2753", # Integrations
    "unip": "2df94061-0c2b-4e7e-8a64-4e3a2b3591eb",       # UNIP Operations
    "prompts": "7478d357-f8da-4426-8343-464eb602ff9b",     # Prompts & Docs
    "docs": "7478d357-f8da-4426-8343-464eb602ff9b",        # Prompts & Docs
    "experimental": "ab429505-87ff-4373-9991-8ff066f82d00", # Experimental
}
OPERATIONAL_NOTE_PREFIXES = (
    "task-ref:",
    "read-source:",
    "read-status:",
    "content-type:",
    "summary:",
    "relevance:",
    "llm-type:",
    "user-hint:",
)
OPERATIONAL_EMOJI_PREFIXES = ("📋", "💡", "↪", "➕", "🔎")

# --- Karakeep rich metadata extraction ---

KARAKEEP_BASE_URL = os.getenv("KARAKEEP_API_ADDR", "http://localhost:3030").rstrip("/")


def extract_karakeep_rich_metadata(bookmark: dict) -> dict:
    """Extract AI tags, screenshot ref, author, publisher, and crawled content from bookmark."""
    content = bookmark.get("content") or {}
    assets = bookmark.get("assets") or []

    ai_tags = [t["name"] for t in bookmark.get("tags", []) if t.get("attachedBy") == "ai" and t.get("name")]

    screenshot_asset_id = content.get("screenshotAssetId")
    banner_image_url = content.get("imageUrl")
    screenshot_url = f"{KARAKEEP_BASE_URL}/api/assets/{screenshot_asset_id}" if screenshot_asset_id else None

    html_asset = next((a for a in assets if a.get("assetType") == "linkHtmlContent"), None)
    crawled_content_present = html_asset is not None or content.get("htmlContent")

    return {
        "ai_tags": ai_tags,
        "author": content.get("author"),
        "publisher": content.get("publisher"),
        "meta_description": content.get("description"),
        "screenshot_url": screenshot_url,
        "banner_image_url": banner_image_url,
        "has_crawled_content": crawled_content_present,
        "karakeep_summary": bookmark.get("summary"),
        "source": bookmark.get("source"),
        "bookmark_url": f"{KARAKEEP_BASE_URL}/dashboard/preview/{bookmark.get('id', '')}",
    }


# --- User instruction extraction ---

def extract_user_instruction(bookmark: dict) -> str:
    """Extract human-written note lines (non-operational) from a bookmark."""
    note = (bookmark.get("note") or "").strip()
    if not note:
        return ""
    lines = [
        line.strip()
        for line in note.splitlines()
        if line.strip()
        and not any(line.strip().startswith(prefix) for prefix in OPERATIONAL_NOTE_PREFIXES)
        and not any(line.strip().startswith(emoji) for emoji in OPERATIONAL_EMOJI_PREFIXES)
    ]
    return " ".join(lines).strip()


# --- Mission Control API helpers ---

def get_mc_token() -> str | None:
    """Read LOCAL_AUTH_TOKEN from MC backend .env."""
    return read_env_key(MC_ENV_FILE, "LOCAL_AUTH_TOKEN")


def mc_api_call(method: str, path: str, token: str, body: dict | None = None) -> dict:
    """Make an authenticated call to MC API. Returns parsed JSON response."""
    data = json.dumps(body).encode("utf-8") if body else None
    req = Request(
        f"{MC_BASE_URL}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method=method,
    )
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def route_to_mc_board(classification: dict, llm_summary: dict | None = None) -> tuple[str, str]:
    """Determine MC board ID and reason for routing.

    Returns (board_id, reason).
    High confidence + known area → direct board.
    Everything else → External Triage inbox (B4).
    """
    confidence = classification.get("confidence", "low")
    area = classification.get("area", "")
    match_mode = classification.get("match_mode", "review")

    # Reviews always go to inbox
    if match_mode == "review":
        return MC_INBOX_BOARD_ID, "review_mode"

    # High confidence + known area → direct board
    if confidence in ("high", "exact", "strong", "forced") and area in MC_AREA_BOARD_MAP:
        return MC_AREA_BOARD_MAP[area], f"high_confidence_direct:{area}"

    # Medium confidence + known area + strong LLM hint → direct board
    if confidence == "medium" and llm_summary and llm_summary.get("status") == "ok":
        if llm_summary.get("relevance_hint") == "high" and area in MC_AREA_BOARD_MAP:
            return MC_AREA_BOARD_MAP[area], f"medium_plus_llm_high:{area}"

    # Default: inbox for human review
    return MC_INBOX_BOARD_ID, f"confidence_{confidence}_no_direct_match"


def find_mc_task_by_source(board_id: str, bookmark_id: str, token: str) -> dict | None:
    """Search for an existing MC task by import_source custom field.

    Scans tasks in the given board for custom_field_values.import_source
    matching 'karakeep:{bookmark_id}'. Returns the first match or None.
    """
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


def create_mc_task(
    classification: dict,
    bookmark: dict,
    read_payload: dict,
    llm_summary: dict | None = None,
    user_instruction: str = "",
    rich_metadata: dict | None = None,
) -> dict:
    """Create or update a task in Mission Control via API with rich Karakeep metadata.

    If an existing task with matching import_source is found on the target board,
    it is updated (PUT) instead of creating a new one (POST). This prevents
    duplicates when reprocessing bookmarks.

    Returns {status, task_id, board_id, board_name, reason} or {status: error, ...}.
    """
    token = get_mc_token()
    if not token:
        return {"status": "error", "reason": "mc_token_missing"}

    board_id, reason = route_to_mc_board(classification, llm_summary)

    title = bookmark_title(bookmark)
    url = bookmark_url(bookmark)
    task_title = f"{url} — {title}" if title and title != url else (url or title or "Untitled bookmark")
    rich = rich_metadata or {}
    ai_tags = rich.get("ai_tags", [])

    # Build rich description
    desc_parts = []

    # 1. Contextual judgment from LLM
    if llm_summary and llm_summary.get("status") == "ok":
        if llm_summary.get("one_line_summary"):
            desc_parts.append(llm_summary["one_line_summary"])
        if llm_summary.get("why"):
            desc_parts.append(f"**Why this matters:** {llm_summary['why']}")
    elif read_payload.get("normalized_summary"):
        desc_parts.append(read_payload["normalized_summary"])

    # 2. Karakeep AI tags
    if ai_tags:
        desc_parts.append(f"**Karakeep tags:** {', '.join(ai_tags)}")

    # 3. User instruction
    if user_instruction:
        desc_parts.append(f"**User note:** {user_instruction}")

    # 4. Source metadata
    source_meta = []
    if rich.get("author"):
        source_meta.append(f"Author: {rich['author']}")
    if rich.get("publisher"):
        source_meta.append(f"Publisher: {rich['publisher']}")
    if source_meta:
        desc_parts.append(" | ".join(source_meta))

    # 5. Screenshot and bookmark links
    link_parts = []
    if rich.get("screenshot_url"):
        link_parts.append(f"[Screenshot]({rich['screenshot_url']})")
    if rich.get("bookmark_url"):
        link_parts.append(f"[Karakeep]({rich['bookmark_url']})")
    if link_parts:
        desc_parts.append(" | ".join(link_parts))

    # 6. Routing info
    desc_parts.append(f"Karakeep ID: {bookmark.get('id', 'unknown')}")
    desc_parts.append(f"Routing: {reason}")

    description = "\n\n".join(desc_parts) if desc_parts else None

    # LLM-generated tags for MC
    mc_tags = []
    if llm_summary and llm_summary.get("status") == "ok" and llm_summary.get("tags"):
        mc_tags = llm_summary["tags"][:4]
    elif ai_tags:
        mc_tags = [t.lower().replace(" ", "-")[:30] for t in ai_tags[:4]]

    body = {
        "title": task_title,
        "description": description,
        "status": "inbox",
        "priority": classification.get("confidence", "low") if classification.get("confidence") in ("high", "exact", "strong") else "low",
        "custom_field_values": {
            "area": classification.get("area", ""),
            "estimate": classification.get("estimate", "simple"),
            "type": classification.get("task_type", "link-intake"),
            "import_source": f"karakeep:{bookmark.get('id', 'unknown')}",
            "note": user_instruction if user_instruction else None,
        },
    }

    # Dedup: check if a task with this import_source already exists
    bookmark_id = bookmark.get("id", "unknown")
    existing_task = find_mc_task_by_source(board_id, bookmark_id, token)

    is_update = existing_task is not None
    task_id = existing_task["id"] if is_update else None

    try:
        if is_update:
            # Update existing task via board-scoped endpoint
            result = mc_api_call("PATCH", f"/api/v1/boards/{board_id}/tasks/{task_id}", token, body)
        else:
            # Create new task
            result = mc_api_call("POST", f"/api/v1/boards/{board_id}/tasks", token, body)
            task_id = result.get("id")
    except Exception as exc:
        return {"status": "error", "reason": f"mc_api_failed:{type(exc).__name__}:{exc}", "board_id": board_id}

    # Attach tags to MC task if any
    task_id = task_id or result.get("id")
    if task_id and mc_tags:
        try:
            # MC uses tag names; create or find them
            tag_body = {"tags": mc_tags}
            mc_api_call("PUT", f"/api/v1/tasks/{task_id}/tags", token, tag_body)
        except Exception:
            pass  # Non-critical: tags are enrichment, not essential

    return {
        "status": "ok",
        "task_id": task_id,
        "board_id": board_id,
        "board_name": next(
            (name for name, bid in {
                k: v for k, v in [
                    ("External Triage", MC_INBOX_BOARD_ID),
                    ("Agent Architecture", "40851a1e-fe67-460c-889f-eba0d8649b1a"),
                    ("Governance & Gates", "ee065313-414e-4113-83c1-2b3eb3f30d8e"),
                    ("Models & Cost", "76f10c1e-6f4e-4d42-b2dc-d5cc1fe6c926"),
                    ("Infrastructure Baseline", "0f302d65-dd09-4fd3-848f-8989636d9334"),
                    ("Knowledge & RAG", "78fad92f-6aa2-446f-9120-f30c70ce9cd7"),
                    ("Integrations", "7aa5ee71-938f-4b61-9e61-603a731b2753"),
                    ("UNIP Operations", "2df94061-0c2b-4e7e-8a64-4e3a2b3591eb"),
                    ("Prompts & Docs", "7478d357-f8da-4426-8343-464eb602ff9b"),
                    ("Experimental", "ab429505-87ff-4373-9991-8ff066f82d00"),
                ]
            }.items() if bid == board_id)
        ),
        "reason": reason,
        "task_title": task_title,
        "mc_tags": mc_tags,
        "dedup": "updated" if is_update else "created",
    }


# --- Environment context for semantic enrichment ---

ENVIRONMENT_CONTEXT = """\
## Active infrastructure
- OpenClaw gateway on localhost:18789, agents: main, karakeep, sentinel
- LiteLLM proxy on localhost:4000 (multi-model routing)
- Karakeep on localhost:3030 (bookmark management + AI tagging)
- MCPHub on localhost:3000 (24 MCP servers)
- Mission Control on localhost:3100/8001 (task management, 10 boards)
- BrowserOS on localhost:9000 (Playwright-based, CDP on 9024)
- ModelRelay on localhost:7352 (free model auto-routing)

## Key decisions already made
- Karakeep stays as pure OpenClaw agent (Opção A), writes to MC via API
- MC is destination of record for tasks (221 tasks across 10 boards)
- Sub-agent default model: GLM-5 via Z.AI (cost discipline)
- BrowserOS has Playwright — web scraping/interaction tooling already available
- Serena available for source-code consultation
- Tool adoption gated: no installs without explicit triage

## Active work areas
- triage: evaluating external tools/repos for environment fit
- agents: architecture and design of OpenClaw agent fleet
- integrations: connecting services (Karakeep↔MC, etc.)
- openclaw: gateway config, agent workspaces, cron jobs
- models: cost routing, provider fallbacks, benchmarking
- knowledge-pipeline: RAG, parsing, document extraction
- security: exec approvals, audit, host hardening
- unip: university administrative tasks (MEC forms, student groups)

## Current program phase
Post-migration: MC has 221 tasks, karakeep pipeline connected.
Priority: quality of triage output, not volume.
Each bookmark analysis should explain WHY it matters (or doesn't) for this specific environment.
"""


# --- ModelRelay summarization step ---

def summarize_via_modelrelay(
    bookmark: dict,
    read_payload: dict,
    user_instruction: str,
    model: str = DEFAULT_SEMANTIC_MODEL,
) -> dict[str, Any]:
    """Call ModelRelay to produce an enriched summary + pre-classification hint."""
    key = get_litellm_key()
    if not key:
        return {"status": "skipped", "reason": "no_litellm_key"}

    title = bookmark_title(bookmark)
    url = bookmark_url(bookmark)
    source_type = read_payload.get("source_type", "")
    raw_summary = read_payload.get("normalized_summary", "")
    fields = read_payload.get("fields") or {}
    description = fields.get("description", "")
    readme = fields.get("readme_excerpt", "")
    topics = fields.get("topics") or []
    language = fields.get("primary_language", "")

    # Extract rich Karakeep metadata
    rich_meta = extract_karakeep_rich_metadata(bookmark)
    ai_tags = rich_meta.get("ai_tags", [])
    author = rich_meta.get("author")
    publisher = rich_meta.get("publisher")
    meta_desc = rich_meta.get("meta_description")
    kk_summary = rich_meta.get("karakeep_summary")

    content_parts = [f"Title: {title}", f"URL: {url}"]
    if author:
        content_parts.append(f"Author: {author}")
    if publisher:
        content_parts.append(f"Publisher: {publisher}")
    if source_type:
        content_parts.append(f"Type: {source_type}")
    if meta_desc:
        content_parts.append(f"Meta description: {clip_text(meta_desc, 200)}")
    if description:
        content_parts.append(f"Page description: {clip_text(description, 200)}")
    if readme:
        content_parts.append(f"README excerpt: {clip_text(readme, 300)}")
    if topics:
        content_parts.append(f"Topics: {', '.join(str(t) for t in topics[:8])}")
    if language:
        content_parts.append(f"Language: {language}")
    if raw_summary:
        content_parts.append(f"Fetch summary: {clip_text(raw_summary, 200)}")
    if kk_summary:
        content_parts.append(f"Karakeep AI summary: {clip_text(kk_summary, 200)}")
    if ai_tags:
        content_parts.append(f"AI-generated tags: {', '.join(ai_tags)}")
    if user_instruction:
        content_parts.append(f"User instruction: {user_instruction}")

    system_prompt = (
        "You analyze a saved bookmark for a task-routing system with a specific technical environment. "
        "You MUST produce a contextual judgment — explain WHY this is or isn't relevant for THIS environment, "
        "not just classify what it is.\n\n"
        "Environment context:\n" + ENVIRONMENT_CONTEXT + "\n\n"
        "Return JSON only with these fields:\n"
        "  content_type: repo | tool | service | library | article | docs | tutorial | other\n"
        "  one_line_summary: max 120 chars, factual description of what this IS\n"
        "  relevance_hint: high (directly useful now), medium (relevant to known areas), "
        "low (tangential or unclear fit), review (cannot determine)\n"
        "  relevant_areas: list of 1-3 area tags from: triage, security, agents, models, openclaw, "
        "backup, bibliography, knowledge-pipeline, parsing, rag, governance, planning, "
        "claude-code, integrations, unip, experimental\n"
        "  why: 2-3 sentences of CONTEXTUAL judgment — reference specific tools, decisions, or gaps "
        "in the environment that make this relevant or not. Do NOT just paraphrase the description.\n"
        "  tags: list of 2-4 concise lowercase tags for MC task categorization (e.g. web-scraping, rag, cost-optimization)\n"
        "Be specific. Reference the environment. Avoid generic statements like 'could be useful'."
    )

    request_body = json.dumps({
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(content_parts)},
        ],
        "response_format": {"type": "json_object"},
    }).encode("utf-8")

    request = Request(
        f"{DEFAULT_LITELLM_BASE_URL}/chat/completions",
        data=request_body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
        parsed = extract_json_object(content)
    except Exception as exc:
        return {"status": "failed", "reason": f"summarize_error:{type(exc).__name__}:{exc}"}

    return {
        "status": "ok",
        "content_type": parsed.get("content_type", "other"),
        "one_line_summary": clip_text(parsed.get("one_line_summary", ""), 140),
        "relevance_hint": parsed.get("relevance_hint", "review"),
        "relevant_areas": parsed.get("relevant_areas", []),
        "tags": parsed.get("tags", [])[:4],
        "why": parsed.get("why", ""),
        "model": model,
    }


@dataclass
class MatchResult:
    mode: str
    confidence: str
    reason: str
    task: dict | None = None
    score: float = 0.0
    alternatives: list[dict] | None = None


def normalize_name(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def list_name_equals(actual: str | None, expected: str) -> bool:
    return normalize_name(actual) == normalize_name(expected)


def _coerce_lists_payload(payload) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("lists"), list):
        return payload["lists"]
    return []


def get_list_by_name(client, name: str) -> dict | None:
    lists = _coerce_lists_payload(client.list_lists())
    for item in lists:
        if list_name_equals(item.get("name"), name):
            return item
    return None


def ensure_list(client, name: str, icon: str) -> dict:
    existing = get_list_by_name(client, name)
    if existing:
        return existing
    created = client.create_list(name, icon=icon)
    if not isinstance(created, dict) or not created.get("id"):
        raise RuntimeError(f"failed to create Karakeep list: {name}")
    return created


def get_bookmarks_for_list(client, list_name: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    list_item = get_list_by_name(client, list_name)
    if not list_item:
        raise RuntimeError(f"Karakeep list not found: {list_name}")

    result = client.list_list_bookmarks(list_item["id"])
    bookmarks = result.get("bookmarks") if isinstance(result, dict) else None
    if not isinstance(bookmarks, list):
        return []
    return bookmarks[:limit]


def get_open_tasks() -> list[dict]:
    _, tasks_data = load_tasks(personal=False)
    return [task for task in tasks_data.get("all", []) if not task.get("done")]


def bookmark_url(bookmark: dict) -> str:
    content = bookmark.get("content") or {}
    return bookmark.get("url") or content.get("url") or ""


def bookmark_title(bookmark: dict) -> str:
    content = bookmark.get("content") or {}
    return bookmark.get("title") or content.get("title") or bookmark_url(bookmark)


def bookmark_note(bookmark: dict) -> str:
    return (bookmark.get("note") or "").strip()


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", (text or "").lower())
        if token not in {"http", "https", "www", "com", "org", "github", "openclaw"}
    }


def bookmark_text(bookmark: dict) -> str:
    parts = [bookmark_title(bookmark), bookmark_url(bookmark), bookmark_note(bookmark)]
    return " ".join(part for part in parts if part)


def infer_area(bookmark: dict, read_payload: dict | None = None) -> str:
    if read_payload:
        source_type = normalize_name(read_payload.get("source_type"))
        summary = (read_payload.get("normalized_summary") or "").lower()
        if source_type == "repo":
            return "triage"
        if source_type in {"article", "pdf"} and any(token in summary for token in ["paper", "research", "study", "artigo"]):
            return "bibliography"
    return detect_area(bookmark_text(bookmark))


def infer_estimate(bookmark: dict, read_payload: dict | None = None) -> str:
    text = bookmark_text(bookmark).lower()
    url = bookmark_url(bookmark).lower()
    source_type = normalize_name((read_payload or {}).get("source_type"))
    if source_type in {"repo", "docs"}:
        return "complex"
    if any(key in text for key in ["github.com", "agent", "mcp", "plugin", "integration", "workflow", "orchestr", "architecture"]):
        return "complex"
    if any(key in url for key in ["github.com", "/tree/", "/issues", "/pull/"]):
        return "complex"
    if any(key in text for key in ["article", "artigo", "paper", "docs", "documentation", "guide"]):
        return "simple"
    return "simple"


def infer_task_type(bookmark: dict, read_payload: dict | None = None) -> str:
    source_type = normalize_name((read_payload or {}).get("source_type"))
    if source_type == "repo":
        return "triage"
    if source_type in {"article", "pdf"}:
        return "bibliography"
    area = infer_area(bookmark, read_payload=read_payload)
    if area in {"triage", "agents", "models", "backup", "bibliography"}:
        return area
    return "link-intake"


def build_candidate_title(bookmark: dict) -> str:
    url = bookmark_url(bookmark)
    title = bookmark_title(bookmark)
    if title and title != url:
        return f"{url} — {title}"
    return url or title or "Untitled bookmark"


def score_task_match(task: dict, bookmark: dict, read_payload: dict | None = None) -> float:
    task_title = (task.get("title") or "").lower()
    url = bookmark_url(bookmark).strip().lower()
    title = (bookmark_title(bookmark) or "").lower()
    summary = ((read_payload or {}).get("normalized_summary") or "").lower()

    if url and url in task_title:
        return 1.0

    bookmark_tokens = tokenize(bookmark_text(bookmark)) | tokenize(summary)
    task_tokens = tokenize(task.get("title") or "")
    if not bookmark_tokens or not task_tokens:
        return 0.0

    overlap = len(bookmark_tokens & task_tokens)
    score = overlap / max(1, len(bookmark_tokens))

    task_area = normalize_name(task.get("area"))
    inferred_area = normalize_name(infer_area(bookmark, read_payload=read_payload))
    if task_area and inferred_area and task_area == inferred_area:
        score += 0.15

    if title and title in task_title:
        score += 0.25

    if summary and any(token in task_title for token in tokenize(summary)):
        score += 0.10

    return round(min(score, 1.0), 4)


def shortlist_task_candidates(bookmark: dict, tasks: list[dict], read_payload: dict | None = None, limit: int = 5) -> list[dict]:
    scored = []
    bookmark_id = bookmark.get("id")
    for task in tasks:
        score = score_task_match(task, bookmark, read_payload=read_payload)
        if bookmark_id and bookmark_id in extract_bookmark_ids(task):
            score = 1.0
        scored.append({
            "title": task.get("title"),
            "area": task.get("area"),
            "section": task.get("section"),
            "score": score,
            "task": task,
        })
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


def match_existing_task(bookmark: dict, tasks: list[dict] | None = None, read_payload: dict | None = None) -> MatchResult:
    tasks = tasks or get_open_tasks()
    bookmark_id = bookmark.get("id")
    linked = []
    for task in tasks:
        if bookmark_id and bookmark_id in extract_bookmark_ids(task):
            linked.append(task)
    if len(linked) == 1:
        return MatchResult(
            mode="complement_existing",
            confidence="exact",
            reason="bookmark_already_linked_to_task",
            task=linked[0],
            score=1.0,
        )
    if len(linked) > 1:
        return MatchResult(
            mode="review",
            confidence="conflict",
            reason="bookmark_linked_to_multiple_tasks",
            alternatives=[{"title": task.get("title"), "area": task.get("area")} for task in linked],
        )

    scored = []
    for task in tasks:
        score = score_task_match(task, bookmark, read_payload=read_payload)
        if score > 0:
            scored.append((score, task))
    scored.sort(key=lambda item: item[0], reverse=True)

    if not scored:
        return MatchResult(
            mode="create_new",
            confidence="none",
            reason="no_direct_task_match",
        )

    top_score, top_task = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0

    if top_score >= 0.85:
        return MatchResult(
            mode="complement_existing",
            confidence="strong",
            reason="unique_high_overlap_match",
            task=top_task,
            score=top_score,
        )

    if top_score >= 0.60 and (top_score - second_score) >= 0.20:
        return MatchResult(
            mode="complement_existing",
            confidence="medium",
            reason="unique_direct_match",
            task=top_task,
            score=top_score,
        )

    return MatchResult(
        mode="review",
        confidence="ambiguous",
        reason="match_not_confident_enough",
        score=top_score,
        alternatives=[
            {
                "title": task.get("title"),
                "area": task.get("area"),
                "score": score,
            }
            for score, task in scored[:3]
        ],
    )


def read_env_key(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def get_litellm_key() -> str | None:
    return read_env_key(LITELLM_ENV_FILE, "LITELLM_MASTER_KEY")


def extract_json_object(text: str) -> dict[str, Any]:
    payload = text.strip()
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", payload, re.S)
    if not match:
        raise ValueError("semantic classifier did not return JSON")
    return json.loads(match.group(0))


def candidate_titles(candidates: list[dict]) -> set[str]:
    return {candidate.get("title") for candidate in candidates if candidate.get("title")}


def call_semantic_classifier(
    bookmark: dict,
    read_payload: dict,
    deterministic: MatchResult,
    tasks: list[dict],
    model: str = DEFAULT_SEMANTIC_MODEL,
    llm_summary: dict | None = None,
    user_instruction: str = "",
) -> dict[str, Any]:
    key = get_litellm_key()
    if not key:
        return {
            "enabled": True,
            "status": "failed",
            "model": model,
            "reason": "litellm_key_missing",
            "route": None,
            "confidence": "low",
            "matched_task_title": None,
            "rationale": "",
            "evidence": [],
        }

    candidates = shortlist_task_candidates(bookmark, tasks, read_payload=read_payload, limit=5)
    candidate_view = [
        {
            "title": candidate.get("title"),
            "area": candidate.get("area"),
            "section": candidate.get("section"),
            "score": candidate.get("score"),
        }
        for candidate in candidates
    ]

    system_prompt = (
        "You classify one saved bookmark for a task-routing workflow. "
        "Return JSON only. Be conservative. If evidence is weak or ambiguous, choose review. "
        "Allowed routes: complement_existing, create_new, review. "
        "If route is complement_existing, matched_task_title must exactly match one candidate title. "
        "Confidence must be one of: high, medium, low.\n\n"
        "Environment context:\n" + ENVIRONMENT_CONTEXT
    )

    # Build enriched user payload
    bookmark_info = {
        "id": bookmark.get("id"),
        "title": bookmark_title(bookmark),
        "url": bookmark_url(bookmark),
        "note": clip_text(bookmark_note(bookmark), 200),
    }
    read_info = {
        "source_type": read_payload.get("source_type"),
        "reader_used": read_payload.get("reader_used"),
        "status": read_payload.get("status"),
        "confidence": read_payload.get("confidence"),
        "reason": read_payload.get("reason"),
        "normalized_summary": clip_text(read_payload.get("normalized_summary"), 240),
        "fields": read_payload.get("fields"),
    }

    user_payload: dict[str, Any] = {
        "bookmark": bookmark_info,
        "read_link": read_info,
        "candidate_tasks": candidate_view,
        "deterministic_baseline": {
            "route": deterministic.mode,
            "confidence": deterministic.confidence,
            "reason": deterministic.reason,
            "matched_task_title": deterministic.task.get("title") if deterministic.task else None,
        },
    }

    # Enrich with LLM-generated summary if available
    if llm_summary and llm_summary.get("status") == "ok":
        user_payload["llm_analysis"] = {
            "content_type": llm_summary.get("content_type"),
            "one_line_summary": llm_summary.get("one_line_summary"),
            "relevance_hint": llm_summary.get("relevance_hint"),
            "relevant_areas": llm_summary.get("relevant_areas"),
            "why": llm_summary.get("why"),
        }

    # Include user instruction if present
    if user_instruction:
        user_payload["user_instruction"] = user_instruction

    user_payload["json_schema"] = {
        "route": "complement_existing|create_new|review",
        "confidence": "high|medium|low",
        "matched_task_title": "exact candidate title or null",
        "rationale": "short evidence-grounded explanation",
        "evidence": ["short bullet", "short bullet"],
    }

    request_body = json.dumps(
        {
            "model": model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")

    request = Request(
        f"{DEFAULT_LITELLM_BASE_URL}/chat/completions",
        data=request_body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=45) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "enabled": True,
            "status": "failed",
            "model": model,
            "reason": f"semantic_request_failed:{type(exc).__name__}",
            "route": None,
            "confidence": "low",
            "matched_task_title": None,
            "rationale": "",
            "evidence": [],
        }

    try:
        content = raw["choices"][0]["message"]["content"]
        parsed = extract_json_object(content)
    except Exception as exc:
        return {
            "enabled": True,
            "status": "failed",
            "model": model,
            "reason": f"semantic_response_invalid:{type(exc).__name__}",
            "route": None,
            "confidence": "low",
            "matched_task_title": None,
            "rationale": "",
            "evidence": [],
        }

    route = parsed.get("route")
    confidence = normalize_name(parsed.get("confidence")) or "low"
    matched_task_title = parsed.get("matched_task_title")
    rationale = clip_text(parsed.get("rationale"), 220)
    evidence = parsed.get("evidence") if isinstance(parsed.get("evidence"), list) else []

    if route not in {"complement_existing", "create_new", "review"}:
        return {
            "enabled": True,
            "status": "failed",
            "model": model,
            "reason": "semantic_route_invalid",
            "route": None,
            "confidence": "low",
            "matched_task_title": None,
            "rationale": "",
            "evidence": [],
        }
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    if route == "complement_existing" and matched_task_title not in candidate_titles(candidates):
        return {
            "enabled": True,
            "status": "failed",
            "model": model,
            "reason": "semantic_matched_task_invalid",
            "route": None,
            "confidence": "low",
            "matched_task_title": None,
            "rationale": "",
            "evidence": [],
        }

    return {
        "enabled": True,
        "status": "ok",
        "model": model,
        "reason": "semantic_result_available",
        "route": route,
        "confidence": confidence,
        "matched_task_title": matched_task_title,
        "rationale": rationale,
        "evidence": [clip_text(str(item), 120) for item in evidence[:4]],
        "candidate_tasks": candidate_view,
    }


def semantic_matches_deterministic(deterministic: MatchResult, semantic: dict[str, Any]) -> bool:
    if semantic.get("route") != deterministic.mode:
        return False
    if deterministic.mode == "complement_existing":
        return semantic.get("matched_task_title") == (deterministic.task or {}).get("title")
    return True


CONFIDENCE_RANK = {
    "conflict": 0,
    "ambiguous": 1,
    "none": 1,
    "medium": 2,
    "strong": 3,
    "exact": 4,
    "low": 1,
    "high": 3,
}


def finalize_decision(
    deterministic: MatchResult,
    semantic: dict[str, Any],
    bookmark: dict,
    read_payload: dict,
) -> tuple[dict[str, Any], dict | None]:
    area = infer_area(bookmark, read_payload=read_payload)
    estimate = infer_estimate(bookmark, read_payload=read_payload)
    task_type = infer_task_type(bookmark, read_payload=read_payload)

    final_mode = deterministic.mode
    final_reason = f"deterministic:{deterministic.reason}"
    final_confidence = deterministic.confidence
    matched_task = deterministic.task
    alternatives = deterministic.alternatives
    decision_source = "deterministic"

    if semantic.get("status") == "ok":
        semantic_conf = semantic.get("confidence") or "low"
        if semantic_conf == "low":
            decision_source = "deterministic_fallback"
            final_reason = f"semantic_low_confidence:{deterministic.reason}"
        elif semantic_matches_deterministic(deterministic, semantic):
            decision_source = "deterministic+semantic"
            final_reason = f"converged:{deterministic.reason}"
            final_confidence = semantic_conf
        else:
            final_mode = "review"
            matched_task = None
            decision_source = "conflict_to_review"
            final_reason = f"semantic_disagreement:{deterministic.reason}->{semantic.get('route')}"
            final_confidence = "ambiguous"
            alternatives = alternatives or []
            if deterministic.task:
                alternatives = list(alternatives or []) + [{
                    "title": deterministic.task.get("title"),
                    "area": deterministic.task.get("area"),
                    "score": deterministic.score,
                    "source": "deterministic",
                }]
            if semantic.get("matched_task_title"):
                alternatives = list(alternatives or []) + [{
                    "title": semantic.get("matched_task_title"),
                    "source": "semantic",
                }]
    elif semantic.get("status") == "failed":
        decision_source = "deterministic_fallback"
        final_reason = f"semantic_unavailable:{semantic.get('reason')}"

    destination = REVIEW_LIST_NAME if final_mode == "review" else INCORPORATED_LIST_NAME

    classification = {
        "area": area,
        "task_type": task_type,
        "estimate": estimate,
        "match_mode": final_mode,
        "confidence": final_confidence,
        "reason": final_reason,
        "score": deterministic.score,
        "destination_list": destination,
        "decision_source": decision_source,
    }
    if matched_task:
        classification["matched_task"] = {
            "title": matched_task.get("title"),
            "area": matched_task.get("area"),
            "section": matched_task.get("section"),
        }
    if alternatives:
        classification["alternatives"] = alternatives
    if final_mode == "create_new":
        classification["new_task_title"] = build_candidate_title(bookmark)
        classification["new_task_priority"] = "low"
    if final_mode == "review":
        classification["review_task_title"] = build_candidate_title(bookmark)
        classification["review_task_priority"] = "low"
    return classification, matched_task


def classify_bookmark_payload(
    bookmark: dict,
    tasks: list[dict] | None = None,
    semantic_enabled: bool = True,
    model: str = DEFAULT_SEMANTIC_MODEL,
) -> dict:
    tasks = tasks or get_open_tasks()

    # Extract user instruction before any operational merge
    user_instruction = extract_user_instruction(bookmark)

    # Extract rich Karakeep metadata (AI tags, screenshot, author, etc.)
    rich_metadata = extract_karakeep_rich_metadata(bookmark)

    read_payload = read_bookmark_context(bookmark)
    deterministic = match_existing_task(bookmark, tasks=tasks, read_payload=read_payload)

    # LLM-generated enrichment via ModelRelay (now with rich Karakeep context)
    llm_summary: dict[str, Any] = {"status": "skipped"}
    if semantic_enabled:
        llm_summary = summarize_via_modelrelay(
            bookmark, read_payload, user_instruction, model=model,
        )

    semantic = call_semantic_classifier(
        bookmark, read_payload, deterministic, tasks, model=model,
        llm_summary=llm_summary, user_instruction=user_instruction,
    ) if semantic_enabled else {
        "enabled": False,
        "status": "skipped",
        "model": model,
        "reason": "semantic_disabled",
        "route": None,
        "confidence": "low",
        "matched_task_title": None,
        "rationale": "",
        "evidence": [],
    }
    classification, matched_task = finalize_decision(deterministic, semantic, bookmark, read_payload)

    payload = {
        "bookmark": {
            "id": bookmark.get("id"),
            "title": bookmark_title(bookmark),
            "url": bookmark_url(bookmark),
            "note": bookmark_note(bookmark),
        },
        "karakeep_metadata": rich_metadata,
        "read_link": read_payload,
        "llm_summary": llm_summary,
        "user_instruction": user_instruction,
        "deterministic": {
            "match_mode": deterministic.mode,
            "confidence": deterministic.confidence,
            "reason": deterministic.reason,
            "score": deterministic.score,
            "matched_task": {
                "title": deterministic.task.get("title"),
                "area": deterministic.task.get("area"),
                "section": deterministic.task.get("section"),
            } if deterministic.task else None,
            "alternatives": deterministic.alternatives,
        },
        "semantic": semantic,
        "classification": classification,
    }
    if matched_task:
        payload["_matched_task"] = matched_task
    return payload


def append_note_meta_to_task(task: dict, note_value: str) -> dict:
    raw_line = task.get("raw_line")
    if not raw_line:
        raise RuntimeError("task raw line unavailable")
    if f"note:: {note_value}" in raw_line:
        return {"changed": False, "task_title": task.get("title")}

    tasks_file, _ = get_tasks_file(False)
    content = tasks_file.read_text()
    new_line = f"{raw_line} note:: {note_value}"
    if raw_line not in content:
        raise RuntimeError("task raw line no longer found in tasks file")
    tasks_file.write_text(content.replace(raw_line, new_line, 1))
    return {"changed": True, "task_title": task.get("title")}


def run_tasks_add(title: str, area: str, task_type: str, estimate: str, note_meta: list[str], priority: str = "low") -> None:
    cmd = [
        sys.executable,
        str(TASKS_SCRIPT),
        "add",
        title,
        "--priority",
        priority,
        "--area",
        area,
        "--type",
        task_type,
        "--estimate",
        estimate,
    ]
    for note in note_meta:
        cmd.extend(["--note-meta", note])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "tasks.py add failed")


def merge_operational_note(existing_note: str, task_ref: str, read_payload: dict, classification: dict | None = None, llm_summary: dict | None = None, user_instruction: str = "") -> str:
    # Preserve human-written lines only — strip operational and emoji-prefixed lines from prior runs
    preserved = []
    for raw_line in (existing_note or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(line.startswith(prefix) for prefix in OPERATIONAL_NOTE_PREFIXES):
            continue
        if any(line.startswith(emoji) for emoji in OPERATIONAL_EMOJI_PREFIXES):
            continue
        preserved.append(line)

    # Layer 1: human-readable summary
    human_lines = []
    if llm_summary and llm_summary.get("status") == "ok" and llm_summary.get("one_line_summary"):
        human_lines.append(f"📋 {llm_summary['one_line_summary']}")
        if llm_summary.get("why"):
            human_lines.append(f"💡 {llm_summary['why']}")
    elif read_payload.get("normalized_summary"):
        human_lines.append(f"📋 {clip_text(read_payload['normalized_summary'], 160)}")

    if classification:
        mode = classification.get("match_mode", "")
        dest = classification.get("destination_list", "")
        if mode == "complement_existing" and classification.get("matched_task", {}).get("title"):
            human_lines.append(f"↪ Complemented: {classification['matched_task']['title']}")
        elif mode == "create_new":
            human_lines.append(f"➕ New task created ({dest})")
        elif mode == "review":
            human_lines.append(f"🔎 Routed to {dest} — needs manual review")

    # Layer 2: structured metadata
    operational = [
        task_ref,
        f"read-source: {read_payload.get('reader_used')}",
        f"read-status: {read_payload.get('status')}",
        f"content-type: {read_payload.get('source_type')}",
    ]
    if llm_summary and llm_summary.get("status") == "ok":
        operational.append(f"relevance: {llm_summary.get('relevance_hint', 'unknown')}")
        if llm_summary.get("content_type"):
            operational.append(f"llm-type: {llm_summary['content_type']}")
    if user_instruction:
        operational.append(f"user-hint: {clip_text(user_instruction, 80)}")

    lines = list(preserved)
    if lines:
        lines.append("")
    lines.extend(human_lines)
    if human_lines:
        lines.append("")
    lines.extend(operational)
    return "\n".join(lines).strip()


def update_bookmark_operational_note(
    client,
    bookmark_id: str,
    task_ref: str,
    read_payload: dict,
    classification: dict | None = None,
    llm_summary: dict | None = None,
    user_instruction: str = "",
) -> dict:
    bookmark = client.get_bookmark(bookmark_id)
    if not isinstance(bookmark, dict):
        raise RuntimeError(f"bookmark not found: {bookmark_id}")
    current_note = bookmark_note(bookmark)
    merged = merge_operational_note(
        current_note, task_ref, read_payload,
        classification=classification, llm_summary=llm_summary,
        user_instruction=user_instruction,
    )
    if merged == current_note:
        return {"changed": False, "bookmark_id": bookmark_id}
    client.update_bookmark(bookmark_id, note=merged)
    return {"changed": True, "bookmark_id": bookmark_id}


def relocate_bookmark(client, bookmark: dict, destination_name: str, source_name: str = TODO_LIST_NAME) -> dict:
    source = get_list_by_name(client, source_name)
    if not source:
        raise RuntimeError(f"source list not found: {source_name}")

    destination = get_list_by_name(client, destination_name)
    destination_created = False
    if not destination:
        destination_icon = "📦" if destination_name == INCORPORATED_LIST_NAME else "🔎"
        destination = ensure_list(client, destination_name, destination_icon)
        destination_created = True

    bookmark_id = bookmark.get("id")
    if not bookmark_id:
        raise RuntimeError("bookmark id missing")

    destination_lists = bookmark.get("bookmarkLists") or []
    already_in_destination = destination.get("id") in destination_lists

    if not already_in_destination:
        client.add_bookmark_to_list(bookmark_id, destination["id"])

    if source.get("id") in destination_lists or list_name_equals(source.get("name"), source_name):
        try:
            client.remove_bookmark_from_list(bookmark_id, source["id"])
        except RuntimeError:
            pass

    return {
        "bookmark_id": bookmark_id,
        "destination": destination.get("name"),
        "removed_from": source.get("name"),
        "destination_created": destination_created,
    }


def route_bookmark(
    bookmark_id: str,
    apply: bool = False,
    forced_task_query: str | None = None,
    forced_mode: str = "auto",
    semantic_enabled: bool = True,
    model: str = DEFAULT_SEMANTIC_MODEL,
    mc_enabled: bool = False,
) -> dict:
    client = get_client()
    bookmark = client.get_bookmark(bookmark_id)
    if not isinstance(bookmark, dict):
        raise RuntimeError(f"bookmark not found: {bookmark_id}")

    tasks = get_open_tasks()
    payload = classify_bookmark_payload(bookmark, tasks=tasks, semantic_enabled=semantic_enabled, model=model)
    classification = payload["classification"]

    if forced_task_query:
        matches = [task for task in tasks if forced_task_query.lower() in (task.get("title") or "").lower()]
        if len(matches) != 1:
            raise RuntimeError(f"forced task query must resolve to exactly one task: {forced_task_query}")
        classification["match_mode"] = "complement_existing"
        classification["confidence"] = "forced"
        classification["reason"] = "forced_task_query"
        classification["decision_source"] = "forced"
        classification["matched_task"] = {
            "title": matches[0].get("title"),
            "area": matches[0].get("area"),
            "section": matches[0].get("section"),
        }
        classification["destination_list"] = INCORPORATED_LIST_NAME
        payload["_matched_task"] = matches[0]

    if forced_mode != "auto":
        classification["match_mode"] = forced_mode
        classification["confidence"] = "forced"
        classification["reason"] = f"forced_mode:{forced_mode}"
        classification["decision_source"] = "forced"
        if forced_mode == "review":
            classification["destination_list"] = REVIEW_LIST_NAME
        else:
            classification["destination_list"] = INCORPORATED_LIST_NAME

    operations: list[dict[str, Any]] = []
    matched_task = payload.get("_matched_task")

    if not matched_task and classification.get("matched_task"):
        matched_title = classification["matched_task"]["title"]
        for task in tasks:
            if task.get("title") == matched_title:
                matched_task = task
                break

    if classification["match_mode"] == "complement_existing":
        note_value = f"karakeep:{bookmark_id}"
        operations.append({
            "action": "complement_task",
            "task_title": matched_task.get("title") if matched_task else classification.get("matched_task", {}).get("title"),
            "note_meta": note_value,
        })
        expected_task_ref = f"task-ref: Work Tasks.md#{slugify_task_ref((matched_task or {}).get('title', ''))}" if matched_task else None
        operations.append({
            "action": "update_bookmark_note",
            "task_ref": expected_task_ref,
            "read_source": payload["read_link"].get("reader_used"),
            "read_status": payload["read_link"].get("status"),
        })
    elif classification["match_mode"] == "create_new":
        operations.append({
            "action": "create_task",
            "title": classification["new_task_title"],
            "priority": classification["new_task_priority"],
            "area": classification["area"],
            "task_type": classification["task_type"],
            "estimate": classification["estimate"],
            "note_meta": [f"karakeep:{bookmark_id}"],
        })
        operations.append({
            "action": "update_bookmark_note",
            "task_ref": f"task-ref: Work Tasks.md#{slugify_task_ref(classification['new_task_title'])}",
            "read_source": payload["read_link"].get("reader_used"),
            "read_status": payload["read_link"].get("status"),
        })
    else:
        operations.append({
            "action": "create_review_task",
            "title": classification["review_task_title"],
            "priority": classification["review_task_priority"],
            "area": classification["area"],
            "task_type": "review",
            "estimate": classification["estimate"],
            "note_meta": [f"karakeep:{bookmark_id}"],
            "reason": classification["reason"],
        })
        operations.append({
            "action": "update_bookmark_note",
            "task_ref": f"task-ref: Work Tasks.md#{slugify_task_ref(classification['review_task_title'])}",
            "read_source": payload["read_link"].get("reader_used"),
            "read_status": payload["read_link"].get("status"),
        })

    operations.append({
        "action": "move_bookmark",
        "destination_list": classification["destination_list"],
        "source_list": TODO_LIST_NAME,
    })
    payload["operations"] = operations
    payload["apply"] = apply

    # Mission Control preview (dry run)
    if mc_enabled and not apply:
        board_id, reason = route_to_mc_board(classification, payload.get("llm_summary"))
        payload["mc_result"] = {"status": "dry_run", "board_id": board_id, "reason": reason}

    if not apply:
        return payload

    # Prepare enriched note data for all branches
    _classification = classification
    _llm_summary = payload.get("llm_summary")
    _user_instruction = payload.get("user_instruction", "")

    if classification["match_mode"] == "complement_existing":
        if not matched_task:
            raise RuntimeError("matched task missing for complement_existing")
        append_result = append_note_meta_to_task(matched_task, f"karakeep:{bookmark_id}")
        task_ref = f"task-ref: Work Tasks.md#{slugify_task_ref(matched_task.get('title') or '')}"
        note_result = update_bookmark_operational_note(
            client, bookmark_id, task_ref, payload["read_link"],
            classification=_classification, llm_summary=_llm_summary, user_instruction=_user_instruction,
        )
        payload["results"] = [append_result, note_result]
    elif classification["match_mode"] == "create_new":
        run_tasks_add(
            classification["new_task_title"],
            classification["area"],
            classification["task_type"],
            classification["estimate"],
            [f"karakeep:{bookmark_id}"],
            priority=classification["new_task_priority"],
        )
        task_ref = f"task-ref: Work Tasks.md#{slugify_task_ref(classification['new_task_title'])}"
        note_result = update_bookmark_operational_note(
            client, bookmark_id, task_ref, payload["read_link"],
            classification=_classification, llm_summary=_llm_summary, user_instruction=_user_instruction,
        )
        payload["results"] = [{"created_task": classification["new_task_title"]}, note_result]
    else:
        run_tasks_add(
            classification["review_task_title"],
            classification["area"],
            "review",
            classification["estimate"],
            [f"karakeep:{bookmark_id}"],
            priority=classification["review_task_priority"],
        )
        task_ref = f"task-ref: Work Tasks.md#{slugify_task_ref(classification['review_task_title'])}"
        note_result = update_bookmark_operational_note(
            client, bookmark_id, task_ref, payload["read_link"],
            classification=_classification, llm_summary=_llm_summary, user_instruction=_user_instruction,
        )
        payload["results"] = [{"created_review_task": classification["review_task_title"], "reason": classification["reason"]}, note_result]

    payload.setdefault("results", []).append(relocate_bookmark(client, bookmark, classification["destination_list"]))

    # Mission Control write (optional, alongside local task write)
    if mc_enabled and apply:
        mc_result = create_mc_task(
            classification, bookmark, payload["read_link"],
            llm_summary=payload.get("llm_summary"),
            user_instruction=payload.get("user_instruction", ""),
            rich_metadata=payload.get("karakeep_metadata"),
        )
        payload["mc_result"] = mc_result
        if mc_result.get("status") == "ok":
            payload.setdefault("results", []).append({"mc_task": mc_result})
        else:
            payload.setdefault("results", []).append({"mc_task_error": mc_result})
    elif mc_enabled:
        board_id, reason = route_to_mc_board(classification, payload.get("llm_summary"))
        payload["mc_result"] = {"status": "dry_run", "board_id": board_id, "reason": reason}

    return payload


def print_json(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def print_human_review(payload: dict) -> None:
    bookmark = payload["bookmark"]
    classification = payload["classification"]
    read_link = payload.get("read_link") or {}
    semantic = payload.get("semantic") or {}
    print(f"Bookmark: {bookmark.get('id')}")
    print(f"Title: {bookmark.get('title')}")
    print(f"URL: {bookmark.get('url')}")
    print(
        f"Read-link: {read_link.get('reader_used')} | {read_link.get('status')} | {read_link.get('confidence')} | {read_link.get('source_type')}"
    )
    if read_link.get("normalized_summary"):
        print(f"Summary: {read_link.get('normalized_summary')}")
    print(f"Area: {classification.get('area')} | Type: {classification.get('task_type')} | Estimate: {classification.get('estimate')}")
    print(f"Decision: {classification.get('match_mode')} ({classification.get('confidence')})")
    print(f"Reason: {classification.get('reason')} | Source: {classification.get('decision_source')}")
    if classification.get("matched_task"):
        print(f"Matched task: {classification['matched_task']['title']}")
    if classification.get("new_task_title"):
        print(f"New task: {classification['new_task_title']}")
    if classification.get("review_task_title"):
        print(f"Review task: {classification['review_task_title']}")
    print(f"Destination list: {classification.get('destination_list')}")
    if semantic.get("enabled"):
        print(f"Semantic: {semantic.get('status')} | {semantic.get('model')} | {semantic.get('confidence')}")
        if semantic.get("route"):
            print(f"Semantic route: {semantic.get('route')} | task: {semantic.get('matched_task_title')}")
        if semantic.get("rationale"):
            print(f"Semantic rationale: {semantic.get('rationale')}")
    if classification.get("alternatives"):
        print("Alternatives:")
        for alt in classification["alternatives"]:
            print(f"- {alt}")
    mc = payload.get("mc_result")
    if mc:
        print(f"MC: {mc.get('status')} | board: {mc.get('board_name', mc.get('board_id'))} | reason: {mc.get('reason')}")
        if mc.get("task_id"):
            print(f"MC task: {mc['task_id']} — {mc.get('task_title', '')}")


def cmd_review_inbox(args) -> None:
    client = get_client()
    bookmarks = get_bookmarks_for_list(client, args.list_name, limit=args.limit)
    tasks = get_open_tasks()
    payload = {
        "list_name": args.list_name,
        "count": len(bookmarks),
        "semantic_enabled": not args.deterministic_only,
        "model": args.model,
        "items": [
            classify_bookmark_payload(
                bookmark,
                tasks=tasks,
                semantic_enabled=not args.deterministic_only,
                model=args.model,
            )
            for bookmark in bookmarks
        ],
    }
    if args.json:
        print_json(payload)
    else:
        print(f"Inbox review: {args.list_name} ({len(bookmarks)} item(s))\n")
        for item in payload["items"]:
            print_human_review(item)
            print()


def cmd_classify_bookmark(args) -> None:
    client = get_client()
    bookmark = client.get_bookmark(args.bookmark_id)
    payload = classify_bookmark_payload(
        bookmark,
        semantic_enabled=not args.deterministic_only,
        model=args.model,
    )
    if args.json:
        print_json(payload)
    else:
        print_human_review(payload)


def cmd_route_item(args) -> None:
    payload = route_bookmark(
        args.bookmark_id,
        apply=args.apply,
        forced_task_query=args.task,
        forced_mode=args.mode,
        semantic_enabled=not args.deterministic_only,
        model=args.model,
        mc_enabled=getattr(args, 'mc', False),
    )
    if args.json:
        print_json(payload)
    else:
        print_human_review(payload)
        print()
        print(f"Apply: {'yes' if args.apply else 'no (dry-run)'}")
        print("Operations:")
        for operation in payload.get("operations", []):
            print(f"- {json.dumps(operation, ensure_ascii=False)}")
        for result in payload.get("results", []):
            print(f"- result: {json.dumps(result, ensure_ascii=False)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bounded Karakeep inbox review and routing")
    subparsers = parser.add_subparsers(dest="command", required=True)

    review = subparsers.add_parser("review-inbox", help="Review a small inbox slice from one Karakeep list")
    review.add_argument("--list-name", default=TODO_LIST_NAME)
    review.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    review.add_argument("--deterministic-only", action="store_true")
    review.add_argument("--model", default=DEFAULT_SEMANTIC_MODEL)
    review.add_argument("--json", action="store_true")
    review.set_defaults(func=cmd_review_inbox)

    classify = subparsers.add_parser("classify-bookmark", help="Classify one bookmark without mutating")
    classify.add_argument("--bookmark-id", required=True)
    classify.add_argument("--deterministic-only", action="store_true")
    classify.add_argument("--model", default=DEFAULT_SEMANTIC_MODEL)
    classify.add_argument("--json", action="store_true")
    classify.set_defaults(func=cmd_classify_bookmark)

    route = subparsers.add_parser("route-item", help="Route one bookmark; dry-run unless --apply")
    route.add_argument("--bookmark-id", required=True)
    route.add_argument("--task", help="Force complement of one task query")
    route.add_argument("--mode", choices=["auto", "create_new", "complement_existing", "review"], default="auto")
    route.add_argument("--deterministic-only", action="store_true")
    route.add_argument("--model", default=DEFAULT_SEMANTIC_MODEL)
    route.add_argument("--apply", action="store_true")
    route.add_argument("--mc", action="store_true", help="Create task in Mission Control alongside local task")
    route.add_argument("--json", action="store_true")
    route.set_defaults(func=cmd_route_item)

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
