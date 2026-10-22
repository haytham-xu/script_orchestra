"""AES-256-GCM encryption for kubeconfig storage.

Key is loaded from backend/k8s_console/secrets.key (auto-generated on first use,
gitignored). The key never leaves the server — the DB stores only ciphertext.
Decryption is only performed server-side when injecting kubeconfig into a PTY.
"""
import base64
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_FILE = os.path.join(os.path.dirname(__file__), 'secrets.key')
_NONCE_SIZE = 12  # 96-bit GCM nonce


def _load_key() -> bytes:
    if os.path.exists(_KEY_FILE):
        raw = open(_KEY_FILE, 'rb').read().strip()
        return base64.b64decode(raw)
    key = secrets.token_bytes(32)
    with open(_KEY_FILE, 'wb') as f:
        f.write(base64.b64encode(key))
    os.chmod(_KEY_FILE, 0o600)
    return key


_KEY: bytes | None = None


def _key() -> bytes:
    global _KEY
    if _KEY is None:
        _KEY = _load_key()
    return _KEY


def encrypt(plaintext: str) -> str:
    """Return base64(nonce + ciphertext) for storage in DB."""
    nonce = secrets.token_bytes(_NONCE_SIZE)
    ct = AESGCM(_key()).encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(blob: str) -> str:
    """Decrypt a blob produced by encrypt()."""
    raw = base64.b64decode(blob)
    nonce, ct = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
    return AESGCM(_key()).decrypt(nonce, ct, None).decode()
