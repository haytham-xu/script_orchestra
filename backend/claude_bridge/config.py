"""Claude Bridge — configuration.

Env-driven, mirrors the conventions in knowledge_vault/ai_client.py and
assistant/config.py (ANTHROPIC_BASE_URL from the environment, CLI path resolution).
"""
import os
import shutil


def base_url() -> str:
    # The CLI reads ANTHROPIC_BASE_URL from the environment; provide it via the
    # process env (e.g. pm2 ecosystem config). Empty when unset — no baked-in default.
    return os.environ.get("ANTHROPIC_BASE_URL", "")


# Optional fallback auth token for the local proxy, forwarded to the SDK
# subprocess only when the backend process itself is missing ANTHROPIC_AUTH_TOKEN
# (e.g. launched by pm2 / a non-interactive shell). Leave unset when the backend
# already inherits auth from its launcher.
AUTH_TOKEN = os.environ.get("CLAUDE_BRIDGE_AUTH_TOKEN", os.environ.get("ANTHROPIC_AUTH_TOKEN", ""))


def cli_path() -> str:
    """Resolve the `claude` executable, mirroring knowledge_vault/ai_client.py."""
    return os.environ.get("CLAUDE_BRIDGE_CLI") or shutil.which("claude") or "claude"


# Model aliases exposed to the client (label -> model id). First is the default.
MODEL_ALIASES = [
    {"label": "Sonnet (default)", "id": "<model>"},
    {"label": "Opus", "id": "<model>"},
    {"label": "Haiku (fast)", "id": "<model>"},
]
DEFAULT_MODEL = os.environ.get("CLAUDE_BRIDGE_MODEL", MODEL_ALIASES[0]["id"])

# cwd root whitelist: a new session's cwd must live under one of these roots.
# Defaults to the repo root's parent (…/code/github) plus the user's home code dir.
_DEFAULT_ROOTS = [
    os.path.expanduser("~/Documents/code"),
]
CWD_ROOTS = [
    os.path.realpath(p)
    for p in (os.environ.get("CLAUDE_BRIDGE_CWD_ROOTS", "").split(os.pathsep) or [])
    if p
] or [os.path.realpath(p) for p in _DEFAULT_ROOTS]

DEFAULT_CWD = os.environ.get(
    "CLAUDE_BRIDGE_DEFAULT_CWD",
    os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..")),
)

# Approval policy (Phase 2):
#   - Tools in ALLOWED_TOOLS are auto-approved (passed to the CLI as --allowedTools,
#     so they never hit the can_use_tool callback).
#   - Any other permission-requiring tool (Write, Edit, Bash, …) fires can_use_tool
#     and prompts the phone client to Allow/Deny.
# Read-only tools are safe to auto-allow; write/exec go through approval.
DEFAULT_ALLOWED_TOOLS = ["Read", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite"]

# Tools we consider high-risk (mutating or executing). Used only to annotate the
# approval prompt shown on the phone — the SDK still routes anything not in
# ALLOWED_TOOLS through can_use_tool regardless of this list.
HIGH_RISK_TOOLS = {"Bash", "Write", "Edit", "MultiEdit", "NotebookEdit", "KillShell"}


def tool_risk(tool_name: str) -> str:
    """Classify a tool for the approval UI: 'high' (mutating/exec) or 'normal'."""
    return "high" if tool_name in HIGH_RISK_TOOLS else "normal"


# Bearer token gating HTTP + WebSocket. Empty string => auth disabled (LAN dev).
BRIDGE_TOKEN = os.environ.get("CLAUDE_BRIDGE_TOKEN", "")


def cwd_allowed(path: str) -> bool:
    """True if `path` is a real directory under one of the whitelisted roots."""
    try:
        rp = os.path.realpath(path)
    except OSError:
        return False
    if not os.path.isdir(rp):
        return False
    return any(rp == root or rp.startswith(root + os.sep) for root in CWD_ROOTS)
