#!/usr/bin/env bash
#
# tailscale-info.sh — prints exactly what URL to open on your phone to reach the
# Claude Bridge over your private Tailscale network, and sanity-checks the setup.
#
# Prereq: install Tailscale on this Mac AND your phone, log both into the SAME
# account (see DEPLOY.md "Tailscale" section). Then run this.

set -uo pipefail

echo "=== Tailscale ==="
if ! command -v tailscale >/dev/null 2>&1; then
  echo "  tailscale NOT installed. Install: brew install tailscale (or the app),"
  echo "  then run: sudo tailscale up"
  exit 1
fi

TS_IP="$(tailscale ip -4 2>/dev/null | head -1)"
# MagicDNS name from the JSON status; tolerate absence without parsing JSON in python.
TS_NAME="$(tailscale status --json 2>/dev/null | grep -o '"DNSName":"[^"]*"' | head -1 | sed 's/"DNSName":"//; s/"//; s/\.$//')"

if [ -z "$TS_IP" ]; then
  echo "  Tailscale installed but this Mac has no tailnet IP yet."
  echo "  Run: sudo tailscale up   then approve in the browser."
  exit 1
fi
echo "  this Mac tailnet IP : $TS_IP"
[ -n "$TS_NAME" ] && echo "  this Mac MagicDNS   : $TS_NAME"

echo
echo "=== services on this Mac ==="
if lsof -nP -iTCP:5001 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "  frontend (:5001)    : listening"
else
  echo "  frontend (:5001)    : NOT listening -- start it (pm2 start ecosystem.config.js)"
fi
if lsof -nP -iTCP:50001 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "  backend  (:50001)   : listening"
else
  echo "  backend  (:50001)   : NOT listening -- start it (pm2 start ecosystem.config.js)"
fi

echo
echo "=== bridge auth ==="
AUTH="$(curl -s http://localhost:50001/claude-bridge/auth/check 2>/dev/null)"
case "$AUTH" in
  *'"auth_required": true'*|*'"auth_required":true'*)
    echo "  token required (good -- CLAUDE_BRIDGE_TOKEN is set)" ;;
  *)
    echo "  WARNING: token NOT required -- anyone on your tailnet can use the bridge."
    echo "  Set CLAUDE_BRIDGE_TOKEN (see DEPLOY.md) before relying on this." ;;
esac

echo
echo "============================================================"
echo " On your phone (logged into the SAME Tailscale account),"
echo " open in the browser:"
echo
echo "     http://$TS_IP:5001/claude-bridge"
[ -n "$TS_NAME" ] && echo "     or  http://$TS_NAME:5001/claude-bridge"
echo
echo " Enter your CLAUDE_BRIDGE_TOKEN when prompted."
echo "============================================================"
