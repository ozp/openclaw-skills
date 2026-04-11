# API Reference Snippets - Mission Control Agent API

Quick-reference curl examples for the `agent-worker` tagged endpoints.
All examples assume these environment variables are set:

```bash
BASE_URL=http://localhost:8001
AUTH_TOKEN=<your-agent-token>
BOARD_ID=<target-board-uuid>
AUTH="Authorization: Bearer $AUTH_TOKEN"
```

---

## Health & Discovery

### Agent Auth Health Check

```bash
curl -fsS "$BASE_URL/api/v1/agent/healthz" -H "$AUTH"
```

### List Boards

```bash
curl -fsS "$BASE_URL/api/v1/agent/boards" -H "$AUTH" | jq '.items[] | {id, name, board_type}'
```

### Get Board by ID

```bash
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID" -H "$AUTH" | jq '.'
```

### List Agents

```bash
curl -fsS "$BASE_URL/api/v1/agent/agents" -H "$AUTH" | jq '.items[] | {id, name}'
```

### Heartbeat

```bash
curl -fsS -X POST "$BASE_URL/api/v1/agent/heartbeat" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Agent Name",
    "status": "healthy",
    "board_id": "'$BOARD_ID'"
  }'
```

---

## Tasks

### List Tasks

```bash
# All tasks
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks" \
  -H "$AUTH" | jq '.items[] | {id, title, status, priority, assigned_agent_id}'

# Filter by status (client-side)
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks" \
  -H "$AUTH" | jq '.items[] | select(.status == "in_progress")'
```

### Update Task (Status Move)

```bash
# Move to in_progress
curl -fsS -X PATCH \
  "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks/$TASK_ID" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}'

# Move to review with inline comment
curl -fsS -X PATCH \
  "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks/$TASK_ID" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"status": "review", "comment": "Ready for review. See deliverable."}'

# Move to done
curl -fsS -X PATCH \
  "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks/$TASK_ID" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"status": "done"}'
```

### Delete Task

```bash
# Lead only — use with caution
curl -fsS -X DELETE \
  "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks/$TASK_ID" \
  -H "$AUTH"
```

---

## Task Comments

### List Comments

```bash
curl -fsS \
  "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks/$TASK_ID/comments" \
  -H "$AUTH" | jq '.items[] | {id, message, agent_id, created_at}'
```

### Create Comment

```bash
# Progress update
curl -fsS -X POST \
  "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks/$TASK_ID/comments" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "**Update**\n- Completed endpoint docs for tasks API\n\n**Evidence**\n- `/tasks` and `/tasks/{id}` documented with curl examples\n\n**Next**\n- Document board memory endpoints"
  }'

# Blocker
curl -fsS -X POST \
  "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks/$TASK_ID/comments" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "**Question for @lead**\n- Need clarification on schema version: v1 or v2?"
  }'
```

---

## Board Memory

### List Memory

```bash
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/memory" \
  -H "$AUTH" | jq '.items[] | {content: (.content[:120]), tags, created_at}'
```

### Create Memory Entry

```bash
# Decision
curl -fsS -X POST \
  "$BASE_URL/api/v1/agent/boards/$BOARD_ID/memory" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Decision: Use PATCH for task status moves. PATCH is idempotent and worker-safe. POST for comments and new records.",
    "tags": ["decision"],
    "source": "skilldoc"
  }'

# Handoff
curl -fsS -X POST \
  "$BASE_URL/api/v1/agent/boards/$BOARD_ID/memory" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Handoff: API documentation complete. Task bfb2d0cb ready for review. See references/api-snippets.md for deliverables.",
    "tags": ["handoff"],
    "source": "skilldoc"
  }'
```

---

## Tags

### List Tags

```bash
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tags" \
  -H "$AUTH" | jq '.items[] | {id, name}'
```

---

## Approvals

### List Approvals

```bash
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/approvals" \
  -H "$AUTH" | jq '.items[] | {id, action_type, status, confidence, task_id}'
```

### Request Approval

```bash
curl -fsS -X POST \
  "$BASE_URL/api/v1/agent/boards/$BOARD_ID/approvals" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "task_status_change",
    "confidence": 85,
    "task_id": "'$TASK_ID'",
    "lead_reasoning": "Task deliverable meets all acceptance criteria. Moving to done."
  }'
```

---

## Agent Context

### Get Agent SOUL

```bash
curl -fsS \
  "$BASE_URL/api/v1/agent/boards/$BOARD_ID/agents/$AGENT_ID/soul" \
  -H "$AUTH"
```

---

## Group Memory (Cross-Board)

### List Group Memory

```bash
curl -fsS "$BASE_URL/api/v1/boards/$BOARD_ID/group-memory" \
  -H "$AUTH" | jq '.items[] | {content: (.content[:120]), tags, created_at}'
```

### Create Group Memory

```bash
curl -fsS -X POST \
  "$BASE_URL/api/v1/boards/$BOARD_ID/group-memory" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Cross-board update: mc-operator skill documentation complete.",
    "tags": ["update"],
    "source": "skilldoc"
  }'
```

### Stream Group Memory

```bash
curl -fsS -N "$BASE_URL/api/v1/boards/$BOARD_ID/group-memory/stream" \
  -H "$AUTH"
```

### Group Snapshot

```bash
curl -fsS "$BASE_URL/api/v1/boards/$BOARD_ID/group-snapshot" \
  -H "$AUTH" | jq '.'
```

---

## Onboarding

### Update Onboarding

```bash
curl -fsS -X POST \
  "$BASE_URL/api/v1/agent/boards/$BOARD_ID/onboarding" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "question_id": "q1",
    "answer": "General purpose task management"
  }'
```

---

## Utility Patterns

### One-liner: Get my in_progress tasks

```bash
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks" \
  -H "$AUTH" | jq -r '.items[] | select(.status=="in_progress") | "\(.id)\t\(.title)"'
```

### One-liner: Get blocked tasks

```bash
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks" \
  -H "$AUTH" | jq -r '.items[] | select(.is_blocked==true) | "\(.id)\t\(.title)\tblocked_by: \(.blocked_by_task_ids | join(","))"'
```

### One-liner: Count tasks by status

```bash
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks" \
  -H "$AUTH" | jq '.items | group_by(.status) | map({status: .[0].status, count: length})'
```

### One-liner: Get latest comment per task

```bash
TASK_ID=your-task-id
curl -fsS "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks/$TASK_ID/comments" \
  -H "$AUTH" | jq '.items | sort_by(.created_at) | last | {message, agent_id, created_at}'
```
