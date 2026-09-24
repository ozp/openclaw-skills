#!/usr/bin/env python3
"""Chat completion evidence capture.

Free-form chat is untrusted evidence. It can resolve to confirm buttons or a
candidate/miss record, but it never authorizes a board write.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from completion_candidates import candidate_id_for, project_candidates
from evidence_matching import (
    CONFIRM_CANDIDATE_LIMIT,
    FUZZY_REVIEW_THRESHOLD,
    build_task_catalog,
    confirmation_tier,
    extract_inline_identifiers,
    match_evidence_all,
    normalize_title,
    safe_load_task_records,
)
from task_ledger import append_event, ledger_path, new_event, read_events
from task_records import active_records
from utils import get_tasks_file

NOW_ENV = "TASK_TRACKER_CHAT_CAPTURE_NOW"
FUZZY_MATCH_LIMIT = 5
MAX_TEXT_CHARS = 4096
MAX_STORED_PHRASE_CHARS = 512
MISS_DEDUPE_WINDOW = timedelta(hours=1)
BROWSE_LIMIT = 5
_SECTION_RANK: dict[str | None, int] = {"q1": 0, "today": 0, "q2": 1, "q3": 2, "team": 3, None: 4}
_DEFAULT_SECTION_RANK = 9

# Candidate denoising/ranking heuristics only; never use them as trust gates or
# authorization to write.
NEGATED_OR_HEDGED_RE = re.compile(
    r"\b(?:didn['’]?t|did\s+not|not\s+done|not\s+finished|not\s+complete(?:d)?|"
    r"not\s+yet|haven['’]?t|have\s+not|almost|still|will\s+finish|going\s+to|"
    r"plan\s+to|hoping\s+to|unable\s+to|can['’]?t|cannot|won['’]?t)\b",
    re.IGNORECASE,
)
QUOTE_OR_FORWARD_RE = re.compile(
    r"^\s*(?:>+|[\"'“”]|forwarded(?:\s+from)?|fwd|quote|quoted)\b|"
    r"^\s*[<]?[\w .@-]{1,40}[>]?\s*:(?!:)|"
    r"\b(?:forwarded(?:\s+from)?|fwd|quote|quoted)\b|\b(?:wrote|said):|»",
    re.IGNORECASE,
)
LEADING_EVIDENCE_PREFIX_RE = re.compile(
    r"^\s*(?:(?:i|we)\s+)?(?:just\s+|finally\s+|also\s+)?"
    r"(?:done(?:\s+with)?|finished|finish|wrapped\s+up|shipped|completed|"
    r"complete|did|closed\s+out|close\s+out|closed|sent|merged|resolved)\b\s*",
    re.IGNORECASE,
)
RECURRING_MARKER_RE = re.compile(r"\brecur\s*::", re.IGNORECASE)


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def current_time() -> datetime:
    override = os.getenv(NOW_ENV)
    if override:
        parsed = parse_timestamp(override)
        if parsed is not None:
            return parsed
    return datetime.now(timezone.utc)


def _capture_ledger_path(personal: bool = False):
    tasks_file, _fmt = get_tasks_file(personal)
    return ledger_path(tasks_file)


def _stored_phrase(text: str) -> str:
    phrase = " ".join((text or "").split()).strip()
    if len(phrase) > MAX_STORED_PHRASE_CHARS:
        phrase = phrase[:MAX_STORED_PHRASE_CHARS].rstrip()
    return phrase


def _collapse_statement(text: str) -> str:
    return " ".join(line.strip() for line in text.splitlines() if line.strip()).strip()


def _strip_transport_markers(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = re.sub(r"^\s*>+\s?", "", line).strip()
        stripped = re.sub(r"^\s*(?:forwarded(?:\s+from)?|fwd|quote|quoted)\b[:\s-]*", "", stripped, flags=re.I)
        stripped = stripped.strip("\"'“” ")
        if stripped:
            lines.append(stripped)
    return " ".join(lines).strip()


def _phrase_for_matching(text: str) -> str:
    bounded = (text or "")[:MAX_TEXT_CHARS]
    cleaned = _collapse_statement(_strip_transport_markers(bounded))
    cleaned = re.sub(r"^\s*scratch\s+that[,.;:-]?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^\s*\[[^\]\n]{1,40}\]\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(
        r"^\s*(?:per|via|from|according\s+to)\s+[A-Za-z][\w.@/-]*(?:\s+[A-Za-z][\w.@/-]*){0,3}\s*[,:\-]\s*",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(
        r"^\s*(?!(?:i|we|you)\b)[A-Za-z][\w.@-]*(?:\s+[A-Za-z][\w.@-]*){0,3}\s+"
        r"(?:said|told\s+me|wrote)\b\s*",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"^\s*[<]?[\w .@-]{1,40}[>]?\s*:(?!:)\s*", "", cleaned, flags=re.I)
    cleaned = LEADING_EVIDENCE_PREFIX_RE.sub("", cleaned, count=1)
    return _stored_phrase(cleaned.strip(" \t\r\n-:;,.!✅"))


def _line_for_phrase(phrase: str, raw_text: str) -> dict[str, Any]:
    identifiers = extract_inline_identifiers(raw_text)
    identifiers_from_phrase = extract_inline_identifiers(phrase)
    exact_identifiers = identifiers["exact"] | identifiers_from_phrase["exact"]
    fallback_identifiers = identifiers["fallback"] | identifiers_from_phrase["fallback"]
    return {
        "raw_line": _stored_phrase(phrase),
        "title": phrase,
        "normalized_title": normalize_title(phrase),
        "exact_identifiers": exact_identifiers,
        "fallback_identifiers": fallback_identifiers,
    }


def _is_reviewable_match(match: dict[str, Any]) -> bool:
    match_types = set(match.get("match_types") or [match.get("match_type")])
    return bool(
        match_types & {"exact-id-or-link", "issue-number-fallback", "normalized-title"}
        or float(match.get("score") or 0.0) >= FUZZY_REVIEW_THRESHOLD
    )


def _best_reviewable(matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    for match in matches:
        if _is_reviewable_match(match):
            return match
    return None


def _match_text(text: str, catalog: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    phrase = _phrase_for_matching(text)
    if not phrase:
        phrase = _stored_phrase(text)
    if not phrase:
        return "", []
    match_payload = match_evidence_all(
        _line_for_phrase(phrase, text),
        catalog,
        fuzzy_limit=FUZZY_MATCH_LIMIT,
    )
    return phrase, match_payload["matches"]


def _record_is_recurring(record: Any) -> bool:
    return bool(getattr(record, "recur", None) or RECURRING_MARKER_RE.search(getattr(record, "raw_line", "") or ""))


def _confirm_catalog(personal: bool = False) -> list[dict[str, Any]]:
    catalog = []
    for item in build_task_catalog(safe_load_task_records(personal)):
        record = item.get("record")
        if record is None:
            continue
        if getattr(record, "is_objective", False) or _record_is_recurring(record):
            continue
        canonical = item.get("canonical") or {}
        if not canonical.get("task_id"):
            continue
        catalog.append(item)
    return catalog


def resolve_for_confirm(hint: str | None, *, personal: bool = False) -> dict[str, Any]:
    """Resolve a natural-language hint to button candidates.

    The result only tells the caller which confirm buttons to post. It never
    authorizes or performs completion.
    """
    phrase, matches = _match_text(hint or "", _confirm_catalog(personal))
    if not phrase:
        return {"ok": True, "tier": "none", "phrase": "", "candidates": [], "matches": []}
    tiered = confirmation_tier(matches, limit=CONFIRM_CANDIDATE_LIMIT)
    return {
        "ok": True,
        "tier": tiered["tier"],
        "phrase": phrase,
        "candidates": tiered["candidates"],
        "matches": matches,
    }


def _due_sort_value(value: str | None) -> tuple[int, str]:
    if not value:
        return (1, "")
    return (0, value)


def _browse_sort_key(record: Any) -> tuple[int, tuple[int, str], str, int]:
    section_rank = _SECTION_RANK.get(getattr(record, "section", None), _DEFAULT_SECTION_RANK)
    task_id = getattr(record, "canonical_id", None) or getattr(record, "fallback_id", "") or ""
    return (
        section_rank,
        _due_sort_value(getattr(record, "due", None)),
        task_id,
        int(getattr(record, "line_number", None) or 0),
    )


def open_tasks_for_browse(
    *,
    personal: bool = False,
    page: int = 1,
    limit: int = BROWSE_LIMIT,
) -> dict[str, Any]:
    """Return a bounded, read-only open-task page with Done buttons."""
    import telegram_buttons

    page = max(1, int(page or 1))
    limit = max(1, min(int(limit or BROWSE_LIMIT), 10))
    records = [
        record
        for record in active_records(safe_load_task_records(personal))
        if not getattr(record, "is_objective", False)
        and not _record_is_recurring(record)
        and getattr(record, "canonical_id", None)
    ]
    ordered = sorted(records, key=_browse_sort_key)
    start = (page - 1) * limit
    selected = ordered[start:start + limit]
    items = []
    for record in selected:
        task_id = str(getattr(record, "canonical_id", "") or "")
        button = telegram_buttons.done_button(task_id)
        items.append(
            {
                "task_id": task_id,
                "title": getattr(record, "title", "") or "(untitled task)",
                "section": getattr(record, "section", None),
                "due": getattr(record, "due", None),
                "buttons": [button] if button else [],
            }
        )
    return {
        "ok": True,
        "total": len(ordered),
        "page": page,
        "limit": limit,
        "items": items,
        "has_more": start + len(items) < len(ordered),
        "next_page": page + 1 if start + len(items) < len(ordered) else None,
    }


def _candidate_payload(
    *,
    phrase: str,
    source: dict[str, Any],
    matches: list[dict[str, Any]],
    decision_reason: str,
) -> dict[str, Any]:
    best = _best_reviewable(matches)
    best_task = (best or {}).get("canonical_task") or {}
    safe_phrase = _stored_phrase(best_task.get("title") or phrase)
    match_metadata: dict[str, Any] = {
        "matched_task_id": None,
        "score": 0.0,
        "decision": "needs-review",
        "match_type": "none",
        "decision_reason": decision_reason,
    }
    suggested_match = None
    if best:
        suggested_match = best.get("canonical_task")
        match_metadata.update(
            {
                "matched_task_id": best.get("matched_task_id"),
                "score": best.get("score"),
                "match_type": best.get("match_type"),
                "match_types": best.get("match_types") or [best.get("match_type")],
            }
        )

    candidate_id = candidate_id_for(source, safe_phrase)
    candidate = {
        "candidate_id": candidate_id,
        "status": "new",
        "source": source,
        "raw_summary": safe_phrase,
        "summary": safe_phrase,
        "normalized_summary": normalize_title(safe_phrase),
        "suggested_match": suggested_match,
        "matches": matches,
        "match_metadata": match_metadata,
        "matched_task_id": match_metadata.get("matched_task_id"),
        "review_required": True,
    }
    if match_metadata.get("match_type") == "exact-id-or-link" and match_metadata.get("matched_task_id"):
        candidate["confirmable_task_id"] = match_metadata["matched_task_id"]
        # Skips match review; still requires user confirmation; never auto-writes.
        candidate["review_required"] = False
    return candidate


def _record_candidate(
    *,
    phrase: str,
    source: dict[str, Any],
    matches: list[dict[str, Any]],
    decision_reason: str,
    personal: bool,
) -> dict[str, Any]:
    candidate = _candidate_payload(
        phrase=phrase,
        source=source,
        matches=matches,
        decision_reason=decision_reason,
    )
    existing = {
        item["candidate_id"]: item
        for item in project_candidates(include_terminal=True, personal=personal)
    }
    candidate_id = candidate["candidate_id"]
    if candidate_id in existing:
        return {"candidate": existing[candidate_id], "created": False}

    append_event(
        new_event(
            "candidate_seen",
            task_id=candidate_id,
            source="chat_capture",
            metadata={"candidate": candidate},
        ),
        path=_capture_ledger_path(personal),
    )
    return {"candidate": candidate, "created": True}


def _event_timestamp(event: dict[str, Any]):
    timestamp = str(event.get("timestamp") or "")
    parsed = parse_timestamp(timestamp)
    if parsed is None:
        raise ValueError("invalid event timestamp")
    return parsed


def _record_capture_miss(
    *,
    phrase: str,
    source: dict[str, Any],
    matches: list[dict[str, Any]],
    personal: bool,
    reason: str,
) -> dict[str, Any]:
    safe_phrase = _stored_phrase(phrase)
    normalized_phrase = normalize_title(safe_phrase)
    now = current_time()
    for event in reversed(read_events(_capture_ledger_path(personal), strict=True)):
        if event.get("event_type") != "capture_miss":
            continue
        metadata = event.get("metadata") or {}
        if metadata.get("normalized_phrase") != normalized_phrase:
            continue
        try:
            event_time = _event_timestamp(event)
        except ValueError:
            continue
        if now - event_time <= MISS_DEDUPE_WINDOW:
            return event

    event = new_event(
        "capture_miss",
        source="chat_capture",
        metadata={
            "source": source,
            "phrase": safe_phrase,
            "normalized_phrase": normalized_phrase,
            "matches": matches,
            "reason": reason,
        },
    )
    append_event(event, path=_capture_ledger_path(personal))
    return event


def _source_pointer(
    *,
    source: str,
    sender: str | None,
    channel: str | None,
    message_id: str | None,
    timestamp: str | None,
) -> dict[str, Any]:
    pointer: dict[str, Any] = {
        "type": "chat",
        "channel": channel or source,
        # Chat candidates keep line_number for parity with file-source candidate schemas.
        "line_number": 1,
        "timestamp": timestamp or current_time().isoformat(),
    }
    if sender:
        pointer["sender"] = sender
    if message_id:
        pointer["message_id"] = message_id
    return pointer


def _rollup_action(actions: list[dict[str, Any]]) -> str:
    if not actions:
        return "miss"
    if len(actions) == 1:
        return str(actions[0]["action"])
    if all(action["action"] == "auto" for action in actions):
        return "auto"
    if all(action["action"] == "miss" for action in actions):
        return "miss"
    return "candidate"


def _quality_reason(text: str) -> str | None:
    if NEGATED_OR_HEDGED_RE.search(text or ""):
        return "negated-or-hedged"
    if QUOTE_OR_FORWARD_RE.search(text or ""):
        return "quoted-or-forwarded"
    return None


def _candidate_or_miss_action(
    *,
    text: str,
    catalog: list[dict[str, Any]],
    source_pointer: dict[str, Any],
    decision_reason: str,
    personal: bool,
    suppress_negated_candidate: bool = True,
) -> dict[str, Any]:
    phrase, matches = _match_text(text, catalog)
    reason = _quality_reason(text) or decision_reason
    best = _best_reviewable(matches)

    if not phrase:
        phrase = "unparsed chat capture"
    if best is None or (suppress_negated_candidate and reason in ("negated-or-hedged", "quoted-or-forwarded")):
        miss = _record_capture_miss(
            phrase=phrase,
            source=source_pointer,
            matches=matches,
            personal=personal,
            reason=reason if best is not None else "no-match",
        )
        return {
            "action": "miss",
            "phrase": phrase,
            "event_id": miss["event_id"],
            "matches": matches,
            "decision_reason": reason if best is not None else "no-match",
        }

    recorded = _record_candidate(
        phrase=phrase,
        source=source_pointer,
        matches=matches,
        decision_reason=reason,
        personal=personal,
    )
    candidate = recorded["candidate"]
    return {
        "action": "candidate",
        "phrase": phrase,
        "task_id": candidate.get("matched_task_id"),
        "candidate_id": candidate["candidate_id"],
        "candidate_created": recorded["created"],
        "candidate": candidate,
        "matches": matches,
        "decision_reason": reason,
    }


def _merge_single_action(payload: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    if len(actions) != 1:
        return
    for key, value in actions[0].items():
        payload[key] = value


def record_deferred_candidate(
    text: str | None,
    *,
    sender: str | None = None,
    source: str = "chat",
    channel: str | None = None,
    message_id: str | None = None,
    personal: bool = False,
    decision_reason: str = "confirm-prompt-posted",
) -> dict[str, Any]:
    # Use the SAME chat-completable catalog the confirm resolver uses (excludes recurring and
    # objective tasks). A deferred candidate must point only at a task a chat tap can actually
    # complete, so the two lanes agree on what "open" means.
    catalog = _confirm_catalog(personal)
    source_pointer = _source_pointer(
        source=source,
        sender=sender,
        channel=channel,
        message_id=message_id,
        timestamp=None,
    )
    return _candidate_or_miss_action(
        text=text or "",
        catalog=catalog,
        source_pointer=source_pointer,
        decision_reason=decision_reason,
        personal=personal,
        suppress_negated_candidate=False,
    )


def capture_text(
    text: str | None = None,
    *,
    sender: str | None = None,
    source: str = "chat",
    channel: str | None = None,
    message_id: str | None = None,
    personal: bool = False,
) -> dict[str, Any]:
    catalog = build_task_catalog(safe_load_task_records(personal))
    actions: list[dict[str, Any]] = []

    source_pointer = _source_pointer(
        source=source,
        sender=sender,
        channel=channel,
        message_id=message_id,
        timestamp=None,
    )
    actions.append(
        _candidate_or_miss_action(
            text=text or "",
            catalog=catalog,
            source_pointer=source_pointer,
            decision_reason="raw-chat",
            personal=personal,
        )
    )

    payload: dict[str, Any] = {
        "ok": True,
        "action": _rollup_action(actions),
        "actions": actions,
    }
    _merge_single_action(payload, actions)
    return payload
