#!/usr/bin/env python3
"""
karakeep_cron_summary.py — announce accumulated Karakeep cron progress every N successes
or immediately when errors occur.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_STATE_FILE = Path("/home/ozp/clawd/agents/karakeep/memory/cron-state.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "pending_successes": 0,
        "pending_results": [],
        "pending_errors": [],
        "last_run_at": None,
        "last_processed_at": None,
        "last_summary_at": None,
    }


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_state()
    state = default_state()
    state.update(data if isinstance(data, dict) else {})
    if not isinstance(state.get("pending_results"), list):
        state["pending_results"] = []
    if not isinstance(state.get("pending_errors"), list):
        state["pending_errors"] = []
    if not isinstance(state.get("pending_successes"), int):
        state["pending_successes"] = 0
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def should_announce(state: dict[str, Any], threshold: int) -> tuple[bool, str]:
    errors = state.get("pending_errors") or []
    if errors:
        return True, "errors"
    if int(state.get("pending_successes") or 0) >= threshold:
        return True, "threshold"
    return False, "quiet"


def build_message(state: dict[str, Any], threshold: int, reason: str) -> str:
    results = state.get("pending_results") or []
    errors = state.get("pending_errors") or []
    incorporated = sum(1 for item in results if item.get("destination_list") == "Incorporated")
    review = sum(1 for item in results if item.get("destination_list") == "Review")
    created = sum(1 for item in results if item.get("task_action") == "created")
    created_review = sum(1 for item in results if item.get("task_action") == "created_review")
    complemented = sum(1 for item in results if item.get("task_action") == "complemented")

    header = (
        f"Karakeep cron: lote de {len(results)} processado(s)."
        if reason == "threshold"
        else f"Karakeep cron: alerta operacional com {len(errors)} erro(s)."
    )

    lines = [header]
    if results:
        lines.extend(
            [
                f"- Incorporated: {incorporated}",
                f"- Review: {review}",
                f"- Tasks novas: {created + created_review}",
                f"- Tasks complementadas: {complemented}",
                "- Itens:",
            ]
        )
        for item in results:
            task_title = item.get("task_title") or "(sem task)"
            lines.append(
                f"  - {item.get('bookmark_id')} → {item.get('destination_list')} | {item.get('decision')} | {task_title}"
            )
    if errors:
        lines.append("- Erros:")
        for error in errors[-3:]:
            lines.append(f"  - {error.get('at')}: {error.get('error')}")
    if reason == "threshold":
        lines.append(f"- Critério: anúncio a cada {threshold} processados")
    return "\n".join(lines)


def reset_pending(state: dict[str, Any]) -> dict[str, Any]:
    state["pending_successes"] = 0
    state["pending_results"] = []
    state["pending_errors"] = []
    state["last_summary_at"] = utc_now()
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit a Karakeep cron summary when threshold/error criteria are met")
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--threshold", type=int, default=5)
    parser.add_argument("--human", action="store_true", help="Print HEARTBEAT_OK when no announcement is due")
    args = parser.parse_args()

    state_path = Path(args.state_file)
    state = load_state(state_path)
    announce, reason = should_announce(state, args.threshold)

    if not announce:
        payload = {"announce": False, "reason": reason, "threshold": args.threshold}
        if args.human:
            print("HEARTBEAT_OK")
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    message = build_message(state, args.threshold, reason)
    reset_pending(state)
    save_state(state_path, state)

    if args.human:
        print(message)
    else:
        print(json.dumps({"announce": True, "reason": reason, "message": message}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
