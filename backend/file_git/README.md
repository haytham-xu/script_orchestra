# File-Git

Git-style local ↔ cloud backup tool with optional AES-256-GCM encryption.

- Each repo is independently managed; mode (`ORIGINAL` or `ENCRYPTED`) is set at creation and cannot be changed.
- Encrypted repos: filenames and directory structure are obfuscated on the cloud side (hmac16 per-segment encoding).
- Small incremental changes: fully automatic `push`/`pull` via API. Large batches: manual upload/download path bypasses API rate limits.
- Resumable sync, structured operation logs, soft-delete to trash.

---

## Setup

### 1. Python 3.11+

**macOS** (pyenv recommended):
```bash
brew install pyenv
pyenv install 3.13.5
pyenv global 3.13.5
```

**Windows**: download the installer from https://www.python.org/downloads/ — check "Add Python to PATH".

**Linux**: `apt install python3 python3-venv` (or your distro's equivalent).

Verify: `python3 --version` should show 3.11 or above.

### 2. Node.js 20+

**macOS / Linux** (nvm recommended):
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
nvm install 22
```

**Windows**: download the LTS installer from https://nodejs.org/.

Verify: `node --version` should show v20+ or v22+.

### 3. Clone the repository

```bash
git clone <repo-url> script_orchestra
cd script_orchestra
```

### 4. Backend Python environment

```bash
cd backend
python3 -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# Windows (cmd)
venv\Scripts\activate.bat

pip install -r requirements.txt
```

Key dependencies (installed automatically): `flask`, `flask-restx`, `flask-socketio`, `cryptography`, `flask-cors`.

### 5. Frontend dependencies

```bash
cd ../script-orchestra
npm install
```

---

## Starting the servers

Two terminal windows are required.

**Terminal 1 — backend:**
```bash
cd backend
source venv/bin/activate   # Windows: venv\Scripts\Activate.ps1
python app.py
```
Ready when you see: `[App] Starting with WebSocket support on 0.0.0.0:5001`

**Terminal 2 — frontend:**
```bash
cd script-orchestra
npm run dev
```
Ready when you see: `Local: http://localhost:5173/`

Open http://localhost:5173/ in a browser. Click the **File-Git** card on the Dashboard, or navigate directly to http://localhost:5173/file-git.

---

## First-time configuration

1. Click **Add Repository**, enter an absolute local path and select a mode.
2. Click the new repo card to open the detail page.
3. In the **Config** panel, set **Remote path** and (for encrypted repos) **Password**, then click **Save Config**.

> Key derivation: `scrypt(password, salt=remote_path)`. The same password + same remote path on any machine derives the same key, so restoring on a new machine requires only the password and the remote path — no key export needed.

`repos.json` and `settings.json` are in `.gitignore` and are never committed.
