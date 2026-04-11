---
name: skill-scanner
description: >
  Automates security scanning of Claude/Codex/Copilot skills using Oath Audit Engine.
  Use when submitting skills for security review, checking compliance, or batch scanning
  multiple skills. Handles rate limits, retry logic, and result polling automatically.
category: security
risk: safe
source: community
tags: ["security", "audit", "oathe", "skills", "scanner"]
date_added: "2026-04-11"
---

# skill-scanner

## Purpose

Automates security scanning of CLI skills using the Oath Audit Engine API. This skill handles:
- Submitting skills for security analysis
- Rate limit compliance (60+ second delays)
- Polling for results
- Batch scanning multiple skills
- Error handling (server overload, invalid URLs)

## When to Use This Skill

Use this skill when:
- Submitting a new skill for security audit before publishing
- Batch scanning multiple skills from a repository
- Checking compliance status of existing skills
- Need to poll audit status after submission
- Want to generate security badges for documentation

**Trigger phrases:** "scan skill with oath", "audit skill security", "submit skill to oathe", "check skill compliance", "batch scan skills"

## Core Capabilities

1. **Single Skill Scan** - Submit one skill URL for audit
2. **Batch Scanning** - Process multiple skills with rate limiting
3. **Result Polling** - Automatic status checking until complete
4. **Error Recovery** - Retry with exponential backoff
5. **Badge Generation** - Get security badge URLs

## Quick Start

### Single Skill Scan

```bash
# Submit and poll for result
skill-scan submit https://github.com/owner/skill-repo

# Check specific audit
skill-scan status <audit_id>

# Get badge URL
skill-scan badge https://github.com/owner/skill-repo
```

### Batch Scan

```bash
# Scan all skills in a monorepo
skill-scan batch \
  https://github.com/owner/skills/tree/main/skills/skill-1 \
  https://github.com/owner/skills/tree/main/skills/skill-2 \
  https://github.com/owner/skills/tree/main/skills/skill-3
```

## API Reference

### Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `https://audit-engine.oathe.ai/api/submit` | POST | Submit skill for audit |
| `https://audit-engine.oathe.ai/api/audit/{id}` | GET | Check audit status |
| `https://oathe.ai/api/badge` | GET | Get badge for skill |

### Request/Response Examples

**Submit:**
```bash
POST /api/submit
Content-Type: application/json

{"skill_url": "https://github.com/owner/repo"}

# Response:
{"audit_id": "uuid", "queue_position": 0}
```

**Status:**
```bash
GET /api/audit/{audit_id}

# Response:
{
  "audit_id": "uuid",
  "skill_url": "...",
  "status": "analyzing" | "complete" | "failed",
  "error_message": "..."  # only if failed
}
```

**Badge:**
```bash
GET /api/badge?skill_url=https://github.com/owner/repo

# Returns: SVG badge or redirect to badge
```

### Rate Limits

⚠️ **Critical:** Cloudflare blocks after 1-2 rapid requests

- **Minimum delay:** 60 seconds between API calls
- **Scan duration:** 30-90 seconds per skill
- **Free tier:** 200 scans/month without auth
- **Auth tier:** Higher limits with API key (optional)

## Workflow

### Phase 1: Submission

```bash
# Submit skill
curl -s -X POST "https://audit-engine.oathe.ai/api/submit" \
  -H "Content-Type: application/json" \
  -d '{"skill_url": "URL"}'
```

Expected responses:
- `201 Created` + audit_id → Success, proceed to polling
- `422 repo_not_found` → Check URL (private/deleted)
- `429` → Rate limited, wait 60s+ and retry

### Phase 2: Polling

```bash
# Poll every 30 seconds until complete
while true; do
  result=$(curl -s "https://audit-engine.oathe.ai/api/audit/{audit_id}")
  status=$(echo "$result" | jq -r '.status')

  if [[ "$status" == "complete" ]]; then
    echo "✅ Audit complete"
    break
  elif [[ "$status" == "failed" ]]; then
    echo "❌ Audit failed: $(echo "$result" | jq -r '.error_message')"
    break
  else
    echo "⏳ Still analyzing... (waiting 30s)"
    sleep 30
  fi
done
```

### Phase 3: Result Handling

**Success (complete):**
- Security issues found → Review detailed report
- Clean scan → Generate badge for README

**Failure scenarios:**
- `"Oh no! Looks like we're getting a lot of requests"` → Server overloaded, retry later
- `422 repo_not_found` → Verify repository is public
- Connection closed → Network issue, retry

## Monorepo Scanning

For repositories with multiple skills:

```bash
# Individual skill paths
https://github.com/owner/repo/tree/main/skills/skill-name
https://github.com/owner/repo/tree/branch/skills/another-skill

# Batch scan with rate limiting
for skill_url in "$@"; do
  echo "Scanning: $skill_url"
  result=$(submit_scan "$skill_url")
  audit_id=$(echo "$result" | jq -r '.audit_id')

  # Wait 60s before next submission
  echo "Waiting 60s for rate limit..."
  sleep 60
done
```

⚠️ **Note:** No auto-discovery - each skill must be explicitly submitted

## Error Handling

### Retry Logic

```bash
submit_with_retry() {
  local url=$1
  local retries=3
  local delay=60

  for i in $(seq 1 $retries); do
    result=$(curl -s -X POST "https://audit-engine.oathe.ai/api/submit" \
      -H "Content-Type: application/json" \
      -d "{\"skill_url\": \"$url\"}")

    if [[ "$result" == *"audit_id"* ]]; then
      echo "$result"
      return 0
    elif [[ "$result" == *"429"* ]]; then
      echo "Rate limited, waiting ${delay}s..."
      sleep $delay
      delay=$((delay * 2))  # exponential backoff
    else
      echo "Error: $result"
      return 1
    fi
  done

  return 1
}
```

### Server Overload Handling

When status returns `"failed"` with overload message:

```bash
# Option 1: Retry immediately (may fail again)
sleep 300  # Wait 5 minutes
resubmit_and_poll

# Option 2: Queue for later
queue_scan "$skill_url" --delay 3600  # Retry in 1 hour

# Option 3: Manual retry
# Log failed audit_id and retry manually later
```

## Integration with Skill Creator

After creating a skill with skill-creator:

```bash
# 1. Create skill (local)
skill-creator create my-new-skill

# 2. Push to GitHub
git push origin main

# 3. Scan for security
skill-scan submit https://github.com/owner/my-new-skill

# 4. If clean, add badge to README
echo "![Oath Security](https://oathe.ai/api/badge?skill_url=...)" >> README.md
```

## Output Format

### CLI Output

```
╔════════════════════════════════════════════════════════╗
║ SKILL SECURITY SCANNER - Oath Audit Engine             ║
╠════════════════════════════════════════════════════════╣
║ URL: https://github.com/owner/skill-name               ║
╠════════════════════════════════════════════════════════╣
║ Status: SUBMITTED                                      ║
║ Audit ID: 95ee25db-3910-4b80-8327-6a8fe377d8df        ║
╠════════════════════════════════════════════════════════╣
║ Polling for results...                                 ║
╚════════════════════════════════════════════════════════╝
```

### JSON Output

```json
{
  "scan": {
    "skill_url": "https://github.com/owner/skill",
    "audit_id": "uuid",
    "status": "complete",
    "submitted_at": "2026-04-11T16:30:00Z",
    "completed_at": "2026-04-11T16:32:15Z"
  },
  "result": {
    "passed": true,
    "issues": [],
    "badge_url": "https://oathe.ai/api/badge?skill_url=..."
  }
}
```

## Known Limitations

| Issue | Workaround |
|-------|-----------|
| Server overload | Retry after 5-30 minutes |
| No monorepo discovery | Submit each skill individually |
| MCP server unstable | Use REST API directly |
| No webhook/callback | Poll every 30s |
| 200 scans/month limit | No auth required for free tier |

## References

- **Oath Website:** https://oathe.ai
- **Audit Engine API:** https://audit-engine.oathe.ai
- **Dashboard:** https://oathe.ai/dashboard
- **Badge Endpoint:** https://oathe.ai/api/badge

## Security Notes

- Only scan public repositories
- Do not expose API keys in logs
- Audit IDs are public - no auth required to check status
- Free tier is sufficient for personal/development use
