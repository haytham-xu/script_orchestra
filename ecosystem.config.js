// PM2 ecosystem for Script Orchestra.
//
// Purpose: give the backend the two env vars claude_bridge needs, durably,
// instead of relying on `pm2 restart --update-env` from a shell that happens to
// have them. See backend/claude_bridge/DEPLOY.md.
//
//   ANTHROPIC_AUTH_TOKEN / ANTHROPIC_BASE_URL — so the Claude SDK/CLI can auth
//   CLAUDE_BRIDGE_TOKEN                        — the bridge password (phone login)
//
// Secrets are NOT hardcoded here — they're read from the environment when you
// run `pm2 start ecosystem.config.js`. Provide them once, e.g.:
//
//   export ANTHROPIC_AUTH_TOKEN=...      # from your normal Claude shell
//   export ANTHROPIC_BASE_URL=<your-anthropic-base-url>
//   export CLAUDE_BRIDGE_TOKEN=$(openssl rand -hex 24)   # save it for the phone
//   pm2 start ecosystem.config.js
//
// (Or put them in a gitignored .env and `source` it before the pm2 command.)

const path = require('path')
const HOME = process.env.HOME
const ROOT = __dirname

module.exports = {
  apps: [
    {
      name: 'sob', // Script Orchestra Backend
      cwd: path.join(ROOT, 'backend'),
      script: path.join(ROOT, 'backend/venv/bin/python'),
      args: 'app.py',
      interpreter: 'none',
      exec_mode: 'fork',
      env: {
        PORT: '50001',
        ANTHROPIC_AUTH_TOKEN: process.env.ANTHROPIC_AUTH_TOKEN || '',
        ANTHROPIC_BASE_URL: process.env.ANTHROPIC_BASE_URL || '',
        // Empty => auth disabled (LAN only). Set before internet exposure.
        CLAUDE_BRIDGE_TOKEN: process.env.CLAUDE_BRIDGE_TOKEN || '',
      },
    },
    {
      name: 'sof', // Script Orchestra Frontend (Vite dev)
      cwd: path.join(ROOT, 'script-orchestra'),
      script: 'npm',
      args: 'run dev -- --strictPort',
      exec_mode: 'fork',
    },
  ],
}
