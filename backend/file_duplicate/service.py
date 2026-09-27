"""
File Duplicate — Service (business logic singleton)

Indexing pipeline:
  Phase 1: walk all scan roots, upsert file rows (size + mtime only)
  Phase 2: compute hashes — stage A (partial) then stage B (full) for collision-candidates only
  Phase 3: rebuild duplicate groups from full hashes
"""
import os
import threading
import uuid
from typing import Optional

from . import repository as repo
from . import settings_manager as sm
from .hasher import compute_partial_hashes, compute_full_hashes
from . import websocket_service as ws

_BATCH_DB = 500   # rows per DB write


class FileDuplicateService:

    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._running_op: Optional[str] = None

    # ── Stop control ─────────────────────────────────────────────────────────

    def stop(self) -> None:
        self._stop_event.set()

    def is_running(self) -> bool:
        return self._running_op is not None

    def _claim_op(self, name: str) -> str:
        """Atomically claim an op slot. Raises RuntimeError if already running.
        Must be called from the HTTP handler (not the background thread) to avoid TOCTOU."""
        with self._lock:
            if self._running_op is not None:
                raise RuntimeError(f'A scan is already running: {self._running_op}')
            op_id = f'{name}-{uuid.uuid4().hex[:8]}'
            self._stop_event.clear()
            self._running_op = op_id
            return op_id

    def _start_op(self, name: str) -> str:
        """Legacy: must be called with self._lock held. Use _claim_op from HTTP handlers."""
        if self._running_op is not None:
            raise RuntimeError(f'Already running: {self._running_op}')
        op_id = f'{name}-{uuid.uuid4().hex[:8]}'
        self._stop_event.clear()
        self._running_op = op_id
        return op_id

    def _end_op(self) -> None:
        self._running_op = None

    # ── Phase 1: filesystem walk ─────────────────────────────────────────────

    def run_phase1_index(self, op_id: str) -> dict:
        """Walk all scan roots, upsert file rows. Runs in calling thread (caller should thread it).
        op_id must be pre-claimed via _claim_op('phase1') before launching this in a thread."""
        try:
            settings = sm.load()
            roots = settings.get('scan_roots', [])
            include_exts = set(e.lower().lstrip('.') for e in settings.get('include_extensions', []))
            exclude_patterns = set(settings.get('exclude_patterns', []))

            total_inserted = 0
            total_removed = 0

            for root_cfg in roots:
                if self._stop_event.is_set():
                    break
                root_id = root_cfg['id']
                root_path = root_cfg['path']
                if not os.path.isdir(root_path):
                    ws.emit_progress(op_id, 0, 1, f'Root not found: {root_path}')
                    continue

                ws.emit_progress(op_id, 0, 0, f'Scanning {root_cfg["name"]} ({root_path})')

                known_paths = []
                batch = []
                file_count = 0

                for dirpath, dirnames, filenames in os.walk(root_path, topdown=True):
                    if self._stop_event.is_set():
                        break
                    # Prune excluded dirs in-place
                    dirnames[:] = [d for d in dirnames
                                   if d not in exclude_patterns and not d.startswith('.')]

                    for fname in filenames:
                        if self._stop_event.is_set():
                            break
                        if fname.startswith('.'):
                            continue
                        if include_exts:
                            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
                            if ext not in include_exts:
                                continue

                        fpath = os.path.join(dirpath, fname)
                        try:
                            st = os.stat(fpath)
                        except OSError:
                            continue
                        if st.st_size == 0:
                            continue

                        rel = os.path.relpath(fpath, root_path)
                        known_paths.append(fpath)
                        batch.append((root_id, root_path, fpath, rel, fname,
                                      st.st_size, st.st_mtime))
                        file_count += 1

                        if len(batch) >= _BATCH_DB:
                            for args in batch:
                                repo.upsert_file(*args)
                            total_inserted += len(batch)
                            batch.clear()
                            ws.emit_progress(op_id, total_inserted, 0,
                                             f'{root_cfg["name"]}: {total_inserted} files indexed')

                # Flush remaining
                if batch:
                    for args in batch:
                        repo.upsert_file(*args)
                    total_inserted += len(batch)

                # Remove stale rows — only safe when the walk completed fully for this root
                if not self._stop_event.is_set():
                    removed = repo.delete_files_not_in(root_id, known_paths)
                    total_removed += removed
                    ws.emit_progress(op_id, total_inserted, 0,
                                     f'{root_cfg["name"]}: done ({file_count} files, {removed} stale removed)')
                else:
                    ws.emit_progress(op_id, total_inserted, 0,
                                     f'{root_cfg["name"]}: stopped early ({file_count} files seen, stale-removal skipped)')

            result = {
                'total_inserted': total_inserted,
                'total_removed': total_removed,
                'total_in_db': repo.get_total_file_count(),
            }
            ws.emit_complete(op_id, result)
            return result
        except Exception as e:
            ws.emit_error(op_id, str(e))
            raise
        finally:
            self._end_op()

    # ── Phase 2: hashing ─────────────────────────────────────────────────────

    def run_phase2_hash(self, op_id: str) -> dict:
        """Compute partial then full hashes for collision candidates.
        op_id must be pre-claimed via _claim_op('phase2') before launching this in a thread."""
        try:
            workers = sm.get_max_workers()
            batch_size = sm.get_hash_batch_size()

            # Stage A: partial hashes for same-size candidates
            partial_done = 0
            partial_total = 0
            while not self._stop_event.is_set():
                candidates = repo.get_files_needing_partial_hash(limit=batch_size)
                if not candidates:
                    break
                partial_total += len(candidates)
                tasks = [(row[0], row[1]) for row in candidates]

                def _prog_a(cur, tot, _base=partial_done):
                    ws.emit_progress(op_id, _base + cur, partial_total + tot,
                                     f'Partial hash: {_base + cur}/{partial_total}')

                results = compute_partial_hashes(tasks, workers=workers, progress_cb=_prog_a)
                updates = [(h, fid) for fid, h in results if h is not None]
                if updates:
                    repo.bulk_update_partial_hashes(updates)
                partial_done += len(candidates)

            ws.emit_progress(op_id, partial_done, partial_done, 'Partial hashes done')

            # Stage B: full hashes for same-partial candidates
            full_done = 0
            full_total = 0
            while not self._stop_event.is_set():
                candidates = repo.get_files_needing_full_hash(limit=batch_size)
                if not candidates:
                    break
                full_total += len(candidates)
                tasks = [(row[0], row[1]) for row in candidates]

                def _prog_b(cur, tot, _base=full_done):
                    ws.emit_progress(op_id, _base + cur, full_total + tot,
                                     f'Full hash: {_base + cur}/{full_total}')

                results = compute_full_hashes(tasks, workers=workers, progress_cb=_prog_b)
                updates = [(h, fid) for fid, h in results if h is not None]
                if updates:
                    repo.bulk_update_full_hashes(updates)
                full_done += len(candidates)

            result = {
                'partial_hashed': partial_done,
                'full_hashed': full_done,
                'counts': repo.count_pending(),
            }
            ws.emit_complete(op_id, result)
            return result
        except Exception as e:
            ws.emit_error(op_id, str(e))
            raise
        finally:
            self._end_op()

    # ── Phase 3: build groups ─────────────────────────────────────────────────

    def run_phase3_group(self, op_id: str) -> dict:
        """Rebuild duplicate_groups table from full hashes.
        op_id must be pre-claimed via _claim_op('phase3') before launching this in a thread."""
        try:
            ws.emit_progress(op_id, 0, 1, 'Building duplicate groups...')
            count = repo.rebuild_groups()
            stats = repo.get_group_stats()
            result = {'group_count': count, **stats}
            ws.emit_complete(op_id, result)
            return result
        except Exception as e:
            ws.emit_error(op_id, str(e))
            raise
        finally:
            self._end_op()

    # ── File operations ───────────────────────────────────────────────────────

    def move_to_trash(self, file_ids: list) -> dict:
        """Move files to trash_path (soft delete). Removes DB entries for moved files."""
        import shutil
        trash = sm.get_trash_path()
        if not trash:
            raise ValueError('trash_path not configured in settings')
        os.makedirs(trash, exist_ok=True)

        moved = []
        errors = []
        for fid in file_ids:
            row = repo.get_file_entry_by_id(fid)
            if not row:
                continue
            src, rel = row
            if not os.path.exists(src):
                repo.remove_file_entry(fid)
                continue
            dest = os.path.join(trash, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            # Avoid overwriting existing files in trash
            if os.path.exists(dest):
                base, ext = os.path.splitext(dest)
                n = 1
                while os.path.exists(f'{base}_{n}{ext}'):
                    n += 1
                dest = f'{base}_{n}{ext}'
            try:
                shutil.move(src, dest)
                repo.remove_file_entry(fid)
                moved.append({'id': fid, 'src': src, 'dest': dest})
            except Exception as e:
                errors.append({'id': fid, 'src': src, 'error': str(e)})

        # Refresh affected groups
        if moved:
            repo.rebuild_groups()

        return {'moved': moved, 'errors': errors}

    def get_status(self) -> dict:
        return {
            'running': self.is_running(),
            'op_id': self._running_op,
        }


_service: Optional[FileDuplicateService] = None


def get_service() -> FileDuplicateService:
    global _service
    if _service is None:
        _service = FileDuplicateService()
    return _service
