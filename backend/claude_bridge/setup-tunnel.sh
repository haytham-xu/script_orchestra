#!/usr/bin/env bash
#
# setup-tunnel.sh — scripts the Cloudflare Tunnel setup for claude_bridge as far
# as it can be automated. Interactive/account-specific steps (browser login,
# picking your domain) stop and prompt you. See DEPLOY.md for the full picture.
#
# Usage:
#   ./setup-tunnel.sh claude.yourdomain.com
#
# What it does:
#   1. installs cloudflared (brew) if missing
#   2. cloudflared tunnel login            (opens browser — you authorize a zone)
#   3. creates a tunnel named "claude-bridge" (idempotent)
#   4. writes ~/.cloudflared/config.yml routing your hostname -> localhost:50001
#   5. routes DNS for the hostname
#   6. prints the next manual steps (Cloudflare Access + run/install service)
#
# It does NOT touch tokens or PM2 — do that via ecosystem.config.js (see DEPLOY.md).

set -euo pipefail

HOSTNAME="${1:-}"
TUNNEL_NAME="claude-bridge"
BACKEND="http://localhost:50001"
CF_DIR="$HOME/.cloudflared"

if [[ -z "$HOSTNAME" ]]; then
  echo "usage: $0 <hostname>   e.g. $0 claude.yourdomain.com" >&2
  exit 1
fi

# 1. install cloudflared -----------------------------------------------------
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "==> installing cloudflared via brew"
  brew install cloudflared
else
  echo "==> cloudflared already installed ($(cloudflared --version 2>&1 | head -1))"
fi

# 2. login (interactive) -----------------------------------------------------
if [[ ! -f "$CF_DIR/cert.pem" ]]; then
  echo "==> cloudflared tunnel login  (a browser will open — authorize your domain)"
  cloudflared tunnel login
else
  echo "==> already logged in (found $CF_DIR/cert.pem)"
fi

# 3. create tunnel (idempotent) ---------------------------------------------
if cloudflared tunnel list 2>/dev/null | awk '{print $2}' | grep -qx "$TUNNEL_NAME"; then
  echo "==> tunnel '$TUNNEL_NAME' already exists"
else
  echo "==> creating tunnel '$TUNNEL_NAME'"
  cloudflared tunnel create "$TUNNEL_NAME"
fi

TUNNEL_UUID="$(cloudflared tunnel list 2>/dev/null | awk -v n="$TUNNEL_NAME" '$2==n {print $1}')"
if [[ -z "$TUNNEL_UUID" ]]; then
  echo "!! could not determine tunnel UUID — check 'cloudflared tunnel list'" >&2
  exit 1
fi
CRED_FILE="$CF_DIR/$TUNNEL_UUID.json"
echo "==> tunnel UUID: $TUNNEL_UUID"

# 4. write config.yml --------------------------------------------------------
CONFIG="$CF_DIR/config.yml"
if [[ -f "$CONFIG" ]]; then
  echo "==> $CONFIG exists — backing up to $CONFIG.bak"
  cp "$CONFIG" "$CONFIG.bak"
fi
cat > "$CONFIG" <<YAML
tunnel: $TUNNEL_UUID
credentials-file: $CRED_FILE

ingress:
  - hostname: $HOSTNAME
    service: $BACKEND
  - service: http_status:404
YAML
echo "==> wrote $CONFIG"

# 5. route DNS ---------------------------------------------------------------
echo "==> routing DNS: $HOSTNAME -> $TUNNEL_NAME"
cloudflared tunnel route dns "$TUNNEL_NAME" "$HOSTNAME" || \
  echo "   (route may already exist — that's fine)"

# 6. next steps --------------------------------------------------------------
cat <<NEXT

============================================================
 Tunnel configured. Two things left (manual):

 1) Cloudflare Access (login gate) — in the Cloudflare dashboard:
      Zero Trust -> Access -> Applications -> Add
      Self-hosted app, domain: $HOSTNAME
      Policy: Allow -> your email (One-time PIN) or Google

 2) Run the tunnel, then install it as a service:
      cloudflared tunnel run $TUNNEL_NAME        # test in foreground
      sudo cloudflared service install           # auto-start on boot

 Also make sure the backend has its tokens (see DEPLOY.md / ecosystem.config.js):
   CLAUDE_BRIDGE_TOKEN  and  ANTHROPIC_AUTH_TOKEN

 Then open https://$HOSTNAME on your phone.
============================================================
NEXT
