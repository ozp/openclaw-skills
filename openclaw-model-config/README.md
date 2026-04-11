# OpenClaw Model Configuration Skill

Skill para visualização rápida e modificação de configurações de modelos/provedores no OpenClaw.

## Uso

### Via Trigger Automático

Mencione qualquer um dos triggers:
- "openclaw modelos"
- "quais modelos"
- "configuração de modelos"
- "trocar modelo"
- "openclaw-status"

### Via /skill

```
/skill openclaw-model-config
```

## O que é Gerado

A skill produz:

1. **Tabela de Defaults** - Modelo primário, fallbacks, heartbeat, subagentes
2. **Matriz de Agentes** - Cada agente com seu modelo atual, provider e workspace
3. **Aliases Disponíveis** - @alias → modelos reais
4. **Legenda de Providers** - Emoji → provider com URLs
5. **Guia de Modificação** - Como alterar cada aspecto da configuração

## Arquivos Envolvidos

| Arquivo | Propósito |
|---------|-----------|
| `~/.openclaw/openclaw.json` | Config principal de agentes e modelos |
| `~/.config/litellm/config.yaml` | LiteLLM proxy - modelos disponíveis |
| `~/.zshrc` ou env | API keys via variáveis de ambiente |

## Comandos Relacionados

```bash
# Visualização rápida (criado anteriormente)
openclaw-status           # Markdown
openclaw-status html      # Browser
openclaw-status json      # JSON

# CLI OpenClaw (se disponível)
openclaw models list
openclaw models aliases list
```

## Formatos de Modelo

```
provider/model-id

Exemplos:
- litellm/glm-5.1              # LiteLLM via OpenAI API
- litellm-anthropic/glm-5.1    # LiteLLM via Anthropic API
- zai/glm-5.1                  # Z.AI direto
- anthropic/claude-sonnet-4-6  # Anthropic direto
- openai-codex/gpt-5.4         # OpenAI Codex
```

## Modificações Comuns

### Trocar modelo de um agente
Editar `~/.openclaw/openclaw.json` → section `agents.list` → campo `model`

### Trocar defaults globais
Editar `~/.openclaw/openclaw.json` → section `agents.defaults`

### Adicionar modelo ao LiteLLM
Editar `~/.config/litellm/config.yaml` → section `model_list`

### Criar novo alias
Editar `~/.openclaw/openclaw.json` → section `agents.defaults.models`

## Providers Disponíveis

| Provider | Emoji | API Type | Base URL |
|----------|-------|----------|----------|
| litellm | 🟦 | openai-completions | http://localhost:4000/v1 |
| litellm-anthropic | 🟩 | anthropic-messages | http://localhost:4000/v1 |
| zai | 🟨 | openai-completions | https://api.z.ai/api/coding/paas/v4 |
| anthropic | 🟥 | anthropic-messages | https://api.anthropic.com |
| openai-codex | 🟪 | codex | https://api.openai.com |
