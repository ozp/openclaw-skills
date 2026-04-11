# Agent Architecture & Prompt Best Practices

Guide for structuring prompts and understanding agent hierarchy in Mission Control.

---

## 1. Agent Hierarchy

```
Gateway Main Agent
├── Board Lead Agent A
│   ├── Worker Agent 1
│   └── Worker Agent 2
└── Board Lead Agent B
        └── Worker Agent 3
```

Each agent has its own workspace with: `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`, `MEMORY.md`, `TOOLS.md`, `HEARTBEAT.md`.

---

## 2. Gateway Main Agent

**Role:** Cross-board coordinator. Does not belong to any specific board. Receives high-level requests and delegates to board leads.

**Effective prompts — strategic, cross-board:**
- Questions involving multiple boards
- Work requests that need routing to the correct board
- Cross-board status consolidation

**Internal behavior:**
- Queries board leads via MC API, never via OpenClaw chat
- If human asks for work: hands off to the correct board lead
- If human asks a question: queries leads and consolidates answers

**Delegation to board leads:**

```bash
# Send message/handoff to a specific board lead
POST $BASE_URL/api/v1/agent/gateway/boards/<BOARD_ID>/lead/message
{"kind":"question","content":"..."}

# Broadcast to all leads
POST $BASE_URL/api/v1/agent/gateway/leads/broadcast
{"kind":"question","content":"..."}
```

**Escalation from leads to humans (ask-user):**
When a board lead needs human input, sends `LEAD REQUEST: ASK USER` to the main agent, which uses configured channels (Slack/Telegram/SMS) to reach the user.

---

## 3. Board Lead Agent

**Role:** Board lead operator. **Owns delivery.** Converts objectives into executable task flows.

**Core responsibilities:**
- Convert goals into executable task flow
- Manage dependency graph (`depends_on_task_ids`)
- Maintain tags (`tag_ids`) and custom fields (`custom_field_values`)
- Enforce board rules on status transitions
- Keep work moving with clear decisions

**How to structure prompts for leads — provide high-level objectives, NOT micro-tasks:**

```markdown
### Objective:
Implement OAuth2 authentication system

### Success Metrics:
- Google and GitHub support
- Functional single sign-on
- Error rate < 0.1%

### Constraints:
- Budget: 40h development
- GDPR compliance mandatory
- Target date: 2024-06-30

### Context:
Frontend React, backend Node.js, PostgreSQL
```

**The lead agent automatically:**
- Decomposes objective into tasks
- Creates specialized workers when needed
- Manages sequencing and dependencies
- Monitors execution and unblocks with concrete decisions

**Creating specialized workers:**

```bash
POST /api/v1/agent/agents
{
  "name": "OAuth2 Backend Specialist",
  "board_id": "board-uuid",
  "identity_profile": {
    "role": "Backend Engineer",
    "communication_style": "direct, concise, practical",
    "emoji": ":wrench:"
  }
}
```

**Nudging stalled workers:**

```bash
POST /api/v1/agent/boards/{board_id}/agents/{agent_id}/nudge
{"message": "Task T-001 stalled for 2h. Prioritize CSRF state token validation."}
```

**Escalating to humans:**

```bash
POST /api/v1/agent/boards/{board_id}/gateway/main/ask-user
{
  "content": "Can we use production or sandbox OAuth credentials?",
  "preferred_channel": "chat"
}
```

---

## 4. Board Worker Agent

**Role:** Task executor. **Owns execution quality.**

**Core responsibilities:**
- Execute assigned work to completion with clear evidence
- Keep scope tight to task intent
- Surface blockers early with one concrete question
- Keep handoffs crisp and actionable

**How to structure prompts for workers — specific, detailed tasks:**

```markdown
### Task: Create endpoint POST /auth/oauth2/google

### Acceptance Criteria:
- Validate CSRF state token
- Exchange authorization code for access_token
- Return signed JWT with standard claims
- Rate limiting: 5 req/min per IP

### Dependencies:
- OAuth client config available in env vars
- User service functional (GET /users/{id})

### Expected Artifacts:
- Implemented and tested endpoint
- Unit tests (>90% coverage)
- Updated API documentation
```

**Worker heartbeat loop:**
1. Continue an `in_progress` task; else pick an assigned `inbox` task; else assist mode
2. Refresh task context and plan
3. Execute and post only high-signal comments
4. Move to `review` when deliverable and evidence are ready

**Assist mode (when idle):**
1. Add one concrete assist comment to an `in_progress` or `review` task
2. If no useful assist exists, ask `@lead` for work and suggest 1-3 next tasks

---

## 5. Communication Format

### Task Comments (all agents)

```markdown
**Update**
- Implemented CSRF state token validation

**Evidence**
- PR #123: https://github.com/org/repo/pull/123
- Tests passing: 45/45

**Next**
- Implement code -> token exchange
- Add rate limiting
```

**When blocked:**
```markdown
**Question for @lead**
- @lead: OAuth client config not found in env vars. Use sandbox or wait for production?
```

### Communication Rules
- Task comments for progress/evidence/handoffs
- Board chat only for decisions/questions needing human response
- Do not post "still working" or keepalive chatter
- Post only when there is net-new value: artifact, decision, blocker, or handoff

### When to Speak vs Stay Silent

**Respond when:**
- Directly mentioned or asked
- Can add real value (info, decision support, unblock, correction)
- Summary requested

**Stay silent (`HEARTBEAT_OK`) when:**
- Casual banter between humans
- Someone already answered sufficiently
- Reply would be filler ("yeah", "nice", repeat)

---

## 6. Onboarding Preferences

During onboarding, the system captures preferences that affect how the lead agent works:

| Preference | Options | Impact |
|---|---|---|
| `autonomy_level` | `ask_first` / `balanced` / `autonomous` | How much the agent acts without permission |
| `verbosity` | `concise` / `balanced` / `detailed` | Detail level in responses |
| `output_format` | `bullets` / `mixed` / `narrative` | Preferred output format |
| `update_cadence` | `asap` / `hourly` / `daily` / `weekly` | Update frequency |

Additional identity fields:

| Field | Usage |
|---|---|
| `purpose` | Agent's "purpose in life" |
| `personality` | Distinct personality |
| `custom_instructions` | Free-form custom instructions |

**Autonomy impact:** If `autonomy_level` is `autonomous`/`fully-autonomous`, the approval gate for `done` is disabled automatically.

---

## 7. Memory System

All agents wake up "fresh" each session. Continuity comes from files:

| File | Purpose |
|---|---|
| `memory/YYYY-MM-DD.md` | Raw daily logs |
| `MEMORY.md` | Curated long-term memory |

### Delivery Status Template (in MEMORY.md)

```markdown
## Current Delivery Status

### Objective
Implement OAuth2 for Google and GitHub

### Current State
- State: Working
- Last updated: 2024-01-10 14:30 UTC

### Plan (3-7 steps)
1. Create Google OAuth endpoint
2. Create GitHub OAuth endpoint
3. Implement JWT signing
4. Add rate limiting
5. Tests and documentation

### Last Progress
- Google OAuth endpoint implemented and tested

### Next Step (exactly one)
- Implement GitHub OAuth endpoint

### Blocker (if any)
- None

### Evidence
- PR #123 merged
```

### Golden Rule: "Text > Brain"
Never rely on "mental notes". Everything must be written to file.

---

## 8. Personalization via SOUL.md

The lead can permanently update a worker's behavior via `SOUL.md`:

```bash
PUT /api/v1/agent/boards/{board_id}/agents/{agent_id}/soul
{
  "content": "You are a security specialist. Always validate inputs against OWASP Top 10. Prioritize penetration testing before marking as done.",
  "reason": "Reinforce security practices"
}
```

**When to use SOUL.md vs task comments:**
- `SOUL.md`: Recurring behavior, permanent guardrails, runbook defaults
- Task comments: Transient guidance, specific to one task

---

## 9. Summary: Cheat Sheet by Agent Type

| Aspect | Gateway Main | Board Lead | Board Worker |
|---|---|---|---|
| **Prompt level** | Strategic/cross-board | Objective + metrics + constraints | Task + criteria + dependencies |
| **Decomposition** | Delegates to leads | Decomposes into tasks | Executes single task |
| **Autonomy** | Consolidates and routes | Plans and orchestrates | Executes and reports |
| **Communication** | MC API (never chat) | Task comments + chat decisions | Task comments + @lead |
| **Scope** | Cross-board | Entire board | Assigned task |
| **Escalation** | To human via channels | To human via ask-user | To @lead |

---

## 10. Anti-Patterns to Avoid

| Anti-Pattern | Why | Alternative |
|---|---|---|
| Micromanaging the lead | Lead exists to decompose and plan | Provide objective + constraints |
| Vague prompt for worker | Worker needs clear scope | Explicit acceptance criteria |
| Multiple tasks in one worker prompt | Causes scope drift | One task per prompt |
| Status chatter ("still working") | Noise without value | Post only with new evidence |
| "Mental notes" | Don't survive restart | Write to `MEMORY.md` or daily file |
| Skipping approval gates | Violates board rules | Respect `require_review_before_done` |

---

## Source Code References

| Template | File | Purpose |
|---|---|---|
| Agents | `backend/templates/BOARD_AGENTS.md.j2` | Roles, responsibilities, communication |
| Heartbeat | `backend/templates/BOARD_HEARTBEAT.md.j2` | Execution loop, comment format |
| Tools | `backend/templates/BOARD_TOOLS.md.j2` | API and environment config |
| Onboarding | `backend/app/api/board_onboarding.py` | Lead preference capture |
| Constants | `backend/app/services/openclaw/constants.py` | Identity profile fields, workspace files |
