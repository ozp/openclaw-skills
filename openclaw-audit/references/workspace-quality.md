# OpenClaw Workspace Content Quality Guide

Reference for `openclaw-audit` skill. Criteria for evaluating the content quality of each workspace file. Use alongside the security checklist.

Sub-agents inherit AGENTS.md and TOOLS.md but not SOUL.md, IDENTITY.md, or USER.md. Files that sub-agents read are therefore more critical to keep complete and current.

---

## SOUL.md

**Purpose:** Persona, tone, epistemics, operating rules, decision policy.

**Must have:**
- Core traits (explicit, actionable — not vague adjectives)
- Execution policy: when to proceed vs. pause, how to handle lists/backlogs
- Decision policy: when to escalate vs. make a choice and proceed
- Epistemics: how to handle uncertainty and unverified claims
- Communication style: direct vs. verbose, language, formatting rules

**Should have:**
- Tool posture: tool-first vs. answer-first, verification policy
- Boundaries: what the agent is and is not

**Common gaps:**
- Generic traits with no operational meaning ("helpful", "professional")
- Missing tool posture (especially important if agent uses web/exec)
- No escalation thresholds specified

---

## IDENTITY.md

**Purpose:** Name, role, surfaces, autonomy level.

**Must have:**
- Name
- Role / mission statement
- Surfaces (where the agent operates: CLI, Discord, Telegram, WhatsApp, email, etc.)

**Should have:**
- Autonomy level (advisor / operator / broad autonomy)
- Tone or personality anchor
- Preferred language(s)

**Common gaps:**
- No surfaces declared → agent makes formatting and behavior decisions blindly
- No autonomy level → ambiguity about when to act vs. ask

---

## AGENTS.md

**Purpose:** Startup ritual, memory policy, safety rules, group chat rules, heartbeat behavior. Read by all agents including sub-agents.

**Must have:**
- Session startup ritual (what to read on every session)
- Memory architecture (daily files vs. long-term MEMORY.md, how to record)
- Safety rules (destructive actions, external side effects)
- Prompt injection defense (patterns to reject, what never to output)

**Should have:**
- Group chat etiquette (when to speak, when to stay silent)
- Heartbeat behavior (what to check, when to reach out, when to stay quiet)
- Memory curation policy (when to update MEMORY.md, what qualifies)

**Watch for:**
- File too long: sub-agents receive this file on every turn. A 300-line AGENTS.md is a per-turn token cost. Consider splitting non-critical sections.
- Missing workspace isolation documentation: sub-agents use isolated workspaces by default; sharing requires explicit config.
- Injection defense present but shallow: must cover encoded content (Base64, ROT13), typoglycemia, role-play jailbreaks, not just "ignore previous instructions".

---

## WORKFLOW.md

**Purpose:** Task intake protocol, routing policy, escalation rules.

**Must have:**
- Task intake protocol (how to handle a raw list of demands)
- Escalation rules (what requires user confirmation, what does not)
- Progress protocol (how to report state after each task)

**Should have:**
- Model/provider routing policy (which tier to use for which task type)
- Cross-provider fallback rationale
- Sub-agent cleanup policy (what to do with sessions when done)

**Common gaps:**
- No model tier table (premium / upper-balanced / balanced / cheap)
- No cross-provider fallback rule → risk of entire chain failing when one provider hits quota

---

## WORKING.md

**Purpose:** Current task state, active blockers, next session objectives.

**Must have:**
- Date of last update
- Active tracks / tasks with current status
- Blockers with explicit gate or condition
- Next session objectives

**Critical quality rule:**
WORKING.md is only useful if it is current. An outdated WORKING.md misleads future sessions and creates conflicts with other files (e.g., SYSTEM-INVENTORY.md).

**Check for:**
- Resolved items still marked as pending
- Conflicts between WORKING.md status and other files (especially SYSTEM-INVENTORY.md)
- "Next session" objectives that are weeks old

**Action on stale file:** Update or archive. A stale WORKING.md is worse than no WORKING.md.

---

## MEMORY.md

**Purpose:** Curated long-term context. The distilled essence of decisions, preferences, architecture choices, and operational lessons.

**Must have:**
- At least one entry about memory system setup (how the agent stores and retrieves memory)
- Entries about key architectural decisions that are still active

**Should have:**
- Operational preferences of the user
- Key infrastructure facts that don't change often (model providers, LiteLLM setup, etc.)
- Lessons from significant incidents or mistakes

**Anti-patterns:**
- Empty or near-empty file despite months of operation → curación periodic not running
- Raw logs in MEMORY.md → these belong in `memory/YYYY-MM-DD.md`
- Outdated entries that are no longer true (stale decisions)

**Freshness check:** If the most recent entry is more than 2 weeks old and the agent has been active, curación has not been running. Flag this.

---

## TOOLS.md

**Purpose:** Environment-specific notes. Infrastructure that sub-agents need to know to operate correctly.

Sub-agents receive TOOLS.md. A nearly empty TOOLS.md means sub-agents have no knowledge of local infrastructure and cannot make informed tool decisions.

**Must have (for any production OpenClaw setup):**
- Task tracker or task management tool: paths, commands, relevant skills
- Main services the agent interacts with: name, port, how to start/stop

**Should have (for setups with adjacent infrastructure):**
- LiteLLM or model proxy: port, aliases, config location
- MCPHub or MCP endpoint: URL, how to add servers
- Browser profile name if browser is used
- OpenClaw gateway: port, management commands
- Active skills: location, what they do, any local patches

**Red flags:**
- Template text still in place ("Camera names: ...", "SSH hosts: ...")
- File has Task Tracker but nothing else despite a full infrastructure stack
- No mention of model provider config or proxy

---

## USER.md

**Purpose:** Who the user is, how to communicate with them, what they care about.

**Must have:**
- Name and preferred form of address
- Timezone (for scheduling, heartbeat timing)
- Communication style preference (direct, formal, casual, etc.)

**Should have:**
- Preferred language (especially if different from English or if the agent operates in multiple languages)
- Platforms/surfaces the user communicates through
- Professional context relevant to recurring tasks
- Typical working hours (so heartbeats respect quiet time correctly)

**Common gaps:**
- No language preference → agent may respond in the wrong language
- No platform list → agent makes formatting decisions blindly
- No professional context → agent does not understand domain-specific recurring tasks

---

## INDEX.md

**Purpose:** Central document index. Prevents documents from becoming orphaned.

**Must have:**
- List of auto-loaded files (files read every session)
- List of active working documents with status
- Archive reference

**Should have:**
- Status column (Active / Verify / Archived) for each document
- Indexed skills directory
- Notes on which documents are not auto-loaded and require explicit loading

**Maintenance check:**
- Documents with status "Verify" that have not been verified
- New files created but not indexed (especially new skills)
- Archived documents still referenced as active

---

## HEARTBEAT.md

**Purpose:** Rotating checklist for periodic agent checks. Prevents heartbeats from being no-ops.

**Must have:**
- At least 2-3 concrete check items (not template examples)
- Any temporary reminders or follow-up items

**Should have:**
- Reminder of what "productive heartbeat" means for this specific agent
- Scheduled checks tied to real obligations (e.g., "check email for UNIP deadline notices")

**Red flag:** File exists but contains only generic examples → agent will HEARTBEAT_OK with no useful work done.

---

## Consistency Checks (Cross-File)

After reviewing individual files, check for cross-file conflicts:

| Check | Files to compare |
|-------|-----------------|
| Model defaults | openclaw.json vs. WORKING.md vs. SYSTEM-INVENTORY.md |
| Pending tasks | WORKING.md vs. tasks/*.md |
| Infrastructure state | WORKING.md vs. SYSTEM-INVENTORY.md |
| Tool documentation | TOOLS.md vs. SYSTEM-INVENTORY.md |
| Skills indexed | INDEX.md vs. actual `skills/` directory |
| Memory entries | MEMORY.md vs. `memory/YYYY-MM-DD.md` (recent) |

Common conflict pattern: WORKING.md marks something as "PENDING" but SYSTEM-INVENTORY.md documents it as configured (or vice versa). One of them is outdated.
