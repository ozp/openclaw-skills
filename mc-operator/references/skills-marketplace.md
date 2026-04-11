# Skills Marketplace

Manage skill catalogs and skill packs. Skills are registered in the org's marketplace and installed/uninstalled on specific gateways via agent dispatch.

---

## Concepts

- **Marketplace Skill**: A registered skill entry (name, description, category, risk, source URL) in the org catalog.
- **Skill Pack**: A GitHub repository containing multiple skills (discovered via `skills_index.json` or `**/SKILL.md` files). Syncing a pack clones the repo and upserts discovered skills.
- **Gateway Install State**: Tracks which skills are installed on which gateways. Install/uninstall dispatches an instruction message to the gateway agent, which performs the actual operation.
- **Source URLs**: Only GitHub HTTPS URLs are allowed for packs. Direct marketplace skills accept any URL.

---

## Endpoints

All under `/api/v1/skills`. Auth: org admin.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/skills/marketplace` | List marketplace skill cards (with install state for a gateway) |
| `POST` | `/skills/marketplace` | Register/update a direct marketplace skill URL |
| `DELETE` | `/skills/marketplace/{skill_id}` | Delete a marketplace catalog entry + install records |
| `POST` | `/skills/marketplace/{skill_id}/install` | Install a skill on a gateway (dispatches to agent) |
| `POST` | `/skills/marketplace/{skill_id}/uninstall` | Uninstall a skill from a gateway |
| `GET` | `/skills/packs` | List skill packs |
| `GET` | `/skills/packs/{pack_id}` | Get one skill pack |
| `POST` | `/skills/packs` | Register a new skill pack source URL |
| `PATCH` | `/skills/packs/{pack_id}` | Update a skill pack |
| `DELETE` | `/skills/packs/{pack_id}` | Delete a skill pack |
| `POST` | `/skills/packs/{pack_id}/sync` | Clone repo and upsert discovered skills |

---

## Query Parameters

### List marketplace skills (`GET /skills/marketplace`)
| Param | Type | Description |
|---|---|---|
| `gateway_id` | UUID (required) | Gateway to check install state against |
| `search` | string | Search in name, description, category, risk, source |
| `category` | string | Filter by category (`uncategorized` for null) |
| `risk` | string | Filter by risk level (`uncategorized` for null) |
| `pack_id` | UUID | Filter to skills from a specific pack |
| `limit` | int | Pagination limit (1-200) |
| `offset` | int | Pagination offset |

Response headers include `X-Total-Count`, `X-Limit`, `X-Offset` when `limit` is set.

---

## Key Schemas

### MarketplaceSkillCreate
```json
{
  "source_url": "string (required)",
  "name": "string | null",
  "description": "string | null"
}
```

### SkillPackCreate
```json
{
  "source_url": "string (required, GitHub HTTPS only)",
  "name": "string | null",
  "description": "string | null",
  "branch": "string (default: main)",
  "metadata_": {}
}
```

### SkillPackSyncResponse
```json
{
  "pack_id": "uuid",
  "synced": 5,
  "created": 2,
  "updated": 3,
  "warnings": []
}
```

### MarketplaceSkillActionResponse (install/uninstall)
```json
{
  "skill_id": "uuid",
  "gateway_id": "uuid",
  "installed": true
}
```

---

## Common Patterns

### Register a direct skill and install it
```bash
# 1. Register skill
SKILL_ID=$(curl -fsS -X POST "$BASE_URL/api/v1/skills/marketplace" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"source_url":"https://github.com/user/skill-repo","name":"My Skill"}' | jq -r '.id')

# 2. Install on gateway
curl -fsS -X POST "$BASE_URL/api/v1/skills/marketplace/$SKILL_ID/install?gateway_id=$GATEWAY_ID" \
  -H "$AUTH" | jq '.'
```

### Register a pack, sync, and check marketplace
```bash
# 1. Create pack
PACK_ID=$(curl -fsS -X POST "$BASE_URL/api/v1/skills/packs" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"source_url":"https://github.com/user/skill-pack-repo","name":"My Pack"}' | jq -r '.id')

# 2. Sync (clones repo, discovers skills)
curl -fsS -X POST "$BASE_URL/api/v1/skills/packs/$PACK_ID/sync" \
  -H "$AUTH" | jq '{synced, created, updated}'

# 3. List marketplace with install state
curl -fsS "$BASE_URL/api/v1/skills/marketplace?gateway_id=$GATEWAY_ID" \
  -H "$AUTH" | jq '.[] | {name, installed, category}'
```

---

## How Install/Uninstall Works

1. MC dispatches a structured message to the gateway agent via OpenClaw
2. The message contains skill name, source URL, and install destination path
3. Gateway agent clones/copies the skill, verifies discoverability, replies with status
4. MC updates `GatewayInstalledSkill` tracking table
5. If gateway is offline, the API returns `502 Bad Gateway`

---

## Pack Discovery Logic

1. If `skills_index.json` exists in repo root → parse it for skill entries (supports `path`, `name`, `description`, `category`, `risk`, `source_url`)
2. Else → scan recursively for `SKILL.md` files (skipping hidden dirs like `.git`)
3. Skill names inferred from YAML frontmatter `name:` field, or first markdown heading, or directory name
4. Descriptions inferred from YAML frontmatter `description:` field, or first non-heading content line

---

## ozp Skills Pack — Fluxo Operacional

O pack público `ozp/openclaw-skills` já está registrado e sincronizado no MC.

| Item | Valor |
|---|---|
| Repo | https://github.com/ozp/openclaw-skills |
| Local | `/home/ozp/code/openclaw-skills/` |
| Pack ID | `90b5260b-c221-4296-b2c5-6fa064722aac` |
| Branch | `main` |

### Adicionar uma nova skill ao pack

```bash
# 1. Copiar skill para o repo local
cp -r /home/ozp/clawd/skills/<nome-da-skill> /home/ozp/code/openclaw-skills/

# 2. Adicionar entrada no skills_index.json
# Editar /home/ozp/code/openclaw-skills/skills_index.json e adicionar:
# { "path": "<nome-da-skill>", "name": "...", "description": "...", "category": "...", "risk": "low" }

# 3. Commitar e enviar para o GitHub
cd /home/ozp/code/openclaw-skills
git add -A && git commit -m 'feat: add <nome-da-skill>'
git push

# 4. Resincronizar no MC (descobre e importa a nova skill automaticamente)
TOKEN=$(grep LOCAL_AUTH_TOKEN ~/code/openclaw-mission-control/backend/.env | cut -d= -f2)
curl -fsS -X POST "http://localhost:8001/api/v1/skills/packs/90b5260b-c221-4296-b2c5-6fa064722aac/sync" \
  -H "Authorization: Bearer $TOKEN" | jq '{synced, created, updated, warnings}'
```

### Instalar skill no gateway após sync

```bash
TOKEN=$(grep LOCAL_AUTH_TOKEN ~/code/openclaw-mission-control/backend/.env | cut -d= -f2)
GW=2e5ea409-bdcb-4a3d-91a4-70ad9ad6e307
PACK=90b5260b-c221-4296-b2c5-6fa064722aac

# Encontrar o ID da skill no marketplace
SKILL_ID=$(curl -fsS "http://localhost:8001/api/v1/skills/marketplace?gateway_id=$GW&pack_id=$PACK" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.[] | select(.name=="<Nome da Skill>") | .id')

# Instalar
curl -fsS -X POST "http://localhost:8001/api/v1/skills/marketplace/$SKILL_ID/install?gateway_id=$GW" \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

> Se o gateway estiver offline no momento do install, a API retorna 502. Aguardar o gateway agent estar online (`status=online`) antes de instalar.

---

## Source Reference

| File | Purpose |
|---|---|
| `backend/app/api/skills_marketplace.py` | All marketplace + pack endpoints |
| `backend/app/models/skills.py` | `MarketplaceSkill`, `SkillPack`, `GatewayInstalledSkill` models |
| `backend/app/schemas/skills_marketplace.py` | Request/response schemas |
