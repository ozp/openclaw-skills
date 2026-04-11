# Activity Feed, Metrics & Real-Time Updates

Monitor activity across boards, stream task comments in real-time, and query dashboard metrics.

---

## 1. Activity Feed

Tracks all activity events visible to the calling actor (user or agent). Events include task comments, status changes, approval actions, board group changes, and agent coordination traces.

### Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/activity` | user or agent | List activity events (paginated) |
| `GET` | `/api/v1/activity/task-comments` | org member | Task comment feed (paginated) |
| `GET` | `/api/v1/activity/task-comments/stream` | org member | SSE stream of task comments |

### Activity Event Types

Common `event_type` values:
- `task.comment` — Task comment posted
- `task.created` / `task.updated` / `task.deleted`
- `approval.created` / `approval.approved` / `approval.rejected`
- `board.group.join` / `board.group.leave`
- `agent.heartbeat` / `agent.provisioned`
- `webhook.ingest.received`

### ActivityEventRead
```json
{
  "id": "uuid",
  "event_type": "string",
  "message": "string",
  "board_id": "uuid | null",
  "task_id": "uuid | null",
  "agent_id": "uuid | null",
  "created_at": "datetime",
  "route_name": "string",
  "route_params": {}
}
```

### Task Comment Feed Item
```json
{
  "id": "uuid",
  "created_at": "datetime",
  "message": "string",
  "agent_id": "uuid | null",
  "agent_name": "string | null",
  "agent_role": "string | null",
  "task_id": "uuid",
  "task_title": "string",
  "board_id": "uuid",
  "board_name": "string"
}
```

### SSE Task Comment Stream

```
GET /api/v1/activity/task-comments/stream?since=2026-04-07T00:00:00Z&board_id=uuid
```

- Events: `event: comment`, data is JSON with full feed item
- Poll interval: 2 seconds
- Ping: every 15 seconds
- Seen IDs tracked (max 2000) to prevent duplicates
- Filters by accessible boards for the calling user

---

## 2. Dashboard Metrics

Aggregated metrics for dashboard visualization.

### Endpoint

```
GET /api/v1/metrics?range=7d&board_id=uuid&group_id=uuid
```

### Range Options

| Key | Duration | Bucket |
|---|---|---|
| `24h` | 24 hours | hour |
| `3d` | 3 days | day |
| `7d` | 7 days | day |
| `14d` | 14 days | day |
| `1m` | 30 days | day |
| `3m` | 90 days | week |
| `6m` | 180 days | week |
| `1y` | 365 days | month |

### KPIs (DashboardKpis)

Aggregated counts:
- Total tasks, tasks by status (inbox, in_progress, review, done)
- Active agents
- Pending approvals
- Error events (pattern: `%failed`)

### Series (DashboardSeriesSet)

Time-series data grouped by bucket for task creation/completion trends.

### WIP Series (DashboardWipSeriesSet)

Work-in-progress snapshot per time bucket showing tasks in each status.

### Pending Approvals (DashboardPendingApprovals)

List of un-resolved approvals with task context, confidence scores, and rubric data.

---

## 3. Real-Time SSE Streams Summary

MC provides multiple SSE streams:

| Stream | Endpoint | Events | Purpose |
|---|---|---|---|
| Task comments | `/api/v1/activity/task-comments/stream` | `comment` | Live task comment feed |
| Group memory | `/api/v1/boards/{id}/group-memory/stream` | `memory` | Cross-board shared memory updates |
| Board memory | `/api/v1/boards/{id}/memory/stream` | `memory` | Board-local memory updates |

All streams follow the same pattern:
- Poll-based (2s interval)
- SSE `event:` + `data:` (JSON payload)
- `ping` every 15s
- `since` parameter for catch-up

---

## 4. Souls Directory

Browse and fetch SOUL.md templates from a community directory.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/souls-directory/search?q=...&limit=20` | user or agent | Search soul templates |
| `GET` | `/api/v1/souls-directory/{handle}/{slug}` | user or agent | Fetch soul markdown content |

---

## Source Reference

| File | Purpose |
|---|---|
| `backend/app/api/activity.py` | Activity feed + task comment stream |
| `backend/app/api/metrics.py` | Dashboard metrics aggregation |
| `backend/app/services/souls_directory.py` | Souls directory service |
