---
name: taskmaster-setup
description: Configure TaskMaster AI with LiteLLM proxy in any project directory. Use when setting up task management for a new project, initializing TaskMaster, or troubleshooting TaskMaster + LiteLLM integration issues.
---

# TaskMaster + LiteLLM Setup

Configure TaskMaster to use LiteLLM proxy for AI-powered task management.

## Quick Setup

```bash
# Run from any project directory
~/.wcgw/skills/taskmaster-setup/scripts/setup-taskmaster.sh .
```

## Prerequisites

- LiteLLM running on localhost:4000
- task-master-ai installed globally (`npm i -g task-master-ai`)

## What This Does

1. Creates `.taskmaster/config.json` with LiteLLM models
2. Creates `.env` with proxy credentials
3. Runs `task-master init` if needed
4. Tests connection

## Default Models

| Role | Model | Provider | Max Tokens |
|------|-------|----------|------------|
| main | glm-4.7 | Z.AI | 128000 |
| research | glm-4.7 | Z.AI | 128000 |
| fallback | qwen-235b | Cerebras | 40000 |

## Configuration

### LiteLLM Requirement

LiteLLM must use `custom_openai/` prefix for Z.AI models:

```yaml
# ~/.config/litellm/config.yaml
- model_name: glm-4.7
  litellm_params:
    model: custom_openai/glm-4.7  # NOT openai/ or hosted_vllm/
    api_base: https://api.z.ai/api/coding/paas/v4
```

This ensures proper OpenAI-compatible routing via `/chat/completions`.

### TaskMaster Provider

**CRITICAL**: Use `openai-compatible` provider, NOT `openai`:

```json
{
  "models": {
    "main": {
      "provider": "openai-compatible",
      "modelId": "glm-4.7",
      "maxTokens": 128000,
      "baseURL": "http://localhost:4000/v1"
    }
  }
}
```

The `openai` provider uses OpenAI-specific endpoints (`/responses`) that Z.AI doesn't support.

### Custom Models

Edit `.taskmaster/config.json` after setup:

```json
{
  "models": {
    "main": {
      "provider": "openai-compatible",
      "modelId": "YOUR_MODEL_ID",
      "maxTokens": 128000,
      "baseURL": "http://localhost:4000/v1"
    }
  }
}
```

See `references/models-reference.md` for available models.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| AI_TypeValidationError | Check provider is `openai-compatible`, NOT `openai` |
| 404 on Z.AI | Check LiteLLM uses `custom_openai/` prefix |
| Connection refused | Start LiteLLM: `litellm-start` |
| Model not found | Verify model name in LiteLLM config |

## Files Created

```
.taskmaster/
├── config.json    # Model configuration
└── .env           # API credentials (gitignored)
```
