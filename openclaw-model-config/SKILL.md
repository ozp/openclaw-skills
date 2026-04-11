---
name: openclaw-model-config
description: "This skill generates complete OpenClaw model/provider configuration tables and provides comprehensive instructions for model modifications and provider management"
triggers:
  - pattern: "openclaw modelos?"
  - pattern: "quais (agentes|modelos|provedores)"
  - pattern: "config(uração)? (de )?modelos"
  - pattern: "trocar modelo"
  - pattern: "alterar (provider|modelo)"
  - pattern: "como (configurar|mudar) modelo"
  - pattern: "openclaw-status"
tags: [openclaw, models, configuration, litellm]
entrypoint: SKILL.md
category: configuration
risk: safe
author: ozp
date_added: "2026-04-11"
version: "1.0.0"
---

# openclaw-model-config

## Purpose

This skill provides comprehensive visualization and configuration management for OpenClaw models and providers. It reads configuration files, generates detailed tables showing current setups, and provides step-by-step instructions for making modifications to models, providers, and agent configurations.

## When to Use This Skill

This skill should be used when:
- User needs to view current OpenClaw model configurations in a readable format
- User wants to change the model assigned to a specific agent
- User needs to modify default models (primary, fallback, image, heartbeat, subagents)
- User wants to add a new model to LiteLLM proxy
- User needs to add a new provider to OpenClaw
- User wants to create or modify model aliases (e.g., @sonnet, @opus)
- User requests "openclaw-status" or model overview information
- User asks about available agents and their configurations

## Core Capabilities

1. **Configuration Discovery** - Automatically reads `~/.openclaw/openclaw.json` and `~/.config/litellm/config.yaml`
2. **Table Generation** - Creates comprehensive Markdown tables for quick scanning
3. **Agent Matrix** - Displays all agents with their current models, providers, and workspaces
4. **Alias Documentation** - Lists all available @aliases with their real model mappings
5. **Provider Legend** - Visual emoji-based provider identification system
6. **Modification Guides** - Step-by-step instructions for all common configuration changes

## Step 1: Read Configuration Files

When this skill is triggered, first read these configuration files to gather current state:

1. `~/.openclaw/openclaw.json` - Main OpenClaw configuration containing agents, defaults, and providers
2. `~/.config/litellm/config.yaml` - LiteLLM proxy configuration with available models
3. `~/clawd/CONFIG-MODELS.md` - Optional cached snapshot from previous runs

Use the Read tool to access these files. If they do not exist, report the missing configuration to the user and suggest checking their OpenClaw installation.

## Step 2: Generate Configuration Tables

After reading the configuration files, generate a comprehensive Markdown document with the following sections:

### Section A: Quick Reference - Default Models

Create a table showing the global default configuration:

```markdown
## ⚙️ Configurações Padrão

| Config | Valor |
|--------|-------|
| **Modelo Primário** | `{agents.defaults.model.primary}` |
| **Fallback Chain** | List first 3 fallbacks |
| **Modelo de Imagem** | `{agents.defaults.imageModel}` |
| **Heartbeat Model** | `{agents.defaults.heartbeat.model}` |
| **Subagent Model** | `{agents.defaults.subagents.model}` |
| **Subagent Thinking** | `{agents.defaults.subagents.thinking}` |
```

### Section B: Agent Configuration Matrix (REQUIRED)

**ALWAYS generate this table** when this skill is triggered. This is the primary output expected by the user.

Create a comprehensive table with **ALL** configured agents showing:

```markdown
## 👤 TABELA COMPLETA — Agentes, Modelos e Fallbacks

| # | Agente | Nome | Modelo Atual | Provider | Fallbacks | Heartbeat | Workspace |
|---|--------|------|--------------|----------|-----------|-----------|-----------|
| 1 | main | — | litellm/glm-5.1 | 🟦 LiteLLM | litellm/glm-5.1 → zai/glm-5.1 → litellm/kimi-k2p5-turbo | 30m | ~/clawd |
| 2 | mineru | mineru | litellm-anthropic/glm-4.6v | 🟩 Anthropic | (herda defaults) | — | ~/clawd/agents/mineru |
| ... | ... | ... | ... | ... | ... | ... | ... |
```

**Required columns:**
- `#` - Sequential numbering of all agents
- `Agente` - Agent ID from `agents.list[].id`
- `Nome` - Agent name from `agents.list[].name` (if exists, else "—")
- `Modelo Atual` - Full model string from `agents.list[].model`
- `Provider` - Provider emoji + name from parsing model string prefix
- `Fallbacks` - Show fallback chain:
  - For `main` agent: List ALL fallbacks from `agents.defaults.model.fallbacks[]`
  - For other agents: Write "(herda defaults)" or "(inherits defaults)"
- `Heartbeat` - Interval from `agents.list[].heartbeat.every` or "—"
- `Workspace` - Path from `agents.list[].workspace`

**After the table, ALWAYS add:**
1. A summary table by Provider (count + agent list)
2. A summary table by Model (count + agent list)
3. The fallback chain diagram showing the sequence

**Data extraction rules:**
- Extract ALL agents from `agents.list[]` - never skip any
- Use provider emoji mapping: litellm=🟦, litellm-anthropic=🟩, zai=🟨, anthropic=🟥, openai-codex=🟪
- If agent has no explicit fallbacks, it uses the global defaults

### Section C: Model Aliases Available

Document all available aliases that can be used with `@alias` syntax:

```markdown
## 📋 Aliases Disponíveis (via @alias)

| Alias | Modelo Real | Thinking | Uso Recomendado |
|-------|-------------|----------|-----------------|
| @sonnet | anthropic/claude-sonnet-4-6 | adaptive | Balanceado, uso geral |
| @opus | anthropic/claude-opus-4-6 | adaptive | Máxima capacidade |
| @glm5.1 | zai/glm-5.1 | adaptive | Principal Z.AI |
| @glm5turbo | zai/glm-5-turbo | adaptive | Rápido Z.AI |
| @codex | openai-codex/gpt-5.4 | adaptive | Coding especializado |
| ... | ... | ... | ... |
```

Aliases are typically defined in `agents.defaults.models` with their alias property.

### Section D: Provider Legend

Create a legend mapping emoji indicators to provider configurations:

```markdown
## 🎨 Legenda de Providers

| Emoji | Provider | Tipo | URL/Base |
|-------|----------|------|----------|
| 🟦 | `litellm` | OpenAI API | http://localhost:4000/v1 |
| 🟩 | `litellm-anthropic` | Anthropic API | http://localhost:4000/v1 |
| 🟨 | `zai` | Z.AI direto | https://api.z.ai/api/coding/paas/v4 |
| 🟥 | `anthropic` | Anthropic direto | https://api.anthropic.com |
| 🟪 | `openai-codex` | OpenAI Codex | https://api.openai.com |
```

Match the emoji to the provider prefix in model strings (e.g., `litellm/*` → 🟦).

### Section E: LiteLLM Model List

If LiteLLM is configured, list available models from the proxy:

```markdown
## 🔌 LiteLLM Models (via localhost:4000)

| Model Name | Provider Real | Tags |
|------------|---------------|------|
| glm-5.1 | zai/glm-5.1 | chat, vision |
| glm-4.6v | zai/glm-4.6v | chat, vision |
| glm-5-turbo | zai/glm-5-turbo | fast |
```

## Step 3: Validation Checks

Before presenting the configuration, perform these validation checks:

### Check 1: Model Consistency
Verify that each agent's model references a valid provider. If an agent uses `provider/model-id`, check if that provider exists in `models.providers`.

### Check 2: Fallback Chain Validity
Check that all fallbacks in `agents.defaults.model.fallbacks[]` reference valid, available models.

### Check 3: LiteLLM Health
Attempt to verify if LiteLLM proxy is responding at `http://localhost:4000/health`. Note the status in output.

### Check 4: Environment Variables
Check if referenced API keys (format: `${VAR_NAME}`) are likely to be available. Common variables:
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `ZAI_API_KEY`
- `LITELLM_MASTER_KEY`

## Step 4: Modification Instructions

Always include this comprehensive guide at the end of the output:

```markdown
---

## 🔧 Como Alterar Configurações

### Alterar Modelo de um Agente Específico

**Arquivo:** `~/.openclaw/openclaw.json`

Localize o agente na seção `agents.list`:
```json
{
  "id": "nome-agente",
  "model": "PROVIDER/MODELO-ATUAL",  // ← ALTERAR AQUI
  ...
}
```

**Formato:** `provider/model-id`
**Providers disponíveis:**
- `litellm/*` → Via LiteLLM proxy (OpenAI API)
- `litellm-anthropic/*` → Via LiteLLM (Anthropic API)
- `zai/*` → Z.AI direto
- `anthropic/*` → Anthropic API direta
- `openai-codex/*` → OpenAI Codex

### Alterar Defaults Globais

**Arquivo:** `~/.openclaw/openclaw.json`

Seção `agents.defaults`:
```json
{
  "model": {
    "primary": "litellm/glm-5.1",      // ← Modelo padrão
    "fallbacks": ["litellm/glm-5.1", "zai/glm-5.1"]  // ← Fallback chain
  },
  "imageModel": "litellm/glm-4.6v",   // ← Modelo para imagens
  "heartbeat": {
    "model": "litellm/glm-4.5-air"    // ← Modelo heartbeat
  },
  "subagents": {
    "model": "litellm/glm-5.1"        // ← Modelo subagentes
  }
}
```

### Adicionar Novo Modelo (LiteLLM)

**Arquivo:** `~/.config/litellm/config.yaml`

Adicionar em `model_list`:
```yaml
- model_name: meu-novo-modelo
  litellm_params:
    model: provider/nome-real-do-modelo
    api_key: os.environ/NOME_API_KEY
    api_base: https://api.provider.com/v1
  model_info:
    description: "Descrição do modelo"
    tags: ["tag1", "tag2"]
```

**Recarregar LiteLLM:**
```bash
# Verificar se está rodando
curl http://localhost:4000/health

# Restart se necessário (systemd user service)
systemctl --user restart litellm  # ou kill + reinit
```

### Adicionar Provider Novo

**Arquivo:** `~/.openclaw/openclaw.json`

Seção `models.providers`:
```json
{
  "meu-provider": {
    "baseUrl": "https://api.novo.com/v1",
    "apiKey": "${MINHA_API_KEY}",
    "auth": "api-key",
    "api": "openai-completions",
    "models": [
      {"id": "modelo-1", "name": "Modelo 1"}
    ]
  }
}
```

### Usar Aliases (@alias)

Na CLI ou código, use `@alias` para referenciar modelos:
```bash
# Exemplos de uso
claude @sonnet  # Usa anthropic/claude-sonnet-4-6
claude @glm5.1   # Usa zai/glm-5.1
claude @opus     # Usa anthropic/claude-opus-4-6
```

**Definir novos aliases:** Seção `agents.defaults.models`:
```json
{
  "provider/model-id": {
    "alias": "meu-alias",
    "params": {
      "thinking": "adaptive"  // off | on | adaptive
    }
  }
}
```

### Comandos Úteis

```bash
# Verificar LiteLLM
curl -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  http://localhost:4000/models | jq '.data[].id'

# Ver config OpenClaw atual
cat ~/.openclaw/openclaw.json | jq '.agents'

# Backup antes de alterar
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak.$(date +%Y%m%d-%H%M%S)

# Usar script de visualização
openclaw-status           # Markdown no terminal
openclaw-status html      # HTML no browser
```
```

## Output Format

Generate clean, copy-paste friendly Markdown output with:
- Tables for quick scanning
- Code blocks for file paths
- Clear section headers
- Emoji indicators for visual scanning
- Copy-paste ready JSON/YAML examples

## Error Handling

### Missing Configuration Files

If `~/.openclaw/openclaw.json` is missing:
```
⚠️ Configuração OpenClaw não encontrada
Verifique se OpenClaw está instalado: ls -la ~/.openclaw/
```

### Invalid JSON

If the configuration file contains invalid JSON:
```
⚠️ Erro ao parsear ~/.openclaw/openclaw.json
Execute: jq . ~/.openclaw/openclaw.json
```

### LiteLLM Unreachable

If LiteLLM proxy is not responding:
```
⚠️ LiteLLM proxy não responde em localhost:4000
Verifique: systemctl --user status litellm
```

## Best Practices

When modifying OpenClaw configurations, follow these best practices:

### Backup Strategy

Always create backups before modifying configuration files:

```bash
# Create timestamped backup
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak.$(date +%Y%m%d-%H%M%S)

# Verify backup was created
ls -la ~/.openclaw/openclaw.json.bak.*
```

### Testing Changes

After making modifications, validate before applying system-wide:

```bash
# Validate JSON syntax
jq . ~/.openclaw/openclaw.json > /dev/null && echo "✅ JSON válido"

# Test specific agent configuration
openclaw validate --agent <agent-id>

# Check LiteLLM connectivity
curl -s http://localhost:4000/health | jq -r '.status'
```

### Fallback Chain Design

Design fallback chains thoughtfully:
- First fallback should be same provider, different model
- Second fallback should be different provider
- Include at least one fast model for responsiveness
- Include at least one capable model for complex tasks

Example fallback design:
```json
{
  "fallbacks": [
    "litellm/glm-5-turbo",
    "zai/glm-5.1",
    "litellm/glm-4.5-air"
  ]
}
```

## Common Scenarios

### Scenario 1: Switching Primary Model

When the primary model is underperforming or unavailable, quickly switch to an alternative:

1. Backup current config
2. Edit `~/.openclaw/openclaw.json`
3. Modify `agents.defaults.model.primary`
4. Save and restart OpenClaw if necessary
5. Test with a simple query

### Scenario 2: Adding New Model to LiteLLM

When integrating a new provider or model:

1. Obtain API credentials and endpoint
2. Add to `~/.config/litellm/config.yaml`
3. Restart LiteLLM proxy
4. Test via curl: `curl http://localhost:4000/models`
5. Add to OpenClaw provider configuration
6. Reference in agent configs

### Scenario 3: Debugging Model Issues

When models fail or behave unexpectedly:

1. Check LiteLLM health: `curl http://localhost:4000/health`
2. Verify API keys are set: `echo $ANTHROPIC_API_KEY`
3. Check model name matches exactly in config
4. Review LiteLLM logs: `journalctl --user -u litellm`
5. Test direct API call to provider
6. Compare with working model configuration

## References

- OpenClaw Documentation: Internal knowledge base
- LiteLLM Configuration: https://docs.litellm.ai/
- Anthropic API: https://docs.anthropic.com/
- Z.AI API: Internal provider documentation
