# skill-scanner

Automated security scanning for CLI skills using the Oath Audit Engine.

## Quick Start

```bash
# Scan a single skill
./scripts/skill-scan.sh submit https://github.com/owner/skill-repo

# Check audit status
./scripts/skill-scan.sh status <audit_id>

# Get security badge
./scripts/skill-scan.sh badge https://github.com/owner/skill-repo

# Batch scan multiple skills
./scripts/skill-scan.sh batch url1 url2 url3
```

## What It Does

This skill automates security audits of Claude/Codex/Copilot skills via the Oath Audit Engine API:

- **Submit** skills for security analysis
- **Poll** for results with automatic rate limiting
- **Handle** Cloudflare protection (60s delays)
- **Retry** on server overload
- **Generate** security badges for documentation

## API Endpoints

| Endpoint | Purpose |
|------------|---------|
| `POST audit-engine.oathe.ai/api/submit` | Submit skill for scan |
| `GET audit-engine.oathe.ai/api/audit/{id}` | Check status |
| `GET oathe.ai/api/badge?skill_url={url}` | Get badge |

## Rate Limits

⚠️ **Critical:** 60+ seconds between API calls (Cloudflare protection)

- Each scan takes 30-90 seconds
- Free tier: 200 scans/month
- No API key required for basic usage

## Known Issues

- Server occasionally overloaded: retry after 10-30 minutes
- No monorepo auto-discovery: submit each skill individually
- MCP server unstable: use REST API directly

## Files

- `SKILL.md` - Full skill documentation
- `references/api-detailed.md` - Complete API reference
- `examples/` - Usage examples
- `scripts/skill-scan.sh` - Main CLI tool
