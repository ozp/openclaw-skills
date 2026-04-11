---
name: openclaw-session-governance
description: Audit and govern OpenClaw session lifecycle in a structured way. Use when reviewing session sprawl, distinguishing binding vs retention vs deletion, classifying persistent versus ephemeral sessions, generating cleanup candidate reports, or implementing recurring session hygiene for a local OpenClaw environment.
---

# OpenClaw Session Governance

Use this skill to manage session lifecycle without conflating routing, retention, and real deletion.

## When to use

Trigger this skill when the user asks to:
- clean up old OpenClaw sessions
- reduce session sprawl
- understand why sessions still appear active
- implement session retention policy
- review recurring workers versus ephemeral runs
- audit sessions before deleting anything

## Core rule

Do not treat these as the same thing:
1. conversation binding
2. session-store retention
3. explicit deletion / cleanup
4. currently executing work

Always identify which layer is actually being discussed before proposing a fix.

## Workflow

### 1. Collect runtime evidence

Gather current state first:

```bash
openclaw status --deep
openclaw sessions --all-agents --json
openclaw sessions cleanup --all-agents --dry-run --json
```

If the user is discussing a specific residue incident, also capture the implicated session keys and any related report paths.

### 2. Apply the local policy

Read `references/session-policy.md`.

Classify every relevant session into one of four buckets:
- **persistent**
- **recurring_worker**
- **ephemeral_completed**
- **review_required**

Use the local policy defaults unless the user explicitly changes them.

### 3. Generate an audit report before mutating

Run:

```bash
python3 scripts/session_governance.py audit \
  --output /home/ozp/clawd/reports/session-governance-audit-YYYY-MM-DD.md
```

The audit should summarize:
- total visible sessions
- per-agent counts
- dry-run maintenance result
- keep list
- review list
- cleanup-candidate list
- reasoning for each classification

Do not delete anything on the first pass unless the user explicitly asked for enforcement.

### 4. Cleanup policy

Default retention logic:
- persistent: keep
- recurring worker base sessions: keep
- ephemeral completed sessions: candidate after 72h
- orphaned / inconsistent sessions: manual review first

Use cleanup as a two-stage flow:
1. generate candidates
2. enforce only after review or explicit approval

### 5. Enforcement options

This skill supports three operational modes:
- **maintenance preview** using `openclaw sessions cleanup --dry-run`
- **governance audit** using `scripts/session_governance.py audit`
- **cleanup-safe** using `scripts/session_governance.py cleanup-safe`

`cleanup-safe` is intentionally guarded:
- preview mode lists safe candidates only
- apply mode requires `--apply --yes`
- targeted deletion uses `openclaw gateway call sessions.delete` per session key

Do not assume store maintenance equals targeted deletion. They are separate mechanisms.

## Local defaults

This workspace currently treats these as protected by default:
- `agent:main:main`
- `agent:karakeep:karakeep-cron-worker`
- `agent:sentinel:main`

These require manual review by default:
- `agent:karakeep:karakeep-cron-summary`
- `agent:mineru:main`
- unclear lead / mc session bases

Typical cleanup candidates:
- `:subagent:` sessions older than threshold
- `:cron:...:run:` sessions older than threshold
- transient provider sessions such as `:openai:` older than threshold

## Outputs

Preferred outputs:
- a markdown audit report under `/home/ozp/clawd/reports/`
- a markdown cleanup preview/result report under `/home/ozp/clawd/reports/`
- a short operator summary with counts and next action

## Recommended commands

Audit:

```bash
python3 scripts/session_governance.py audit \
  --output /home/ozp/clawd/reports/session-governance-audit-YYYY-MM-DD.md
```

Cleanup preview:

```bash
python3 scripts/session_governance.py cleanup-safe \
  --output /home/ozp/clawd/reports/session-governance-cleanup-preview-YYYY-MM-DD.md
```

Cleanup apply:

```bash
python3 scripts/session_governance.py cleanup-safe \
  --apply --yes \
  --output /home/ozp/clawd/reports/session-governance-cleanup-apply-YYYY-MM-DD.md
```

## References

Read `references/session-policy.md` for the policy model and operational guidance.
Use `scripts/session_governance.py` for repeatable audit runs.
