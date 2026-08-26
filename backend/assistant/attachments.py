"""
Attachment storage + Anthropic content-block conversion.

Files are stored on disk under `MEDIA_DIR/<sha256[:2]>/<sha256>` so
identical uploads dedupe automatically. Only the DB row differs when a
user re-uploads the same image in two conversations.
"""
import base64
import hashlib
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import db
from .config import (
    DOCUMENT_MIME_TYPES,
    IMAGE_MIME_TYPES,
    MAX_ATTACHMENT_BYTES,
    MAX_TEXT_INLINE_BYTES,
    MEDIA_DIR,
    TEXT_MIME_PREFIXES,
)

logger = logging.getLogger("assistant.attachments")


def _classify_kind(mime_type: str) -> str:
    if mime_type in IMAGE_MIME_TYPES:
        return "image"
    if mime_type in DOCUMENT_MIME_TYPES:
        return "document"
    if mime_type.startswith(TEXT_MIME_PREFIXES):
        return "text"
    # Unknowns land in "document" so Claude at least sees the base64 blob
    # — the API will reject unsupported types with a clear error.
    return "document"


def store_attachment(
    conv_id: str,
    data: bytes,
    filename: str,
    mime_type: str,
) -> Dict:
    """
    Persist an uploaded file and its DB row. Returns the created row.
    Raises ValueError on size / mime problems.
    """
    if not data:
        raise ValueError("attachment is empty")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise ValueError(
            f"attachment exceeds max size ({MAX_ATTACHMENT_BYTES} bytes)"
        )
    if not mime_type:
        raise ValueError("mime_type is required")

    if db.get_conversation(conv_id) is None:
        raise LookupError(f"Conversation not found: {conv_id}")

    kind = _classify_kind(mime_type)
    sha256 = hashlib.sha256(data).hexdigest()

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    bucket = MEDIA_DIR / sha256[:2]
    bucket.mkdir(parents=True, exist_ok=True)
    storage_path = bucket / sha256

    # Content-addressed: only write once per unique payload.
    if not storage_path.exists():
        storage_path.write_bytes(data)

    attachment_id = str(uuid.uuid4())
    return db.create_attachment(
        attachment_id=attachment_id,
        conv_id=conv_id,
        kind=kind,
        mime_type=mime_type,
        filename=filename or f"upload-{sha256[:8]}",
        byte_size=len(data),
        sha256=sha256,
        storage_path=str(storage_path),
    )


def read_attachment_bytes(row: Dict) -> bytes:
    path = Path(row["storage_path"])
    if not path.exists():
        raise FileNotFoundError(f"missing storage file: {path}")
    return path.read_bytes()


def as_content_blocks(rows: List[Dict]) -> Tuple[List[Dict], List[str]]:
    """
    Convert a list of attachment rows into Anthropic API content blocks.

    Returns (blocks, warnings) — warnings are non-fatal notes appended to
    the user text so the assistant knows an attachment couldn't be
    included as expected (e.g. text file truncated).
    """
    blocks: List[Dict] = []
    warnings: List[str] = []

    for row in rows:
        try:
            data = read_attachment_bytes(row)
        except FileNotFoundError as exc:
            warnings.append(f"[attachment {row['filename']}: {exc}]")
            continue

        kind = row["kind"]
        mime_type = row["mime_type"]
        filename = row["filename"]

        if kind == "image":
            blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": base64.b64encode(data).decode("ascii"),
                },
            })
        elif kind == "document":
            blocks.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": base64.b64encode(data).decode("ascii"),
                },
            })
        elif kind == "text":
            text = data.decode("utf-8", errors="replace")
            truncated = False
            if len(text.encode("utf-8")) > MAX_TEXT_INLINE_BYTES:
                text = text[:MAX_TEXT_INLINE_BYTES]
                truncated = True
            blocks.append({
                "type": "text",
                "text": (
                    f"<<< attached file: {filename} "
                    f"(mime={mime_type})>>>\n{text}\n<<< end of file >>>"
                ),
            })
            if truncated:
                warnings.append(
                    f"[note: attached text file '{filename}' was truncated "
                    f"to {MAX_TEXT_INLINE_BYTES} bytes]"
                )
        else:
            warnings.append(f"[unsupported attachment kind: {kind}]")

    return blocks, warnings


def lookup_and_check_ownership(
    attachment_ids: List[str], conv_id: str
) -> List[Dict]:
    """Return the attachment rows, verifying all belong to `conv_id`."""
    rows: List[Dict] = []
    for aid in attachment_ids:
        row = db.get_attachment(aid)
        if row is None:
            raise LookupError(f"attachment not found: {aid}")
        if row["conversation_id"] != conv_id:
            raise PermissionError(
                f"attachment {aid} does not belong to conversation {conv_id}"
            )
        rows.append(row)
    return rows
