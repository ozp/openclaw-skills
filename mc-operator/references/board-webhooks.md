# Board Webhooks

Configure inbound webhooks for boards. External services POST payloads to webhook endpoints; MC stores the payload, writes a board memory entry, and notifies the board lead.

---

## Concepts

- **Board Webhook**: A per-board endpoint that accepts inbound HTTP POST payloads. Configured with optional HMAC-SHA256 secret for signature verification.
- **Payload Storage**: Each inbound payload is persisted as `BoardWebhookPayload` with headers, source IP, content type, and decoded body.
- **Board Memory**: On ingest, a `BoardMemory` entry is created with tags `webhook`, `webhook:{id}`, `payload:{id}`.
- **Agent Notification**: The board lead (or the webhook's assigned agent) receives a structured message with the payload preview and action instructions.

---

## Endpoints

All under `/api/v1/boards/{board_id}/webhooks`. Auth: board read/write.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/webhooks` | board read | List webhooks |
| `POST` | `/webhooks` | board write | Create webhook |
| `GET` | `/webhooks/{webhook_id}` | board read | Get webhook config |
| `PATCH` | `/webhooks/{webhook_id}` | board write | Update webhook |
| `DELETE` | `/webhooks/{webhook_id}` | board write | Delete webhook + payloads |
| `GET` | `/webhooks/{webhook_id}/payloads` | board read | List stored payloads |
| `GET` | `/webhooks/{webhook_id}/payloads/{payload_id}` | board read | Get single payload |
| `POST` | `/webhooks/{webhook_id}` | **none** (public endpoint) | Ingest inbound payload |

---

## Key Schemas

### BoardWebhookCreate
```json
{
  "description": "string (instruction for the agent processing payloads)",
  "enabled": true,
  "agent_id": "uuid | null (target agent, defaults to board lead)",
  "secret": "string | null (HMAC-SHA256 secret)",
  "signature_header": "string | null (custom header name for signature)"
}
```

### BoardWebhookRead
```json
{
  "id": "uuid",
  "board_id": "uuid",
  "agent_id": "uuid | null",
  "description": "string",
  "enabled": true,
  "has_secret": true,
  "signature_header": "string | null",
  "endpoint_path": "/api/v1/boards/{board_id}/webhooks/{webhook_id}",
  "endpoint_url": "https://mc.example.com/api/v1/boards/{board_id}/webhooks/{webhook_id}",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### BoardWebhookIngestResponse
```json
{
  "board_id": "uuid",
  "webhook_id": "uuid",
  "payload_id": "uuid"
}
```

---

## Signature Verification

When a webhook has a `secret` configured, the inbound request must include a valid HMAC-SHA256 signature:

- Header checked: `webhook.signature_header` if set, otherwise `X-Hub-Signature-256` then `X-Webhook-Signature`
- Format: `sha256=<hex_digest>` (GitHub-style prefix is stripped automatically)
- Missing signature → `403 Forbidden`
- Invalid signature → `403 Forbidden`
- No secret configured → signature check skipped

---

## Common Patterns

### Create a webhook for GitHub events
```bash
curl -fsS -X POST "$BASE_URL/api/v1/boards/$BOARD_ID/webhooks" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{
    "description": "Create tasks from GitHub issues. Extract title, body, labels, and assignee.",
    "enabled": true,
    "secret": "my-webhook-secret"
  }' | jq '{id, endpoint_url}'
```

### Send a test payload
```bash
curl -X POST "$BASE_URL/api/v1/boards/$BOARD_ID/webhooks/$WEBHOOK_ID" \
  -H "Content-Type: application/json" \
  -d '{"action":"opened","issue":{"title":"Bug: login fails","body":"Steps to reproduce..."}}'
```

### List recent payloads
```bash
curl -fsS "$BASE_URL/api/v1/boards/$BOARD_ID/webhooks/$WEBHOOK_ID/payloads" \
  -H "$AUTH" | jq '.items[] | {id, received_at, payload_preview: (.payload | tostring[:120])}'
```

---

## Ingest Flow

1. External service POSTs to the webhook endpoint (no auth required)
2. Rate limit check per source IP
3. If webhook disabled → `410 Gone`
4. Payload size check (configurable max)
5. HMAC signature verification (if secret configured)
6. Payload decoded (JSON auto-parsed, otherwise stored as string)
7. `BoardWebhookPayload` + `BoardMemory` persisted
8. Delivery enqueued (or synchronous fallback if queue unavailable)
9. Board lead / assigned agent receives notification with payload preview

---

## Source Reference

| File | Purpose |
|---|---|
| `backend/app/api/board_webhooks.py` | All webhook endpoints + ingest logic |
| `backend/app/models/board_webhooks.py` | `BoardWebhook` model |
| `backend/app/models/board_webhook_payloads.py` | `BoardWebhookPayload` model |
| `backend/app/services/webhooks/queue.py` | Delivery queue |
