"""Captcha solver — Tesseract OCR only.

Pipeline:
    isolate near-white pixels → invert to black-on-white → median-filter
    → upscale x5 → tesseract (whitelist: 0-9 + - =) → parse arithmetic

Returns None when tesseract is unavailable or the expression can't be parsed;
the caller then falls back to human input.
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


def solve(image_bytes: bytes) -> Tuple[Optional[int], str]:
    """Try to auto-solve the captcha via Tesseract.

    Returns (answer, ocr_text). answer is None if tesseract is unavailable
    or the OCR output can't be parsed as an arithmetic expression.
    """
    if not _TESSERACT_AVAILABLE:
        return None, ""

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.asarray(img)
    fg = _binarize(arr)
    bw = np.where(fg, 0, 255).astype("uint8")
    pil = Image.fromarray(bw, mode="L")
    pil = pil.filter(ImageFilter.MedianFilter(size=3))
    w, h = pil.size
    pil = pil.resize((w * 5, h * 5), Image.LANCZOS)

    def _try(psm: int) -> str:
        try:
            return pytesseract.image_to_string(
                pil,
                config=f"--psm {psm} -c tessedit_char_whitelist=0123456789+-="
                       f" -c load_system_dawg=0 -c load_freq_dawg=0",
            )
        except Exception:
            return ""

    for psm in (7, 8, 6, 13):
        text = _try(psm).strip().replace(" ", "").replace("\n", "").rstrip("=")
        m = re.match(r"^(\d+)([+\-])(\d+)$", text)
        if m:
            a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
            return (a + b if op == "+" else a - b), text

    return None, ""
