"""
hmac16 path codec (REQUIREMENTS §3.3).

Each middle_path segment is independently transformed via
``hmac_sha256(key, segment)`` → base64url → first 16 chars.

* Same segment → same output (deterministic; the cloud_index maps back)
* Different segments → practically no collision at 62^16 ≈ 4.7·10^28
* Fixed 16-char length regardless of input (Chinese-safe)
* URL/filesystem-safe alphabet (letters, digits, ``-``, ``_``)
"""
from __future__ import annotations

import base64
import hmac
import hashlib

SEGMENT_LEN = 16


def hmac16_segment(key: bytes, segment: str) -> str:
    """Encode one path segment. ``segment`` MUST NOT contain a path separator."""
    if '/' in segment or '\\' in segment:
        raise ValueError("segment must not contain path separators")
    digest = hmac.new(key, segment.encode('utf-8'), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode('ascii')[:SEGMENT_LEN]


def encode_middle_path(key: bytes, middle_path: str) -> str:
    """Encode a full middle_path (segments joined by '/').

    Leading/trailing separators are stripped; internal empty segments
    are dropped. Both '/' and '\\' are accepted as inputs; the output
    always uses '/'.
    """
    if not middle_path:
        return ''
    normalized = middle_path.replace('\\', '/').strip('/')
    if not normalized:
        return ''
    return '/'.join(hmac16_segment(key, seg) for seg in normalized.split('/') if seg)


def decode_middle_path(*_args, **_kwargs):
    """Not implementable — hmac is one-way.

    Callers must look up the original middle_path in ``cloud_index.json``
    (REQUIREMENTS §3.9). This shim exists purely to document intent for
    anyone searching the codebase for a decoder.
    """
    raise NotImplementedError(
        "hmac16 is one-way; resolve middle_path via cloud_index.json"
    )
