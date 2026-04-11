---
name: openclaw-audit
description: Audit an OpenClaw installation for security, configuration, and workspace content quality. Use when the user asks to audit OpenClaw, review the agent workspace, check configuration health, verify security settings, assess workspace file quality, or identify gaps in agent setup. Covers both the technical config (openclaw.json) and the content quality of workspace files (SOUL.md, AGENTS.md, TOOLS.md, etc.).
---

# OpenClaw Audit Skill

Performs a structured audit of an OpenClaw installation. Covers two layers: (1) security and configuration correctness, and (2) workspace content quality.

## Workflow

### 1. Locate the installation

Identify the paths before starting:

```bash
# Config
cat ~/.openclaw/openclaw.json

# Workspace
ls ~/.openclaw/workspace/ 2>/dev/null || ls ~/clawd/ 2>/dev/null

# Env file
ls -la ~/.openclaw/.env 2>/dev/null
```

Ask the user for the workspace path if it differs from the defaults (`~/.openclaw/workspace/` or `~/clawd/`).

### 2. Run the security and config audit

Work through `references/security-checklist.md`. For each item:
- Run the verification command
- Record the result (pass / fail / not applicable)
- Note the remediation if it fails

Do not skip items. Some items that appear minor (e.g. file permissions) have cascading security implications.

### 3. Run the workspace content audit

Work through `references/workspace-quality.md`. Read each file and assess it against the criteria. Look for:
- Missing required sections
- Outdated or conflicting information
- Files that are present but effectively empty (template text still in place)
- Cross-file inconsistencies

### 4. Compile the report

Produce a structured report with two sections:

**Section A — Security & Config**
One row per checklist item: item name, status (✅/⚠️/❌), finding, action required.

**Section B — Workspace Content**
One row per workspace file: file, status (✅/⚠️/❌), principal gap, action required.

### 5. Prioritize and propose next steps

After the report, list the top 3-5 actions by impact. Propose a concrete execution order.

Do not automatically apply fixes. Present the report and proposed actions, then wait for confirmation before executing changes.

## Scope boundaries

This audit covers:
- `~/.openclaw/openclaw.json` — security, model config, gateway, logging, compaction, heartbeat
- `~/.openclaw/.env` or env vars — key management, file permissions
- Workspace files — SOUL.md, IDENTITY.md, AGENTS.md, WORKFLOW.md, WORKING.md, MEMORY.md, TOOLS.md, USER.md, INDEX.md, HEARTBEAT.md

Out of scope (unless explicitly requested):
- LiteLLM, MCPHub, or other adjacent infrastructure
- Content of memory files (only structure and freshness)
- Code inside skills

## References

Read `references/security-checklist.md` for the technical audit checklist with verification commands.
Read `references/workspace-quality.md` for the workspace content quality criteria.
