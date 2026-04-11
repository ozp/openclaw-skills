#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROTECTED_EXACT_KEYS = {
    "agent:main:main",
    "agent:karakeep:karakeep-cron-worker",
    "agent:sentinel:main",
}

REVIEW_EXACT_KEYS = {
    "agent:karakeep:karakeep-cron-summary",
    "agent:mineru:main",
}

CLEANUP_PATTERNS = [
    re.compile(r":subagent:"),
    re.compile(r":openai:"),
    re.compile(r":cron:[^:]+:run:"),
]

PERSISTENT_MAIN_RE = re.compile(r"^agent:(?P<agent>[^:]+):main$")


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


def run_json(cmd: list[str]) -> dict:
    completed = run_cmd(cmd)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(cmd)}\n{completed.stderr.strip()}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from command: {' '.join(cmd)}\n{exc}\nSTDOUT:\n{completed.stdout[:1000]}") from exc


def iso_from_ms(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def age_hours(age_ms: int) -> float:
    return age_ms / 1000 / 60 / 60


def classify(session: dict, threshold_hours: float) -> tuple[str, str]:
    key = session["key"]
    age_h = age_hours(session.get("ageMs", 0))
    agent_id = session.get("agentId", "unknown")

    if key in PROTECTED_EXACT_KEYS:
        if "cron-worker" in key:
            return "recurring_worker", "protected recurring worker base"
        return "persistent", "protected exact key"

    if key in REVIEW_EXACT_KEYS:
        return "review_required", "review-first exact key"

    for pattern in CLEANUP_PATTERNS:
        if pattern.search(key):
            if age_h >= threshold_hours:
                return "ephemeral_completed", f"matches cleanup pattern and age {age_h:.1f}h >= {threshold_hours:.1f}h"
            return "review_required", f"matches cleanup pattern but age {age_h:.1f}h < {threshold_hours:.1f}h"

    main_match = PERSISTENT_MAIN_RE.match(key)
    if main_match:
        if agent_id in {"main", "sentinel"}:
            return "persistent", "known durable main session"
        return "review_required", "main/base session for non-protected agent"

    if key.endswith(":cron-summary"):
        return "review_required", "summary helper session"

    return "review_required", "no safe automatic rule matched"


def load_snapshot(threshold_hours: float) -> tuple[list[dict], dict]:
    sessions_payload = run_json(["openclaw", "sessions", "--all-agents", "--json"])
    maintenance_payload = run_json(["openclaw", "sessions", "cleanup", "--all-agents", "--dry-run", "--json"])
    sessions = []
    for session in sessions_payload.get("sessions", []):
        category, reason = classify(session, threshold_hours)
        item = dict(session)
        item["category"] = category
        item["reason"] = reason
        item["ageHours"] = round(age_hours(session.get("ageMs", 0)), 1)
        item["updatedAtIso"] = iso_from_ms(session["updatedAt"])
        sessions.append(item)
    return sessions, maintenance_payload


def build_markdown_report(classified: list[dict], maintenance_payload: dict, threshold_hours: float) -> str:
    category_counts = Counter(item["category"] for item in classified)
    agent_counts = Counter(item.get("agentId", "unknown") for item in classified)
    by_category = defaultdict(list)
    for item in classified:
        by_category[item["category"]].append(item)

    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    lines = []
    lines.append("# Session Governance Audit")
    lines.append("")
    lines.append(f"Generated: {now}")
    lines.append(f"Safe cleanup threshold: {threshold_hours:.1f} hours")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total visible sessions: {len(classified)}")
    lines.append(f"- Persistent: {category_counts['persistent']}")
    lines.append(f"- Recurring worker: {category_counts['recurring_worker']}")
    lines.append(f"- Cleanup candidates: {category_counts['ephemeral_completed']}")
    lines.append(f"- Review required: {category_counts['review_required']}")
    lines.append("")
    lines.append("## Per-agent counts")
    lines.append("")
    for agent_id, count in sorted(agent_counts.items()):
        lines.append(f"- {agent_id}: {count}")
    lines.append("")
    lines.append("## Store maintenance preview")
    lines.append("")
    for store in maintenance_payload.get("stores", []):
        lines.append(
            f"- {store['agentId']}: before={store['beforeCount']}, after={store['afterCount']}, "
            f"pruned={store['pruned']}, capped={store['capped']}, missing={store['missing']}, wouldMutate={store['wouldMutate']}"
        )
    lines.append("")

    section_titles = {
        "persistent": "Persistent",
        "recurring_worker": "Recurring worker",
        "ephemeral_completed": "Cleanup candidates",
        "review_required": "Review required",
    }

    for category in ["persistent", "recurring_worker", "ephemeral_completed", "review_required"]:
        lines.append(f"## {section_titles[category]}")
        lines.append("")
        items = sorted(by_category.get(category, []), key=lambda x: x["ageMs"], reverse=True)
        if not items:
            lines.append("- None")
            lines.append("")
            continue
        for item in items:
            lines.append(
                f"- `{item['key']}` | agent={item.get('agentId','unknown')} | age={item['ageHours']}h | "
                f"updated={item['updatedAtIso']} | reason={item['reason']}"
            )
        lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- This audit is conservative. Review-required sessions were intentionally not auto-promoted to cleanup.")
    lines.append("- Store maintenance preview reflects OpenClaw maintenance rules, not targeted deletion policy.")
    lines.append("- Safe deletion, when explicitly enabled, uses `openclaw gateway call sessions.delete` per session key.")
    lines.append("")
    return "\n".join(lines)


def build_cleanup_report(candidates: list[dict], threshold_hours: float, applied: bool, delete_results: list[dict] | None = None) -> str:
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    lines = []
    lines.append("# Session Governance Cleanup")
    lines.append("")
    lines.append(f"Generated: {now}")
    lines.append(f"Safe cleanup threshold: {threshold_hours:.1f} hours")
    lines.append(f"Mode: {'apply' if applied else 'preview'}")
    lines.append("")
    lines.append(f"- Candidate count: {len(candidates)}")
    lines.append("")
    lines.append("## Candidates")
    lines.append("")
    if not candidates:
        lines.append("- None")
    else:
        for item in candidates:
            lines.append(
                f"- `{item['key']}` | agent={item.get('agentId','unknown')} | age={item['ageHours']}h | updated={item['updatedAtIso']}"
            )
    lines.append("")
    if delete_results is not None:
        lines.append("## Delete results")
        lines.append("")
        if not delete_results:
            lines.append("- No delete attempts executed")
        else:
            for result in delete_results:
                lines.append(
                    f"- `{result['key']}` | ok={result['ok']} | deleted={result.get('deleted')} | note={result.get('note','')}"
                )
        lines.append("")
    return "\n".join(lines)


def cmd_audit(args: argparse.Namespace) -> int:
    classified, maintenance_payload = load_snapshot(args.safe_age_hours)
    report = build_markdown_report(classified, maintenance_payload, args.safe_age_hours)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    category_counts = Counter(item["category"] for item in classified)
    print(f"Wrote report: {output_path}")
    print(
        "Summary: "
        f"total={len(classified)}, "
        f"persistent={category_counts['persistent']}, "
        f"recurring_worker={category_counts['recurring_worker']}, "
        f"cleanup_candidates={category_counts['ephemeral_completed']}, "
        f"review_required={category_counts['review_required']}"
    )
    return 0


def delete_session_key(key: str) -> dict:
    params = json.dumps({"key": key})
    completed = run_cmd(["openclaw", "gateway", "call", "sessions.delete", "--json", "--params", params, "--timeout", "20000"])
    if completed.returncode != 0:
        return {"key": key, "ok": False, "deleted": False, "note": completed.stderr.strip() or completed.stdout.strip()}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"key": key, "ok": False, "deleted": False, "note": f"non-json response: {completed.stdout[:300]}"}
    return {"key": key, "ok": True, "deleted": payload.get("deleted", False), "note": payload.get("message", "")}


def cmd_cleanup_safe(args: argparse.Namespace) -> int:
    classified, _maintenance_payload = load_snapshot(args.safe_age_hours)
    candidates = [item for item in classified if item["category"] == "ephemeral_completed"]
    candidates.sort(key=lambda x: x["ageMs"], reverse=True)

    if args.limit is not None:
        candidates = candidates[: args.limit]

    delete_results = None
    applied = False
    if args.apply:
        if not args.yes:
            raise RuntimeError("Refusing destructive cleanup without --yes")
        delete_results = [delete_session_key(item["key"]) for item in candidates]
        applied = True

    if args.output:
        report = build_cleanup_report(candidates, args.safe_age_hours, applied, delete_results)
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"Wrote cleanup report: {output_path}")

    if args.json:
        payload = {
            "thresholdHours": args.safe_age_hours,
            "applied": applied,
            "candidateCount": len(candidates),
            "candidates": candidates,
            "deleteResults": delete_results,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Cleanup-safe {'apply' if applied else 'preview'}: {len(candidates)} candidate(s)")
        for item in candidates:
            print(f"- {item['key']} | age={item['ageHours']}h | agent={item.get('agentId','unknown')}")
        if delete_results is not None:
            print("Delete results:")
            for result in delete_results:
                print(f"- {result['key']} | ok={result['ok']} | deleted={result.get('deleted')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit OpenClaw session governance state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="Generate a markdown governance audit report.")
    audit.add_argument("--output", required=True, help="Path to markdown report output.")
    audit.add_argument("--safe-age-hours", type=float, default=72.0, help="Age threshold for safe cleanup candidates.")
    audit.set_defaults(func=cmd_audit)

    cleanup = subparsers.add_parser("cleanup-safe", help="Preview or apply safe cleanup candidates.")
    cleanup.add_argument("--safe-age-hours", type=float, default=72.0, help="Age threshold for safe cleanup candidates.")
    cleanup.add_argument("--limit", type=int, help="Optional max number of candidates to include.")
    cleanup.add_argument("--output", help="Optional path to markdown cleanup report.")
    cleanup.add_argument("--apply", action="store_true", help="Apply targeted deletion to safe candidates.")
    cleanup.add_argument("--yes", action="store_true", help="Confirm destructive cleanup when using --apply.")
    cleanup.add_argument("--json", action="store_true", help="Emit JSON output.")
    cleanup.set_defaults(func=cmd_cleanup_safe)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
