"""Captcha solver — Tesseract OCR only.

Pipeline:
    isolate near-white pixels → invert to black-on-white → morphological
    dilation (close small gaps) → median-filter → 5x upscale (LANCZOS)
    → tesseract (whitelist: 0-9 + - =, multiple PSMs) → parse arithmetic

Returns (None, "") when tesseract is unavailable or the expression can't be
parsed; caller falls back to human input.
"""
from __future__ import annotations

import io
import os
import re
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter

try:
    import pytesseract  # type: ignore
    _TESSERACT_CANDIDATES = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for _p in _TESSERACT_CANDIDATES:
        if os.path.exists(_p):
            pytesseract.pytesseract.tesseract_cmd = _p
            break
    _TESSERACT_AVAILABLE = True
except Exception:
    _TESSERACT_AVAILABLE = False

FG_MIN_CHANNEL = 130


def _binarize(arr: np.ndarray) -> np.ndarray:
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    return (r >= FG_MIN_CHANNEL) & (g >= FG_MIN_CHANNEL) & (b >= FG_MIN_CHANNEL)


def _dilate(mask: np.ndarray, radius: int = 1) -> np.ndarray:
    """Simple boolean dilation: OR-shifts by ±radius in each direction."""
    out = mask.copy()
    for d in range(1, radius + 1):
        out[d:, :] |= mask[:-d, :]
        out[:-d, :] |= mask[d:, :]
        out[:, d:] |= mask[:, :-d]
        out[:, :-d] |= mask[:, d:]
    return out


def solve(image_bytes: bytes) -> Tuple[Optional[int], str]:
    """Try to auto-solve the captcha via Tesseract.

    Returns (answer, ocr_text). answer is None if tesseract is unavailable
    or the OCR output can't be parsed as an arithmetic expression.
    """
    if not _TESSERACT_AVAILABLE:
        return None, ""

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.asarray(img)

    # Isolate foreground (near-white text) and dilate slightly to close gaps
    # introduced by JPEG compression artifacts around character edges.
    fg = _binarize(arr)
    fg = _dilate(fg, radius=1)

    # Invert: foreground (text) becomes black (0), background becomes white (255).
    bw = np.where(fg, 0, 255).astype("uint8")
    pil = Image.fromarray(bw, mode="L")

    # Median filter removes isolated noise pixels.
    pil = pil.filter(ImageFilter.MedianFilter(size=3))

    # 5x upscale — Tesseract works much better on larger images.
    w, h = pil.size
    pil = pil.resize((w * 5, h * 5), Image.LANCZOS)

    # Sharpen after upscaling to restore edge crispness.
    pil = pil.filter(ImageFilter.SHARPEN)
    pil = pil.filter(ImageFilter.SHARPEN)

    def _try(psm: int) -> str:
        try:
            return pytesseract.image_to_string(
                pil,
                config=(
                    f"--psm {psm}"
                    " -c tessedit_char_whitelist=0123456789+-="
                    " -c load_system_dawg=0"
                    " -c load_freq_dawg=0"
                ),
            )
        except Exception:
            return ""

    for psm in (7, 8, 6, 13):
        text = _try(psm).strip().replace(" ", "").replace("\n", "").rstrip("=")
        # Tolerate OCR confusing '−' (en-dash) with '-' and similar glitches.
        text = text.replace("—", "-").replace("–", "-").replace("×", "*")
        m = re.match(r"^(\d+)([+\-])(\d+)$", text)
        if m:
            a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
            return (a + b if op == "+" else a - b), text

    return None, ""
