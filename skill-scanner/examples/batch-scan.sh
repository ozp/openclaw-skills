#!/bin/bash
# Example: Batch scan multiple skills with rate limiting

SKILLS=(
  "https://github.com/modelcontextprotocol/servers"
  # Add more URLs here
  # "https://github.com/owner/repo/tree/main/skills/skill-name"
)

DELAY_BETWEEN=60  # Seconds between submissions
POLL_INTERVAL=30  # Seconds between status checks

echo "╔════════════════════════════════════════════════════════╗"
echo "║ OATH SKILL SCANNER - Batch Scan                        ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "Skills to scan: ${#SKILLS[@]}"
echo "Rate limit: ${DELAY_BETWEEN}s between submissions"
echo ""

# Array to store audit IDs
declare -a AUDIT_IDS
declare -a STATUSES

# Phase 1: Submit all skills
for i in "${!SKILLS[@]}"; do
  url="${SKILLS[$i]}"
  num=$((i + 1))

  echo "[$num/${#SKILLS[@]}] Submitting: $url"

  RESPONSE=$(curl -s -X POST "https://audit-engine.oathe.ai/api/submit" \
    -H "Content-Type: application/json" \
    -d "{\"skill_url\": \"$url\"}")

  if [[ "$RESPONSE" == *"audit_id"* ]]; then
    AUDIT_ID=$(echo "$RESPONSE" | jq -r '.audit_id')
    AUDIT_IDS+=("$AUDIT_ID")
    echo "    ✅ Audit ID: $AUDIT_ID"
  else
    echo "    ❌ Failed: $RESPONSE"
    AUDIT_IDS+=("ERROR")
  fi

  # Rate limit delay (except after last)
  if [[ $i -lt $((${#SKILLS[@]} - 1)) ]]; then
    echo "    ⏳ Waiting ${DELAY_BETWEEN}s for rate limit..."
    sleep $DELAY_BETWEEN
  fi
done

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║ Phase 2: Polling Results                               ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# Phase 2: Poll for all results
ALL_COMPLETE=false
while [[ "$ALL_COMPLETE" == "false" ]]; do
  ALL_COMPLETE=true

  for i in "${!AUDIT_IDS[@]}"; do
    audit_id="${AUDIT_IDS[$i]}"

    # Skip failed submissions
    [[ "$audit_id" == "ERROR" ]] && continue

    # Check status if not already complete
    if [[ "${STATUSES[$i]}" != "complete" && "${STATUSES[$i]}" != "failed" ]]; then
      RESULT=$(curl -s "https://audit-engine.oathe.ai/api/audit/$audit_id")
      STATUS=$(echo "$RESULT" | jq -r '.status')
      STATUSES[$i]="$STATUS"

      if [[ "$STATUS" == "analyzing" || "$STATUS" == "pending" ]]; then
        ALL_COMPLETE=false
      fi
    fi
  done

  if [[ "$ALL_COMPLETE" == "false" ]]; then
    echo -n "."
    sleep $POLL_INTERVAL
  fi
done

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║ Results Summary                                        ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# Print summary
for i in "${!SKILLS[@]}"; do
  url="${SKILLS[$i]}"
  status="${STATUSES[$i]}"

  case "$status" in
    "complete") icon="✅" ;;
    "failed") icon="❌" ;;
    *) icon="⚠️ " ;;
  esac

  echo "$icon [$status] ${url:0:50}..."
done
