"""
Video Duplicate Finder — Frame Extractor.

Pure helper module: video → frames + metadata + thumbnails.

DECOUPLED: this module must not import from duplicate_finder.

Primary path: OpenCV (cv2.VideoCapture).
Fallback path: ffmpeg subprocess (via imageio_ffmpeg-bundled binary).
See DECISIONS D-12 (revised), D-15, D-17, D-18.

All functions in this module are TOP-LEVEL (no closures, no instance methods)
so they can be safely pickled by multiprocessing on Windows (spawn).
"""

import hashlib
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

import cv2
from PIL import Image


# ---- Constants ------------------------------------------------------------

# Phash output width: see DECISION D-17. hash_size=8 produces 64-bit hashes
# = 16 hex chars. Frames are downscaled to THUMB_WIDTH before phash for speed.
THUMB_WIDTH = 320

# Sample-point math: skip 5% of duration at head + tail, capped at 2s each.
# Avoids the bias that identical opening/closing logos (anime, TVB serials,
# corporate intros) would otherwise inject into video signatures.
SKIP_PERCENT = 0.05
SKIP_HEAD_MAX_SEC = 2.0
SKIP_TAIL_MAX_SEC = 2.0

# Error type tags. Workers return these in `error_type` so the controller
# can group errors by class in summary reports.
FRAME_EXTRACT_ERROR_TYPES = (
    'cv2_open_failed',       # cv2.VideoCapture refused to open the file
    'no_duration',           # cv2 opened but FPS/frame_count are zero
    'all_frames_failed',     # every sample point returned None
    'ffmpeg_timeout',        # subprocess fallback timed out
    'ffmpeg_failed',         # subprocess fallback returned non-zero or empty stdout
    'pil_decode_failed',     # PIL.Image.open on ffmpeg stdout bytes blew up
    'unsupported_codec',     # cv2 reports negative/zero frame counts likely codec issue
    'unknown_error',         # catch-all for unexpected exceptions
)


# ---- Sample-point math ----------------------------------------------------

def compute_sample_points(duration_sec: float, n_frames: int) -> List[float]:
    """
    Return `n_frames` equally-spaced timestamps (in seconds) inside the
    effective region of the video (after trimming head/tail).

    Degenerate cases:
      - duration <= 0          → []
      - duration < 1 second    → single midpoint
      - eff_end <= eff_start   → single midpoint
      - n_frames == 1          → single midpoint of effective region
    """
    if duration_sec <= 0:
        return []
    if duration_sec < 1.0:
        return [duration_sec / 2.0]

    skip_head = min(SKIP_HEAD_MAX_SEC, duration_sec * SKIP_PERCENT)
    skip_tail = min(SKIP_TAIL_MAX_SEC, duration_sec * SKIP_PERCENT)
    eff_start = skip_head
    eff_end = duration_sec - skip_tail
    if eff_end <= eff_start:
        return [duration_sec / 2.0]

    if n_frames <= 1:
        return [(eff_start + eff_end) / 2.0]

    step = (eff_end - eff_start) / (n_frames - 1)
    return [eff_start + i * step for i in range(n_frames)]


# ---- Metadata probe -------------------------------------------------------

def _fourcc_to_str(fourcc_int: int) -> str:
    """Decode cv2 FOURCC integer into 4-char codec string. Returns '' on fail."""
    try:
        i = int(fourcc_int)
        if i <= 0:
            return ''
        chars = bytes([(i >> (8 * k)) & 0xFF for k in range(4)])
        s = chars.decode('ascii', errors='replace').strip()
        return s
    except Exception:
        return ''


def probe_metadata(file_path: str) -> Optional[Dict]:
    """
    Open the video with cv2 and read basic metadata.

    Returns a dict on success, None on failure. The returned dict always
    contains the keys: duration, width, height, fps, frame_count, vcodec,
    container, bitrate.

    bitrate is CALCULATED as `filesize * 8 / duration` (approximate average
    bitrate in bits/sec). This is not the true encoded bitrate — a proper
    ffprobe would give tighter numbers — but it's zero-dependency and
    accurate enough for the max/min_bitrate sort options in Phase 3 to be
    useful (Q-06 resolution).

    acodec remains None — cv2 doesn't expose audio codec information.

    No file is held open after return.
    """
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        return None
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fourcc = _fourcc_to_str(cap.get(cv2.CAP_PROP_FOURCC))
        duration = (frame_count / fps) if fps > 0 else 0.0

        # Container guessed from extension; cv2 doesn't tell us directly.
        ext = os.path.splitext(file_path)[1].lower().lstrip('.')

        if frame_count <= 0 or fps <= 0:
            return None

        # Estimated bitrate (bits/sec) — Q-06. Filesize includes container
        # overhead + audio track, but for sort purposes on a homogeneous set
        # (same container, similar resolution) it ranks correctly.
        bitrate = None
        try:
            if duration > 0:
                filesize = os.path.getsize(file_path)
                bitrate = int(filesize * 8 / duration)
        except OSError:
            pass

        return {
            'duration':    duration,
            'width':       width,
            'height':      height,
            'fps':         fps,
            'frame_count': frame_count,
            'vcodec':      fourcc,
            'container':   ext,
            'bitrate':     bitrate,
        }
    finally:
        cap.release()


# ---- Frame extraction (cv2 primary) ---------------------------------------

def extract_frame_at_cv2(file_path: str, t_seconds: float):
    """
    Seek to `t_seconds` and return a single BGR ndarray.

    Returns None on any failure (file unreadable, seek beyond end, decode error).
    Opens + releases the capture per-call — for batch extraction prefer
    `extract_frames_at_cv2_batch` to amortize the open.
    """
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, t_seconds * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        return frame
    finally:
        cap.release()


def extract_frames_at_cv2_batch(file_path: str, t_seconds_list: List[float]) -> List[Optional["cv2.Mat"]]:
    """
    Open the file once and read N frames at the given timestamps.

    Returns a list aligned with `t_seconds_list`; entries are BGR ndarrays
    or None for frames that couldn't be read.
    """
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        return [None] * len(t_seconds_list)
    out = []
    try:
        for t in t_seconds_list:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            out.append(frame if ok and frame is not None else None)
        return out
    finally:
        cap.release()


# ---- Frame extraction (ffmpeg fallback) -----------------------------------

def extract_frame_at_ffmpeg_fallback(file_path: str, t_seconds: float,
                                     ffmpeg_path: str,
                                     timeout: int = 30):
    """
    Last-resort frame extractor using the ffmpeg CLI subprocess.

    Used only when cv2 fails (e.g. HEVC on Windows default build). Returns a
    PIL.Image (already decoded) or None. Writes nothing to disk.

    Args:
        file_path: source video path
        t_seconds: timestamp to extract
        ffmpeg_path: absolute path to ffmpeg binary (see SettingsManager)
        timeout: seconds before SIGTERM-ing the subprocess

    Returns: PIL.Image (RGB mode) or None.

    Note: -ss is placed BEFORE -i for fast input seek (no full demux).
    """
    cmd = [
        ffmpeg_path,
        '-hide_banner',
        '-loglevel', 'error',
        '-ss', f'{t_seconds:.3f}',
        '-i', file_path,
        '-frames:v', '1',
        '-f', 'image2pipe',
        '-vcodec', 'mjpeg',
        '-an',
        '-',
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    except (OSError, FileNotFoundError):
        return None

    if proc.returncode != 0 or not proc.stdout:
        return None

    try:
        import io
        return Image.open(io.BytesIO(proc.stdout)).convert('RGB')
    except Exception:
        return None


# ---- BGR → phash-ready PIL helper -----------------------------------------

def bgr_to_pil(frame_bgr, target_width: int = THUMB_WIDTH) -> Image.Image:
    """
    Convert a cv2 BGR ndarray to an RGB PIL.Image, downscaled to `target_width`
    while preserving aspect ratio. Used as input to imagehash.phash.

    cv2.resize is significantly faster than PIL.Image.thumbnail, so the
    downscaling happens before crossing the cv2→PIL boundary (D-17).
    """
    h, w = frame_bgr.shape[:2]
    if w > target_width:
        scale = target_width / w
        frame_bgr = cv2.resize(
            frame_bgr,
            (target_width, int(h * scale)),
            interpolation=cv2.INTER_AREA,
        )
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


# ---- Thumbnail generation -------------------------------------------------

def thumbnail_filename_for(file_path: str) -> str:
    """
    Deterministic per-video thumbnail filename: md5(abs_path)[:16].jpg.

    16 hex chars = 64 bits of entropy, collision-safe at any plausible scale
    (≤ a few million videos).
    """
    abs_path = os.path.abspath(file_path)
    h = hashlib.md5(abs_path.encode('utf-8', errors='replace')).hexdigest()
    return h[:16] + '.jpg'


def extract_thumbnail(file_path: str, dest_path: str,
                      t_seconds: Optional[float] = None,
                      width: int = 320,
                      thumbnail_position_percent: int = 30,
                      ffmpeg_path: Optional[str] = None,
                      ffmpeg_timeout: int = 30) -> bool:
    """
    Generate a JPG thumbnail and write to `dest_path`.

    If `t_seconds` is None, picks a frame at `thumbnail_position_percent`% of
    the video's duration (default 30% — avoids head black frames / tail credits).

    Order of operations:
      1. cv2: probe duration → seek + read frame
      2. on cv2 failure, ffmpeg fallback (if `ffmpeg_path` given)
      3. write JPG to dest_path (creates parent dir if needed)

    Returns True on success, False otherwise.
    """
    try:
        os.makedirs(os.path.dirname(dest_path) or '.', exist_ok=True)
    except Exception:
        return False

    # Step 1: figure out the timestamp
    meta = probe_metadata(file_path)
    if meta is None:
        # No metadata → can't compute timestamp from percent; use t_seconds or fail
        if t_seconds is None:
            return False
        target_t = float(t_seconds)
    else:
        if t_seconds is None:
            pct = max(0, min(100, thumbnail_position_percent))
            target_t = meta['duration'] * (pct / 100.0)
        else:
            target_t = float(t_seconds)

    # Step 2: cv2 primary
    frame = extract_frame_at_cv2(file_path, target_t)

    # Step 3: ffmpeg fallback
    pil_img: Optional[Image.Image] = None
    if frame is not None:
        pil_img = bgr_to_pil(frame, target_width=width)
    elif ffmpeg_path:
        pil_img = extract_frame_at_ffmpeg_fallback(
            file_path, target_t,
            ffmpeg_path=ffmpeg_path,
            timeout=ffmpeg_timeout,
        )
        if pil_img is not None and pil_img.width > width:
            # match the cv2 path's resize
            scale = width / pil_img.width
            pil_img = pil_img.resize(
                (width, int(pil_img.height * scale)),
                Image.LANCZOS,
            )

    if pil_img is None:
        return False

    try:
        pil_img.save(dest_path, format='JPEG', quality=85, optimize=True)
        return True
    except Exception:
        return False
