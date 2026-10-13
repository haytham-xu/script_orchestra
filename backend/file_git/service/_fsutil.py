"""
Filesystem helpers shared across file_git services.

``atomic_write_json`` writes JSON to a UNIQUE temp file in the destination
directory, fsyncs it, then ``os.replace``s it into place. The unique temp
name (via ``tempfile.mkstemp``) is important: a shared ``<name>.tmp`` path
lets two concurrent writers truncate each other's temp and publish a
half-written file (observed as mid-file JSON corruption on large indexes /
queues). os.replace is atomic on both POSIX and Windows, so readers always
see either the old or the new complete file, never a partial one.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Optional


def atomic_write_json(path: str, data: Any, *, indent: Optional[int] = None) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
