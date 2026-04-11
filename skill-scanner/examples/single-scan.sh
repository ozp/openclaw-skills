#!/bin/bash
# Example: Single skill scan with polling

SKILL_URL="${1:-https://github.com/modelcontextprotocol/servers}"

echo "╔════════════════════════════════════════════════════════╗"
echo "║ OATH SKILL SCANNER - Single Scan                       ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "Submitting: $SKILL_URL"
echo ""

# Submit
RESPONSE=$(curl -s -X POST "https://audit-engine.oathe.ai/api/submit" \
  -H "Content-Type: application/json" \
  -d "{\"skill_url\": \"$SKILL_URL\"}")

# Check if submission succeeded
if [[ "$RESPONSE" != *"audit_id"* ]]; then
  echo "❌ Submission failed:"
  echo "$RESPONSE" | jq .
  exit 1
fi

AUDIT_ID=$(echo "$RESPONSE" | jq -r '.audit_id')
QUEUE_POS=$(echo "$RESPONSE" | jq -r '.queue_position')

echo "✅ Submitted successfully"
echo "   Audit ID: $AUDIT_ID"
echo "   Queue position: $QUEUE_POS"
echo ""

# Poll for results
echo "⏳ Polling for results (Ctrl+C to cancel)..."
echo "   Waiting 60s before first check (rate limit)..."
sleep 60

while true; do
  RESULT=$(curl -s "https://audit-engine.oathe.ai/api/audit/$AUDIT_ID")
  STATUS=$(echo "$RESULT" | jq -r '.status')

  case "$STATUS" in
    "complete")
      echo ""
      echo "✅ Audit complete!"
      echo "$RESULT" | jq .
      break
      ;;
    "failed")
      echo ""
      echo "❌ Audit failed"
      ERROR=$(echo "$RESULT" | jq -r '.error_message')
      echo "   Error: $ERROR"
      if [[ "$ERROR" == *"lot of requests"* ]]; then
        echo "   💡 Server overloaded. Retry in 10-30 minutes."
      fi
      break
      ;;
    "analyzing"|"pending")
      echo -n "."
      sleep 30
      ;;
    *)
      echo ""
      echo "⚠️ Unknown status: $STATUS"
      echo "$RESULT" | jq .
      break
      ;;
  esac
done

echo ""
echo "Badge URL: https://oathe.ai/api/badge?skill_url=$SKILL_URL"
