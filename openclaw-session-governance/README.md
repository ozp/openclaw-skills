# openclaw-session-governance

Skill for structured OpenClaw session hygiene.

It separates four concerns that are often mixed together:
- conversation binding
- session-store retention
- explicit deletion / cleanup
- actual runtime activity

## Files

- `SKILL.md` — operational workflow
- `references/session-policy.md` — local governance policy
- `scripts/session_governance.py` — repeatable audit script

## Main command

```bash
python3 scripts/session_governance.py audit --output /home/ozp/clawd/reports/session-governance-audit-YYYY-MM-DD.md
```

## Commands

Audit:
```bash
python3 scripts/session_governance.py audit --output /home/ozp/clawd/reports/session-governance-audit-YYYY-MM-DD.md
```

Cleanup preview:
```bash
python3 scripts/session_governance.py cleanup-safe --output /home/ozp/clawd/reports/session-governance-cleanup-preview-YYYY-MM-DD.md
```

Cleanup apply:
```bash
python3 scripts/session_governance.py cleanup-safe --apply --yes --output /home/ozp/clawd/reports/session-governance-cleanup-apply-YYYY-MM-DD.md
```

## Current design choice

This version remains conservative by default.
It can perform targeted deletion, but only when explicitly invoked with `--apply --yes`.
