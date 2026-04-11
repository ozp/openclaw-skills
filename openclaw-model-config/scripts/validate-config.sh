#!/bin/bash

# Validate OpenClaw and LiteLLM configuration files
# Usage: ./validate-config.sh [path/to/openclaw.json] [path/to/litellm.yaml]

set -e

OPENCLAW_CONFIG="${1:-$HOME/.openclaw/openclaw.json}"
LITELLM_CONFIG="${2:-$HOME/.config/litellm/config.yaml}"

ERRORS=0
WARNINGS=0

echo "🔍 Validating OpenClaw Model Configuration"
echo "=========================================="
echo

# Check OpenClaw config exists
if [ ! -f "$OPENCLAW_CONFIG" ]; then
    echo "❌ ERROR: OpenClaw config not found: $OPENCLAW_CONFIG"
    ERRORS=$((ERRORS + 1))
else
    echo "✅ OpenClaw config found: $OPENCLAW_CONFIG"

    # Validate JSON syntax
    if jq . "$OPENCLAW_CONFIG" > /dev/null 2>&1; then
        echo "✅ JSON syntax valid"
    else
        echo "❌ ERROR: Invalid JSON in $OPENCLAW_CONFIG"
        ERRORS=$((ERRORS + 1))
    fi

    # Check required sections
    if jq -e '.agents' "$OPENCLAW_CONFIG" > /dev/null 2>&1; then
        echo "✅ 'agents' section present"

        # Check defaults
        if jq -e '.agents.defaults' "$OPENCLAW_CONFIG" > /dev/null 2>&1; then
            echo "✅ 'agents.defaults' present"

            # Check primary model
            if jq -e '.agents.defaults.model.primary' "$OPENCLAW_CONFIG" > /dev/null 2>&1; then
                PRIMARY=$(jq -r '.agents.defaults.model.primary' "$OPENCLAW_CONFIG")
                echo "✅ Primary model: $PRIMARY"
            else
                echo "⚠️  WARNING: No primary model set"
                WARNINGS=$((WARNINGS + 1))
            fi
        else
            echo "⚠️  WARNING: No defaults section"
            WARNINGS=$((WARNINGS + 1))
        fi

        # Check agent list
        AGENT_COUNT=$(jq '.agents.list | length' "$OPENCLAW_CONFIG" 2>/dev/null || echo "0")
        if [ "$AGENT_COUNT" -gt 0 ]; then
            echo "✅ Found $AGENT_COUNT agent(s)"
        else
            echo "⚠️  WARNING: No agents defined"
            WARNINGS=$((WARNINGS + 1))
        fi
    else
        echo "❌ ERROR: Missing 'agents' section"
        ERRORS=$((ERRORS + 1))
    fi
fi

echo

# Check LiteLLM config
if [ ! -f "$LITELLM_CONFIG" ]; then
    echo "⚠️  WARNING: LiteLLM config not found: $LITELLM_CONFIG"
    WARNINGS=$((WARNINGS + 1))
else
    echo "✅ LiteLLM config found: $LITELLM_CONFIG"

    # Basic YAML validation
    if python3 -c "import yaml; yaml.safe_load(open('$LITELLM_CONFIG'))" 2>/dev/null; then
        echo "✅ YAML syntax valid"
    else
        echo "⚠️  WARNING: YAML syntax check requires Python with PyYAML"
    fi
fi

echo

# Check LiteLLM health
echo "🔍 Checking LiteLLM proxy..."
if curl -s http://localhost:4000/health > /dev/null 2>&1; then
    echo "✅ LiteLLM proxy responding on localhost:4000"

    # Get model count
    MODEL_COUNT=$(curl -s http://localhost:4000/models 2>/dev/null | jq '.data | length' 2>/dev/null || echo "?")
    echo "📊 Available models: $MODEL_COUNT"
else
    echo "⚠️  WARNING: LiteLLM proxy not responding on localhost:4000"
    WARNINGS=$((WARNINGS + 1))
fi

echo
echo "=========================================="
echo "Validation complete:"
echo "  Errors: $ERRORS"
echo "  Warnings: $WARNINGS"

if [ $ERRORS -eq 0 ]; then
    echo "✅ Configuration is valid!"
    exit 0
else
    echo "❌ Please fix errors before continuing"
    exit 1
fi
