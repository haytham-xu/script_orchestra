"""Web Terminal — scrollback file store.

Each window gets its own file: data/<window_id>.scrollback
Raw ANSI bytes are appended on every PTY output chunk.
Read truncates to the last SCROLLBACK_MAX bytes so memory stays bounded.
"""
import os
import re

_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
SCROLLBACK_MAX = 500 * 1024  # 500 KB

# xterm sends these terminal capability queries; the PTY reader captures the
# shell's responses and they must NOT be saved to scrollback — on replay they
# appear as raw garbage text because no one answers them a second time.
#   ESC [ ? <digits> c   — Primary/Secondary DA response
#   ESC [ <row> ; <col> R — CPR (Cursor Position Report) response
#   ESC [ > <digits> c   — Secondary DA response
_STRIP_RE = re.compile(r'\x1b\[\?[\d;]*c|\x1b\[>\d+c|\x1b\[\d+;\d+R')


def _path(window_id: str) -> str:
    os.makedirs(_DATA_DIR, exist_ok=True)
    return os.path.join(_DATA_DIR, f'{window_id}.scrollback')


def append(window_id: str, data: str) -> None:
    cleaned = _STRIP_RE.sub('', data)
    if not cleaned:
        return
    try:
        with open(_path(window_id), 'ab') as f:
            f.write(cleaned.encode('utf-8', errors='replace'))
    except OSError:
        pass


def read(window_id: str) -> str:
    p = _path(window_id)
    if not os.path.exists(p):
        return ''
    try:
        size = os.path.getsize(p)
        with open(p, 'rb') as f:
            if size > SCROLLBACK_MAX:
                f.seek(size - SCROLLBACK_MAX)
            raw = f.read()
        text = raw.decode('utf-8', errors='replace')
        return _STRIP_RE.sub('', text)
    except OSError:
        return ''


def delete(window_id: str) -> None:
    p = _path(window_id)
    try:
        os.remove(p)
    except OSError:
        pass
