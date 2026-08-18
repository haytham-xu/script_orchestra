"""
AES-256-GCM streaming encryption / decryption (REQUIREMENTS §3.3).

Wire format (per chunk):
    [4B big-endian body_len][12B nonce][ciphertext ‖ 16B GCM tag]

``body_len`` is ``len(ciphertext) + 16`` (tag included), so the
decrypter knows exactly how much to read even when the tail chunk is
shorter than ``CHUNK_SIZE``.

Key derivation uses ``scrypt(password, salt=repo_id.encode())`` so the
same password produces distinct keys across repos.
"""
from __future__ import annotations

import io
import os
import struct
from typing import BinaryIO, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


NONCE_SIZE = 12
TAG_SIZE = 16
LEN_SIZE = 4              # big-endian uint32 body length prefix
CHUNK_SIZE = 1 << 20      # 1 MiB plaintext per chunk

# scrypt parameters — REQUIREMENTS §3.3
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LEN = 32


def derive_key(password: str, repo_id: str) -> bytes:
    if not password:
        raise ValueError("password must be non-empty for ENCRYPTED repos")
    kdf = Scrypt(
        salt=repo_id.encode('utf-8'),
        length=_KEY_LEN,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
    )
    return kdf.derive(password.encode('utf-8'))


class AesGcmEncryptStream(io.RawIOBase):
    """Reads plaintext, emits [len][nonce][ciphertext+tag] chunks."""

    def __init__(self, source: BinaryIO, key: bytes, chunk_size: int = CHUNK_SIZE):
        if len(key) != _KEY_LEN:
            raise ValueError(f"key must be {_KEY_LEN} bytes")
        self._source = source
        self._aes = AESGCM(key)
        self._chunk_size = chunk_size
        self._pending = b""
        self._eof = False

    def readable(self) -> bool:
        return True

    def _emit_next_chunk(self) -> bytes:
        plaintext = self._source.read(self._chunk_size)
        if not plaintext:
            self._eof = True
            return b""
        nonce = os.urandom(NONCE_SIZE)
        body = self._aes.encrypt(nonce, plaintext, associated_data=None)
        header = struct.pack(">I", len(body))
        return header + nonce + body

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            parts = [self._pending]
            self._pending = b""
            while not self._eof:
                parts.append(self._emit_next_chunk())
            return b"".join(parts)
        while len(self._pending) < n and not self._eof:
            self._pending += self._emit_next_chunk()
        out, self._pending = self._pending[:n], self._pending[n:]
        return out


class AesGcmDecryptStream(io.RawIOBase):
    """Reads [len][nonce][ciphertext+tag] chunks, emits plaintext."""

    def __init__(self, source: BinaryIO, key: bytes):
        if len(key) != _KEY_LEN:
            raise ValueError(f"key must be {_KEY_LEN} bytes")
        self._source = source
        self._aes = AESGCM(key)
        self._pending = b""
        self._eof = False

    def readable(self) -> bool:
        return True

    def _read_exact(self, n: int) -> Optional[bytes]:
        buf = bytearray()
        while len(buf) < n:
            piece = self._source.read(n - len(buf))
            if not piece:
                return None
            buf.extend(piece)
        return bytes(buf)

    def _decrypt_next_chunk(self) -> bytes:
        header = self._read_exact(LEN_SIZE)
        if header is None:
            self._eof = True
            return b""
        body_len = struct.unpack(">I", header)[0]
        nonce = self._read_exact(NONCE_SIZE)
        body = self._read_exact(body_len)
        if nonce is None or body is None:
            raise ValueError("truncated ciphertext")
        return self._aes.decrypt(nonce, body, associated_data=None)

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            parts = [self._pending]
            self._pending = b""
            while not self._eof:
                parts.append(self._decrypt_next_chunk())
            return b"".join(parts)
        while len(self._pending) < n and not self._eof:
            self._pending += self._decrypt_next_chunk()
        out, self._pending = self._pending[:n], self._pending[n:]
        return out
