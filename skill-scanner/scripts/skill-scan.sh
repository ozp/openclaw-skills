#!/bin/bash
# skill-scan: CLI wrapper for Oath Audit Engine API
# Usage: skill-scan submit <url> | skill-scan status <audit_id> | skill-scan badge <url>

set -e

API_BASE="https://audit-engine.oathe.ai"
BADGE_BASE="https://oathe.ai/api/badge"
DELAY_BETWEEN=60
POLL_INTERVAL=30

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

show_help() {
  cat << EOF
Usage: skill-scan <command> [args]

Commands:
  submit <url>        Submit skill for audit and poll for result
  status <audit_id>   Check audit status
  badge <url>         Get badge URL for skill
  batch <urls...>     Scan multiple skills with rate limiting

Examples:
  skill-scan submit https://github.com/owner/skill-repo
  skill-scan status 95ee25db-3910-4b80-8327-6a8fe377d8df
  skill-scan badge https://github.com/owner/skill-repo
  skill-scan batch url1 url2 url3

Rate limits: 60s between submissions (Cloudflare protection)
EOF
}

submit_skill() {
  local url=$1
  local retry_count=${2:-0}
  local max_retries=3

  echo "Submitting: $url"

  RESPONSE=$(curl -s -X POST "$API_BASE/api/submit" \
    -H "Content-Type: application/json" \
    -d "{\"skill_url\": \"$url\"}" 2>&1)

  # Check for rate limit
  if [[ "$RESPONSE" == *"429"* ]] && [[ $retry_count -lt $max_retries ]]; then
    echo -e "${YELLOW}⚠️ Rate limited. Waiting ${DELAY_BETWEEN}s before retry...${NC}"
    sleep $DELAY_BETWEEN
    submit_skill "$url" $((retry_count + 1))
    return
  fi

  # Check for success
  if [[ "$RESPONSE" != *"audit_id"* ]]; then
    echo -e "${RED}❌ Submission failed:${NC}"
    echo "$RESPONSE"
    exit 1
  fi

  echo -e "${GREEN}✅ Submitted successfully${NC}"
  echo "$RESPONSE" | jq -r '.audit_id'
}

check_status() {
  local audit_id=$1

  curl -s "$API_BASE/api/audit/$audit_id" | jq .
}

poll_until_complete() {
  local audit_id=$1

  echo "⏳ Polling for results..."
  echo "   (Ctrl+C to cancel - audit will continue server-side)"
  echo ""

  # Initial delay
  sleep 10

  local dots=0
  while true; do
    RESULT=$(curl -s "$API_BASE/api/audit/$audit_id")
    STATUS=$(echo "$RESULT" | jq -r '.status // "unknown"')

    case "$STATUS" in
      "complete")
        echo ""
        echo -e "${GREEN}✅ Audit complete!${NC}"
        echo "$RESULT" | jq .
        return 0
        ;;
      "failed")
        echo ""
        echo -e "${RED}❌ Audit failed${NC}"
        echo "$RESULT" | jq .
        ERROR=$(echo "$RESULT" | jq -r '.error_message // ""')
        if [[ "$ERROR" == *"lot of requests"* ]]; then
          echo ""
          echo -e "${YELLOW}💡 Server overloaded. Retry later with:${NC}"
          echo "   skill-scan status $audit_id"
        fi
        return 1
        ;;
      "analyzing"|"pending"|"unknown")
        dots=$((dots + 1))
        if [[ $dots -gt 60 ]]; then
          dots=0
          echo ""
        fi
        echo -n "."
        sleep $POLL_INTERVAL
        ;;
      *)
        echo ""
        echo -e "${YELLOW}⚠️ Unexpected status: $STATUS${NC}"
        echo "$RESULT" | jq .
        return 1
        ;;
    esac
  done
}

get_badge() {
  local url=$1
  echo "Badge URL:"
  echo "  ${BADGE_BASE}?skill_url=${url}"
  echo ""
  echo "Markdown:"
  echo "  [![Oath Security](${BADGE_BASE}?skill_url=${url})](${url})"
}

submit_and_poll() {
  local url=$1
  local audit_id

  audit_id=$(submit_skill "$url")

  if [[ -n "$audit_id" ]]; then
    echo "   Audit ID: $audit_id"
    echo ""
    poll_until_complete "$audit_id"
  fi
}

batch_scan() {
  local urls=("$@")
  local audit_ids=()

  echo "╔════════════════════════════════════════════════════════╗"
  echo "║ SKILL SCANNER - Batch Mode                             ║"
  echo "╚════════════════════════════════════════════════════════╝"
  echo ""
  echo "Skills to scan: ${#urls[@]}"
  echo ""

  # Submit all
  for i in "${!urls[@]}"; do
    local url="${urls[$i]}"
    local num=$((i + 1))

    echo "[$num/${#urls[@]}] $url"
    local audit_id=$(submit_skill "$url" 2>/dev/null)

    if [[ -n "$audit_id" ]]; then
      audit_ids+=("$audit_id")
    else
      audit_ids+=("ERROR")
    fi

    # Rate limit delay (except after last)
    if [[ $i -lt $((${#urls[@]} - 1)) ]]; then
      echo "   Waiting ${DELAY_BETWEEN}s for rate limit..."
      sleep $DELAY_BETWEEN
    fi
    echo ""
  done

  # Poll for results
  echo ""
  echo "╔════════════════════════════════════════════════════════╗"
  echo "║ Polling Results                                        ║"
  echo "╚════════════════════════════════════════════════════════╝"
  echo ""

  local all_complete=false
  while [[ "$all_complete" == "false" ]]; do
    all_complete=true

    for i in "${!audit_ids[@]}"; do
      local id="${audit_ids[$i]}"
      [[ "$id" == "ERROR" ]] && continue

      local result=$(curl -s "$API_BASE/api/audit/$id")
      local status=$(echo "$result" | jq -r '.status // "unknown"')

      if [[ "$status" == "analyzing" || "$status" == "pending" ]]; then
        all_complete=false
      fi
    done

    if [[ "$all_complete" == "false" ]]; then
      echo -n "."
      sleep $POLL_INTERVAL
    fi
  done

  echo ""
  echo ""
  echo "╔════════════════════════════════════════════════════════╗"
  echo "║ Summary                                                ║"
  echo "╚════════════════════════════════════════════════════════╝"

  for i in "${!urls[@]}"; do
    local url="${urls[$i]}"
    local id="${audit_ids[$i]}"
    local status="ERROR"

    if [[ "$id" != "ERROR" ]]; then
      local result=$(curl -s "$API_BASE/api/audit/$id")
      status=$(echo "$result" | jq -r '.status // "unknown"')
    fi

    case "$status" in
      "complete") icon="✅" ;;
      "failed") icon="❌" ;;
      *) icon="⚠️ " ;;
    esac

    printf "  %s [%s] %s\n" "$icon" "$status" "${url:0:50}"
    if [[ ${#url} -gt 50 ]]; then
      echo "     ${url:50}"
    fi
  done
}

# Main
case "${1:-}" in
  "submit")
    if [[ -z "${2:-}" ]]; then
      echo "Error: URL required"
      show_help
      exit 1
    fi
    submit_and_poll "$2"
    ;;
  "status")
    if [[ -z "${2:-}" ]]; then
      echo "Error: Audit ID required"
      show_help
      exit 1
    fi
    check_status "$2"
    ;;
  "badge")
    if [[ -z "${2:-}" ]]; then
      echo "Error: URL required"
      show_help
      exit 1
    fi
    get_badge "$2"
    ;;
  "batch")
    if [[ $# -lt 2 ]]; then
      echo "Error: At least one URL required"
      show_help
      exit 1
    fi
    shift
    batch_scan "$@"
    ;;
  "help"|"-h"|"--help")
    show_help
    ;;
  *)
    echo "Error: Unknown command: ${1:-}"
    show_help
    exit 1
    ;;
esac
