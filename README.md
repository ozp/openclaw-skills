# openclaw-skills

Public skills compatible with the [OpenClaw Mission Control](https://github.com/openclaw/openclaw-mission-control) marketplace.

## How to use in MC

### Register as Skill Pack

```bash
BASE=http://localhost:8001
TOKEN=<your_token>

# 1. Register the pack
PACK_ID=$(curl -fsS -X POST "$BASE/api/v1/skills/packs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_url":"https://github.com/ozp/openclaw-skills","name":"ozp/openclaw-skills","branch":"main"}' | jq -r '.id')

# 2. Sync (discovers and imports all skills)
curl -fsS -X POST "$BASE/api/v1/skills/packs/$PACK_ID/sync" \
  -H "Authorization: Bearer $TOKEN" | jq '{synced, created, updated}'

# 3. Install a skill to the gateway
SKILL_ID=$(curl -fsS "$BASE/api/v1/skills/marketplace?gateway_id=$GATEWAY_ID" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.[] | select(.name=="MC Operator") | .id')

curl -fsS -X POST "$BASE/api/v1/skills/marketplace/$SKILL_ID/install?gateway_id=$GATEWAY_ID" \
  -H "Authorization: Bearer $TOKEN"
```

## Available Skills

| Skill | Category | Risk | Description |
|---|---|---|---|
| [antv-infographic](./antv-infographic/) | visualization | low | Create data visualizations and infographics using AntV |
| [code-reviewer](./code-reviewer/) | development | low | Review code for quality, best practices, and potential issues |
| [doc-generator](./doc-generator/) | documentation | low | Generate documentation from code and comments |
| [error-analyzer](./error-analyzer/) | debugging | low | Analyze errors and suggest fixes |
| [litellm-cadastrador](./litellm-cadastrador/) | infrastructure | low | Register and manage LiteLLM model configurations |
| [mc-operator](./mc-operator/) | operations | low | Operate Mission Control boards via REST API |
| [mineru](./mineru/) | document-processing | low | Parse PDF/Word/PPT/images to Markdown via MinerU API |
| [openclaw-agent-creator](./openclaw-agent-creator/) | infrastructure | medium | Create and bootstrap OpenClaw agents with complete workspace |
| [openclaw-audit](./openclaw-audit/) | security | low | Audit OpenClaw installation for security and configuration |
| [openclaw-model-config](./openclaw-model-config/) | configuration | safe | Generate and manage OpenClaw model/provider configurations |
| [openclaw-session-governance](./openclaw-session-governance/) | infrastructure | low | Audit and govern OpenClaw session lifecycle |
| [openclaw-update](./openclaw-update/) | maintenance | low | Update OpenClaw gateway and CLI to latest version |
| [prompt-improver](./prompt-improver/) | productivity | low | Improve prompts applying prompt engineering techniques |
| [repo-ecosystem-evaluator](./repo-ecosystem-evaluator/) | analysis | low | Evaluate repositories for architectural quality and stack fit |
| [serena-source-consultation](./serena-source-consultation/) | research | low | Consult source code to verify system behavior |
| [skill-check](./skill-check/) | development | safe | Validate Claude Code skills against agentskills specification |
| [skill-creator](./skill-creator/) | meta | safe | Create new CLI skills following best practices |
| [skill-scanner](./skill-scanner/) | security | safe | Scan and analyze skills for security and quality |
| [skills-discovery](./skills-discovery/) | meta | low | Search for and install Agent Skills |
| [task-decomposer](./task-decomposer/) | productivity | low | Break down complex tasks into manageable steps |
| [taskmaster-setup](./taskmaster-setup/) | infrastructure | low | Configure TaskMaster AI with LiteLLM proxy |
| [task-tracker-openclaw-skill](./task-tracker-openclaw-skill/) | productivity | low | Personal task management with daily standups and weekly reviews |

## Adding Skills to this Repository

### Option 1: Use the Sync Script (Recommended)

Use the `sync-skills.sh` script to automatically sync skills from your local directories:

```bash
# Add/update all skills from local directories
./sync-skills.sh

# Add only specific skills
./sync-skills.sh skill-name-1 skill-name-2
```

### Option 2: Manual Process

To manually add a new skill:

1. Create a directory with the skill name (e.g., `my-skill/`)
2. Add a `SKILL.md` with YAML frontmatter:
   ```yaml
   ---
   name: My Skill
   description: What it does and when to use it.
   category: operations
   risk: low
   ---
   ```
3. Add the entry to `skills_index.json`
4. Push and resync in MC: `POST /api/v1/skills/packs/{pack_id}/sync`

## Sync Script

The `sync-skills.sh` script in this repository handles:

- **Adding new skills** from `/home/ozp/clawd/skills/` and `/home/ozp/.wcgw/skills/`
- **Updating existing skills** when local versions have changed (based on file modification time or hash)
- **Updating `skills_index.json`** automatically with new entries
- **Generating README** skill table automatically

### Usage

```bash
./sync-skills.sh              # Sync all skills from local directories
./sync-skills.sh --dry-run    # Preview changes without applying
./sync-skills.sh skill-name   # Sync only specific skill
```

### Directories Scanned

The script scans these directories for skills:
- `/home/ozp/clawd/skills/` - Main OpenClaw skills
- `/home/ozp/.wcgw/skills/` - WCGW skills
