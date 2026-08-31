# Claude Bridge — Deployment (remote phone access)

How to reach the `claude_bridge` tool from your phone, with the backend + Claude
running on your home Mac. Two options, most-secure first:

- **Tailscale (recommended, most secure, free)** — a private encrypted network;
  your Mac is NEVER exposed to the public internet. Only your own devices can
  reach it. See **§A** below.
- **Cloudflare Tunnel + Access** — the Mac is reachable on a public domain,
  gated by Cloudflare login + a token. Convenient but public-facing. See **§B**.

Everything runs on your Mac either way; Claude uses the Mac's logged-in CLI. The
app has a bearer-token gate (`CLAUDE_BRIDGE_TOKEN`) as an always-on second layer.

---

## §A. Tailscale (recommended)

**Why:** the bridge can read/write files and run commands on your Mac. Tailscale
puts it inside a private WireGuard-encrypted network (a "tailnet"), so it is not
reachable from the public internet at all — attackers can't even knock. Your
phone joins the same tailnet and connects to the Mac's private `100.x` address.
Free for personal use (unlimited devices, up to 6 users).

### Steps

1. **Set the bridge token** (second layer, in case a device is lost):
   ```bash
   export ANTHROPIC_AUTH_TOKEN=...  ANTHROPIC_BASE_URL=<your-anthropic-base-url>
   export CLAUDE_BRIDGE_TOKEN="$(openssl rand -hex 24)"   # save it for the phone
   pm2 delete sob sof 2>/dev/null; pm2 start ecosystem.config.js   # from repo root
   ```
2. **Install Tailscale on the Mac** and bring it up:
   ```bash
   brew install tailscale        # or the macOS app from tailscale.com/download
   sudo tailscale up             # approve in the browser (log into your account)
   ```
3. **Install Tailscale on your phone** (App Store / Play Store) and log into the
   **same account**.
4. **Find the URL to open** — run the helper:
   ```bash
   ./backend/claude_bridge/tailscale-info.sh
   ```
   It prints your Mac's tailnet IP and the exact phone URL, e.g.
   `http://100.x.y.z:5001/claude-bridge`, and checks the backend/frontend/token.
5. **On the phone**, open that URL, enter your `CLAUDE_BRIDGE_TOKEN`, and use it.
   (Add to Home Screen for an app-like PWA.)

No public DNS, no tunnel, no port-forwarding. The Vite dev server already allows
`*.ts.net` hosts (see `vite.config.ts`). Done.

---

## §B. Cloudflare Tunnel + Access (public-facing alternative)

Use this if you specifically want a public HTTPS URL instead of a private network.

Architecture: **phone → Cloudflare (Access login) → Tunnel → your Mac's backend
:50001**. The tunnel makes it reachable without a public IP or port-forwarding.

### TL;DR (scripted path)

```bash
# 1. give the backend its tokens durably (edit/export first — see step 1 below)
export ANTHROPIC_AUTH_TOKEN=...     ANTHROPIC_BASE_URL=<your-anthropic-base-url>
export CLAUDE_BRIDGE_TOKEN=$(openssl rand -hex 24)   # save it for the phone
pm2 delete sob sof 2>/dev/null; pm2 start ecosystem.config.js   # repo root

# 2. set up the tunnel (stops for browser login + Cloudflare Access)
./backend/claude_bridge/setup-tunnel.sh claude.yourdomain.com
```

The two scripts are `ecosystem.config.js` (repo root) and
`backend/claude_bridge/setup-tunnel.sh`. The sections below explain each step if
you'd rather do it by hand or need to debug.

---

## 0. Prerequisites (on the Mac)

- The `claude` CLI is installed and logged in (`claude` works in a terminal).
- The backend runs (PM2 process `sob`, `backend/app.py`, port 50001).
- A domain managed in Cloudflare (free plan is fine).

---

## 1. Give the backend its two tokens ⚠️ REQUIRED

The backend process needs **two** environment variables. Without them you'll get
`Invalid API key` (missing Claude auth) or an open bridge (missing bridge token):

| Var | Purpose |
|-----|---------|
| `ANTHROPIC_AUTH_TOKEN` (+ `ANTHROPIC_BASE_URL`) | Lets the SDK/CLI authenticate. These are what your interactive shell already has — the PM2-launched backend does NOT inherit them. |
| `CLAUDE_BRIDGE_TOKEN` | The bridge password your phone enters. Pick a long random string. Empty = **no auth** (fine on LAN, NOT for the internet). |

Because `sob` is a PM2 fork of `venv/bin/python app.py`, the durable way is the
repo-root **`ecosystem.config.js`**, which reads these vars from your environment
at start time:

```bash
# from a shell that HAS your Anthropic auth env (check: echo $ANTHROPIC_AUTH_TOKEN)
export ANTHROPIC_AUTH_TOKEN=...  ANTHROPIC_BASE_URL=<your-anthropic-base-url>
export CLAUDE_BRIDGE_TOKEN="$(openssl rand -hex 24)"   # save this; type it on the phone
echo "bridge token: $CLAUDE_BRIDGE_TOKEN"
pm2 delete sob sof 2>/dev/null
pm2 start ecosystem.config.js          # from repo root
```

(Quick one-off alternative without the ecosystem file:
`cd backend && CLAUDE_BRIDGE_TOKEN=... pm2 restart sob --update-env`.)

Verify:

```bash
curl -s localhost:50001/claude-bridge/auth/check     # => {"auth_required": true}
```

---

## 2–7. Cloudflare Tunnel — scripted

Steps 2 through 7 (install cloudflared, login, create tunnel, write config.yml,
route DNS) are automated by **`backend/claude_bridge/setup-tunnel.sh`**:

```bash
./backend/claude_bridge/setup-tunnel.sh claude.yourdomain.com
```

It stops for the browser login and prints the two remaining manual bits
(Cloudflare Access + running the tunnel as a service). The manual reference for
each step follows.

### 2. Install and log in cloudflared

```bash
brew install cloudflared
cloudflared tunnel login          # opens a browser; pick your domain/zone
```

## 3. Create the tunnel

```bash
cloudflared tunnel create claude-bridge
# prints a Tunnel UUID and writes credentials to ~/.cloudflared/<UUID>.json
```

## 4. Configure ingress

Create `~/.cloudflared/config.yml` (replace UUID and hostname):

```yaml
tunnel: <TUNNEL-UUID>
credentials-file: /Users/<you>/.cloudflared/<TUNNEL-UUID>.json

ingress:
  - hostname: claude.yourdomain.com
    service: http://localhost:50001
  - service: http_status:404
```

WebSockets need no special config — Cloudflare upgrades them automatically.

## 5. Route DNS

```bash
cloudflared tunnel route dns claude-bridge claude.yourdomain.com
```

## 6. Add Cloudflare Access (second factor — strongly recommended)

In the Cloudflare dashboard → **Zero Trust → Access → Applications → Add**:

- Type: Self-hosted
- Application domain: `claude.yourdomain.com`
- Policy: Allow → your email (One-time PIN) or Google login

Now nobody reaches the bridge without passing Cloudflare's login first; the
`CLAUDE_BRIDGE_TOKEN` is your second factor.

## 7. Run the tunnel (and auto-start it)

```bash
cloudflared tunnel run claude-bridge          # foreground test first
# then install as a login service so it survives reboots:
sudo cloudflared service install
```

---

## 8. On the phone

1. Open `https://claude.yourdomain.com` → pass Cloudflare Access login.
2. Navigate to the Claude Bridge tool → enter your `CLAUDE_BRIDGE_TOKEN`.
3. Chat, approve/deny tools, or switch to the Terminal view.

The frontend auto-detects same-origin (no `:50001` needed) when served through
the tunnel — see `src/claude_bridge/service/origin.ts`.

---

## Security notes

- This bridge can read/write files and run commands on your Mac. Treat the URL
  and token like SSH access.
- Keep Cloudflare Access ON. The app token alone is a single secret; Access adds
  a real identity check in front.
- Tool calls (Bash/Write/Edit) still require per-call approval on the phone
  (PreToolUse hook). Read-only tools auto-run. Never disable that gate for remote
  use.
