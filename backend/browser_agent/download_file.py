"""Browser Agent — chunked file download with progress callback and
robust exception handling.

The original prototype crashed the whole background thread on
ChunkedEncodingError / SSLError (see the tracebacks in the old temp.md).
Here every failure is caught and surfaced as a return value so the
dispatcher can mark the task FAILED and move on.
"""
import os

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}


def download_file(download_url: str, output_path: str, file_size_mb,
                  progress_cb=None) -> bool:
    """Download ``download_url`` to ``output_path`` in 1 MB chunks.

    ``progress_cb(percent)`` is called as the download advances (0-100).
    Returns True on success, False on any handled failure.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    downloaded = 0
    total_bytes = int(file_size_mb) * 1024 * 1024 if file_size_mb else None
    try:
        with requests.get(download_url, headers=HEADERS, stream=True,
                          timeout=(10, 30)) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total_bytes:
                        pct = int((downloaded / total_bytes) * 100)
                        progress_cb(min(pct, 100))
        if progress_cb:
            progress_cb(100)
        return True
    except requests.exceptions.SSLError as e:
        print(f"[browser_agent] SSL error downloading {output_path}: {e}")
    except requests.exceptions.ChunkedEncodingError as e:
        print(f"[browser_agent] connection broken for {output_path}: {e}")
    except requests.exceptions.RequestException as e:
        print(f"[browser_agent] request failed for {output_path}: {e}")
    except OSError as e:
        print(f"[browser_agent] filesystem error for {output_path}: {e}")
    # Clean up a partial file so a retry starts fresh.
    try:
        if os.path.exists(output_path):
            os.remove(output_path)
    except OSError:
        pass
    return False
