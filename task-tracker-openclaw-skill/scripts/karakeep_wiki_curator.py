#!/usr/bin/env python3
"""
karakeep_wiki_curator.py — LLM-based curator/writer for Karakeep wiki ingest.

The LLM performs the curatorial decision and writes the Markdown entry. This
script supplies evidence and wiki context, validates the JSON response, applies
safe wiki mutations, and updates wiki index/log bookkeeping.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VAULT = Path("/home/ozp/obsidian-wiki-vault")
REFERENCES = VAULT / "📚 references"
INDEX = REFERENCES / "_index.md"
INGEST_LOG = REFERENCES / "_logs" / "karakeep-wiki-ingest.jsonl"
PROMPT_FILE = Path("/home/ozp/clawd/agents/karakeep/references/wiki-entry-curation-prompt.xml")
CURATION_PROTOCOL = Path("/home/ozp/clawd/agents/karakeep/references/wiki-curation-protocol.md")
SYSTEM_INVENTORY = Path("/home/ozp/clawd/SYSTEM-INVENTORY.md")
LITELLM_BASE = "http://localhost:4000/v1"
LITELLM_ENV_FILE = Path("/home/ozp/.config/env/.env")
DEFAULT_MODEL = "glm-5-turbo"
MAX_CONTEXT_CHARS = 12000


def _read_env_key(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def get_litellm_key() -> str:
    return _read_env_key(LITELLM_ENV_FILE, "LITELLM_MASTER_KEY") or "sk-local"


def append_ingest_log(event: str, **fields) -> None:
    from datetime import datetime, timezone

    INGEST_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now(timezone.utc).isoformat(), "event": event}
    row.update(fields)
    with INGEST_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_markdown_id_index() -> dict[str, list[str]]:
    ids: dict[str, list[str]] = {}
    if not REFERENCES.exists():
        return ids
    pattern = re.compile(r"karakeep:([A-Za-z0-9_-]+)")
    for path in sorted(REFERENCES.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = str(path.relative_to(REFERENCES))
        for bid in pattern.findall(text):
            ids.setdefault(bid, []).append(rel)
    return ids


def markdown_files_for_id(bookmark_id: str) -> list[str]:
    return build_markdown_id_index().get(bookmark_id, [])


def bm_url(bm: dict) -> str:
    return bm.get("url") or (bm.get("content") or {}).get("url") or ""


def bm_title(bm: dict) -> str:
    return bm.get("title") or (bm.get("content") or {}).get("title") or bm_url(bm) or "Untitled"


def tag_names(bm: dict) -> list[str]:
    out = []
    for tag in bm.get("tags") or []:
        name = tag.get("name") if isinstance(tag, dict) else str(tag)
        name = (name or "").strip()
        if name:
            out.append(name)
    return sorted(set(out), key=str.lower)


def ensure_category_file(key: str, title: str | None = None) -> Path:
    path = REFERENCES / key
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        heading = title or key.replace("/", " / ").replace(".md", "").replace("-", " ").title()
        path.write_text(f"# {heading}\n\n", encoding="utf-8")
        register_category_in_index(key, heading)
    return path


def register_category_in_index(key: str, title: str) -> None:
    if not INDEX.exists():
        return
    text = INDEX.read_text(encoding="utf-8")
    if key in text:
        return
    lines = text.splitlines()
    row = f"| {title} | [{key}]({key}) | 0 | — |"
    insert_at = None
    in_table = False
    for i, line in enumerate(lines):
        if line.startswith("| Category"):
            in_table = True
        elif in_table and line.strip() == "":
            insert_at = i
            break
    if insert_at is None:
        lines.append(row)
    else:
        lines.insert(insert_at, row)
    INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_index_stats() -> None:
    if not INDEX.exists():
        return
    ids_by_file: dict[str, set[str]] = {}
    for bid, files in build_markdown_id_index().items():
        for file_key in files:
            ids_by_file.setdefault(file_key, set()).add(bid)

    text = INDEX.read_text(encoding="utf-8")
    total_entries = len(build_markdown_id_index())
    text = re.sub(r"(\*\*Total entries:\*\* )\d+", rf"\g<1>{total_entries}", text)

    migration_state_path = Path("/home/ozp/clawd/agents/karakeep/memory/wiki-migration-state.json")
    if migration_state_path.exists():
        try:
            state = json.loads(migration_state_path.read_text(encoding="utf-8"))
            parts = []
            processed_total = 0
            expected_total = 0
            for key in ("incorporated", "review", "triage"):
                section = state.get(key) or {}
                processed = int(section.get("processed") or 0)
                total = int(section.get("total") or 0)
                processed_total += processed
                expected_total += total
                parts.append(f"{key.capitalize()}: {processed}/{total}")
            if expected_total:
                replacement = f"**Migration progress:** {processed_total} / {expected_total} ({' · '.join(parts)})"
                text = re.sub(r"\*\*Migration progress:\*\* .*", replacement, text)
        except Exception:
            pass

    text = re.sub(r"(\*\*Last ingest:\*\* ).*", rf"\g<1>{date.today().isoformat()}", text)

    lines = []
    for line in text.splitlines():
        updated = line
        m = re.match(r"^(\|\s*.+?\s*\|\s*\[[^\]]+\]\(([^)]+)\)\s*\|\s*)(\d+)(\s*\|.*)$", line)
        if m:
            key = m.group(2)
            updated = f"{m.group(1)}{len(ids_by_file.get(key, set()))}{m.group(4)}"
        lines.append(updated)
    INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")

def extract_json_object(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    return json.loads(raw)


def call_litellm(prompt: str, model: str) -> dict:
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 6000,
    }).encode()
    req = Request(
        f"{LITELLM_BASE}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {get_litellm_key()}"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    msg = data["choices"][0]["message"]
    content = msg.get("content") or msg.get("reasoning_content")
    if not content:
        raise ValueError("LLM returned empty content")
    return extract_json_object(content)


def compact_file(path: Path, limit: int) -> str:
    if not path.exists():
        return "(missing)"
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:limit]


def find_similar_entries(bm: dict, candidate_category: str | None, limit: int = 6) -> str:
    terms = set()
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", bm_title(bm).lower()):
        if token not in {"the", "and", "for", "with", "github", "open", "source"}:
            terms.add(token)
    for tag in tag_names(bm):
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", tag.lower()):
            terms.add(token)

    candidates: list[Path] = []
    if candidate_category:
        candidate_path = REFERENCES / candidate_category
        if candidate_path.exists():
            candidates.append(candidate_path)
    for path in sorted(REFERENCES.rglob("*.md")):
        if path not in candidates:
            candidates.append(path)

    scored = []
    for path in candidates:
        text = compact_file(path, 18000).lower()
        score = sum(1 for t in terms if t in text)
        if candidate_category and path == REFERENCES / candidate_category:
            score += 3
        if score:
            scored.append((score, path))
    scored.sort(reverse=True, key=lambda x: x[0])

    blocks = []
    for _, path in scored[:limit]:
        text = compact_file(path, 18000)
        excerpt = text[:1600]
        blocks.append(f"--- similar file: {path.relative_to(REFERENCES)}\n{excerpt}")
    return "\n\n".join(blocks) if blocks else "(no similar entries found)"

def fetch_url_text(url: str, limit: int = 6000) -> dict:
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
            if text:
                return {"ok": True, "kind": "fetch_url_text", "text": text[:limit]}
        return {"ok": False, "kind": "fetch_url_text", "error": "no extractable text"}
    except Exception as exc:
        return {"ok": False, "kind": "fetch_url_text", "error": str(exc)}


def fetch_github_readme(url: str, limit: int = 6000) -> dict:
    m = re.match(r"https?://github\.com/([^/]+/[^/?#]+)", url)
    if not m:
        return {"ok": False, "kind": "fetch_github_readme", "error": "not a github repo url"}
    repo = m.group(1)
    try:
        meta_proc = subprocess.run(
            ["gh", "repo", "view", repo, "--json", "description,stargazerCount,repositoryTopics,primaryLanguage,pushedAt,url"],
            capture_output=True, text=True, timeout=25,
        )
        meta = json.loads(meta_proc.stdout) if meta_proc.returncode == 0 and meta_proc.stdout.strip() else {}

        readme_proc = subprocess.run(
            ["gh", "api", f"repos/{repo}/readme", "--jq", ".content"],
            capture_output=True, text=True, timeout=25,
        )
        if readme_proc.returncode != 0:
            return {"ok": False, "kind": "fetch_github_readme", "error": readme_proc.stderr[:500], "metadata": meta}

        import base64
        encoded = "".join(readme_proc.stdout.split())
        readme = base64.b64decode(encoded).decode("utf-8", errors="replace")[:limit]
        return {"ok": True, "kind": "fetch_github_readme", "text": json.dumps(meta | {"readme_text_excerpt": readme}, ensure_ascii=False)}
    except Exception as exc:
        return {"ok": False, "kind": "fetch_github_readme", "error": str(exc)}


def build_prompt(bm: dict, enrichment: dict, classification: dict, extra_fetch: dict | None = None) -> str:
    prompt_template = PROMPT_FILE.read_text(encoding="utf-8") if PROMPT_FILE.exists() else "{{BOOKMARK_JSON}}"
    candidate_category = (classification or {}).get("category")
    candidate_text = compact_file(REFERENCES / candidate_category, 6000) if candidate_category else "(no candidate category)"
    env_context = compact_file(SYSTEM_INVENTORY, 2500)
    protocol = compact_file(CURATION_PROTOCOL, 9000)
    bookmark_context = dict(bm)
    bookmark_context["_deterministic_or_prior_classification"] = classification
    if extra_fetch:
        bookmark_context["_additional_fetch"] = extra_fetch

    replacements = {
        "{{BOOKMARK_JSON}}": json.dumps(bookmark_context, ensure_ascii=False, indent=2)[:MAX_CONTEXT_CHARS],
        "{{ENRICHMENT_JSON}}": json.dumps(enrichment or {}, ensure_ascii=False, indent=2)[:MAX_CONTEXT_CHARS],
        "{{CURRENT_WIKI_INDEX}}": compact_file(INDEX, 9000),
        "{{CANDIDATE_CATEGORY_FILE}}": candidate_text,
        "{{SIMILAR_ENTRIES}}": find_similar_entries(bm, candidate_category),
        "{{ENVIRONMENT_CONTEXT}}": env_context,
        "{{CURATION_PROTOCOL}}": protocol,
    }
    prompt = prompt_template
    for key, value in replacements.items():
        prompt = prompt.replace(key, value)
    return prompt


def normalize_markdown_entry(entry: str, bm: dict) -> str:
    entry = (entry or "").strip()
    if not entry:
        return ""
    bid = bm.get("id", "")
    if f"karakeep:{bid}" not in entry:
        entry += f"\n- **ID:** `karakeep:{bid}`"
    if "- **Date:**" not in entry:
        entry += f"\n- **Date:** {date.today().isoformat()}"
    return entry.rstrip() + "\n"


def validate_curator_result(result: dict, bm: dict) -> list[str]:
    errors = []
    status = result.get("status")
    if status not in {"accept", "stage_for_review", "duplicate", "reject", "needs_fetch"}:
        errors.append("invalid status")
    if result.get("bookmark_id") != bm.get("id"):
        errors.append("bookmark_id mismatch")
    if status == "accept":
        if not result.get("category"):
            errors.append("accepted result missing category")
        entry = result.get("markdown_entry") or ""
        if f"karakeep:{bm.get('id','')}" not in entry:
            errors.append("accepted entry missing karakeep ID")
        for needle in ["- **Summary:**", "- **Relevance:**", "- **Evidence:**", "- **Tags:**"]:
            if needle not in entry:
                errors.append(f"accepted entry missing {needle}")
    if status == "needs_fetch" and not result.get("fetch_request"):
        errors.append("needs_fetch without fetch_request")
    return errors


def apply_curated_result(result: dict, bm: dict, dry_run: bool = False) -> dict:
    bid = bm.get("id", "")
    existing_files = markdown_files_for_id(bid)

    status = result.get("status")
    if status != "accept":
        return {"ok": False, "status": status, "bookmark_id": bid, "curation": result}

    if existing_files:
        return {
            "ok": False,
            "duplicate": True,
            "bookmark_id": bid,
            "existing": {"files": existing_files, "file": existing_files[0]},
            "curation": result,
        }

    errors = validate_curator_result(result, bm)
    if errors:
        return {"ok": False, "status": "validation_failed", "bookmark_id": bid, "errors": errors, "curation": result}

    category = result["category"]
    new_cat = result.get("new_category") or {}
    entry = normalize_markdown_entry(result.get("markdown_entry") or "", bm)
    if dry_run:
        return {"ok": True, "dry_run": True, "bookmark_id": bid, "file": category, "wiki_ref": f"references/{category}", "curation": result}

    path = ensure_category_file(category, title=new_cat.get("title"))
    current = path.read_text(encoding="utf-8")
    sep = "\n" if current.endswith("\n") else "\n\n"
    path.write_text(current + sep + entry, encoding="utf-8")

    update_index_stats()
    append_ingest_log(
        "ingested",
        karakeep_id=bid,
        url=bm_url(bm),
        title=bm_title(bm),
        wiki_ref=f"references/{category}",
        source_list=bm.get("source_list"),
        category=category,
    )
    return {"ok": True, "bookmark_id": bid, "file": category, "wiki_ref": f"references/{category}", "curation": result}

def perform_fetch_request(req: dict, bm: dict) -> dict:
    kind = req.get("kind")
    url = req.get("url") or bm_url(bm)
    if kind == "fetch_github_readme":
        return fetch_github_readme(url)
    if kind in {"fetch_url_text", "fetch_browser_rendered"}:
        # Browser-rendered fetch is not implemented in script context; try text extraction
        # and preserve the requested kind for audit.
        fetched = fetch_url_text(url)
        fetched["requested_kind"] = kind
        return fetched
    return {"ok": False, "kind": kind, "error": "unsupported fetch kind"}


def curate(bm: dict, enrichment: dict, classification: dict, model: str, dry_run: bool = False) -> dict:
    extra_fetches = []
    result = None

    for _attempt in range(4):
        prompt = build_prompt(
            bm,
            enrichment,
            classification,
            extra_fetch={"fetches": extra_fetches} if extra_fetches else None,
        )
        result = call_litellm(prompt, model)
        errors = validate_curator_result(result, bm)
        if errors:
            return {"ok": False, "status": "validation_failed", "bookmark_id": bm.get("id"), "errors": errors, "curation": result, "fetches": extra_fetches}

        if result.get("status") != "needs_fetch":
            break

        req = result.get("fetch_request") or {}
        fetched = perform_fetch_request(req, bm)
        extra_fetches.append({"request": req, "result": fetched})

        # If the requested fetch could not be satisfied, stop looping and return
        # needs_fetch with the fetch audit trail. The workflow may route it out
        # of the active queue for manual/source-specific handling.
        if not fetched.get("ok"):
            return {"ok": False, "status": "needs_fetch", "bookmark_id": bm.get("id"), "curation": result, "fetches": extra_fetches}

    return apply_curated_result(result or {}, bm, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Curate/write one Karakeep bookmark into the wiki")
    parser.add_argument("--bookmark-json", required=True)
    parser.add_argument("--enrichment-json", default="{}")
    parser.add_argument("--classification-json", default="{}")
    parser.add_argument("--model", default=os.environ.get("KARAKEEP_WIKI_CURATOR_MODEL", DEFAULT_MODEL))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    bm = json.loads(args.bookmark_json)
    enrichment = json.loads(args.enrichment_json) if args.enrichment_json else {}
    classification = json.loads(args.classification_json) if args.classification_json else {}
    try:
        result = curate(bm, enrichment, classification, model=args.model, dry_run=args.dry_run)
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        result = {"ok": False, "status": "curator_error", "bookmark_id": bm.get("id"), "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
