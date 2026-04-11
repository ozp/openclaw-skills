---
name: openclaw-update
description: "Update OpenClaw gateway and CLI to the latest version. Use when: (1) User asks to 'atualizar openclaw' or 'update openclaw', (2) New OpenClaw version is available, (3) User wants to upgrade OpenClaw, (4) Post-update health check is needed, (5) User wants to run doctor or verify installation health."
metadata: {"openclaw":{"emoji":"🔄","requires":{"cli":["openclaw"]},"install":[{"id":"verify-openclaw","kind":"check","label":"Verify openclaw CLI is available"}]}}
---

# OpenClaw Update

Standard update workflow for OpenClaw gateway and CLI.

## When to Use

Use this skill when the user asks to:

- Update OpenClaw to the latest version
- Run `openclaw update` workflow
- Verify installation health after updates
- Run doctor and gateway restart sequence

## Update Method

The standard OpenClaw update consists of 3 steps:

1. **Update** - `openclaw update` (detects install type, fetches latest, runs doctor)
2. **Verify** - `openclaw doctor` (migrates config, audits policies, checks health)
3. **Restart & Validate** - `openclaw gateway restart && openclaw health`

## Quick Start

Run the bundled script from the skill directory:

```bash
cd /home/ozp/clawd/skills/openclaw-update
bash scripts/update.sh
```

Or run manually:

```bash
# Step 1: Update
openclaw update

# Step 2: Doctor (automatically runs with update, but can run manually)
openclaw doctor

# Step 3: Restart gateway
openclaw gateway restart

# Step 4: Verify health
openclaw health
```

## Auto-updater Alternative

For automatic updates without confirmation, enable auto-updater in `~/.openclaw/openclaw.json`:

```json5
{
  update: {
    channel: "stable",
    auto: {
      enabled: true,
      stableDelayHours: 6,
    },
  },
}
```

This skill provides controlled manual updates with verification at each step.
