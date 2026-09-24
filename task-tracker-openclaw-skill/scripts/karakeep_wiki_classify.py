#!/usr/bin/env python3
"""
karakeep_wiki_classify.py — classify a karakeep bookmark into a wiki category.

Usage:
  python3 karakeep_wiki_classify.py deterministic --bookmark-json '{"id":"...","tags":[],"note":"..."}'
  python3 karakeep_wiki_classify.py llm --bookmark-json '...' [--wiki-state-json '...'] [--env-context '...']

The deterministic command applies the rule table and returns a category without an LLM call.
The llm command uses the LiteLLM relay to classify ambiguous items.

Both output JSON:
  {"category": "mcp/servers.md", "confidence": "high", "method": "deterministic", "new_category": null}
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

DEFAULT_MODEL = "litellm/freellm/auto"

# Schema for llm-task classification output
_CLASSIFY_SCHEMA = {
    "type": "object",
    "required": ["category", "confidence", "reason", "new_category"],
    "additionalProperties": False,
    "properties": {
        "category": {"type": ["string", "null"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reason": {"type": "string"},
        "new_category": {
            "oneOf": [
                {"type": "null"},
                {"type": "object", "required": ["key", "title", "parent"],
                 "properties": {
                     "key": {"type": "string"},
                     "title": {"type": "string"},
                     "parent": {"type": "string"}},
                 "additionalProperties": False}
            ]
        }
    }
}

def _read_env_key(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None



VAULT = Path("/home/ozp/obsidian-wiki-vault")
REFERENCES = VAULT / "references"
INDEX = REFERENCES / "_index.md"
SYSTEM_INVENTORY = Path("/home/ozp/clawd/SYSTEM-INVENTORY.md")
CURATION_PROTOCOL = Path("/home/ozp/clawd/agents/karakeep/references/wiki-curation-protocol.md")


# ---------------------------------------------------------------------------
# Rule table (deterministic)
# ---------------------------------------------------------------------------

RULES = [
    # (priority, description, test_fn, category)
    (1, "article/docs/blog content-type", lambda bm: _content_type_in(bm, {"article", "docs", "blog"}), "content/articles.md"),
    (2, "MCP tag", lambda bm: _has_tag(bm, {"mcp", "model context protocol"}), "mcp/servers.md"),
    (3, "skill/plugin tag", lambda bm: _has_tag(bm, {"skill", "plugin", "skills"}), "agent-tooling/skills-plugins.md"),
    (4, "OpenClaw/multi-agent tag", lambda bm: _has_tag(bm, {"openclaw", "multi-agent", "agentes de ia", "multi agent"}), "agent-tooling/frameworks.md"),
    (5, "RAG/NLP tag", lambda bm: _has_tag(bm, {"rag", "nlp", "processamento de linguagem", "embeddings", "vector", "retrieval"}), "ai-ml/rag-nlp.md"),
    (6, "vision/multimodal tag", lambda bm: _has_tag(bm, {"visão computacional", "multimodal", "vision", "image generation", "video generation", "computer vision"}), "ai-ml/vision.md"),
    (7, "LLM/ML tag", lambda bm: _has_tag(bm, {"aprendizado de máquina", "llm", "machine learning", "fine-tuning", "inference", "model"}), "ai-ml/models-llms.md"),
    (8, "Obsidian/PKM tag", lambda bm: _has_tag(bm, {"obsidian", "pkm", "wiki", "knowledge management", "note-taking"}), "knowledge-pkm/tools.md"),
    (9, "incorporated repo fallback", lambda bm: _is_incorporated_repo(bm), "dev-tools/repos.md"),
]


def _content_type_in(bm: dict, types: set) -> bool:
    note = bm.get("note", "") or ""
    for line in note.splitlines():
        line = line.strip()
        if line.startswith("content-type:"):
            ct = line[len("content-type:"):].strip().lower()
            return ct in types
    # fallback: content.type from API (link, video, article, etc.)
    ct = (bm.get("content") or {}).get("type", "").lower()
    if ct:
        return ct in types
    ct = bm.get("content_type", "").lower()
    return ct in types


def _tag_names(bm: dict) -> list[str]:
    """Extract tag name strings — tags may be str or {id, name} objects."""
    raw = bm.get("tags") or []
    names = []
    for t in raw:
        if isinstance(t, dict):
            names.append(t.get("name", "").lower())
        else:
            names.append(str(t).lower())
    return names


def _bm_url(bm: dict) -> str:
    return bm.get("url") or (bm.get("content") or {}).get("url") or ""


def _has_tag(bm: dict, targets: set) -> bool:
    tags = _tag_names(bm)
    title_lower = (bm.get("title") or "").lower()
    note_lower = (bm.get("note", "") or "").lower()
    for target in targets:
        if any(target in t for t in tags):
            return True
        if target in title_lower:
            return True
        if target in note_lower:
            return True
    return False


def _is_incorporated_repo(bm: dict) -> bool:
    note = bm.get("note", "") or ""
    for line in note.splitlines():
        line = line.strip()
        if line.startswith("content-type:"):
            ct = line[len("content-type:"):].strip().lower()
            if ct == "repo":
                return True
    ct = bm.get("content_type", "").lower()
    return ct == "repo"


def classify_deterministic(bm: dict) -> dict:
    note = bm.get("note", "") or ""
    is_review = False
    for line in note.splitlines():
        line = line.strip()
        if line.startswith("read-status:"):
            status = line[len("read-status:"):].strip().lower()
            if status in {"review", "triage"}:
                is_review = True

    source_list = bm.get("source_list", "").lower()
    if source_list in {"review", "triage"}:
        is_review = True

    if is_review:
        return {
            "category": "_staging.md",
            "confidence": "high",
            "method": "deterministic",
            "rule": "review/triage → staging",
            "new_category": None,
        }

    for priority, description, test_fn, category in RULES:
        try:
            if test_fn(bm):
                return {
                    "category": category,
                    "confidence": "high",
                    "method": "deterministic",
                    "rule": f"P{priority}: {description}",
                    "new_category": None,
                }
        except Exception:
            continue

    return {
        "category": None,
        "confidence": "low",
        "method": "deterministic",
        "rule": "no match",
        "new_category": None,
    }


# ---------------------------------------------------------------------------
# LLM classification
# ---------------------------------------------------------------------------

def load_wiki_state() -> str:
    if INDEX.exists():
        text = INDEX.read_text(encoding="utf-8")
        # return only the categories table portion to save tokens
        lines = []
        in_table = False
        for line in text.splitlines():
            if "| Category" in line:
                in_table = True
            if in_table:
                lines.append(line)
            if in_table and line.strip() == "":
                break
        return "\n".join(lines) if lines else text[:1500]
    return "(wiki index not found)"


def load_env_context() -> str:
    parts = []
    if CURATION_PROTOCOL.exists():
        parts.append(CURATION_PROTOCOL.read_text(encoding="utf-8"))
    if SYSTEM_INVENTORY.exists():
        parts.append(SYSTEM_INVENTORY.read_text(encoding="utf-8")[:800])
    return "\n\n---\n\n".join(parts) if parts else "(context not found)"


def _extract_user_hint(note: str) -> str | None:
    if not note:
        return None
    for line in note.splitlines():
        line = line.strip()
        if line.startswith("user-hint:"):
            return line[len("user-hint:"):].strip()
    return None


def build_classify_prompt(bm: dict, wiki_state: str, env_context: str, det_hint: dict | None = None) -> str:
    url = _bm_url(bm)
    title = bm.get("title") or (bm.get("content") or {}).get("title") or url
    tags = _tag_names(bm)
    note = bm.get("note", "") or ""
    user_hint = _extract_user_hint(note)

    hint_line = f"\nUser hint: {user_hint}" if user_hint else ""
    desc = bm.get("_description", "") or (bm.get("content") or {}).get("description", "")
    readme = bm.get("_readme_excerpt", "")
    extra = ""
    if desc:
        extra += f"\nDescription: {desc}"
    if readme:
        extra += f"\nREADME excerpt: {readme[:400]}"

    det_section = ""
    if det_hint:
        cat = det_hint.get('category') or 'no match'
        det_section = f"""
## Rule-based signal (pre-analysis)
Suggested: {cat} | Rule: {det_hint.get('rule', 'none')} | Confidence: {det_hint.get('confidence', 'unknown')}

Treat this as a weak signal only. Rule-based matching is shallow — it operates on tags and keywords without understanding content or context. You may confirm, refine, or override it.
"""

    return f"""You are an autonomous knowledge curator building a personal wiki. Apply the curation protocol below to decide where this resource belongs — and evolve the wiki structure when no good category exists.

## Curation protocol and category semantics
{env_context}

## Current wiki categories (live state)
{wiki_state}
{det_section}
## Resource to evaluate
Title: {title}
URL: {url}
Tags: {', '.join(tags) if tags else 'none'}{hint_line}{extra}

## Hard constraints
- The resource format is not the category. A blog post, guide, documentation page, or repository about a clear domain belongs to that domain, not to a format bucket.
- `content/articles.md` is a last-resort bucket for textual content whose domain cannot be mapped or named. Do NOT use it for tutorials/guides about Claude Code, agent tooling, MCP, RAG, AI models, developer tooling, or any other identifiable domain.
- `dev-tools/repos.md` is a last-resort bucket for generic repositories only. Do NOT use it when the repository has a specific domain.
- `_staging.md` is only for genuine ambiguity or insufficient evidence. If your reason names a domain, staging is invalid.
- If no existing category specifically fits the named domain, set `category` to the proposed new category key and include `new_category`.
- Claude Code / Codex CLI / AI coding assistant guides are about the `AI coding agents` domain; use/propose `agent-tooling/coding-agents.md` unless the resource is specifically a plugin/skill registry or extension pack.
- If you choose `content/articles.md`, `dev-tools/repos.md`, or `_staging.md` while your reason names a specific domain, your answer is invalid.

Follow the reasoning steps in the curation protocol. Respond with ONLY a JSON object (no markdown):
{{
  "category": "<file key like mcp/servers.md>",
  "confidence": "high|medium|low",
  "reason": "<one sentence naming the domain and why this category fits>",
  "new_category": null or {{"key": "parent/filename.md", "title": "Human-readable title", "parent": "parent-dir"}}
}}"""


def _get_openclaw_config() -> tuple[str, str]:
    """Return (url, token) for OpenClaw gateway."""
    import os
    url = os.environ.get("OPENCLAW_URL", "http://127.0.0.1:18789")
    token = os.environ.get("OPENCLAW_TOKEN", "")
    if not token:
        try:
            cfg = json.loads(Path("/home/ozp/.openclaw/openclaw.json").read_text())
            token = cfg["gateway"]["auth"]["token"]
        except Exception:
            pass
    return url, token


def call_llm_task(prompt: str, model: str) -> dict:
    """Call llm-task via OpenClaw HTTP API and return the parsed JSON result."""

    url_base, token = _get_openclaw_config()
    payload = json.dumps({
        "tool": "llm-task",
        "action": "json",
        "args": {
            "prompt": prompt,
            "model": model,
            "temperature": 0.1,
            "maxTokens": 8000,
            "schema": _CLASSIFY_SCHEMA,
        },
    }).encode()

    req = Request(
        f"{url_base}/tools/invoke",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    # /tools/invoke returns {ok: true, result: {content: [...], details: {...}}}
    if not data.get("ok"):
        raise RuntimeError(f"llm-task API error: {data}")
    details = data["result"]["details"]
    return details["json"]


def classify_llm(bm: dict, wiki_state: str | None, env_context: str | None, model: str, det_hint: dict | None = None) -> dict:
    ws = wiki_state or load_wiki_state()
    ec = env_context or load_env_context()
    prompt = build_classify_prompt(bm, ws, ec, det_hint=det_hint)

    try:
        result = call_llm_task(prompt, model)
        result["method"] = "llm"
        result["model"] = model
        return result
    except Exception as e:
        return {"category": "_staging.md", "confidence": "low", "method": "llm_failed",
                "error": str(e), "new_category": None}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_deterministic(args):
    bm = json.loads(args.bookmark_json)
    result = classify_deterministic(bm)
    print(json.dumps(result, ensure_ascii=False))


def cmd_llm(args):
    bm = json.loads(args.bookmark_json)
    wiki_state = args.wiki_state_json or None
    env_context = args.env_context or None
    model = args.model or DEFAULT_MODEL
    det_hint = json.loads(args.det_hint_json) if getattr(args, "det_hint_json", None) else None
    result = classify_llm(bm, wiki_state, env_context, model, det_hint=det_hint)
    print(json.dumps(result, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="Classify a karakeep bookmark into a wiki category")
    sub = p.add_subparsers(dest="cmd", required=True)

    det = sub.add_parser("deterministic", help="Apply rule table (no LLM)")
    det.add_argument("--bookmark-json", required=True)
    det.add_argument("--source-list", default="", help="karakeep list name (incorporated/review/triage)")
    det.set_defaults(func=cmd_deterministic)

    llm = sub.add_parser("llm", help="Use LLM to classify item (always runs, uses det hint if provided)")
    llm.add_argument("--bookmark-json", required=True)
    llm.add_argument("--wiki-state-json", default=None)
    llm.add_argument("--env-context", default=None)
    llm.add_argument("--model", default=None)
    llm.add_argument("--det-hint-json", default=None, help="JSON from deterministic step to guide LLM")
    llm.set_defaults(func=cmd_llm)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
