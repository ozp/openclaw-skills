# Oath Audit Engine API - Detailed Reference

## Base URLs

| Environment | URL |
|-------------|-----|
| Production | `https://audit-engine.oathe.ai` |
| Badge Service | `https://oathe.ai/api/badge` |
| Dashboard | `https://oathe.ai/dashboard` |

## Authentication

### Public Access (Free Tier)

Most endpoints work without authentication:
- 200 scans/month limit
- Rate limited by Cloudflare

### Authenticated Access

```bash
# API Key format (from dashboard)
Authorization: Bearer oath_sk_xxxxx

# Not required for basic usage
```

**Note:** Tested API keys returned 401 - may need regeneration from dashboard.

## POST /api/submit

Submit a skill URL for security audit.

### Request

```bash
curl -X POST "https://audit-engine.oathe.ai/api/submit" \
  -H "Content-Type: application/json" \
  -d '{"skill_url": "https://github.com/owner/repo"}'
```

### Success Response (201)

```json
{
  "audit_id": "95ee25db-3910-4b80-8327-6a8fe377d8df",
  "queue_position": 0
}
```

### Error Responses

| Status | Code | Message | Cause |
|--------|------|---------|-------|
| 422 | `repo_not_found` | Repository could not be reached | Private, deleted, or wrong URL |
| 429 | `rate_limited` | Too many requests | Cloudflare protection triggered |
| 500 | - | Internal server error | Server overloaded or error |

## GET /api/audit/{audit_id}

Check audit status and results.

### Request

```bash
curl "https://audit-engine.oathe.ai/api/audit/{audit_id}"
```

### Response States

**Analyzing:**
```json
{
  "audit_id": "uuid",
  "skill_url": "https://github.com/...",
  "status": "analyzing"
}
```

**Complete:**
```json
{
  "audit_id": "uuid",
  "skill_url": "https://github.com/...",
  "status": "complete",
  "result": {
    "passed": true,
    "issues": []
  }
}
```

**Failed (server overload):**
```json
{
  "audit_id": "uuid",
  "skill_url": "https://github.com/...",
  "status": "failed",
  "error_message": "Oh no! Looks like we're getting a lot of requests right now. Please try again shortly."
}
```

**Failed (repo issue):**
```json
{
  "audit_id": "uuid",
  "skill_url": "https://github.com/...",
  "status": "failed",
  "error_message": "This repository could not be reached"
}
```

## GET /api/badge

Get security badge for a skill.

### Request

```bash
curl "https://oathe.ai/api/badge?skill_url=https://github.com/owner/repo"
```

### Response

Returns SVG badge or redirect to badge image.

## Rate Limiting

### Cloudflare Protection

- **Trigger:** 1-2 rapid requests
- **Error code:** 1015
- **Solution:** Wait 60+ seconds between requests

### Recommended Timing

```bash
# Submit → wait 60s → check status
submit_skill() {
  local url=$1
  curl -s -X POST "https://audit-engine.oathe.ai/api/submit" \
    -d "{\"skill_url\": \"$url\"}"
  sleep 60
}

# Check status every 30s until done
poll_status() {
  local audit_id=$1
  while true; do
    status=$(curl -s "https://audit-engine.oathe.ai/api/audit/$audit_id" | jq -r '.status')
    [[ "$status" != "analyzing" ]] && break
    sleep 30
  done
  echo "$status"
}
```

## Monorepo URLs

### Individual Skills

For repos with multiple skills, specify the path:

```
https://github.com/owner/repo/tree/main/skills/skill-name
https://github.com/owner/repo/tree/branch/skills/category/skill-name
```

⚠️ **Important:** No automatic discovery. Each skill must be submitted separately.

### Batch Processing

```bash
scan_monorepo() {
  local base_url="https://github.com/owner/repo/tree/main/skills"
  local skills=("skill-1" "skill-2" "skill-3")

  for skill in "${skills[@]}"; do
    submit_skill "$base_url/$skill"
    sleep 60
  done
}
```

## Testing Examples

### Test with MCP Servers (Large Repo)

```bash
curl -s -X POST "https://audit-engine.oathe.ai/api/submit" \
  -d '{"skill_url": "https://github.com/modelcontextprotocol/servers"}'

# Response: {"audit_id":"...","queue_position":0}
```

### Test Status Check

```bash
curl -s "https://audit-engine.oathe.ai/api/audit/95ee25db-3910-4b80-8327-6a8fe377d8df"
```

## Error Handling Recipes

### Retry with Exponential Backoff

```bash
retry_submit() {
  local url=$1
  local max_retries=5
  local delay=60

  for ((i=1; i<=max_retries; i++)); do
    echo "Attempt $i..."

    result=$(curl -s -X POST "https://audit-engine.oathe.ai/api/submit" \
      -d "{\"skill_url\": \"$url\"}")

    if [[ "$result" == *"audit_id"* ]]; then
      echo "✅ Success: $(echo "$result" | jq -r '.audit_id')"
      return 0
    fi

    echo "❌ Failed, waiting ${delay}s..."
    sleep $delay
    delay=$((delay * 2))
  done

  echo "❌ All retries exhausted"
  return 1
}
```

### Handle Server Overload

```bash
handle_overload() {
  local audit_id=$1
  local result=$(curl -s "https://audit-engine.oathe.ai/api/audit/$audit_id")
  local error=$(echo "$result" | jq -r '.error_message')

  if [[ "$error" == *"lot of requests"* ]]; then
    echo "Server overloaded, queuing for retry in 10 minutes..."
    # Add to queue: echo "$audit_id" >> /tmp/oath_retry_queue
    sleep 600
    # Retry logic here
  fi
}
```
