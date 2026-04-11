# LiteLLM Models Reference

Models available via LiteLLM proxy (localhost:4000) for TaskMaster.

## Z.AI (Subscription)

| Model ID | Context | Max Output | Best For |
|----------|---------|------------|----------|
| `glm-4.7` | 200k | 128k | General, coding - **DEFAULT** |
| `glm-4.6v` | 200k | 128k | Vision (images) |

## Free - Fast

| Model ID | Provider | Context | Max Output | Best For |
|----------|----------|---------|------------|----------|
| `qwen-235b` | Cerebras | 131k | 40k | Ultra fast (~1400 TPS) |
| `llama-3.3-70b` | Groq | 128k | 32k | General fast |
| `kimi-k2` | Groq | 256k | 32k | Long context |

## Free - Coding

| Model ID | Provider | Context | Best For |
|----------|----------|---------|----------|
| `qwen3-coder` | OpenRouter | 262k | Heavy coding, refactoring |
| `devstral` | OpenRouter | 262k | Bugs, patches, PRs |
| `kat-coder` | OpenRouter | 256k | SWE-bench, automation |

## Free - Reasoning

| Model ID | Provider | Context | Best For |
|----------|----------|---------|----------|
| `deepseek-r1` | OpenRouter | 163k | Logic, math |
| `deepresearch` | OpenRouter | 131k | Research, synthesis |
| `olmo-think` | OpenRouter | 65k | Analytical reasoning |

## Free - Efficient

| Model ID | Provider | Context | Best For |
|----------|----------|---------|----------|
| `mimo-flash` | OpenRouter | 262k | Speed, long prompts |
| `r1t-chimera` | OpenRouter | 163k | Good cost-benefit |

## Recommended Configurations

**IMPORTANT**: Always use `"provider": "openai-compatible"` for LiteLLM proxy.

### Default (Z.AI subscription)
```json
"main": { "provider": "openai-compatible", "modelId": "glm-4.7", "maxTokens": 128000 },
"research": { "provider": "openai-compatible", "modelId": "glm-4.7", "maxTokens": 128000 },
"fallback": { "provider": "openai-compatible", "modelId": "qwen-235b", "maxTokens": 40000 }
```

### 100% Free
```json
"main": { "provider": "openai-compatible", "modelId": "qwen-235b", "maxTokens": 40000 },
"research": { "provider": "openai-compatible", "modelId": "deepresearch", "maxTokens": 32000 },
"fallback": { "provider": "openai-compatible", "modelId": "llama-3.3-70b", "maxTokens": 32000 }
```

### Heavy Coding (Free)
```json
"main": { "provider": "openai-compatible", "modelId": "qwen3-coder", "maxTokens": 32000 },
"research": { "provider": "openai-compatible", "modelId": "deepresearch", "maxTokens": 32000 },
"fallback": { "provider": "openai-compatible", "modelId": "devstral", "maxTokens": 32000 }
```

## Usage

Change model in `.taskmaster/config.json`:

```json
{
  "models": {
    "main": {
      "provider": "openai-compatible",
      "modelId": "MODEL_ID_HERE",
      "maxTokens": MAX_TOKENS_HERE,
      "baseURL": "http://localhost:4000/v1"
    }
  }
}
```

Or use script flags:

```bash
setup-taskmaster.sh . --main qwen3-coder --fallback devstral
```
