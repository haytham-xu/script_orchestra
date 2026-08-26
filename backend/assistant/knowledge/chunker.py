"""
Text extraction and chunking.

Chunking strategy: paragraph-first, character-limit-second. We split
text on blank lines to keep paragraphs together where possible, then if
a chunk still exceeds `CHUNK_SIZE_CHARS`, we split it on sentence
boundaries with a sliding overlap.

PDFs are parsed with pypdf. Code files are treated as plain text — no
AST awareness (would be diminishing returns for a v1).
"""
import logging
import re
from pathlib import Path
from typing import List

from .config import (
    CHUNK_OVERLAP_CHARS,
    CHUNK_SIZE_CHARS,
    SUPPORTED_CODE_EXT,
    SUPPORTED_PDF_EXT,
    SUPPORTED_TEXT_EXT,
)

logger = logging.getLogger("assistant.knowledge.chunker")


def extract_text(path: Path) -> str:
    """Return the file's text or an empty string if we can't parse it."""
    ext = path.suffix.lower()
    if ext in SUPPORTED_TEXT_EXT or ext in SUPPORTED_CODE_EXT:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[kb] failed reading text {path}: {exc}")
            return ""
    if ext in SUPPORTED_PDF_EXT:
        try:
            from pypdf import PdfReader
        except ImportError:
            logger.warning("[kb] pypdf not installed — skipping PDFs")
            return ""
        try:
            reader = PdfReader(str(path))
            return "\n\n".join(
                (page.extract_text() or "") for page in reader.pages
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[kb] failed parsing PDF {path}: {exc}")
            return ""
    return ""


def _split_paragraphs(text: str) -> List[str]:
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def _split_by_size(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Split a too-long block on sentence boundaries with a rolling window.
    """
    sentences = re.split(r"(?<=[。.!?！？])\s+|\n", text)
    sentences = [s for s in sentences if s]
    chunks: List[str] = []
    buf = ""
    for s in sentences:
        if len(buf) + len(s) + 1 <= chunk_size:
            buf = f"{buf} {s}".strip() if buf else s
        else:
            if buf:
                chunks.append(buf)
            # Start next chunk with an overlap tail of the previous one.
            tail = buf[-overlap:] if buf and overlap > 0 else ""
            buf = (tail + " " + s).strip() if tail else s
            # If the sentence itself exceeds chunk_size, hard-slice it.
            while len(buf) > chunk_size:
                chunks.append(buf[:chunk_size])
                buf = buf[chunk_size - overlap:]
    if buf:
        chunks.append(buf)
    return chunks


def chunk_text(text: str,
               chunk_size: int = CHUNK_SIZE_CHARS,
               overlap: int = CHUNK_OVERLAP_CHARS) -> List[str]:
    """
    Turn raw text into a list of chunks suitable for embedding.
    """
    text = text.strip()
    if not text:
        return []

    chunks: List[str] = []
    for para in _split_paragraphs(text):
        if len(para) <= chunk_size:
            chunks.append(para)
        else:
            chunks.extend(_split_by_size(para, chunk_size, overlap))

    # Coalesce very small chunks with their neighbours so we don't produce
    # 50-char shards that dilute the retrieval score.
    coalesced: List[str] = []
    for c in chunks:
        if coalesced and len(coalesced[-1]) + len(c) + 1 <= chunk_size:
            coalesced[-1] = coalesced[-1] + "\n\n" + c
        else:
            coalesced.append(c)
    return coalesced
