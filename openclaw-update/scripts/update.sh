#!/usr/bin/env bash
set -euo pipefail

# OpenClaw Update Script
# Standard workflow: update → doctor → restart → health

echo "🔄 OpenClaw Update"
echo "=================="
echo ""

# Step 1: Update
echo "[1/4] Running openclaw update..."
openclaw update
echo ""

# Step 2: Doctor (runs automatically with update, but verify)
echo "[2/4] Running openclaw doctor..."
openclaw doctor
echo ""

# Step 3: Restart gateway
echo "[3/4] Restarting gateway..."
openclaw gateway restart
echo ""

# Step 4: Health check
echo "[4/4] Verifying health..."
openclaw health
echo ""

echo "✅ OpenClaw update complete!"
