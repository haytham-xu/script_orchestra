"""Type 2 captcha — classical-CV template-matching solver.

Pipeline:
    threshold (min-channel ≥ FG) → connected components → dedupe by size
    → merge x-adjacent fragments → normalize each glyph to a fixed box
    → IoU-match against on-disk templates → parse arithmetic → answer

If we don't have enough templates yet, or a glyph doesn't clear the match
threshold, solve() returns None and the caller falls back to human input.

Templates live on disk under captcha_templates/<label>/*.png where <label>
is the digit itself for 0-9, or one of {plus, minus, equals}.
"""
from __future__ import annotations

import io
import os
import re
from collections import deque
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter

# Tesseract wiring: pytesseract needs to know the binary's location on
# Windows. If tesseract is on PATH this is a no-op.
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


HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(HERE, "captcha_templates")
# Training samples MUST live outside the sob watch tree — pm2's chokidar
# picks up new .jpg files inside backend/ even with .jpg / captcha_training
# ignore patterns, and every write here would restart the process mid-job.
TRAINING_DIR = os.path.join(
    os.path.expanduser("~"), ".script_orchestra", "browser_agent", "captcha_training")
# Best-known sample used to bootstrap templates on first run.
BOOTSTRAP_IMAGE = os.path.join(HERE, "captcha_bootstrap_sample.jpg")
BOOTSTRAP_LABEL = "16+5="

TEMPLATE_H = 24
TEMPLATE_W = 24
FG_MIN_CHANNEL = 130
MIN_GLYPH_PIXELS = 15
MIN_GLYPH_DIM = 4
X_MERGE_GAP = 3
MATCH_MIN_IOU = 0.45            # anything below → "unknown glyph"
MATCH_MIN_MARGIN = 0.02         # top-class must beat second-class by this


def _binarize_bytes(image_bytes: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return _binarize(np.asarray(img))


def _binarize(arr: np.ndarray) -> np.ndarray:
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    return (r >= FG_MIN_CHANNEL) & (g >= FG_MIN_CHANNEL) & (b >= FG_MIN_CHANNEL)


def _connected_components(fg: np.ndarray) -> List[np.ndarray]:
    h, w = fg.shape
    seen = np.zeros_like(fg, dtype=bool)
    out: List[np.ndarray] = []
    for y in range(h):
        for x in range(w):
            if not fg[y, x] or seen[y, x]:
                continue
            comp = np.zeros_like(fg, dtype=bool)
            q = deque([(y, x)])
            seen[y, x] = True
            while q:
                cy, cx = q.popleft()
                comp[cy, cx] = True
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and fg[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            out.append(comp)
    return out


def _segment_glyphs(fg: np.ndarray) -> List[np.ndarray]:
    """Return per-glyph masks (H×W bool, cropped to bbox), sorted L→R."""
    comps = _connected_components(fg)
    kept: List[Tuple[np.ndarray, int, int, int, int]] = []
    for c in comps:
        if int(c.sum()) < MIN_GLYPH_PIXELS:
            continue
        ys, xs = np.where(c)
        x1, x2, y1, y2 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
        if (x2 - x1 + 1) < MIN_GLYPH_DIM or (y2 - y1 + 1) < MIN_GLYPH_DIM:
            continue
        kept.append((c, x1, y1, x2, y2))
    kept.sort(key=lambda t: t[1])

    # JPEG artefacts often break single strokes; merge components whose
    # x-ranges touch or overlap.
    groups: List[Tuple[np.ndarray, int, int, int, int]] = []
    for (m, x1, y1, x2, y2) in kept:
        if groups and (x1 - groups[-1][3]) <= X_MERGE_GAP:
            gm, gx1, gy1, gx2, gy2 = groups[-1]
            groups[-1] = (
                gm | m,
                min(gx1, x1), min(gy1, y1),
                max(gx2, x2), max(gy2, y2),
            )
        else:
            groups.append((m.copy(), x1, y1, x2, y2))

    return [g[0][g[2]:g[4] + 1, g[1]:g[3] + 1] for g in groups]


def _normalize(mask: np.ndarray) -> np.ndarray:
    """Resize a glyph mask to TEMPLATE_H × TEMPLATE_W, preserving aspect
    ratio by padding on the shorter dimension."""
    h, w = mask.shape
    if h == 0 or w == 0:
        return np.zeros((TEMPLATE_H, TEMPLATE_W), dtype=bool)
    scale = min(TEMPLATE_W / w, TEMPLATE_H / h)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    img = Image.fromarray((mask * 255).astype("uint8"), mode="L")
    img = img.resize((new_w, new_h), Image.NEAREST)
    canvas = Image.new("L", (TEMPLATE_W, TEMPLATE_H), 0)
    px = (TEMPLATE_W - new_w) // 2
    py = (TEMPLATE_H - new_h) // 2
    canvas.paste(img, (px, py))
    return np.asarray(canvas) >= 128


_LABEL_TO_DIR = {"+": "plus", "-": "minus", "=": "equals"}
_DIR_TO_LABEL = {v: k for k, v in _LABEL_TO_DIR.items()}


def _label_dir(char: str) -> str:
    return _LABEL_TO_DIR.get(char, char)


def _dir_label(dir_name: str) -> str:
    return _DIR_TO_LABEL.get(dir_name, dir_name)


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = int(np.logical_and(a, b).sum())
    union = int(np.logical_or(a, b).sum())
    return inter / union if union else 0.0


def _iou_shift(a: np.ndarray, b: np.ndarray, max_shift: int = 1) -> float:
    """IoU tolerant to small translations: try shifting `a` in a
    (2*max_shift+1)² grid and return the best IoU. Fixes near-misses caused
    by JPEG-noise bbox jitter that shifts the normalized glyph by a pixel."""
    best = _iou(a, b)
    if max_shift <= 0:
        return best
    h, w = a.shape
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            if dy == 0 and dx == 0:
                continue
            shifted = np.zeros_like(a)
            y1s, y1t = max(0, dy), max(0, -dy)
            y2s = h - abs(dy)
            x1s, x1t = max(0, dx), max(0, -dx)
            x2s = w - abs(dx)
            shifted[y1s:y1s + y2s, x1s:x1s + x2s] = a[y1t:y1t + y2s, x1t:x1t + x2s]
            s = _iou(shifted, b)
            if s > best:
                best = s
    return best


def _load_templates() -> dict:
    """Load {char: [normalized_mask, ...]} from TEMPLATES_DIR."""
    templates: dict = {}
    if not os.path.isdir(TEMPLATES_DIR):
        return templates
    for label_dir in os.listdir(TEMPLATES_DIR):
        d = os.path.join(TEMPLATES_DIR, label_dir)
        if not os.path.isdir(d):
            continue
        char = _dir_label(label_dir)
        for fname in os.listdir(d):
            if not fname.lower().endswith(".png"):
                continue
            try:
                img = Image.open(os.path.join(d, fname)).convert("L")
                if img.size != (TEMPLATE_W, TEMPLATE_H):
                    img = img.resize((TEMPLATE_W, TEMPLATE_H), Image.NEAREST)
                templates.setdefault(char, []).append(np.asarray(img) >= 128)
            except Exception:
                continue
    return templates


def _save_template(char: str, mask: np.ndarray) -> None:
    d = os.path.join(TEMPLATES_DIR, _label_dir(char))
    os.makedirs(d, exist_ok=True)
    # Deduplicate by content hash so repeats don't bloat the folder.
    h = abs(hash(mask.tobytes())) & 0xFFFFFFFFFFFFFFFF
    path = os.path.join(d, f"{h:016x}.png")
    if not os.path.exists(path):
        Image.fromarray((mask * 255).astype("uint8"), mode="L").save(path)


def _classify(glyph_norm: np.ndarray, templates: dict) -> Tuple[Optional[str], float]:
    """Return (best_char, best_iou). Confidence is measured PER-CLASS: with
    30 templates for '1' the top two hits are usually both '1', which is a
    strong positive — not an ambiguity. So we compute the best IoU within
    each character class, then apply the min-IoU / min-margin thresholds
    against the top-two CLASSES."""
    per_class_best: dict = {}
    for char, tmpls in templates.items():
        best = 0.0
        for t in tmpls:
            s = _iou_shift(glyph_norm, t, max_shift=1)
            if s > best:
                best = s
        per_class_best[char] = best
    if not per_class_best:
        return None, 0.0
    ranked = sorted(per_class_best.items(), key=lambda kv: kv[1], reverse=True)
    best_char, best_score = ranked[0]
    if best_score < MATCH_MIN_IOU:
        return None, best_score
    # No margin gate — a merely-plausible match is worth trying. If it's
    # wrong, the server hands back a new captcha and we fall to human input
    # for that item's retry. Cheap to be aggressive.
    return best_char, best_score


def learn_from_expression(image_bytes: bytes, expression: str) -> int:
    """Given a labeled captcha image + expression string (e.g. "16+5="),
    save each glyph as a template. Returns number of templates written."""
    fg = _binarize_bytes(image_bytes)
    glyphs = _segment_glyphs(fg)
    if len(glyphs) != len(expression):
        return 0
    saved = 0
    for m, c in zip(glyphs, expression):
        _save_template(c, _normalize(m))
        saved += 1
    return saved


def _bootstrap_if_empty() -> None:
    """If we have no templates yet but the shipped sample exists, seed a
    handful from it — enough to auto-solve any captcha whose glyphs happen
    to be {1, 6, +, 5, =}."""
    if os.path.isdir(TEMPLATES_DIR) and any(
            os.path.isdir(os.path.join(TEMPLATES_DIR, e))
            for e in os.listdir(TEMPLATES_DIR)):
        return
    if not os.path.exists(BOOTSTRAP_IMAGE):
        return
    try:
        with open(BOOTSTRAP_IMAGE, "rb") as f:
            data = f.read()
        learn_from_expression(data, BOOTSTRAP_LABEL)
    except Exception as e:
        print(f"[captcha_solver] bootstrap failed: {e}")


_bootstrap_if_empty()


def _tesseract_solve(image_bytes: bytes) -> Tuple[Optional[int], str]:
    """Run tesseract on a heavily-preprocessed captcha image. Returns
    (answer, ocr_text). answer is None if we can't parse the arithmetic."""
    if not _TESSERACT_AVAILABLE:
        return None, ""

    # Preprocessing tuned for this site's fixed white-on-green font:
    #   1. Isolate near-white pixels via the SAME rule as segmentation.
    #   2. Median-filter to knock out the pink pixel-noise artefacts.
    #   3. Invert to black-on-white — Tesseract's training data assumption.
    #   4. Upscale ×5 with a smooth resampler so glyph strokes end up thick
    #      and continuous. Tesseract wants glyphs ≥ ~30 px tall.
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.asarray(img)
    fg = _binarize(arr)
    bw = np.where(fg, 0, 255).astype("uint8")   # 0 = ink, 255 = paper
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

    # Try a few PSM modes; take the first one that parses cleanly.
    for psm in (7, 8, 6, 13):
        text = _try(psm)
        text = text.strip().replace(" ", "").replace("\n", "").rstrip("=")
        m = re.match(r"^(\d+)([+\-])(\d+)$", text)
        if m:
            a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
            return (a + b if op == "+" else a - b), text
    return None, text  # last-tried text for debugging


def solve(image_bytes: bytes) -> Tuple[Optional[int], List[Tuple[str, float]]]:
    """Try to auto-solve. Returns (answer, per_glyph_[char_or_?, iou]).

    Strategy: tesseract first (fast + accurate on fixed fonts); template
    matching second as a fallback for the (unlikely) case tesseract errors
    out or returns unparseable text.
    """
    # Tesseract fast path.
    tess_answer, tess_text = _tesseract_solve(image_bytes)
    if tess_answer is not None:
        return tess_answer, [("tesseract", 1.0), (tess_text, 1.0)]

    # Fallback: template matching.
    fg = _binarize_bytes(image_bytes)
    glyphs = _segment_glyphs(fg)
    if not glyphs:
        return None, []
    templates = _load_templates()
    per_glyph: List[Tuple[str, float]] = []
    if not templates:
        return None, [("?", 0.0) for _ in glyphs]
    chars: List[str] = []
    for m in glyphs:
        c, score = _classify(_normalize(m), templates)
        per_glyph.append((c or "?", score))
        if c is None:
            return None, per_glyph
        chars.append(c)
    expr = "".join(chars).rstrip("=")
    m = re.match(r"^(\d+)([+\-])(\d+)$", expr)
    if not m:
        return None, per_glyph
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    return (a + b if op == "+" else a - b), per_glyph


def stash_training_sample(image_bytes: bytes, human_answer: str) -> str:
    """Save a raw captcha image + the user's answer so we can later label
    each glyph and grow the template set. Returns the saved path."""
    os.makedirs(TRAINING_DIR, exist_ok=True)
    import time
    ts = time.strftime("%Y%m%d_%H%M%S")
    # Sanitize human_answer for use in a filename.
    safe = re.sub(r"[^\w\-]+", "_", human_answer)[:20] or "unknown"
    stem = os.path.join(TRAINING_DIR, f"{ts}_{safe}")
    img_path = stem + ".jpg"
    with open(img_path, "wb") as f:
        f.write(image_bytes)
    return img_path


def list_training_samples() -> List[dict]:
    """Return a list of pending training samples, oldest first."""
    if not os.path.isdir(TRAINING_DIR):
        return []
    import base64
    out = []
    for fname in sorted(os.listdir(TRAINING_DIR)):
        if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        path = os.path.join(TRAINING_DIR, fname)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception:
            continue
        # Filename format: <ts>_<answer_hint>.jpg. Split on the LAST underscore
        # after the timestamp to recover the answer hint.
        stem = os.path.splitext(fname)[0]
        parts = stem.split("_", 2)   # ts_YYYYMMDD, ts_HHMMSS, rest
        hint = parts[2] if len(parts) >= 3 else ""
        # Probe how many glyphs we'd segment — helps the labeling UI show
        # whether the expression should have 4 or 5 characters.
        try:
            fg = _binarize_bytes(data)
            glyphs = _segment_glyphs(fg)
            glyph_count = len(glyphs)
        except Exception:
            glyph_count = 0
        out.append({
            "filename": fname,
            "image_base64": base64.b64encode(data).decode("ascii"),
            "answer_hint": hint,
            "glyph_count": glyph_count,
        })
    return out


def label_and_learn(filename: str, expression: str) -> dict:
    """Read a training sample, learn its glyphs as templates, then delete
    the raw file on success. Returns {saved, glyph_count, expected}."""
    path = os.path.join(TRAINING_DIR, os.path.basename(filename))
    if not os.path.isfile(path):
        return {"error": "file not found"}
    with open(path, "rb") as f:
        data = f.read()
    fg = _binarize_bytes(data)
    glyphs = _segment_glyphs(fg)
    if len(glyphs) != len(expression):
        return {
            "error": (f"expression length ({len(expression)}) doesn't match "
                      f"segmented glyph count ({len(glyphs)})"),
            "expected_glyph_count": len(glyphs),
        }
    saved = learn_from_expression(data, expression)
    if saved > 0:
        try:
            os.remove(path)
        except OSError:
            pass
    return {"saved": saved, "glyph_count": len(glyphs)}


def delete_training_sample(filename: str) -> bool:
    path = os.path.join(TRAINING_DIR, os.path.basename(filename))
    if not os.path.isfile(path):
        return False
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def get_templates_summary() -> dict:
    """Return {char: count_of_templates}. Handy for the trainer UI to show
    coverage."""
    if not os.path.isdir(TEMPLATES_DIR):
        return {}
    out = {}
    for label_dir in sorted(os.listdir(TEMPLATES_DIR)):
        d = os.path.join(TEMPLATES_DIR, label_dir)
        if not os.path.isdir(d):
            continue
        n = sum(1 for f in os.listdir(d) if f.lower().endswith(".png"))
        out[_dir_label(label_dir)] = n
    return out
