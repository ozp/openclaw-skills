#!/bin/bash
# TaskMaster + LiteLLM Setup Script
# Usage: setup-taskmaster.sh [project_dir] [--main MODEL] [--fallback MODEL]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Defaults
LITELLM_URL="http://localhost:4000"
LITELLM_KEY="sk-litellm-d6ae557b17f81c19a6609fb68d4cf1c7"
MAIN_MODEL="glm-4.7"
MAIN_MAX_TOKENS=128000
FALLBACK_MODEL="qwen-235b"
FALLBACK_MAX_TOKENS=40000
PROJECT_DIR="${1:-.}"

# Parse arguments
shift 2>/dev/null || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --main) MAIN_MODEL="$2"; shift 2 ;;
        --fallback) FALLBACK_MODEL="$2"; shift 2 ;;
        --litellm-url) LITELLM_URL="$2"; shift 2 ;;
        --litellm-key) LITELLM_KEY="$2"; shift 2 ;;
        *) shift ;;
    esac
done

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  TaskMaster + LiteLLM Setup${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Resolve project dir
PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd)
echo -e "\n${YELLOW}📁 Project:${NC} $PROJECT_DIR"

# Check prerequisites
echo -e "\n${YELLOW}🔍 Checking prerequisites...${NC}"

# Check task-master
if ! command -v task-master &> /dev/null; then
    echo -e "${RED}✗ task-master not found${NC}"
    echo "  Install: npm i -g task-master-ai"
    exit 1
fi
TM_VERSION=$(task-master --version 2>/dev/null || echo "unknown")
echo -e "${GREEN}✓${NC} task-master $TM_VERSION"

# Check LiteLLM
if curl -s --connect-timeout 2 "$LITELLM_URL/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} LiteLLM running at $LITELLM_URL"
else
    echo -e "${RED}✗ LiteLLM not responding at $LITELLM_URL${NC}"
    echo "  Start with: litellm-start"
    exit 1
fi

# Create .taskmaster directory
echo -e "\n${YELLOW}📝 Creating configuration...${NC}"
mkdir -p "$PROJECT_DIR/.taskmaster"

# Create config.json
cat > "$PROJECT_DIR/.taskmaster/config.json" << EOF
{
  "models": {
    "main": {
      "provider": "openai-compatible",
      "modelId": "$MAIN_MODEL",
      "maxTokens": $MAIN_MAX_TOKENS,
      "temperature": 0.2,
      "baseURL": "$LITELLM_URL/v1"
    },
    "research": {
      "provider": "openai-compatible",
      "modelId": "$MAIN_MODEL",
      "maxTokens": $MAIN_MAX_TOKENS,
      "temperature": 0.1,
      "baseURL": "$LITELLM_URL/v1"
    },
    "fallback": {
      "provider": "openai-compatible",
      "modelId": "$FALLBACK_MODEL",
      "maxTokens": $FALLBACK_MAX_TOKENS,
      "temperature": 0.2,
      "baseURL": "$LITELLM_URL/v1"
    }
  },
  "global": {
    "logLevel": "info",
    "debug": false,
    "defaultNumTasks": 10,
    "defaultSubtasks": 5,
    "defaultPriority": "medium",
    "projectName": "$(basename "$PROJECT_DIR")",
    "responseLanguage": "Portuguese",
    "enableCodebaseAnalysis": true,
    "anonymousTelemetry": false
  }
}
EOF
echo -e "${GREEN}✓${NC} Created .taskmaster/config.json"

# Create .env
cat > "$PROJECT_DIR/.env" << EOF
# TaskMaster + LiteLLM Configuration
# Provider openai-compatible requires OPENAI_COMPATIBLE_API_KEY
OPENAI_COMPATIBLE_API_KEY=$LITELLM_KEY
EOF
echo -e "${GREEN}✓${NC} Created .env"

# Add .env to .gitignore if exists
if [ -f "$PROJECT_DIR/.gitignore" ]; then
    if ! grep -q "^\.env$" "$PROJECT_DIR/.gitignore"; then
        echo ".env" >> "$PROJECT_DIR/.gitignore"
        echo -e "${GREEN}✓${NC} Added .env to .gitignore"
    fi
fi

# Create initial tasks.json if needed
cd "$PROJECT_DIR"
mkdir -p ".taskmaster/tasks"
if [ ! -f ".taskmaster/tasks/tasks.json" ]; then
    cat > ".taskmaster/tasks/tasks.json" << EOFTASKS
{
  "tasks": [],
  "metadata": {
    "projectName": "$(basename "$PROJECT_DIR")",
    "version": "1.0.0",
    "createdAt": "$(date -Iseconds)"
  }
}
EOFTASKS
    echo -e "${GREEN}✓${NC} Created .taskmaster/tasks/tasks.json"
fi

# Create state.json if needed
if [ ! -f ".taskmaster/state.json" ]; then
    cat > ".taskmaster/state.json" << EOFSTATE
{
  "currentTag": "master",
  "lastSwitched": "$(date -Iseconds)",
  "branchTagMapping": {},
  "migrationNoticeShown": true
}
EOFSTATE
    echo -e "${GREEN}✓${NC} Created .taskmaster/state.json"
fi

# Test connection
echo -e "\n${YELLOW}🧪 Testing connection...${NC}"
if task-master models 2>/dev/null | head -5; then
    echo -e "${GREEN}✓${NC} Connection successful"
else
    echo -e "${YELLOW}⚠${NC} Could not verify models (may still work)"
fi

# Summary
echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✓ Setup Complete${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "\n${BLUE}Models configured:${NC}"
echo -e "  main:     $MAIN_MODEL (max $MAIN_MAX_TOKENS tokens)"
echo -e "  fallback: $FALLBACK_MODEL (max $FALLBACK_MAX_TOKENS tokens)"
echo -e "\n${BLUE}Next steps:${NC}"
echo -e "  cd $PROJECT_DIR"
echo -e "  task-master list"
echo -e "  task-master add-task --prompt \"Your task description\""
