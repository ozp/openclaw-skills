# Model and Provider Reference Guide

This guide provides detailed information about OpenClaw model configuration, provider setup, and advanced customization options.

## Understanding the Configuration Architecture

OpenClaw uses a layered configuration system with three main components:

1. **OpenClaw Core (`~/.openclaw/openclaw.json`)**
   - Agent definitions
   - Default model settings
   - Provider configurations
   - Alias mappings

2. **LiteLLM Proxy (`~/.config/litellm/config.yaml`)**
   - Model routing and load balancing
   - Rate limiting
   - Caching configuration
   - Provider abstraction layer

3. **Environment Configuration (`~/.zshrc` or environment)**
   - API keys
   - Endpoint URLs
   - Authentication tokens

## Provider Types

### litellm (🟦)

The standard LiteLLM provider using OpenAI-compatible API format.

**Configuration:**
```json
{
  "litellm": {
    "baseUrl": "http://localhost:4000/v1",
    "apiKey": "${LITELLM_MASTER_KEY}",
    "auth": "bearer",
    "api": "openai-completions"
  }
}
```

**Use when:** You want to route through LiteLLM with OpenAI API format.

### litellm-anthropic (🟩)

LiteLLM provider using Anthropic Messages API format.

**Configuration:**
```json
{
  "litellm-anthropic": {
    "baseUrl": "http://localhost:4000/v1",
    "apiKey": "${LITELLM_MASTER_KEY}",
    "auth": "bearer",
    "api": "anthropic-messages"
  }
}
```

**Use when:** You need Anthropic API format through LiteLLM proxy.

### zai (🟨)

Direct connection to Z.AI API without LiteLLM routing.

**Configuration:**
```json
{
  "zai": {
    "baseUrl": "https://api.z.ai/api/coding/paas/v4",
    "apiKey": "${ZAI_API_KEY}",
    "auth": "api-key",
    "api": "openai-completions"
  }
}
```

**Use when:** You need direct Z.AI access or LiteLLM doesn't support a specific Z.AI feature.

### anthropic (🟥)

Direct Anthropic API connection.

**Configuration:**
```json
{
  "anthropic": {
    "baseUrl": "https://api.anthropic.com",
    "apiKey": "${ANTHROPIC_API_KEY}",
    "auth": "api-key",
    "api": "anthropic-messages"
  }
}
```

**Use when:** You want direct Anthropic access without LiteLLM routing.

### openai-codex (🟪)

OpenAI Codex API for specialized coding models.

**Configuration:**
```json
{
  "openai-codex": {
    "baseUrl": "https://api.openai.com",
    "apiKey": "${OPENAI_API_KEY}",
    "auth": "bearer",
    "api": "codex"
  }
}
```

**Use when:** Using OpenAI Codex-specific models and features.

## Model Naming Conventions

### Model ID Format

The standard format for model references is: `provider/model-id`

Examples:
- `litellm/glm-5.1`
- `zai/glm-5.1`
- `anthropic/claude-sonnet-4-6`
- `openai-codex/gpt-5.4`

### Model Resolution Process

When an agent references a model, OpenClaw resolves it through these steps:

1. Check if it's an alias (`@alias` → resolve to `provider/model`)
2. Parse provider prefix from `provider/model` string
3. Look up provider in `models.providers`
4. Route request to provider's `baseUrl`
5. Include authentication as specified in `auth` field

## Advanced Configuration

### Custom Model Parameters

You can specify additional parameters for models:

```json
{
  "agents": {
    "defaults": {
      "models": {
        "litellm/glm-5.1": {
          "alias": "glm5",
          "params": {
            "thinking": "adaptive",
            "temperature": 0.7,
            "max_tokens": 4096
          }
        }
      }
    }
  }
}
```

### Environment Variable Substitution

Configuration supports environment variable substitution:

```json
{
  "apiKey": "${ANTHROPIC_API_KEY}"
}
```

Variables are resolved at runtime from:
- Shell environment
- `~/.zshrc` exports
- `.env` files in working directory

### Thinking Modes

Three thinking modes are available:

| Mode | Description | Use Case |
|------|-------------|----------|
| `off` | No explicit thinking | Fast responses, simple tasks |
| `on` | Always show thinking | Debugging, educational purposes |
| `adaptive` | Context-aware thinking | Balanced default behavior |

## Troubleshooting

### LiteLLM Connection Issues

**Symptom:** `Connection refused` to localhost:4000

**Resolution:**
```bash
# Check if LiteLLM is running
systemctl --user status litellm

# Start if not running
systemctl --user start litellm

# Check logs
journalctl --user -u litellm -n 50
```

### Model Not Found Errors

**Symptom:** `Model 'xxx' not found`

**Resolution:**
1. Verify model is in LiteLLM config: `curl http://localhost:4000/models`
2. Check model name spelling matches exactly
3. Verify provider configuration

### Authentication Failures

**Symptom:** `401 Unauthorized` or `Invalid API key`

**Resolution:**
1. Check environment variable is set: `echo $ANTHROPIC_API_KEY`
2. Verify key is valid by testing direct API call
3. Check LiteLLM master key if using proxy

## Migration Guide

### Migrating from Direct Provider to LiteLLM

1. Add model to `~/.config/litellm/config.yaml`
2. Change agent model from `anthropic/claude-sonnet-4-6` to `litellm-anthropic/glm-5.1`
3. Test configuration
4. Remove direct provider if no longer needed

### Adding Multiple Providers for Redundancy

Configure multiple providers in fallbacks:

```json
{
  "model": {
    "primary": "litellm/glm-5.1",
    "fallbacks": [
      "zai/glm-5.1",
      "anthropic/claude-sonnet-4-6"
    ]
  }
}
```

## Performance Optimization

### Caching Strategy

LiteLLM supports response caching:

```yaml
cache:
  type: redis
  host: localhost
  port: 6379
  ttl: 3600
```

### Load Balancing

For high-throughput scenarios, configure multiple LiteLLM instances:

```yaml
router:
  strategy: simple-shuffle
  models:
    - litellm/glm-5.1
    - litellm/glm-5.1-02
```

## Security Considerations

### API Key Management

- Never commit API keys to version control
- Use environment variables or secret management systems
- Rotate keys regularly
- Use separate keys for different environments

### Network Security

- LiteLLM should bind to localhost only in single-user setups
- Use TLS for production deployments
- Consider VPN or private networks for distributed setups

## Reference Implementations

### Minimal Agent Configuration

```json
{
  "id": "minimal-agent",
  "model": "litellm/glm-5.1",
  "workspace": "~/workspace",
  "subagents": []
}
```

### Full Agent Configuration

```json
{
  "id": "full-agent",
  "model": "litellm/glm-5.1",
  "workspace": "~/workspace",
  "subagents": ["helper-1", "helper-2"],
  "params": {
    "thinking": "adaptive",
    "temperature": 0.5
  },
  "tools": ["file-read", "bash"],
  "permissions": ["read", "write"]
}
```
