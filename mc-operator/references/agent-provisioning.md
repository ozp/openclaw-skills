# Agent Provisioning — Profiles, Models & Onboarding

Reference for creating, configuring, and onboarding MC agents manually.
Covers worker agents (direct API), lead agent onboarding, profile catalog,
and per-agent model assignment via the OpenClaw gateway.

---

## 1. Authentication Recap

```bash
BASE_URL="http://localhost:8001"
TOKEN="60c544afef66c229f689db586b03c56e330a34bfb5470f8fb0b24db54f441fdc"
AUTH="Authorization: Bearer $TOKEN"
```

Two endpoints for agent creation — choose based on role:

| Use case | Endpoint | Auth required |
|---|---|---|
| Create worker agent | `POST /api/v1/agents` | User bearer token |
| Create lead agent (onboarding) | `POST /api/v1/boards/{id}/onboarding/confirm` | User bearer token |
| Create agent as board lead | `POST /api/v1/agent/agents` | Agent token (lead only) |

---

## 2. Agent Profile Catalog

`identity_profile` defines how the agent presents itself and how the lead routes work to it.
The gateway uses `identity_profile.role` to fetch a matching SOUL template from the community directory.

### Canonical Profiles

#### executor — Implementation Worker
```json
{
  "role": "Software Engineer",
  "communication_style": "technical, action-oriented, concise",
  "emoji": ":wrench:"
}
```
Use for: code implementation, file editing, running scripts, deployments.

#### reviewer — Quality Gate
```json
{
  "role": "Senior Code Reviewer",
  "communication_style": "analytical, constructive, detailed",
  "emoji": ":shield:"
}
```
Use for: PR review, logic validation, security checks, acceptance criteria verification.
> **Tip:** Assign a *different model* to this agent to get a genuinely independent perspective.

#### researcher — Analysis & Discovery
```json
{
  "role": "Research Analyst",
  "communication_style": "structured, evidence-based, thorough",
  "emoji": ":brain:"
}
```
Use for: codebase exploration, documentation synthesis, technology evaluation, spike tasks.

#### architect — Design Decisions
```json
{
  "role": "Software Architect",
  "communication_style": "strategic, systems-thinking, precise",
  "emoji": ":bulb:"
}
```
Use for: architecture proposals, trade-off analysis, refactoring roadmaps, ADRs.

#### coordinator — Cross-board Liaison
```json
{
  "role": "Project Coordinator",
  "communication_style": "clear, diplomatic, summary-focused",
  "emoji": ":megaphone:"
}
```
Use for: inter-board handoffs, status aggregation, dependency tracking.

#### analyst — Metrics & Reporting
```json
{
  "role": "Data Analyst",
  "communication_style": "data-driven, visual, concise",
  "emoji": ":chart_with_upwards_trend:"
}
```
Use for: metrics collection, cost analysis, dashboards, evaluation pipelines.

#### docwriter — Documentation
```json
{
  "role": "Technical Writer",
  "communication_style": "clear, user-focused, structured",
  "emoji": ":memo:"
}
```
Use for: API docs, guides, READMEs, internal wikis, prompt documentation.

### Extended Identity Fields

Beyond the basic profile, `identity_profile` accepts any key-value pairs the agent can read:

```json
{
  "role": "Senior Code Reviewer",
  "communication_style": "analytical, constructive",
  "emoji": ":shield:",
  "autonomy_level": "balanced",
  "verbosity": "concise",
  "output_format": "bullets",
  "update_cadence": "daily",
  "custom_instructions": "Always check for SQL injection vectors. Flag any hardcoded secrets."
}
```

**Enum values (used by lead agent template rendering):**
- `autonomy_level`: `ask_first` | `balanced` | `autonomous`
- `verbosity`: `concise` | `balanced` | `detailed`
- `output_format`: `bullets` | `mixed` | `narrative`
- `update_cadence`: `asap` | `hourly` | `daily` | `weekly`

---

## 3. Model Selection — Read from Config at Runtime

**Do not rely on any hardcoded model list.** Models are configured in
`~/.openclaw/openclaw.json` and change over time. Always read the live config
before choosing a model, then apply the selection criteria below.

### Step 1 — List available models

```bash
python3 << 'EOF'
import json

cfg = json.load(open('/home/ozp/.openclaw/openclaw.json'))
providers = cfg.get('models', {}).get('providers', {})

print(f"{'Model string':<50} {'Name':<35} {'Context':>10}  {'Reasoning'}")
print("-" * 110)
for provider, data in providers.items():
    for m in data.get('models', []):
        model_str = f"{provider}/{m['id']}"
        name = m.get('name', m['id'])
        ctx = m.get('contextWindow', '')
        reasoning = '✓' if m.get('reasoning') else ''
        print(f"{model_str:<50} {name:<35} {str(ctx):>10}  {reasoning}")
EOF
```

Also list what's currently assigned to existing agents:

```bash
python3 -c "
import json
cfg = json.load(open('/home/ozp/.openclaw/openclaw.json'))
print('DEFAULT:', cfg['agents']['defaults']['model']['primary'])
print()
for a in cfg['agents']['list']:
    print(a['id'][:40], '|', a.get('name',''), '|', a.get('model','(default)'))
"
```

### Step 2 — Apply selection criteria by role

Once you have the live model list, choose based on these criteria:

**Main model (agent tasks):**

| Need | Pick the model with… |
|---|---|
| Deep reasoning / complex tasks | `reasoning: true` + largest `contextWindow` |
| Large diffs / long documents | largest `contextWindow` available |
| Balanced speed + quality | `reasoning: true` + mid-range context |
| Fast execution / simple tasks | smallest model with `reasoning: true` or none |
| Multimodal (images) | `input` includes `"image"` |
| **Reviewer / independent POV** | **Different model than the one used by executor/lead** — this is the primary reason to vary models across agents |

**Heartbeat model (periodic check-ins):**
Always pick the fastest/cheapest model available — the one with the smallest context
window and no reasoning flag. It only needs to process a short status prompt.

**Subagents model (if agent spawns sub-tasks):**
Match the main model unless cost is a concern; then one tier below.

### Step 3 — Check the current default

```bash
python3 -c "
import json
cfg = json.load(open('/home/ozp/.openclaw/openclaw.json'))
d = cfg['agents']['defaults']
print('primary:', d['model']['primary'])
print('fallbacks:', d['model'].get('fallbacks', []))
print('heartbeat:', d.get('heartbeat', {}).get('model', '(none)'))
print('subagents:', d.get('subagents', {}).get('model', '(none)'))
"
```

The default is applied to any agent that does **not** have an explicit `model` entry
in `agents.list`. You only need to set a model explicitly when deviating from the default.

---

## 4. Creating a Worker Agent (Direct API)

`POST /api/v1/agents` accepts the user bearer token directly — no lead agent needed.
The new agent is provisioned on the OpenClaw gateway and workspace files are written immediately.

### Minimal Creation

```bash
curl -fsS -X POST "$BASE_URL/api/v1/agents" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{
    "name": "Vex",
    "board_id": "<BOARD_UUID>",
    "heartbeat_config": {
      "every": "10m",
      "target": "last",
      "includeReasoning": false
    },
    "identity_profile": {
      "role": "Senior Code Reviewer",
      "communication_style": "analytical, constructive, detailed",
      "emoji": ":shield:"
    }
  }' | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['id'], d['name'], d['status'])"
```

### Full Creation with Templates

```bash
curl -fsS -X POST "$BASE_URL/api/v1/agents" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{
    "name": "Vex",
    "board_id": "<BOARD_UUID>",
    "heartbeat_config": {
      "every": "10m",
      "target": "last",
      "includeReasoning": false
    },
    "identity_profile": {
      "role": "Senior Code Reviewer",
      "communication_style": "analytical, constructive, detailed",
      "emoji": ":shield:",
      "autonomy_level": "balanced",
      "verbosity": "concise",
      "output_format": "bullets",
      "custom_instructions": "Flag hardcoded secrets, SQL injection, and missing error handling."
    },
    "identity_template": "You are Vex, a Senior Code Reviewer on the {{board_name}} board.\nYour primary function is quality assurance. Review all code changes critically, flag security issues immediately, and maintain high standards without being obstructive.",
    "soul_template": "You care deeply about code quality and team security. You ask hard questions. You never approve work you have doubts about. You explain *why* something is wrong, not just that it is."
  }' | python3 -m json.tool
```

### Capture Agent ID for Subsequent Steps

```bash
AGENT_ID=$(curl -fsS -X POST "$BASE_URL/api/v1/agents" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"Vex","board_id":"<BOARD_UUID>","heartbeat_config":{"every":"10m","target":"last","includeReasoning":false},"identity_profile":{"role":"Senior Code Reviewer","emoji":":shield:"}}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
echo "Agent created: $AGENT_ID"
```

---

## 5. Assigning a Model to an Agent (Post-Creation)

The MC API does not expose a model field. Model assignment is done via a gateway `config.patch`
**after** the agent is created. The gateway preserves the `model` field through all subsequent
MC updates — the patch code does `dict(existing_entry)` before overwriting `workspace` and
`heartbeat`, so any extra fields (including `model`) survive.

### Agent Key Format in Gateway Config

- Worker agents: `mc-<agent_uuid>` — e.g. `mc-60a40f67-313f-4b0f-891c-8b8f6f349a51`
- Lead agents: `lead-<agent_uuid>` — e.g. `lead-ab429505-87ff-4373-9991-8ff066f82d00`

### Inspect Current State

```bash
python3 -c "
import json
cfg = json.load(open('/home/ozp/.openclaw/openclaw.json'))
for a in cfg['agents']['list']:
    print(a['id'], '|', a.get('name','—'), '|', a.get('model','(default)'))
"
```

### Method A — Edit openclaw.json directly (fastest)

The gateway hot-reloads within ~500ms. Use this for bulk changes.

```bash
python3 << 'PYEOF'
import json

cfg_path = '/home/ozp/.openclaw/openclaw.json'
cfg = json.load(open(cfg_path))

# Set these:
AGENT_GW_ID = "mc-<agent_uuid>"          # or lead-<agent_uuid>
MODEL = "litellm-anthropic/kimi-k2p5-turbo"
HB_MODEL = "litellm-anthropic/glm-4.5-air"

agents_list = cfg['agents']['list']
found = False
for entry in agents_list:
    if entry['id'] == AGENT_GW_ID:
        entry['model'] = MODEL
        entry.setdefault('heartbeat', {})['model'] = HB_MODEL
        found = True
        break

if not found:
    # Not yet in list — MC fills workspace/heartbeat on next provision cycle
    agents_list.append({
        'id': AGENT_GW_ID,
        'model': MODEL,
        'heartbeat': {'model': HB_MODEL}
    })

with open(cfg_path, 'w') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print(f"Model set: {AGENT_GW_ID} -> {MODEL} | hb: {HB_MODEL}")
PYEOF
```

### Method B — Gateway RPC config.patch

```bash
GATEWAY_ID="2e5ea409-bdcb-4a3d-91a4-70ad9ad6e307"
AGENT_GW_ID="mc-<agent_uuid>"
MODEL="litellm-anthropic/kimi-k2p5-turbo"
HB_MODEL="litellm-anthropic/glm-4.5-air"

PATCH=$(python3 -c "
import json
patch = {'agents': {'list': [{'id': '$AGENT_GW_ID', 'model': '$MODEL', 'heartbeat': {'model': '$HB_MODEL'}}]}}
print(json.dumps(json.dumps(patch)))
")

curl -fsS -X POST "$BASE_URL/api/v1/gateways/$GATEWAY_ID/rpc" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"method\": \"config.patch\", \"params\": {\"raw\": $PATCH}}" \
  | python3 -m json.tool
```

### Verify

```bash
python3 -c "
import json
cfg = json.load(open('/home/ozp/.openclaw/openclaw.json'))
target = 'mc-<agent_uuid>'
for a in cfg['agents']['list']:
    if a['id'] == target:
        print('model:', a.get('model', '(default)'))
        print('heartbeat.model:', a.get('heartbeat', {}).get('model', '(default)'))
"
```

---

## 6. Creating a Lead Agent — Onboarding Flow

Lead agents are created via the board onboarding flow. The gateway main agent (ANV15-51)
facilitates the conversation, then MC provisions the lead upon `/confirm`.

### Path A — Full Conversational Onboarding (recommended for new boards)

```bash
# 1. Start onboarding (triggers gateway agent to begin asking questions)
curl -fsS -X POST "$BASE_URL/api/v1/boards/$BOARD_ID/onboarding/start" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{}' | python3 -c "import json,sys; print('Status:', json.load(sys.stdin)['status'])"

# 2. Poll state — check the latest assistant message/question
curl -fsS "$BASE_URL/api/v1/boards/$BOARD_ID/onboarding" \
  -H "$AUTH" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for m in (d.get('messages') or [])[-3:]:
    print(m['role'].upper(), ':', m.get('content','')[:300])
print('--- status:', d['status'])
"

# 3. Answer questions by option ID or free text (repeat until status=completed)
curl -fsS -X POST "$BASE_URL/api/v1/boards/$BOARD_ID/onboarding/answer" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"answer": "2"}' \
  | python3 -c "import json,sys; print('Status:', json.load(sys.stdin)['status'])"

# Free-text answer with "Other" option:
curl -fsS -X POST "$BASE_URL/api/v1/boards/$BOARD_ID/onboarding/answer" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"answer": "Other", "other_text": "Focus on async/await patterns and data pipeline integrity"}' \
  | python3 -c "import json,sys; print('Status:', json.load(sys.stdin)['status'])"

# 4. Confirm when status=completed (provisions the lead agent)
curl -fsS -X POST "$BASE_URL/api/v1/boards/$BOARD_ID/onboarding/confirm" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{
    "board_type": "goal",
    "objective": "Automate code review and quality gates for the backend",
    "success_metrics": {"coverage": ">= 80%", "review_turnaround": "< 2h"},
    "target_date": "2026-06-30"
  }' | python3 -c "import json,sys; d=json.load(sys.stdin); print('Board confirmed:', d['id'])"
```

### Path B — Direct Lead Provisioning (no conversation, explicit config)

When you already know the board goal, confirm directly without starting the conversation.
The lead agent is created with default name "Lead Agent" and default `identity_profile`.

```bash
curl -fsS -X POST "$BASE_URL/api/v1/boards/$BOARD_ID/onboarding/confirm" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{
    "board_type": "goal",
    "objective": "Maintain architectural integrity across the monorepo",
    "success_metrics": {
      "adr_coverage": "all major decisions documented",
      "tech_debt_ratio": "< 15%"
    },
    "target_date": "2026-12-31"
  }' | python3 -m json.tool
```

> **After creation:** Rename the lead and tune its profile:
>
> ```bash
> curl -fsS -X PATCH "$BASE_URL/api/v1/agents/$LEAD_ID" \
>   -H "$AUTH" -H "Content-Type: application/json" \
>   -d '{
>     "name": "Drax",
>     "identity_profile": {
>       "role": "Board Lead",
>       "communication_style": "strategic, decisive, concise",
>       "emoji": ":rocket:",
>       "autonomy_level": "autonomous",
>       "verbosity": "concise",
>       "output_format": "bullets"
>     }
>   }'
> ```

### Find the New Lead After Provisioning

```bash
curl -fsS "$BASE_URL/api/v1/agents?board_id=$BOARD_ID" \
  -H "$AUTH" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for a in d['items']:
    if a['is_board_lead']:
        print('Lead ID:', a['id'])
        print('Name:', a['name'])
        print('Status:', a['status'])
"
```

Then apply section 5 with gateway key `lead-<lead_agent_id>`.

---

## 7. Complete Workflow — New Board with Custom Lead + Workers

```bash
BASE_URL="http://localhost:8001"
TOKEN="60c544afef66c229f689db586b03c56e330a34bfb5470f8fb0b24db54f441fdc"
AUTH="Authorization: Bearer $TOKEN"
BOARD_ID="<your-board-uuid>"

# --- Step 1: Provision lead via onboarding confirm ---
curl -fsS -X POST "$BASE_URL/api/v1/boards/$BOARD_ID/onboarding/confirm" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"board_type":"goal","objective":"Build the Karakeep -> MC pipeline","success_metrics":{"uptime":">=99%"},"target_date":"2026-09-01"}'

# --- Step 2: Find lead ID and assign model ---
LEAD_ID=$(curl -fsS "$BASE_URL/api/v1/agents?board_id=$BOARD_ID" -H "$AUTH" \
  | python3 -c "import json,sys; [print(a['id']) for a in json.load(sys.stdin)['items'] if a['is_board_lead']]")

# Rename lead and set model
curl -fsS -X PATCH "$BASE_URL/api/v1/agents/$LEAD_ID" -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"name":"Nexus","identity_profile":{"role":"Board Lead","communication_style":"strategic, concise","emoji":":rocket:","autonomy_level":"autonomous"}}'

# Edit openclaw.json: set lead-$LEAD_ID model = litellm-anthropic/kimi-k2p5-turbo

# --- Step 3: Create executor worker ---
FORGE_ID=$(curl -fsS -X POST "$BASE_URL/api/v1/agents" -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Forge\",\"board_id\":\"$BOARD_ID\",\"heartbeat_config\":{\"every\":\"10m\",\"target\":\"last\",\"includeReasoning\":false},\"identity_profile\":{\"role\":\"Software Engineer\",\"communication_style\":\"technical, action-oriented\",\"emoji\":\":wrench:\",\"autonomy_level\":\"autonomous\"}}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

# Edit openclaw.json: mc-$FORGE_ID -> litellm-anthropic/glm-5-turbo

# --- Step 4: Create reviewer worker (different model for independent POV) ---
VEX_ID=$(curl -fsS -X POST "$BASE_URL/api/v1/agents" -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Vex\",\"board_id\":\"$BOARD_ID\",\"heartbeat_config\":{\"every\":\"15m\",\"target\":\"last\",\"includeReasoning\":false},\"identity_profile\":{\"role\":\"Senior Code Reviewer\",\"communication_style\":\"analytical, constructive\",\"emoji\":\":shield:\",\"autonomy_level\":\"balanced\",\"custom_instructions\":\"Verify security, edge cases, and error paths before approving.\"}}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

# Edit openclaw.json: mc-$VEX_ID -> litellm-anthropic/kimi-k2p5-turbo (large context + diff perspective)

echo "Board provisioned. Lead: $LEAD_ID | Forge: $FORGE_ID | Vex: $VEX_ID"
```

---

## 8. Reference — Boards, Agents & Gateway IDs

### Boards

| UUID | Name |
|---|---|
| `40851a1e-fe67-460c-889f-eba0d8649b1a` | Agent Architecture |
| `ab429505-87ff-4373-9991-8ff066f82d00` | Experimental |
| `ba06d446-93ce-484a-85eb-9a18ca1104d1` | External Triage |
| `ee065313-414e-4113-83c1-2b3eb3f30d8e` | Governance & Gates |
| `0f302d65-dd09-4fd3-848f-8989636d9334` | Infrastructure Baseline |
| `7aa5ee71-938f-4b61-9e61-603a731b2753` | Integrations |
| `78fad92f-6aa2-446f-9120-f30c70ce9cd7` | Knowledge & RAG |
| `76f10c1e-6f4e-4d42-b2dc-d5cc1fe6c926` | Models & Cost |
| `7478d357-f8da-4426-8343-464eb602ff9b` | Prompts & Docs |
| `2df94061-0c2b-4e7e-8a64-4e3a2b3591eb` | UNIP Operations |

### Current Agents

| MC Agent ID | Name | Role | Board | Gateway key |
|---|---|---|---|---|
| `9f38c39a-1e29-4ee3-91fd-0b2c96d72eeb` | Cerebelo | Lead | Agent Architecture | `lead-9f38c39a-...` |
| `b3e77265-c12d-482b-a5f5-8a86472f6c31` | Axion | Lead | Experimental | `lead-b3e77265-...` |
| `60a40f67-313f-4b0f-891c-8b8f6f349a51` | SkillDoc | Worker | Experimental | `mc-60a40f67-...` |
| `9c7ffe35-62b0-4ad6-a397-658596747f05` | Gateway Agent | Gateway Main | — | `mc-gateway-2e5ea409-...` |

### Gateway

| Resource | Value |
|---|---|
| Gateway ID | `2e5ea409-bdcb-4a3d-91a4-70ad9ad6e307` |
| Gateway URL | `ws://host.docker.internal:18789` |
| Org ID | `ff417ce6-33a0-4a88-9fdb-1faea58511e4` |

---

## 9. Updating an Existing Agent

```bash
# Tune profile without re-provisioning
curl -fsS -X PATCH "$BASE_URL/api/v1/agents/$AGENT_ID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{
    "identity_profile": {
      "role": "Senior Code Reviewer",
      "communication_style": "blunt and direct — no sugarcoating",
      "custom_instructions": "Treat all PRs as security-sensitive until proven otherwise."
    }
  }' | python3 -c "import json,sys; d=json.load(sys.stdin); print('Updated:', d['name'], d['status'])"

# Force re-provision — pushes updated workspace files to gateway
curl -fsS -X PATCH "$BASE_URL/api/v1/agents/$AGENT_ID?force=true" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{}' | python3 -c "import json,sys; d=json.load(sys.stdin); print('Reprovisioned:', d['name'], d['status'])"
```

---

## 10. max_agents Limit

Each board has a `max_agents` field limiting worker count (lead excluded).
This limit only applies when the **lead agent** creates workers via its agent token.
User-token creation bypasses the limit entirely. To raise it for lead-managed boards:

```bash
curl -fsS -X PATCH "$BASE_URL/api/v1/boards/$BOARD_ID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"max_agents": 5}' \
  | python3 -c "import json,sys; print('max_agents:', json.load(sys.stdin)['max_agents'])"
```

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Agent stuck in `provisioning` | Gateway offline or session error | `PATCH /agents/{id}?force=true` |
| Lead agent not appearing on board | Onboarding not confirmed | Complete `/confirm` step |
| Model not taking effect | Entry not in `agents.list` or gateway not reloaded | Check `openclaw.json`; wait ~2s for hot-reload |
| `409 Conflict` on agent create (as lead) | `max_agents` limit reached | Raise `max_agents` or use user token |
| Agent `offline` after backend restart | Gateway session in `done` state | `PATCH /agents/{id}?force=true` |
| `401` on `/api/v1/agent/*` | Admin token used on agent-scoped endpoint | Use agent token for agent-scoped paths |
| Onboarding stuck at `active` | Gateway agent not responding | Re-send via `/start` (retriggers if pending answer) |
