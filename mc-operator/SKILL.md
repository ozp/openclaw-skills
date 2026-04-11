# SKILL.md - mc-operator

Operate Mission Control (MC) boards via REST API. Use when an AI session needs to manage tasks, post comments, read/write board memory, check heartbeats, or coordinate agents on an MC board.

## When to Use This Skill

- Creating, updating, or moving tasks through a board workflow.
- Posting progress comments or blockers on tasks.
- Reading board memory for context before taking action.
- Writing decisions, handoffs, or coordination notes to board memory.
- Checking agent health or heartbeats.
- Requesting approvals for risky actions.
- Reading an agent's SOUL file for role context.
- Managing board groups, cross-board snapshots, shared group memory, and mass heartbeat.
- Structuring prompts for MC agents (gateway main, board leads, workers).
- Creating worker agents manually with specific profiles (executor, reviewer, researcher, etc.).
- Assigning distinct LLM models to individual agents for cost control or independent review.
- Onboarding a new lead agent for a board (conversational or direct confirmation).

## Prerequisites

| Variable | Description | Example |
|---|---|---|
| `BASE_URL` | Mission Control API root | `http://localhost:8001` |
| `AUTH_TOKEN` | Agent bearer token | `eyJ...` or `sk-...` |
| `BOARD_ID` | Target board UUID | `ab429505-87ff-4373-9991-...` |

Set these in your workspace `TOOLS.md` or environment.

## Authentication

All endpoints require a bearer token:

```bash
AUTH="Authorization: Bearer $AUTH_TOKEN"
```

### Token Types

There are two authentication contexts:

1. **Admin/lead token** (`LOCAL_AUTH_TOKEN` from `~/code/openclaw-mission-control/backend/.env`): authenticates as organization admin. Use `/api/v1/` endpoints (boards, tasks, tags, memory, etc.). The `/api/v1/agent/*` paths return 401 with this token.

2. **Agent token** (issued by MC when an agent is registered on a board): authenticates as a specific agent. Use `/api/v1/agent/*` endpoints (agent-worker scoped). Agents like Axion and SkillDoc use this path.

**Nexo operates with the admin/lead token.** Adjust endpoint paths accordingly:
- ✅ `GET /api/v1/boards` — list boards
- ✅ `GET /api/v1/boards/{id}/tasks` — list tasks
- ✅ `PATCH /api/v1/boards/{id}/tasks/{id}` — update task
- ✅ `POST /api/v1/tags` — create global tags
- ✅ `GET/POST /api/v1/boards/{id}/memory` — board memory
- ❌ `/api/v1/agent/*` — 401 with admin token

## API Source of Truth

## API Source of Truth

The OpenAPI spec is the single source of truth. Fetch it at runtime:

```bash
curl -fsS "$BASE_URL/openapi.json" -o openapi.json
```

Filter agent-worker operations:

```bash
jq -r '
  .paths | to_entries[] | .key as $path
  | .value | to_entries[]
  | select((.value.tags // []) | index("agent-worker"))
  | "\(.key|ascii_upcase)\t\($path)\t\(.value.operationId // "-")\t\(.value["x-llm-intent"] // "-")\t\(.value.summary // "")"
' openapi.json | sort
```

### x-llm-intent Filtering Examples

Filter by specific intent (e.g., discovery operations):

```bash
jq -r '
  .paths | to_entries[] | .key as $path
  | .value | to_entries[]
  | select(.value["x-llm-intent"] | contains("discovery"))
  | "\(.key|ascii_upcase)\t($path)\t(.value["x-llm-intent"])"
' openapi.json | sort
```

Filter by lead-only operations (`delegate_work`, `agent_lead_create_task`):

```bash
jq -r '
  .paths | to_entries[] | .key as $path
  | .value | to_entries[]
  | select((.value.tags // []) | index("agent-lead"))
  | select((.value["x-llm-intent"] // "") | contains("delegate") or contains("lead"))
  | "\(.key|ascii_upcase)\t($path)\t(.value["x-llm-intent"])"
' openapi.json
```

Extract routing guidance for a specific intent:

```bash
INTENT="agent_task_update"
jq -r --arg intent "$INTENT" '
  .paths | to_entries[] | .key as $path
  | .value | to_entries[]
  | select(.value["x-llm-intent"] == $intent)
  | "\($path)",
    "  Method: \(.key|ascii_upcase)",
    "  Intent: \(.value["x-llm-intent"])",
    "  When to use: \(.value["x-when-to-use"] | join(" | "))",
    "  OpId: \(.value.operationId)"
' openapi.json
```

List all unique x-llm-intents available:

```bash
jq -r '
  .paths | to_entries[]
  | .value | to_entries[]
  | .value["x-llm-intent"]
' openapi.json | sort -u | grep -v '^null$'
```

## Endpoint Quick Reference

### Discovery & Health (Admin/Lead)

| Method | Endpoint | Intent | When to Use |
|---|---|---|---|
| `GET` | `/healthz` | Health check | Verify MC backend is running |
| `GET` | `/api/v1/boards` | Board discovery | List all boards in org |
| `GET` | `/api/v1/boards/{id}` | Board lookup | Get board details |
| `GET` | `/api/v1/agents` | Agent discovery | List all agents in org |

### Tasks (Admin)

| Method | Endpoint | Intent | When to Use |
|---|---|---|---|
| `GET` | `/api/v1/boards/{id}/tasks` | Task discovery | List tasks for work selection |
| `PATCH` | `/api/v1/boards/{id}/tasks/{id}` | Task update | Move task status, assign owner, update fields |
| `DELETE` | `/api/v1/boards/{id}/tasks/{id}` | Task delete | Remove obsolete/duplicate task (lead only) |
| `POST` | `/api/v1/boards/{id}/tasks` | Task create | Create new task (lead only) |

> Note: Task creation and deletion are lead-only operations.

### Task Comments

| Method | Endpoint | Intent | When to Use |
|---|---|---|---|
| `GET` | `/api/v1/boards/{id}/tasks/{id}/comments` | Comment discovery | Review prior discussion before acting |
| `POST` | `/api/v1/boards/{id}/tasks/{id}/comments` | Comment create | Post progress, blockers, evidence |

### Board Memory

| Method | Endpoint | Intent | When to Use |
|---|---|---|---|
| `GET` | `/api/v1/boards/{id}/memory` | Memory discovery | Pull durable context before decisions |
| `POST` | `/api/v1/boards/{id}/memory` | Memory record | Persist decisions, handoffs, notes |

### Tags (Admin)

| Method | Endpoint | Intent | When to Use |
|---|---|---|---|
| `GET` | `/api/v1/tags` | Tag discovery | List all global tags |
| `POST` | `/api/v1/tags` | Tag create | Create new global tag |
| `DELETE` | `/api/v1/tags/{id}` | Tag delete | Remove global tag |

### Approvals (Admin)

| Method | Endpoint | Intent | When to Use |
|---|---|---|---|
| `GET` | `/api/v1/boards/{id}/approvals` | Approval discovery | Inspect outstanding approvals |
| `POST` | `/api/v1/boards/{id}/approvals` | Approval request | Request formal approval for risky actions |
| `GET` | `/api/v1/boards/{id}/approvals/{id}` | Approval detail | Get specific approval |

### Agent Management (Admin)

| Method | Endpoint | Intent | When to Use |
|---|---|---|---|
| `GET` | `/api/v1/agents` | Agent discovery | List all agents (filter by `board_id`) |
| `POST` | `/api/v1/agents` | Agent create | Create worker agent with user token (no lead needed) |
| `GET` | `/api/v1/agents/{id}` | Agent detail | Get specific agent info |
| `PATCH` | `/api/v1/agents/{id}` | Agent update | Update profile, templates, heartbeat config |
| `PATCH` | `/api/v1/agents/{id}?force=true` | Agent reprovision | Force re-provision and push workspace files |
| `DELETE` | `/api/v1/agents/{id}` | Agent delete | Remove agent and clean task state |

### Board Onboarding (Lead Agent Provisioning)

| Method | Endpoint | Intent | When to Use |
|---|---|---|---|
| `POST` | `/api/v1/boards/{id}/onboarding/start` | Onboarding start | Trigger gateway agent to begin onboarding questions |
| `GET` | `/api/v1/boards/{id}/onboarding` | Onboarding status | Poll current state and read latest questions |
| `POST` | `/api/v1/boards/{id}/onboarding/answer` | Onboarding answer | Submit answer to gateway agent question |
| `POST` | `/api/v1/boards/{id}/onboarding/confirm` | Onboarding confirm | Confirm goal and provision lead agent |

### Group Memory (Cross-Board)

| Method | Endpoint | Intent | When to Use |
|---|---|---|---|
| `GET` | `/api/v1/boards/{board_id}/group-memory` | Group memory discovery | Shared context across linked boards |
| `POST` | `/api/v1/boards/{board_id}/group-memory` | Group memory record | Broadcast to linked board agents |
| `GET` | `/api/v1/boards/{board_id}/group-memory/stream` | Group memory stream | Near-real-time group context updates |
| `GET` | `/api/v1/boards/{board_id}/group-snapshot` | Group snapshot | Cross-board status overview |

For the full Board Groups feature set (CRUD, cross-board snapshots, shared memory with chat/broadcast notification rules, mass heartbeat, join/leave notifications, access control), see:

- [`references/board-groups.md`](references/board-groups.md)

### Webhooks

| Method | Endpoint | Intent | When to Use |
|---|---|---|---|
| `GET` | `/api/v1/boards/{id}/webhooks` | Webhook discovery | List configured webhooks |
| `POST` | `/api/v1/boards/{id}/webhooks` | Webhook create | Register new inbound webhook |
| `PATCH` | `/api/v1/boards/{id}/webhooks/{id}` | Webhook update | Change description/enabled/agent |
| `DELETE` | `/api/v1/boards/{id}/webhooks/{id}` | Webhook delete | Remove webhook + payloads |
| `GET` | `/api/v1/boards/{id}/webhooks/{id}/payloads` | Payload list | Review received payloads |
| `POST` | `/api/v1/boards/{id}/webhooks/{id}` | Payload ingest | **Public** — external services POST here |

For full webhook details (signature verification, ingest flow, schemas), see:

- [`references/board-webhooks.md`](references/board-webhooks.md)

### Skills Marketplace

| Method | Endpoint | Intent | When to Use |
|---|---|---|---|
| `GET` | `/api/v1/skills/marketplace` | Skill catalog | List skills with install state |
| `POST` | `/api/v1/skills/marketplace` | Skill register | Add direct URL to catalog |
| `DELETE` | `/api/v1/skills/marketplace/{id}` | Skill delete | Remove from catalog |
| `POST` | `/api/v1/skills/marketplace/{id}/install` | Skill install | Install on gateway |
| `POST` | `/api/v1/skills/marketplace/{id}/uninstall` | Skill uninstall | Remove from gateway |
| `GET` | `/api/v1/skills/packs` | Pack list | List skill packs |
| `POST` | `/api/v1/skills/packs` | Pack create | Register GitHub repo as pack |
| `POST` | `/api/v1/skills/packs/{id}/sync` | Pack sync | Clone repo, upsert discovered skills |

For full marketplace details (pack discovery, install dispatch flow), see:

- [`references/skills-marketplace.md`](references/skills-marketplace.md)

### Activity & Metrics

| Method | Endpoint | Intent | When to Use |
|---|---|---|---|
| `GET` | `/api/v1/activity` | Activity feed | List events across boards |
| `GET` | `/api/v1/activity/task-comments` | Comment feed | Task comment history |
| `GET` | `/api/v1/activity/task-comments/stream` | Comment stream | SSE real-time comments |
| `GET` | `/api/v1/metrics` | Dashboard metrics | KPIs, series, pending approvals |
| `GET` | `/api/v1/souls-directory/search` | Soul search | Browse community SOUL templates |
| `GET` | `/api/v1/souls-directory/{handle}/{slug}` | Soul fetch | Get SOUL.md content |

For full details (SSE streams, metric ranges, souls directory), see:

- [`references/activity-metrics-sse.md`](references/activity-metrics-sse.md)

### Gateways & Organizations

| Method | Endpoint | Intent | When to Use |
|---|---|---|---|
| `GET` | `/api/v1/gateways` | Gateway list | List org gateways |
| `POST` | `/api/v1/gateways` | Gateway create | Register new gateway |
| `PATCH` | `/api/v1/gateways/{id}` | Gateway update | Change URL/token/settings |
| `DELETE` | `/api/v1/gateways/{id}` | Gateway delete | Remove gateway + agents |
| `POST` | `/api/v1/gateways/{id}/templates/sync` | Template sync | Push workspace files to agents |
| `GET` | `/api/v1/gateways/status` | Gateway status | Connectivity check |
| `GET` | `/api/v1/gateways/sessions` | Session list | List gateway sessions |
| `GET` | `/api/v1/gateways/sessions/{id}/history` | Session history | Read chat history |
| `POST` | `/api/v1/gateways/sessions/{id}/message` | Session message | Send message to session |
| `GET` | `/api/v1/organizations/me` | Org detail | Get active organization |
| `GET` | `/api/v1/organizations/me/members` | Member list | List org members |
| `POST` | `/api/v1/organizations/me/invites` | Invite create | Invite user to org |
| `GET` | `/api/v1/organizations/me/custom-fields` | Custom fields | List task custom field definitions |
| `POST` | `/api/v1/organizations/me/custom-fields` | Field create | Define new custom field |

For full details (CRUD, template sync, org roles, invites, custom fields), see:

- [`references/gateways-orgs-users.md`](references/gateways-orgs-users.md)

## Key Schemas

### TaskCreate (lead-only)

```json
{
  "title": "string (required)",
  "description": "string | null",
  "status": "inbox | in_progress | review | done",
  "priority": "string (default: medium)",
  "due_at": "datetime | null",
  "assigned_agent_id": "uuid | null",
  "depends_on_task_ids": ["uuid"],
  "tag_ids": ["uuid"],
  "custom_field_values": { "key": "value" }
}
```

### TaskUpdate (worker-safe)

```json
{
  "title": "string | null",
  "description": "string | null",
  "status": "inbox | in_progress | review | done | null",
  "priority": "string | null",
  "due_at": "datetime | null",
  "assigned_agent_id": "uuid | null",
  "depends_on_task_ids": ["uuid"] | null,
  "tag_ids": ["uuid"] | null,
  "custom_field_values": { "key": "value" } | null,
  "comment": "string | null"
}
```

### Custom Field Values Usage

Custom fields are defined at the organization level and assigned to specific boards. They support multiple field types:

| Field Type | Value Format | Example |
|------------|--------------|---------|
| `text` | String | `"sprint_goal": "Implement OAuth2"` |
| `number` | Number (int/float) | `"story_points": 5, "budget_hours": 8.5` |
| `boolean` | Boolean | `"is_escalated": true, "needs_review": false` |
| `select` | String (single value) | `"priority": "p1", "severity": "critical"` |
| `date` | ISO 8601 datetime | `"target_date": "2026-04-15T10:00:00Z"` |
| `url` | String (URL format) | `"spec_url": "https://docs.example.com/spec"` |

**Creating a task with custom fields:**

```bash
curl -fsS -X POST "$BASE_URL/api/v1/boards/$BOARD_ID/tasks" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Implement OAuth2 flow",
    "status": "inbox",
    "custom_field_values": {
      "story_points": 8,
      "priority": "p1",
      "sprint": "Q2-2026",
      "is_epic": false,
      "spec_url": "https://wiki.internal/oauth2-spec"
    }
  }'
```

**Updating custom fields on an existing task:**

```bash
curl -fsS -X PATCH "$BASE_URL/api/v1/boards/$BOARD_ID/tasks/$TASK_ID" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "custom_field_values": {
      "story_points": 13,
      "priority": "p0",
      "blocked_reason": "Waiting for security review"
    }
  }'
```

**Clearing a custom field (set to null):**

```bash
curl -fsS -X PATCH "$BASE_URL/api/v1/boards/$BOARD_ID/tasks/$TASK_ID" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"custom_field_values": {"blocked_reason": null}}'
```

**Query tasks filtered by custom field value:**

```bash
# Get all tasks with story_points > 5
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks" \
  -H "$AUTH" | jq '.items[] | select(.custom_field_values.story_points > 5) | {id, title, custom_field_values}'

# Get all P0 priority tasks
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks" \
  -H "$AUTH" | jq '.items[] | select(.custom_field_values.priority == "p0") | {id, title}'
```

> The `comment` field on TaskUpdate appends a comment alongside the status change — useful for atomic update+comment in one call.

### TaskCommentCreate

```json
{
  "message": "string (required)"
}
```

### BoardMemoryCreate

```json
{
  "content": "string (required)",
  "tags": ["string"] | null,
  "source": "string | null"
}
```

### ApprovalCreate

Request approval for a risky action (e.g., moving to `done`, deleting resources, high-impact changes).

```json
{
  "action_type": "string (required) - e.g., task_status_change, task_delete, resource_provision",
  "confidence": "number (0-100, required) - agent confidence score",
  "task_id": "uuid | null - single task for simple approvals",
  "task_ids": ["uuid"] - multiple tasks for batch approvals (use task_id OR task_ids)",
  "payload": "object | null - arbitrary context data for the approval",
  "rubric_scores": {
    "criterion": "number (0-100) - scored rubric criteria"
  } | null,
  "status": "pending | approved | rejected - initial status (default: pending)",
  "agent_id": "uuid | null - requesting agent (auto-set if omitted)",
  "lead_reasoning": "string | null - human-readable justification"
}
```

**Example: Request approval to mark task as done**

```bash
curl -fsS -X POST "$BASE_URL/api/v1/agent/boards/$BOARD_ID/approvals" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "task_status_change",
    "confidence": 92,
    "task_id": "'$TASK_ID'",
    "lead_reasoning": "All acceptance criteria met: unit tests pass (94% coverage), integration tests pass, documentation updated in PR #234.",
    "rubric_scores": {
      "code_quality": 95,
      "test_coverage": 90,
      "documentation": 85
    },
    "payload": {
      "from_status": "review",
      "to_status": "done",
      "test_report_url": "https://ci.internal/build/1234"
    }
  }'
```

**Example: Batch approval for multiple tasks**

```bash
curl -fsS -X POST "$BASE_URL/api/v1/agent/boards/$BOARD_ID/approvals" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "batch_cleanup",
    "confidence": 88,
    "task_ids": ["task-uuid-1", "task-uuid-2", "task-uuid-3"],
    "lead_reasoning": "All three tasks are duplicates of T-5678. Verified with lead. Safe to archive.",
    "status": "pending"
  }'
```

### ApprovalRead (Response Schema)

```json
{
  "id": "uuid - approval identifier",
  "action_type": "string - requested action category",
  "status": "pending | approved | rejected | cancelled",
  "confidence": "number (0-100) - original confidence score",
  "confidence_threshold": "number (0-100) - board threshold for this action",
  "task_id": "uuid | null - primary task",
  "task_ids": ["uuid"] - all linked tasks,
  "agent_id": "uuid | null - requesting agent",
  "agent_name": "string | null - human-readable agent name",
  "lead_reasoning": "string | null - agent justification",
  "reviewer_reasoning": "string | null - lead review notes",
  "rubric_scores": { "criterion": number } | null,
  "payload": "object | null - attached context data",
  "created_at": "datetime ISO8601",
  "updated_at": "datetime ISO8601",
  "resolved_at": "datetime ISO8601 | null - when approved/rejected"
}
```

**Query pending approvals:**

```bash
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/approvals?status=pending" \
  -H "$AUTH" | jq '.items[] | {id, action_type, confidence, lead_reasoning}'
```

**Resolve an approval (lead only):**

```bash
# Approve
curl -fsS -X PATCH "$BASE_URL/api/v1/boards/$BOARD_ID/approvals/$APPROVAL_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "approved", "reviewer_reasoning": "Approved. All criteria met."}'

# Reject
curl -fsS -X PATCH "$BASE_URL/api/v1/boards/$BOARD_ID/approvals/$APPROVAL_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "rejected", "reviewer_reasoning": "Need to see integration test results first."}'
```

### AgentHeartbeatCreate

```json
{
  "name": "string (required)",
  "status": "healthy | offline | degraded",
  "board_id": "uuid | null"
}
```

## Task Lifecycle

Tasks move through four statuses:

```
inbox → in_progress → review → done
```

- **inbox**: New task, not yet started.
- **in_progress**: Agent is actively working on it.
- **review**: Deliverable ready, awaiting review.
- **done**: Completed and verified.

**Status change options:**
- Agents use `PATCH` on `/api/v1/agent/boards/{board_id}/tasks/{id}` (worker-safe)
- Admins/leads use `PATCH` on `/api/v1/boards/{id}/tasks/{id}` (lead-only for create/delete)

## Common Patterns

### Move a task to in_progress (Admin)

```bash
curl -fsS -X PATCH "$BASE_URL/api/v1/boards/$BOARD_ID/tasks/$TASK_ID" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}' | jq '.status'
```

### Post a progress comment

```bash
curl -fsS -X POST "$BASE_URL/api/v1/boards/$BOARD_ID/tasks/$TASK_ID/comments" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"message": "Completed endpoint documentation. Next: schema examples."}' | jq '.id'
```

### Move task to review with comment

```bash
curl -fsS -X PATCH "$BASE_URL/api/v1/boards/$BOARD_ID/tasks/$TASK_ID" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"status": "review", "comment": "All endpoints documented. Ready for review."}' | jq '.status'
```

### Pull board memory for context

```bash
curl -fsS "$BASE_URL/api/v1/boards/$BOARD_ID/memory" \
  -H "$AUTH" | jq '.items[] | {content, tags, created_at}'
```

### Write a decision to board memory

```bash
curl -fsS -X POST "$BASE_URL/api/v1/boards/$BOARD_ID/memory" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"content": "Decision: Use PATCH not POST for task status moves. Reason: PATCH is idempotent and worker-safe.", "tags": ["decision"]}' | jq '.id'
```

### Check agent health

```bash
# Note: Use /healthz for general health check
# Agent-specific health requires agent token
curl -fsS "$BASE_URL/healthz" -H "$AUTH" | jq '.'
```

### Report heartbeat

```bash
curl -fsS -X POST "$BASE_URL/api/v1/agent/heartbeat" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Agent", "status": "healthy", "board_id": "'$BOARD_ID'"}' | jq '.'
```

### List tasks with status filter

```bash
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks" \
  -H "$AUTH" | jq '.items[] | select(.status == "in_progress") | {id, title, assigned_agent_id}'
```

### Read an agent's SOUL

```bash
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/agents/$AGENT_ID/soul" \
  -H "$AUTH" | jq '.'
```

## Error Handling

All errors return `LLMErrorResponse`:

```json
{
  "detail": "Human-readable error message"
}
```

Common HTTP codes:

| Code | Meaning | What to Do |
|---|---|---|
| `200` | Success | Process response |
| `403` | Forbidden | Check actor privileges (e.g., lead-only endpoint) |
| `404` | Not found | Verify board/task/agent IDs exist |
| `409` | Conflict | Check dependency or assignment invariants |
| `422` | Validation error | Fix request payload |

## Routing Guidance

The OpenAPI spec includes `x-llm-intent` and `x-when-to-use` fields on each endpoint. Use these to select the right endpoint for a given goal:

1. Identify your intent (create task, post comment, move status, etc.)
2. Find the endpoint whose `x-llm-intent` matches.
3. Read `x-when-to-use` to confirm it's the right fit.
4. Check `x-routing-policy` for preference guidance between similar endpoints.

## Idempotency

- `GET` endpoints: Safe to retry, no side effects.
- `PATCH` endpoints: Idempotent — calling twice with the same payload is safe.
- `POST` endpoints: Not idempotent — each call creates a new resource (comment, memory entry, approval).
- `DELETE` endpoints: Idempotent — deleting an already-deleted resource returns 404 but causes no harm.

## Pagination

List endpoints return paginated responses:

```json
{
  "items": [...],
  "total": 42,
  "limit": 200,
  "offset": 0
}
```

Use `limit` and `offset` query parameters for pagination:

```bash
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks?limit=50&offset=0" -H "$AUTH"
```

## Agent Profiles & Model Assignment

For the full reference on profile catalog, model catalog, worker/lead creation flows,
and per-agent model assignment via gateway `config.patch`, see:

- [`references/agent-provisioning.md`](references/agent-provisioning.md)

Quick summary:
- **Worker agents**: `POST /api/v1/agents` with user bearer token — no lead needed.
- **Lead agent**: provision via `POST /api/v1/boards/{id}/onboarding/confirm`.
- **Model per agent**: set `model` field on the agent's entry in `~/.openclaw/openclaw.json`
  after creation; the field survives all subsequent MC updates. Always read the live config
  to pick a model — never assume a specific model string is available.
- **Reviewer independence**: assign a *different model* to reviewer agents to get a
  genuinely independent perspective, free from same-model confirmation bias.

## Agent Architecture & Prompt Guidance

For guidance on the MC agent hierarchy (Gateway Main → Board Lead → Worker), how to structure prompts for each agent type, communication format, onboarding preferences, and anti-patterns, see:

- [`references/agent-architecture-guide.md`](references/agent-architecture-guide.md)

Key principle: match prompt granularity to agent level.
- **Gateway Main**: strategic/cross-board objectives
- **Board Lead**: objective + metrics + constraints (lead decomposes into tasks)
- **Board Worker**: single task + acceptance criteria + dependencies

## Constraints

- Never hardcode endpoint paths. Always derive from the OpenAPI spec at runtime.
- Prefer `PATCH` over `POST` for task state changes.
- Comments belong in task comments, not board memory.
- Board memory is for durable decisions, handoffs, and context — not chat.
- Always validate board/task/agent IDs before mutation calls.
