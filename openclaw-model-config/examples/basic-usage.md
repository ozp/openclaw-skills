# Basic Usage Examples

## Example 1: Viewing Current Configuration

**User input:**
```
show me openclaw models
```

**Expected output:**
```markdown
## ⚙️ Configurações Padrão

| Config | Valor |
|--------|-------|
| **Modelo Primário** | litellm/glm-5.1 |
| **Modelo de Imagem** | litellm/glm-4.6v |
| **Heartbeat Model** | litellm/glm-4.5-air |
| **Subagent Model** | litellm/glm-5.1 |

## 👤 Agentes e seus Modelos

| Agente | Modelo Atual | Provider | Workspace |
|--------|--------------|----------|-----------|
| main | openai-codex/gpt-5.4 | 🟪 Codex | ~/clawd |
| mineru | litellm-anthropic/glm-4.6v | 🟩 Anthropic | ~/clawd/agents/mineru |

[... additional sections ...]
```

## Example 2: Changing Agent Model

**User input:**
```
change the mineru agent to use sonnet
```

**Process:**
1. Read `~/.openclaw/openclaw.json`
2. Locate `mineru` in `agents.list`
3. Identify current model and provider
4. Present options for @sonnet alias (anthropic/claude-sonnet-4-6)
5. Show exact file path and JSON structure
6. Provide copy-paste ready modification

**Output:**
```markdown
## Modificação para Agente `mineru`

Arquivo: `~/.openclaw/openclaw.json`

Mude:
```json
{
  "id": "mineru",
  "model": "litellm-anthropic/glm-4.6v",
  ...
}
```

Para:
```json
{
  "id": "mineru",
  "model": "anthropic/claude-sonnet-4-6",
  ...
}
```

Comando de backup:
```bash
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak.$(date +%Y%m%d-%H%M%S)
```
```

## Example 3: Adding LiteLLM Model

**User input:**
```
add new model glm-5-flash to litellm
```

**Output:**
```markdown
## Adicionar Modelo ao LiteLLM

Arquivo: `~/.config/litellm/config.yaml`

Adicione ao `model_list`:

```yaml
- model_name: glm-5-flash
  litellm_params:
    model: zai/glm-5-flash
    api_key: os.environ/ZAI_API_KEY
    api_base: https://api.z.ai/api/coding/paas/v4
  model_info:
    description: "Z.AI GLM-5 Flash - Fast model for quick tasks"
    tags: ["fast", "chat"]
```

Recarregue LiteLLM:
```bash
systemctl --user restart litellm
```

Verifique:
```bash
curl http://localhost:4000/models | jq '.data[].id'
```
```

## Example 4: Creating New Alias

**User input:**
```
create alias @fast for the flash model
```

**Output:**
```markdown
## Criar Novo Alias @fast

Arquivo: `~/.openclaw/openclaw.json`

Adicione em `agents.defaults.models`:

```json
{
  "litellm/glm-5-flash": {
    "alias": "fast",
    "params": {
      "thinking": "off"
    }
  }
}
```

Uso:
```bash
claude @fast  # Usa litellm/glm-5-flash
```
```
