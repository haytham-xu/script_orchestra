"""
Video Duplicate Finder — REST API Controller.

DECOUPLED: this module must not import from duplicate_finder.

Current state: /health + /phase1/refresh + /phase1/stop.
Real Phase 2/2.5/3/Compare/Delete endpoints land in S3-S9.

Conventions (mirror duplicate_finder, see buffer/02_api_reference.md):
  - All routes return JSON
  - Long-running operations send WebSocket progress on rooms
        vscan:{scan_id}:progress / :complete / :error
  - Stop endpoints (`/phase{N}/stop`) set the workflow's stop event
  - HTTP 409 reserved for Phase 3 materialization conflicts
  - HTTP 499 reserved for "stopped by user"
"""
import io
import os
import subprocess
import sys
import uuid

from flask import request, send_file
from flask_restx import Namespace, Resource

from .companion_files import move_with_companions
from .frame_extractor import (
    bgr_to_pil,
    extract_frame_at_cv2,
    extract_frame_at_ffmpeg_fallback,
    extract_thumbnail,
    probe_metadata,
    thumbnail_filename_for,
)
from .settings_manager import settings_manager
from .video_hash_cache import VideoHashCache
from .websocket_service import emit_complete, emit_error, emit_progress

ns = Namespace("")

# File-extension whitelist — only files matching these get scanned.
# Case-insensitive at the call site (use `name.lower().endswith(VIDEO_EXTS)`).
VIDEO_EXTS = (
    '.mp4', '.mkv', '.avi', '.mov', '.webm',
    '.flv', '.wmv', '.m4v', '.ts', '.m2ts',
)


# ---------------------------------------------------------------------------
# Workflow singleton factory
# ---------------------------------------------------------------------------
# CRITICAL (see DECISION pattern E1 in buffer/03_patterns_and_gotchas.md):
# The Workflow instance owns a multiprocessing.Manager().Event() used as the
# cross-process stop signal. Recreating the instance discards the Event,
# which means a user-pressed Stop button silently misses any work in flight
# at the moment of recreation. So we keep ONE instance per process, even if
# config (DB path) changes — we just log a warning.
# ---------------------------------------------------------------------------

_workflow = None  # type: ignore[var-annotated]


def get_workflow():
    """Return the process-wide VideoDuplicateFinderWorkflow singleton."""
    global _workflow
    if _workflow is None:
        # Local import keeps blueprint.py's import-time cheap and avoids
        # circular imports if controller is imported before workflow ready.
        from .video_workflow import VideoDuplicateFinderWorkflow

        db_path = settings_manager.get_video_db_path()
        _workflow = VideoDuplicateFinderWorkflow(db_path=db_path)
        print(f"[Video Workflow] Initialized with DB: {db_path}")
    else:
        try:
            cur = settings_manager.get_video_db_path()
            if str(_workflow.db_path) != str(cur):
                print(f"[Video Workflow] WARNING: configured DB path "
                      f"changed from {_workflow.db_path} to {cur} — "
                      f"keeping existing workflow to preserve stop event")
        except Exception:
            pass
    return _workflow


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _walk_video_files(roots, exclude_paths_abs):
    """Yield absolute paths of all VIDEO_EXTS-matching files under `roots`,
    pruning subtrees that are inside `exclude_paths_abs`.

    `roots` may contain individual files OR directories. Files that aren't
    in VIDEO_EXTS are skipped silently. Non-existent paths log a warning
    and are skipped.
    """
    excluded_pruned = 0

    def _is_excluded(p: str) -> bool:
        # Match exact or as a parent-dir prefix (with os.sep boundary —
        # otherwise '/foo' would falsely exclude '/foobar').
        pa = os.path.abspath(p)
        for ex in exclude_paths_abs:
            if pa == ex or pa.startswith(ex + os.sep):
                return True
        return False

    for raw in roots:
        if not raw:
            continue
        if not os.path.exists(raw):
            print(f"[Phase 1 API] WARNING: path does not exist: {raw}")
            continue

        if os.path.isfile(raw):
            if raw.lower().endswith(VIDEO_EXTS) and not _is_excluded(raw):
                yield os.path.abspath(raw)
            continue

        print(f"[Phase 1 API] walking directory: {raw}")
        for cur_root, dirs, files in os.walk(raw):
            if _is_excluded(cur_root):
                print(f"[Phase 1 API]   excluding subtree: {cur_root}")
                dirs[:] = []
                excluded_pruned += 1
                continue
            # Prune any direct subdirs that are excluded
            pruned = [d for d in dirs if _is_excluded(os.path.join(cur_root, d))]
            if pruned:
                for d in pruned:
                    print(f"[Phase 1 API]   pruning excluded subdir: {os.path.join(cur_root, d)}")
                excluded_pruned += len(pruned)
                dirs[:] = [d for d in dirs if d not in pruned]

            for f in files:
                if f.lower().endswith(VIDEO_EXTS):
                    yield os.path.abspath(os.path.join(cur_root, f))


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@ns.route('/health')
class HealthResource(Resource):
    def get(self):
        """Liveness probe. Returns {ok, tool, version}."""
        return {
            'ok': True,
            'tool': 'video-duplicate-finder',
            'version': '0.1.0-S13',
        }


# ---------------------------------------------------------------------------
# /phase1/refresh — scan FS, sync DB, compute N-frame signatures
# ---------------------------------------------------------------------------
#
# Request body:
#   {
#     "paths":   ["E:\\videos"],          # required, list of files OR dirs
#     "scan_id": "vphase1-..."            # optional, for WS room routing
#   }
#
# Response (always HTTP 200, even when stopped — stopped: true marks that):
#   {
#     "added":   int,
#     "removed": int,
#     "skipped": int,
#     "errors":  [{file_path, error_type, error_msg}, ...],
#     "elapsed": float,
#     "stopped": bool,
#     "scan_id": "vphase1-..."
#   }
# ---------------------------------------------------------------------------

@ns.route('/phase1/refresh')
class Phase1RefreshResource(Resource):
    def post(self):
        data = request.json or {}
        paths = data.get('paths') or []
        if not isinstance(paths, list) or not paths:
            return {'error': 'paths (non-empty list) required'}, 400

        scan_id = data.get('scan_id') or f"vphase1-{uuid.uuid4().hex[:8]}"

        print("=" * 80)
        print(f"[Phase 1 API] START scan_id={scan_id}, paths_count={len(paths)}")
        print(f"[Phase 1 API] DEBUG: first 3 paths = {paths[:3]}{'...' if len(paths) > 3 else ''}")
        print("=" * 80)

        # Resolve excludes (configured globally, applied here)
        exclude_paths = settings_manager.get_exclude_folder_paths() or []
        exclude_paths_abs = [os.path.abspath(p) for p in exclude_paths if p]
        if exclude_paths_abs:
            print(f"[Phase 1 API] exclude_paths_abs: {exclude_paths_abs}")

        # Walk the filesystem
        try:
            video_files = list(_walk_video_files(paths, exclude_paths_abs))
        except Exception as e:
            print(f"[Phase 1 API] walk failed: {e}")
            return {'error': f'walk failed: {e}'}, 500

        print(f"[Phase 1 API] discovered {len(video_files)} video files")

        # Progress callback bridges workflow → WebSocket
        def cb(current, total, message):
            # Verbose per-emit log so operators can trace what the FE receives
            print(f"[Phase 1 API] WS emit → vscan:{scan_id}:progress "
                  f"[{current}/{total}] {message}")
            emit_progress(scan_id, current, total, message)

        # Call workflow
        try:
            workflow = get_workflow()
            print(f"[Phase 1 API] workflow id={id(workflow)} pre-run "
                  f"stop_event={workflow._stop_event.is_set()}")
            result = workflow.phase1_refresh_videos(
                file_paths=video_files,
                progress_callback=cb,
            )
        except InterruptedError as e:
            # Reserved code path per buffer/02 — workflow should NOT raise on
            # stop (it returns stopped:true), but we honor InterruptedError if
            # something inside opts to raise.
            emit_error(scan_id, str(e))
            return {'error': 'stopped', 'message': str(e), 'scan_id': scan_id}, 499
        except Exception as e:
            import traceback; traceback.print_exc()
            emit_error(scan_id, str(e))
            return {'error': str(e), 'scan_id': scan_id}, 500

        result['scan_id'] = scan_id

        # WebSocket completion (summary only, no large arrays)
        emit_complete(scan_id, {
            'scan_id': scan_id,
            'added': result.get('added', 0),
            'removed': result.get('removed', 0),
            'skipped': result.get('skipped', 0),
            'error_count': len(result.get('errors', []) or []),
            'elapsed': result.get('elapsed', 0),
            'stopped': result.get('stopped', False),
        })

        print(f"[Phase 1 API] DONE scan_id={scan_id} "
              f"added={result['added']} removed={result['removed']} "
              f"skipped={result['skipped']} stopped={result['stopped']} "
              f"elapsed={result['elapsed']:.1f}s "
              f"errors_count={len(result.get('errors', []))}")
        return result


# ---------------------------------------------------------------------------
# /phase1/stop
# ---------------------------------------------------------------------------

@ns.route('/phase1/stop')
class Phase1StopResource(Resource):
    def post(self):
        print("=" * 80)
        print("[Phase 1 API] STOP request received")
        wf = get_workflow()
        print(f"[Phase 1 API] workflow id={id(wf)} pre-stop "
              f"stop_event={wf._stop_event.is_set()}")
        wf.set_stop()
        print(f"[Phase 1 API] workflow id={id(wf)} post-stop "
              f"stop_event={wf._stop_event.is_set()}")
        print("=" * 80)
        return {'message': 'Phase 1 stop signal sent'}


# ---------------------------------------------------------------------------
# /phase2/build — compute pairwise distance, write video_similarities
# ---------------------------------------------------------------------------
#
# Request body (all optional):
#   {
#     "threshold_distance": 102,   # int, 0..VIDEO_HASH_BITS (512). Edges
#                                  # with distance ≤ this are stored. Default
#                                  # 102 (= 80% similarity coverage).
#                                  # See video_workflow.phase2_build_similarities
#                                  # docstring for the schema-vs-UI threshold
#                                  # distinction.
#     "threshold_percent": 80,     # alternative: pass UI percent, server
#                                  # converts to distance. ONLY honored if
#                                  # threshold_distance is absent. Min
#                                  # bound applied = 80% so Phase 2.5 can
#                                  # later filter down to any tighter UI %.
#     "scan_id":           "vphase2-..."
#   }
#
# Response (always HTTP 200; stopped:true marks user interruption):
#   {
#     "processed":          int,
#     "similarities_found": int,
#     "elapsed":            float,
#     "stopped":            bool,
#     "scan_id":            "vphase2-..."
#   }
# ---------------------------------------------------------------------------

@ns.route('/phase2/build')
class Phase2BuildResource(Resource):
    def post(self):
        data = request.json or {}

        # Compute threshold_distance — prefer explicit distance, fall back to %
        threshold_distance = data.get('threshold_distance')
        if threshold_distance is None:
            threshold_percent = int(data.get('threshold_percent', 80))
            # Import VIDEO_HASH_BITS lazily — avoids circular at module load
            from .video_hash_cache import VIDEO_HASH_BITS
            ui_distance = int(VIDEO_HASH_BITS * (100 - threshold_percent) / 100)
            # Cover at least 80% so Phase 2.5 can filter to tighter UI thresholds
            min_coverage = int(VIDEO_HASH_BITS * 0.2)
            threshold_distance = max(ui_distance, min_coverage)
        threshold_distance = max(0, int(threshold_distance))

        scan_id = data.get('scan_id') or f"vphase2-{uuid.uuid4().hex[:8]}"

        print("=" * 80)
        print(f"[Phase 2 API] START scan_id={scan_id}, threshold_distance={threshold_distance}")
        print(f"[Phase 2 API] DEBUG: request body = {data}")
        print("=" * 80)

        def cb(current, total, message):
            print(f"[Phase 2 API] WS emit → vscan:{scan_id}:progress [{current}/{total}] {message}")
            emit_progress(scan_id, current, total, message)

        try:
            workflow = get_workflow()
            print(f"[Phase 2 API] workflow id={id(workflow)} pre-run "
                  f"stop_event={workflow._stop_event.is_set()}")
            result = workflow.phase2_build_similarities(
                threshold_distance=threshold_distance,
                progress_callback=cb,
            )
        except InterruptedError as e:
            emit_error(scan_id, str(e))
            return {'error': 'stopped', 'message': str(e), 'scan_id': scan_id}, 499
        except Exception as e:
            import traceback; traceback.print_exc()
            emit_error(scan_id, str(e))
            return {'error': str(e), 'scan_id': scan_id}, 500

        result['scan_id'] = scan_id
        result['threshold_distance'] = threshold_distance

        emit_complete(scan_id, {
            'scan_id': scan_id,
            'processed': result.get('processed', 0),
            'similarities_found': result.get('similarities_found', 0),
            'elapsed': result.get('elapsed', 0),
            'stopped': result.get('stopped', False),
        })

        print(f"[Phase 2 API] DONE scan_id={scan_id} "
              f"processed={result['processed']} edges={result['similarities_found']} "
              f"stopped={result['stopped']} elapsed={result['elapsed']:.1f}s")
        return result


@ns.route('/phase2/stop')
class Phase2StopResource(Resource):
    def post(self):
        print("=" * 80)
        print("[Phase 2 API] STOP request received")
        wf = get_workflow()
        print(f"[Phase 2 API] workflow id={id(wf)} pre-stop "
              f"stop_event={wf._stop_event.is_set()}")
        wf.set_stop()
        print(f"[Phase 2 API] workflow id={id(wf)} post-stop "
              f"stop_event={wf._stop_event.is_set()}")
        print("=" * 80)
        return {'message': 'Phase 2 stop signal sent'}


# ---------------------------------------------------------------------------
# /phase2.5/materialize — materialize duplicate groups + group stats
# ---------------------------------------------------------------------------
#
# Request body (all optional):
#   {
#     "threshold_percent":  80,            # 80/90/95/100
#     "same_folder_filter": true,          # default true
#     "scan_id":            "vphase25-..."
#   }
#
# Response (HTTP 200, even on stop):
#   {
#     "groups_count":        int,
#     "members_count":       int,
#     "whitelisted_dropped": int,
#     "threshold_percent":   int,
#     "same_folder_filter":  bool,
#     "elapsed":             float,
#     "stopped":             bool,
#     "scan_id":             "vphase25-..."
#   }
# ---------------------------------------------------------------------------

@ns.route('/phase2.5/materialize')
class Phase25MaterializeResource(Resource):
    def post(self):
        data = request.json or {}
        threshold_percent = int(data.get('threshold_percent', 80))
        same_folder_filter = bool(data.get('same_folder_filter', True))
        scan_id = data.get('scan_id') or f"vphase25-{uuid.uuid4().hex[:8]}"

        print("=" * 80)
        print(f"[Phase 2.5 API] START scan_id={scan_id}, "
              f"threshold={threshold_percent}%, same_folder_filter={same_folder_filter}")
        print(f"[Phase 2.5 API] DEBUG: request body = {data}")
        print("=" * 80)

        def cb(current, total, message):
            print(f"[Phase 2.5 API] WS emit → vscan:{scan_id}:progress [{current}/{total}] {message}")
            emit_progress(scan_id, current, total, message)

        try:
            wf = get_workflow()
            result = wf.phase2_5_materialize_groups(
                threshold_percent=threshold_percent,
                same_folder_filter=same_folder_filter,
                progress_callback=cb,
            )
        except InterruptedError as e:
            emit_error(scan_id, str(e))
            return {'error': 'stopped', 'message': str(e), 'scan_id': scan_id}, 499
        except Exception as e:
            import traceback; traceback.print_exc()
            emit_error(scan_id, str(e))
            return {'error': str(e), 'scan_id': scan_id}, 500

        result['scan_id'] = scan_id

        emit_complete(scan_id, {
            'scan_id': scan_id,
            'groups_count':        result.get('groups_count', 0),
            'members_count':       result.get('members_count', 0),
            'whitelisted_dropped': result.get('whitelisted_dropped', 0),
            'elapsed':             result.get('elapsed', 0),
            'stopped':             result.get('stopped', False),
        })

        print(f"[Phase 2.5 API] DONE scan_id={scan_id} "
              f"groups={result.get('groups_count', 0)} "
              f"members={result.get('members_count', 0)} "
              f"stopped={result.get('stopped', False)} "
              f"elapsed={result.get('elapsed', 0):.2f}s")
        return result


@ns.route('/phase2.5/stop')
class Phase25StopResource(Resource):
    def post(self):
        print("=" * 80)
        print("[Phase 2.5 API] STOP request received")
        wf = get_workflow()
        print(f"[Phase 2.5 API] workflow id={id(wf)} pre-stop "
              f"stop_event={wf._stop_event.is_set()}")
        wf.set_stop()
        print(f"[Phase 2.5 API] workflow id={id(wf)} post-stop "
              f"stop_event={wf._stop_event.is_set()}")
        print("=" * 80)
        return {'message': 'Phase 2.5 stop signal sent'}


# ---------------------------------------------------------------------------
# GET /phase2.5/meta — read current materialization metadata
# ---------------------------------------------------------------------------
#
# Response:
#   {
#     "meta": {
#       "materialized_threshold":           "80",
#       "materialized_at":                  "1714234567.89",
#       "materialized_same_folder_filter":  "1",
#       "materialized_group_count":         "123"
#     }
#   }
#
# Returns {meta: {}} if Phase 2.5 has never been run on this DB.
# ---------------------------------------------------------------------------

@ns.route('/phase2.5/meta')
class Phase25MetaResource(Resource):
    def get(self):
        try:
            meta = get_workflow().get_materialization_meta()
            return {'meta': meta}
        except Exception as e:
            return {'error': str(e)}, 500


# ---------------------------------------------------------------------------
# /phase3/get-duplicates — paginated read of materialized groups
# ---------------------------------------------------------------------------
#
# Strict mode:
#   - If materialization meta missing → HTTP 409 with error='no_materialization'
#   - If materialized threshold != requested → HTTP 409 with error='threshold_mismatch'
#   - Both responses include enough info for the UI to render a "click here
#     to re-materialize" affordance
#
# Request body (all optional):
#   {
#     "threshold_percent": 80,           # MUST match materialized threshold
#     "page":              1,            # 1-indexed; 0 = return all groups
#     "page_size":         100,
#     "sort_by":           "folder_dup_count",
#     "sort_order":        "desc",       # "asc" | "desc"
#   }
#
# `sort_by` whitelist (server-enforced):
#   representative_file_path, folder_dup_count, member_count,
#   max_filesize, min_filesize,
#   max_duration, min_duration,    (video-specific)
#   max_bitrate,  min_bitrate,     (video-specific)
#   max_mtime,    min_mtime
#
# Response (HTTP 200; 409 on conflict):
#   {
#     "groups":              [[member_dict, ...], ...],
#     "total_groups":        int,
#     "total_duplicates":    int,
#     "total_files_in_db":   int,
#     "current_page":        int,
#     "page_size":           int,
#     "total_pages":         int,
#     "elapsed":             float,
#     "stopped":             false,
#     "materialization_meta": {...},
#     "sort_by":             "folder_dup_count",
#     "sort_order":          "desc",
#     "scan_id":             "vphase3-..."
#   }
#
# Each member_dict carries:
#   id, filename, filesize, file_path, video_hash, duration, width, height,
#   fps, bitrate, vcodec, acodec, container, thumbnail_path, mtime,
#   folder_dup, folder_total, display_path, auto_delete_suggestion
# ---------------------------------------------------------------------------

@ns.route('/phase3/get-duplicates')
class Phase3GetDuplicatesResource(Resource):
    def post(self):
        data = request.json or {}
        threshold_percent = int(data.get('threshold_percent', 80))
        page = int(data.get('page', 1))
        page_size = int(data.get('page_size', 100))
        sort_by = data.get('sort_by') or 'folder_dup_count'
        sort_order = data.get('sort_order') or 'desc'

        scan_id = data.get('scan_id') or f"vphase3-{uuid.uuid4().hex[:8]}"

        # folder_paths from settings → drives display_path computation
        folder_paths = settings_manager.get_folder_paths()

        print(f"[Phase 3 API] scan_id={scan_id}, threshold={threshold_percent}%, "
              f"page={page}, page_size={page_size}, sort={sort_by} {sort_order}")
        print(f"[Phase 3 API] DEBUG: folder_paths_for_display={folder_paths}")

        def cb(current, total, message):
            print(f"[Phase 3 API] WS emit → vscan:{scan_id}:progress [{current}/{total}] {message}")
            emit_progress(scan_id, current, total, message)

        try:
            wf = get_workflow()
            result = wf.phase3_get_duplicates(
                threshold_percent=threshold_percent,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
                folder_paths=folder_paths,
                progress_callback=cb,
            )
        except InterruptedError as e:
            return {'error': 'stopped', 'message': str(e), 'scan_id': scan_id}, 499
        except Exception as e:
            import traceback; traceback.print_exc()
            return {'error': str(e), 'scan_id': scan_id}, 500

        result['scan_id'] = scan_id

        # Strict-mode error markers → HTTP 409
        err = result.get('error')
        if err in ('no_materialization', 'threshold_mismatch'):
            print(f"[Phase 3 API] {err}: {result.get('message')}")
            return result, 409

        print(f"[Phase 3 API] DONE scan_id={scan_id} "
              f"groups_on_page={len(result.get('groups', []))} "
              f"total_groups={result.get('total_groups', 0)} "
              f"elapsed={result.get('elapsed', 0) * 1000:.0f}ms")
        return result


@ns.route('/phase3/stop')
class Phase3StopResource(Resource):
    def post(self):
        print("=" * 80)
        print("[Phase 3 API] STOP request received")
        wf = get_workflow()
        wf.set_stop()
        print("[Phase 3 API] stop event set")
        print("=" * 80)
        return {'message': 'Phase 3 stop signal sent'}


# ===========================================================================
# /delete — move files (+companions) to delete target, clean DB, repair stats
# ===========================================================================
#
# Request:
#   { "files": ["/abs/path/1.mp4", "/abs/path/2.mp4"] }
#
# Behavior:
#   1. Pre-capture stats state for the to-be-deleted video_ids
#   2. For each file: move video + matching companion files (.srt, .nfo, ...)
#      to delete_target_path (mirroring the relative path under scan folder).
#      Collisions resolved via `_N` suffix.
#   3. DELETE FROM video_hashes WHERE id = ?  → CASCADE clears similarities
#      + duplicate_video_groups + whitelist memberships
#   4. Stats repair using the pre-captured state
#
# Response: { success, failed, errors, companions_moved, stats_repair }
# ===========================================================================

@ns.route('/delete')
class DeleteResource(Resource):
    def post(self):
        data = request.json or {}
        files = data.get('files') or []
        if not isinstance(files, list) or not files:
            return {'error': 'files (non-empty list) required'}, 400

        delete_target = settings_manager.get_delete_target_path()
        if not delete_target:
            return {'error': 'delete_target_path not configured'}, 400

        os.makedirs(delete_target, exist_ok=True)
        companion_exts = settings_manager.get_companion_extensions()
        folder_paths = settings_manager.get_folder_paths()
        abs_folder_paths = [os.path.abspath(p) for p in folder_paths if p]
        allowed_roots = _get_allowed_scan_roots()

        print("=" * 80)
        print(f"[Delete API] files={len(files)}, delete_target={delete_target}, "
              f"companion_exts={companion_exts}")
        print("=" * 80)

        # Filter incoming files: must be video-extension AND inside a scan root
        # AND not the delete_target itself (we're moving TO delete_target).
        # A rejection here is a validation error, not a runtime failure.
        rejected: list = []
        safe_files: list = []
        for fp in files:
            if not fp or not isinstance(fp, str):
                rejected.append({'file': str(fp), 'reason': 'invalid path'})
                continue
            if fp.startswith('\\\\') or fp.startswith('//'):
                rejected.append({'file': fp, 'reason': 'UNC path not allowed'})
                continue
            if not fp.lower().endswith(VIDEO_EXTS):
                rejected.append({'file': fp, 'reason': 'not a supported video extension'})
                continue
            if not _is_path_inside_allowed_scope(fp, allowed_roots):
                rejected.append({'file': fp, 'reason': 'path not inside any configured scan folder'})
                continue
            safe_files.append(fp)

        if rejected and not safe_files:
            return {
                'error': 'All files rejected by path validation',
                'rejected': rejected,
            }, 400
        files = safe_files

        # --- Step 1: resolve video_ids + pre-capture stats ---
        wf = get_workflow()
        conn = wf._get_connection()
        cur = conn.cursor()

        abs_files = [os.path.abspath(f) for f in files]
        video_ids: list = []
        BATCH = 900
        for i in range(0, len(abs_files), BATCH):
            chunk = abs_files[i:i + BATCH]
            ph = ','.join('?' * len(chunk))
            cur.execute(
                f"SELECT id FROM video_hashes WHERE file_path IN ({ph})",
                chunk,
            )
            video_ids.extend(r[0] for r in cur.fetchall())

        try:
            affected = wf.stats_collect_affected_before_mutation(video_ids)
        except Exception as e:
            print(f"[Delete API] WARN: pre-capture failed: {e}")
            affected = None

        # --- Step 2: move files (+ companions) ---
        success = 0
        failed = 0
        errors: list = []
        companions_moved_total = 0

        def find_scan_root(abs_file: str):
            """Find the configured scan-folder that contains this file.

            Returns None if the file is NOT under any configured scan root
            (the caller should skip such files rather than silently move
            them into delete_target/<basename>, which was a pre-fix
            vulnerability enabling arbitrary file moves).
            """
            for sf in abs_folder_paths:
                if abs_file == sf or abs_file.startswith(sf + os.sep):
                    return sf
            return None

        for fp in files:
            if not os.path.isfile(fp):
                errors.append(f'File not found: {fp}')
                failed += 1
                continue
            try:
                fp_abs = os.path.abspath(fp)
                root = find_scan_root(fp_abs)
                if root is None:
                    errors.append(f'File not under any configured scan folder: {fp_abs}')
                    failed += 1
                    continue
                try:
                    rel = os.path.relpath(fp_abs, root)
                except ValueError:
                    rel = os.path.basename(fp_abs)
                dest_path = os.path.join(delete_target, rel)

                result = move_with_companions(fp_abs, dest_path, companion_exts)
                success += 1
                companions_moved_total += len(result.get('companions_moved', []))
                errors.extend(result.get('errors', []))
                print(f"[Delete API] moved {fp_abs} → {result['video_moved_to']} "
                      f"(+{len(result['companions_moved'])} companions)")
            except Exception as e:
                failed += 1
                errors.append(f'Move failed for {fp}: {e}')
                print(f"[Delete API] FAILED move {fp}: {e}")

        # --- Step 3: DELETE FROM video_hashes (CASCADE) ---
        if video_ids:
            try:
                for i in range(0, len(video_ids), BATCH):
                    chunk = video_ids[i:i + BATCH]
                    ph = ','.join('?' * len(chunk))
                    cur.execute(
                        f"DELETE FROM video_hashes WHERE id IN ({ph})",
                        chunk,
                    )
                conn.commit()
                print(f"[Delete API] removed {len(video_ids)} video_hashes rows (CASCADE)")
            except Exception as e:
                conn.rollback()
                print(f"[Delete API] DB DELETE failed after file moves: {e}")
                import traceback; traceback.print_exc()
                errors.append(f'DB DELETE failed (files were still moved): {e}')

        # --- Step 4: stats repair ---
        repair_summary = None
        if affected:
            try:
                repair_summary = wf.stats_repair_after_mutation(
                    affected, remove_from_groups=False,
                )
            except Exception as e:
                print(f"[Delete API] WARN: stats repair failed: {e}")
                import traceback; traceback.print_exc()
                errors.append(f'stats repair failed: {e}')

        print(f"[Delete API] DONE: success={success}, failed={failed}, "
              f"companions_moved={companions_moved_total}")
        return {
            'success':            success,
            'failed':             failed,
            'errors':             errors,
            'rejected':           rejected,
            'companions_moved':   companions_moved_total,
            'stats_repair':       repair_summary,
        }


# ===========================================================================
# /whitelist — individual + group whitelist management
# ===========================================================================

@ns.route('/whitelist')
class WhitelistResource(Resource):
    def get(self):
        """Return all whitelist groups + individual whitelisted videos."""
        try:
            wf = get_workflow()
            cache = VideoHashCache(str(wf.db_path))
            return {
                'whitelist_groups':   cache.get_whitelist_groups(),
                'whitelist':          cache.get_whitelist(),
            }
        except Exception as e:
            return {'error': str(e)}, 500

    def post(self):
        """Add a duplicate group to the whitelist.

        Request: { "video_ids": [123, 456, ...] }  (length ≥ 2)
        """
        data = request.json or {}
        video_ids = data.get('video_ids') or []
        if not isinstance(video_ids, list) or len(video_ids) < 2:
            return {'error': 'video_ids (list with ≥ 2 entries) required'}, 400

        try:
            wf = get_workflow()
            affected = wf.stats_collect_affected_before_mutation(video_ids)

            cache = VideoHashCache(str(wf.db_path))
            added_gid = cache.add_group_to_whitelist(video_ids)

            # Compensating rollback: if stats_repair fails, remove the
            # just-added whitelist row so the DB isn't left in a state
            # where the group is whitelisted but duplicate_video_groups
            # still holds those video_ids (Tier-2 review D-25).
            try:
                repair = wf.stats_repair_after_mutation(
                    affected, remove_from_groups=True,
                )
            except Exception as repair_err:
                try:
                    cache.remove_whitelist_group(int(added_gid))
                    print(f"[Whitelist Add] rolled back group {added_gid} after stats_repair failure")
                except Exception as unwind_err:
                    print(f"[Whitelist Add] WARNING: could not roll back group "
                          f"{added_gid}: {unwind_err}")
                raise repair_err

            print(f"[Whitelist Add] video_ids={len(video_ids)}, repair={repair}")
            return {
                'message': 'Added group to whitelist',
                'stats_repair': repair,
            }
        except ValueError as e:
            return {'error': str(e)}, 400
        except Exception as e:
            import traceback; traceback.print_exc()
            return {'error': str(e)}, 500

    def delete(self):
        """Remove a whitelist group by id.

        Query: ?group_id=N
        """
        group_id = request.args.get('group_id')
        if not group_id:
            return {'error': 'group_id (query param) required'}, 400
        try:
            wf = get_workflow()
            cache = VideoHashCache(str(wf.db_path))
            cache.remove_whitelist_group(int(group_id))
            return {'message': f'Removed whitelist group {group_id}'}
        except ValueError:
            return {'error': 'group_id must be an integer'}, 400
        except Exception as e:
            return {'error': str(e)}, 500


@ns.route('/whitelist/cleanup')
class WhitelistCleanupResource(Resource):
    def post(self):
        """Remove whitelist groups that fell below 2 members (defensive)."""
        try:
            wf = get_workflow()
            cache = VideoHashCache(str(wf.db_path))
            removed = cache.cleanup_whitelist_groups()
            return {
                'removed_count': removed,
                'message': f'Cleaned up {removed} invalid whitelist groups',
            }
        except Exception as e:
            import traceback; traceback.print_exc()
            return {'error': str(e)}, 500


# ===========================================================================
# S7.5.2 / S7.5.3: Whitelist preview by path + bulk add groups
# ===========================================================================

@ns.route('/whitelist/preview-by-path')
class WhitelistPreviewByPathResource(Resource):
    def post(self):
        """Preview which materialized duplicate groups have ≥1 member under
        the given folder (recursive). Returns the full groups (all members)
        so the UI can show the exact deletion scope before the user confirms.

        Request:
          { "deep_path": "E:\\folder" }

        Response:
          {
            "deep_path":      "<abs>",
            "matched_groups": int,
            "matched_files":  int,
            "groups":         [[member_dict, ...], ...],
          }
        """
        try:
            data = request.json or {}
            deep_path = (data.get('deep_path') or '').strip()
            if not deep_path:
                return {'error': "'deep_path' required"}, 400
            if deep_path.startswith('\\\\') or deep_path.startswith('//'):
                return {'error': 'UNC paths are not allowed'}, 400

            deep_path_abs = os.path.abspath(deep_path)

            # Round-2 review: scope check missing here. An authenticated
            # caller could probe arbitrary host paths and infer from the
            # returned counts whether those paths appear in the video DB.
            allowed_roots = _get_allowed_scan_roots()
            if not _is_path_inside_allowed_scope(deep_path_abs, allowed_roots):
                return {'error': 'deep_path is not inside any allowed scope'}, 403

            # Windows filesystems are case-insensitive; the DB stores whatever
            # case the FS/os.walk gave us, which typically preserves user's
            # first-time capitalization. If the caller queries in a different
            # case (paste from cmd → different case than Explorer), the plain
            # string startswith below would miss everything. On Windows, use
            # os.path.normcase to normalize both sides. Round-2 review D-low.
            is_win = sys.platform.startswith('win')
            deep_key = os.path.normcase(deep_path_abs.rstrip(os.sep)) if is_win \
                        else deep_path_abs.rstrip(os.sep)
            deep_prefix = deep_key + os.sep

            wf = get_workflow()
            conn = wf._get_connection()
            cur = conn.cursor()

            # Step 1: find distinct group_ids where any member lives under
            # deep_path (exact match OR any subdirectory). Push the prefix
            # filter into SQL to avoid pulling the entire duplicate-groups
            # join through the sqlite cursor + Python for every preview call
            # (Round-2 review D-high — perf on large DBs). Use LIKE with
            # ESCAPE so `_` / `%` / `\` inside the user's path are literal.
            like_stem = (
                deep_path_abs.rstrip(os.sep)
                .replace('\\', '\\\\')
                .replace('%', '\\%')
                .replace('_', '\\_')
            )
            like_prefix_pattern = like_stem + os.sep + '%'
            cur.execute('''
                SELECT DISTINCT dg.group_id, v.dir_path
                FROM duplicate_video_groups dg
                JOIN video_hashes v ON dg.video_id = v.id
                WHERE v.dir_path = ? OR v.dir_path LIKE ? ESCAPE '\\'
            ''', (deep_path_abs.rstrip(os.sep), like_prefix_pattern))
            rows = cur.fetchall()
            # Defense-in-depth Python-side re-check with normcase.
            matched_group_ids = set()
            for gid, dp in rows:
                if not dp:
                    continue
                dp_key = os.path.normcase(dp) if is_win else dp
                if dp_key == deep_key or dp_key.startswith(deep_prefix):
                    matched_group_ids.add(gid)

            if not matched_group_ids:
                return {
                    'deep_path': deep_path_abs,
                    'matched_groups': 0,
                    'matched_files': 0,
                    'groups': [],
                }

            # Step 2: fetch ALL members of those groups (not just the ones
            # in deep_path — whole group is going to be whitelisted).
            groups_dict: dict = {gid: [] for gid in matched_group_ids}
            BATCH = 900
            group_ids_list = list(matched_group_ids)
            for i in range(0, len(group_ids_list), BATCH):
                chunk = group_ids_list[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(f'''
                    SELECT dg.group_id, v.id, v.filename, v.filesize, v.file_path,
                           v.video_hash, v.duration, v.width, v.height, v.vcodec
                    FROM duplicate_video_groups dg
                    JOIN video_hashes v ON dg.video_id = v.id
                    WHERE dg.group_id IN ({ph})
                ''', chunk)
                for gid, vid, filename, filesize, fp, vh, dur, w, h, vc in cur.fetchall():
                    groups_dict[gid].append({
                        'id':         vid,
                        'filename':   filename,
                        'filesize':   filesize,
                        'file_path':  fp,
                        'video_hash': vh,
                        'duration':   dur,
                        'width':      w,
                        'height':     h,
                        'vcodec':     vc,
                    })

            groups = [groups_dict[gid] for gid in matched_group_ids if groups_dict[gid]]
            matched_files = sum(len(g) for g in groups)

            print(f"[Whitelist Preview by Path] path={deep_path_abs}, "
                  f"matched_groups={len(groups)}, matched_files={matched_files}")
            return {
                'deep_path':      deep_path_abs,
                'matched_groups': len(groups),
                'matched_files':  matched_files,
                'groups':         groups,
            }
        except Exception as e:
            import traceback; traceback.print_exc()
            return {'error': str(e)}, 500


@ns.route('/whitelist/bulk-add-groups')
class WhitelistBulkAddGroupsResource(Resource):
    def post(self):
        """Bulk-add multiple groups to the whitelist. Runs ONE stats_repair
        at the end so the cost scales with unique videos, not group count.

        Request:
          { "groups": [[1, 2, 3], [4, 5], [6, 7, 8]] }

        Response:
          {
            "added_groups":   int,
            "skipped_groups": int,
            "video_count":    int,
            "stats_repair":   { ... },
          }
        """
        try:
            data = request.json or {}
            groups = data.get('groups')
            if not isinstance(groups, list) or not groups:
                return {'error': "'groups' (non-empty list) required"}, 400

            # Round-2 review: strict validation — bool is a subclass of int
            # in Python, so `[True, False]` used to pass; also filter negatives
            # and dedupe within a group so `[7, 7]` doesn't become a bogus
            # "group of 1 physical video".
            valid_groups: list = []
            for g in groups:
                if not isinstance(g, list):
                    continue
                cleaned: list = []
                seen: set = set()
                for x in g:
                    if isinstance(x, bool):       # reject bool (subclass of int)
                        continue
                    if not isinstance(x, int):
                        continue
                    if x <= 0:                     # reject non-positive ids
                        continue
                    if x in seen:                  # dedupe within a group
                        continue
                    seen.add(x)
                    cleaned.append(x)
                if len(cleaned) >= 2:
                    valid_groups.append(cleaned)
            skipped = len(groups) - len(valid_groups)
            if not valid_groups:
                return {
                    'error': 'No valid groups (each needs ≥ 2 distinct positive int video_ids)',
                }, 400

            all_video_ids = list({vid for g in valid_groups for vid in g})

            wf = get_workflow()
            affected = wf.stats_collect_affected_before_mutation(all_video_ids)

            cache = VideoHashCache(str(wf.db_path))
            added = 0
            added_gids: list = []   # capture returned ids for compensating rollback
            failed_gids: list = []
            succeeded_video_ids: set = set()
            for g in valid_groups:
                try:
                    gid = cache.add_group_to_whitelist(g)
                    added_gids.append(int(gid))
                    added += 1
                    succeeded_video_ids.update(g)
                except Exception as e:
                    print(f"[Whitelist Bulk] group {g} failed: {e}")
                    failed_gids.append(g)
                    skipped += 1

            # Round-2 review: only include succeeded ids in the stats-repair
            # affected set — otherwise ids from FAILED groups would still be
            # stripped from duplicate_video_groups by remove_from_groups=True.
            filtered_affected = {
                'video_ids':           [v for v in (affected.get('video_ids') or [])
                                        if v in succeeded_video_ids],
                'affected_groups':     affected.get('affected_groups', []),
                'old_primary_folders': affected.get('old_primary_folders', []),
                'affected_folders':    affected.get('affected_folders', []),
            }

            # Single stats repair for all affected groups
            try:
                repair = wf.stats_repair_after_mutation(
                    filtered_affected, remove_from_groups=True,
                )
            except Exception as repair_err:
                # Round-2 review: compensating rollback. Unwind each
                # successfully-added whitelist group so the DB isn't left
                # in a state where groups are whitelisted but
                # duplicate_video_groups still holds those video_ids.
                import traceback; traceback.print_exc()
                unwind_errors: list = []
                for unwind_gid in added_gids:
                    try:
                        cache.remove_whitelist_group(unwind_gid)
                    except Exception as ue:
                        unwind_errors.append(f'{unwind_gid}: {ue}')
                return {
                    'error': f'Bulk whitelist rolled back after stats_repair failure: {repair_err}',
                    'rolled_back_groups': len(added_gids),
                    'unwind_errors':      unwind_errors,
                    'failed_groups':      failed_gids,
                }, 500

            print(f"[Whitelist Bulk] added={added}, skipped={skipped}, "
                  f"unique_videos={len(all_video_ids)}, repair={repair}")
            return {
                'added_groups':   added,
                'skipped_groups': skipped,
                'failed_groups':  failed_gids,   # surface for retry (Round-2 D-low)
                'video_count':    len(all_video_ids),
                'stats_repair':   repair,
            }
        except Exception as e:
            import traceback; traceback.print_exc()
            return {'error': str(e)}, 500


# ===========================================================================
# S6: Compare folders (scoped) / Compare-all (cluster-based)
# ===========================================================================

@ns.route('/compare-folders')
class CompareFoldersResource(Resource):
    def post(self):
        """FOCUSED pairwise comparison of just the given folders.

        Reuses existing hashes from the DB; computes new hashes only for
        files on disk not yet in the DB. Never deletes any video_hashes
        rows; never touches data outside the scope. After compare, runs
        Phase 2.5 so Phase 3 immediately reflects the new edges.

        Request:
          {
            "folders":            ["E:\\path\\1", "E:\\path\\2"],
            "threshold_percent":  80    // optional, default 80
          }
        """
        try:
            data = request.json or {}
            folders = data.get('folders') or []
            threshold_percent = int(data.get('threshold_percent', 80))
            # Clamp threshold_percent to a sane range (Round-2 review D-low):
            # negatives make ui_distance > VIDEO_HASH_BITS (every pair matches);
            # > 100 makes it negative (no pair matches).
            if not 50 <= threshold_percent <= 100:
                return {
                    'error': f'threshold_percent must be in [50, 100], got {threshold_percent}',
                }, 400

            if not isinstance(folders, list) or not folders:
                return {'error': "Missing or invalid 'folders' (non-empty list required)"}, 400

            # Enforce path safety on each folder — must be inside allowed scope.
            allowed_roots = _get_allowed_scan_roots()
            for f in folders:
                if not isinstance(f, str) or not f:
                    return {'error': f'Invalid folder entry: {f!r}'}, 400
                if f.startswith('\\\\') or f.startswith('//'):
                    return {'error': f'UNC paths not allowed: {f}'}, 400
                if not _is_path_inside_allowed_scope(f, allowed_roots):
                    return {
                        'error': f'Folder {f!r} is not inside any configured scan folder',
                    }, 403

            scan_id = f"vcompare-{uuid.uuid4().hex[:8]}"

            def cb(current, total, message):
                print(f"[Compare Folders API] WS emit → vscan:{scan_id}:progress [{current}/{total}] {message}")
                emit_progress(scan_id, current, total, message)

            from .video_hash_cache import VIDEO_HASH_BITS
            # Cover at least 80% breadth so Phase 2.5 can filter to tighter UI %.
            ui_distance = int(VIDEO_HASH_BITS * (100 - threshold_percent) / 100)
            min_coverage = int(VIDEO_HASH_BITS * 0.2)
            compare_distance = max(ui_distance, min_coverage)

            print("=" * 80)
            print(f"[Compare Folders API] START scan_id={scan_id}")
            print(f"  folders             : {folders}")
            print(f"  threshold_percent   : {threshold_percent}%")
            print(f"  compare_distance    : ≤ {compare_distance}")
            print("=" * 80)

            try:
                wf = get_workflow()
                compare_result = wf.compare_folders_focused(
                    folders=folders,
                    threshold_distance=compare_distance,
                    progress_callback=cb,
                )

                print(f"[Compare Folders API] Triggering Phase 2.5 at {threshold_percent}%")
                phase25_result = wf.phase2_5_materialize_groups(
                    threshold_percent=threshold_percent,
                    same_folder_filter=True,
                    progress_callback=cb,
                )
            except InterruptedError as e:
                # User stop signal — treat as HTTP 499 (per project convention).
                emit_error(scan_id, str(e))
                return {'error': 'stopped', 'message': str(e), 'scan_id': scan_id}, 499
            except Exception as e:
                # Round-2 review: previously the outer handler returned 500
                # without emit_error, hanging the WebSocket subscriber.
                emit_error(scan_id, str(e))
                import traceback; traceback.print_exc()
                return {'error': str(e), 'scan_id': scan_id}, 500

            emit_complete(scan_id, {
                'scan_id':               scan_id,
                'new_phashes_computed':  compare_result.get('new_phashes_computed', 0),
                'pairs_found':           compare_result.get('pairs_found', 0),
                'new_edges':             compare_result.get('new_similarities_inserted', 0),
                'phase25_groups':        phase25_result.get('groups_count', 0),
            })
            return {
                'scan_id': scan_id,
                'compare': compare_result,
                'phase25': phase25_result,
            }
        except Exception as e:
            import traceback; traceback.print_exc()
            return {'error': str(e)}, 500


@ns.route('/compare-folders-all')
class CompareFoldersAllResource(Resource):
    def post(self):
        """Global Compare Folder — clusters folders that share a group,
        then runs compare_folders_focused ONCE per cluster.

        Skips clusters with ≥ 4 folders (typically noise: black-screen or
        blank-cover thumbnails linking unrelated folders into one big
        cluster where exhaustive comparison is wasted work).

        Request body (optional):
          { "threshold_percent": 80 }
        """
        scan_id = None
        try:
            data = request.json or {}
            threshold_percent = int(data.get('threshold_percent', 80))
            # Clamp threshold_percent — Round-2 review D-low.
            if not 50 <= threshold_percent <= 100:
                return {
                    'error': f'threshold_percent must be in [50, 100], got {threshold_percent}',
                }, 400

            scan_id = f"vcompareall-{uuid.uuid4().hex[:8]}"

            def cb(current, total, message):
                print(f"[Compare All API] WS emit → vscan:{scan_id}:progress [{current}/{total}] {message}")
                emit_progress(scan_id, current, total, message)

            wf = get_workflow()
            conn = wf._get_connection()
            cur = conn.cursor()

            # Step 1: pull every (group_id, dir_path) pair
            cur.execute('''
                SELECT dg.group_id, v.dir_path
                FROM duplicate_video_groups dg
                JOIN video_hashes v ON dg.video_id = v.id
                WHERE v.dir_path IS NOT NULL
            ''')
            rows = cur.fetchall()

            if not rows:
                return {
                    'scan_id':        scan_id,
                    'clusters_count': 0,
                    'folders_count':  0,
                    'message':        'No folders to compare (no materialized groups).',
                }

            # Step 2: build {folder: {gid}} and {gid: {folder}}
            groups_per_folder: dict = {}
            folders_per_group: dict = {}
            for gid, dp in rows:
                groups_per_folder.setdefault(dp, set()).add(gid)
                folders_per_group.setdefault(gid, set()).add(dp)
            all_folders = list(groups_per_folder.keys())

            # Step 3: BFS to find connected components in the folder graph
            visited: set = set()
            clusters: list = []
            for start in all_folders:
                if start in visited:
                    continue
                cluster: set = set()
                queue: list = [start]
                visited.add(start)
                while queue:
                    f = queue.pop(0)
                    cluster.add(f)
                    for gid in groups_per_folder.get(f, ()):
                        for other_f in folders_per_group.get(gid, ()):
                            if other_f not in visited:
                                visited.add(other_f)
                                queue.append(other_f)
                clusters.append(sorted(cluster))

            cluster_sizes = sorted((len(c) for c in clusters), reverse=True)
            print("=" * 80)
            print(f"[Compare All] START scan_id={scan_id}")
            print(f"  total folders        : {len(all_folders)}")
            print(f"  connected clusters   : {len(clusters)}")
            print(f"  largest cluster sizes: {cluster_sizes[:10]}")
            print(f"  threshold            : {threshold_percent}%")
            print("=" * 80)

            from .video_hash_cache import VIDEO_HASH_BITS
            ui_distance = int(VIDEO_HASH_BITS * (100 - threshold_percent) / 100)
            compare_distance = max(ui_distance, int(VIDEO_HASH_BITS * 0.2))

            # Step 4: run per-cluster. Skip large clusters (image-version §12).
            aggregate = {
                'scope_total': 0,
                'new_phashes_computed': 0,
                'errors': 0,
                'pairs_found': 0,
                'new_similarities_inserted': 0,
                'elapsed': 0.0,
            }
            cluster_errors: list = []
            skipped_clusters = 0
            skipped_folders = 0
            MAX_CLUSTER_FOLDERS = 4
            for idx, cluster in enumerate(clusters):
                if len(cluster) >= MAX_CLUSTER_FOLDERS:
                    skipped_clusters += 1
                    skipped_folders += len(cluster)
                    print(f"[Compare All] SKIP cluster {idx + 1}/{len(clusters)} "
                          f"({len(cluster)} folders ≥ {MAX_CLUSTER_FOLDERS}) — likely noise")
                    continue

                pct = int(80 * idx / max(1, len(clusters)))
                cb(pct, 100, f"Cluster {idx + 1}/{len(clusters)} ({len(cluster)} folders)")
                # Round-2 review: wrap per-cluster call in try/except so a
                # single flaky video doesn't discard the entire batch. Only
                # re-raise on InterruptedError (user stop).
                try:
                    cr = wf.compare_folders_focused(
                        folders=cluster,
                        threshold_distance=compare_distance,
                        progress_callback=None,
                    )
                except InterruptedError:
                    raise
                except Exception as cluster_err:
                    cluster_errors.append({
                        'cluster_index': idx,
                        'folders':       cluster[:5] + (['…'] if len(cluster) > 5 else []),
                        'error':         str(cluster_err),
                    })
                    print(f"[Compare All] cluster {idx + 1} FAILED (recorded, continuing): {cluster_err}")
                    import traceback; traceback.print_exc()
                    continue

                if cr:
                    aggregate['scope_total']               += cr.get('scope_total', 0) or 0
                    aggregate['new_phashes_computed']      += cr.get('new_phashes_computed', 0) or 0
                    aggregate['errors']                    += cr.get('errors', 0) or 0
                    aggregate['pairs_found']               += cr.get('pairs_found', 0) or 0
                    aggregate['new_similarities_inserted'] += cr.get('new_similarities_inserted', 0) or 0
                    aggregate['elapsed']                   += cr.get('elapsed', 0.0) or 0.0

            # Step 5: single Phase 2.5 rematerialization — ALWAYS runs so
            # already-inserted edges become visible, even if some clusters failed.
            cb(85, 100, "Rematerializing groups (Phase 2.5)")
            phase25_result = wf.phase2_5_materialize_groups(
                threshold_percent=threshold_percent,
                same_folder_filter=True,
                progress_callback=cb,
            )

            print("=" * 80)
            print(f"[Compare All] DONE scan_id={scan_id}")
            print(f"  clusters processed: {len(clusters) - skipped_clusters - len(cluster_errors)}")
            print(f"  clusters failed   : {len(cluster_errors)}")
            print(f"  aggregate         : {aggregate}")
            print("=" * 80)

            emit_complete(scan_id, {
                'scan_id':                    scan_id,
                'clusters_count':             len(clusters),
                'clusters_skipped':           skipped_clusters,
                'clusters_failed':            len(cluster_errors),
                'new_edges':                  aggregate['new_similarities_inserted'],
                'phase25_groups':             phase25_result.get('groups_count', 0),
            })

            return {
                'scan_id':                     scan_id,
                'clusters_count':              len(clusters),
                'clusters_skipped':            skipped_clusters,
                'clusters_failed':             len(cluster_errors),
                'cluster_errors':              cluster_errors,
                'folders_in_skipped_clusters': skipped_folders,
                'folders_count':               len(all_folders),
                'largest_cluster_sizes':       cluster_sizes[:10],
                'compare':                     aggregate,
                'phase25':                     phase25_result,
            }
        except InterruptedError as e:
            if scan_id:
                emit_error(scan_id, str(e))
            return {'error': 'stopped', 'message': str(e), 'scan_id': scan_id}, 499
        except Exception as e:
            # Round-2 review: previously emit_error was missing here, hanging
            # WebSocket subscribers who saw progress but never saw :error or
            # :complete.
            if scan_id:
                emit_error(scan_id, str(e))
            import traceback; traceback.print_exc()
            return {'error': str(e)}, 500


# ===========================================================================
# S7.2: Replace / Replace-batch (size=2 groups only, companion rename)
# ===========================================================================

def _find_scan_root_for_file(abs_file: str, abs_folder_paths):
    """Return the configured scan folder containing `abs_file`, or None.

    Uses realpath on both sides so a scan folder configured via symlink
    still matches a file whose abspath resolves through the symlink target.
    Round-2 review D-low: previously plain-abspath prefix could miss.
    """
    try:
        af_real = os.path.realpath(abs_file).rstrip(os.sep)
    except Exception:
        af_real = abs_file.rstrip(os.sep)
    for sf in abs_folder_paths:
        try:
            sf_real = os.path.realpath(sf).rstrip(os.sep)
        except Exception:
            sf_real = sf.rstrip(os.sep)
        if af_real == sf_real or af_real.startswith(sf_real + os.sep):
            # Return the ORIGINAL (non-realpath'd) scan folder — callers rely
            # on the returned root to compute relpath against the caller's
            # configured folder_paths, not the resolved symlink target.
            return sf
        # Also match the plain-abspath prefix as a fallback
        if abs_file == sf or abs_file.startswith(sf + os.sep):
            return sf
    return None


def _move_with_collision(src: str, dest: str) -> str:
    """Move src to dest, appending _1, _2... if dest exists. Returns final dest."""
    import shutil
    if os.path.exists(dest):
        stem, ext = os.path.splitext(dest)
        counter = 1
        while os.path.exists(dest):
            dest = f"{stem}_{counter}{ext}"
            counter += 1
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    shutil.move(src, dest)
    return dest


def _copy_with_collision(src: str, dest: str) -> str:
    """Copy src to dest, appending _N if dest exists. Returns final dest."""
    import shutil
    if os.path.exists(dest):
        stem, ext = os.path.splitext(dest)
        counter = 1
        while os.path.exists(dest):
            dest = f"{stem}_{counter}{ext}"
            counter += 1
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    shutil.copy2(src, dest)
    return dest


@ns.route('/replace')
class ReplaceResource(Resource):
    def post(self):
        """Replace op: within a size-2 group, keep the selected video,
        move the OTHER to delete_target (with companions), and move the
        selected video into the ANCHOR's directory + anchor basename +
        selected's own extension. Companions of the selected video are
        renamed to match too.

        Request:
          {
            "selected_file_path": "...",
            "anchor_file_path":   "...",
            "group_file_paths":   ["...", "..."]   // must be size 2
          }
        """
        import shutil
        from .companion_files import find_companion_files, move_with_companions

        try:
            data = request.json or {}
            selected_raw = (data.get('selected_file_path') or '').strip()
            anchor_raw   = (data.get('anchor_file_path')   or '').strip()
            group_paths_raw = data.get('group_file_paths') or []

            if not selected_raw or not anchor_raw or not group_paths_raw:
                return {'error': 'Missing selected_file_path / anchor_file_path / group_file_paths'}, 400
            if not isinstance(group_paths_raw, list):
                return {'error': 'group_file_paths must be a list'}, 400
            if len(group_paths_raw) != 2:
                return {'error': 'Replace is only allowed when the group has exactly 2 videos'}, 400

            sel_abs    = os.path.abspath(selected_raw)
            anchor_abs = os.path.abspath(anchor_raw)
            group_abs  = [os.path.abspath(p) for p in group_paths_raw]

            if sel_abs not in group_abs:
                return {'error': 'selected_file_path must appear in group_file_paths'}, 400
            if anchor_abs not in group_abs:
                return {'error': 'anchor_file_path must appear in group_file_paths'}, 400

            del_target = settings_manager.get_delete_target_path()
            if not del_target:
                return {'error': 'Delete target path not configured'}, 400
            os.makedirs(del_target, exist_ok=True)

            folder_paths = settings_manager.get_folder_paths() or []
            abs_folder_paths = [os.path.abspath(p) for p in folder_paths]
            companion_exts = settings_manager.get_companion_extensions()

            # Scope safety: both endpoints of the group must live under a scan root
            allowed_roots = _get_allowed_scan_roots()
            for g in group_abs:
                if not _is_path_inside_allowed_scope(g, allowed_roots):
                    return {'error': f'Path not inside allowed scope: {g}'}, 403

            # ---- Step 1: resolve video_ids + pre-capture stats ----
            wf = get_workflow()
            conn = wf._get_connection()
            cur = conn.cursor()
            id_by_path: dict = {}
            ph = ','.join('?' * len(group_abs))
            cur.execute(
                f"SELECT id, file_path FROM video_hashes WHERE file_path IN ({ph})",
                group_abs,
            )
            for vid, fp in cur.fetchall():
                id_by_path[fp] = vid

            selected_id = id_by_path.get(sel_abs)
            to_delete_paths = [p for p in group_abs if p != sel_abs]
            to_delete_ids = [id_by_path[p] for p in to_delete_paths if p in id_by_path]

            ids_for_capture = list(to_delete_ids)
            do_rename = (sel_abs != anchor_abs)
            if selected_id is not None and do_rename:
                ids_for_capture.append(selected_id)

            try:
                affected_capture = wf.stats_collect_affected_before_mutation(ids_for_capture)
            except Exception as e:
                print(f"[Replace] WARN: pre-capture failed: {e}")
                affected_capture = None

            # ---- Step 2: COPY selected → anchor slot (rename), plus companions.
            # Round-2 review: previously this ran AFTER moving the non-selected
            # video to trash, so if the copy failed (ENOSPC, EPERM, cross-drive)
            # the anchor was already destroyed. Copy first — non-destructive.
            new_selected_path = None
            renamed_to = None
            errors: list = []
            copied_companions: list = []  # tracked so we can attempt rollback if needed
            if do_rename:
                try:
                    if not os.path.exists(sel_abs):
                        errors.append(f'Selected file not on disk: {sel_abs}')
                    else:
                        anchor_dir = os.path.dirname(anchor_abs)
                        anchor_base_noext = os.path.splitext(os.path.basename(anchor_abs))[0]
                        sel_ext = os.path.splitext(os.path.basename(sel_abs))[1]
                        target_video = os.path.join(anchor_dir, anchor_base_noext + sel_ext)

                        # 2a: COPY selected video → target (collision handled)
                        target_video = _copy_with_collision(sel_abs, target_video)
                        renamed_to = target_video
                        new_selected_path = target_video
                        # Derive the ACTUAL new stem from the returned path.
                        # If the anchor slot was already occupied and _copy_with_collision
                        # returned e.g. `anchor_1.mp4`, companions must use `anchor_1`
                        # as their stem — NOT `anchor`. Round-2 review D-companion-drift.
                        actual_stem = os.path.splitext(os.path.basename(target_video))[0]
                        print(f"[Replace] copied selected: {sel_abs} -> {renamed_to} "
                              f"(actual stem = {actual_stem!r})")

                        # 2b: COPY selected's companions → same target dir with ACTUAL stem
                        sel_companions = find_companion_files(sel_abs, companion_exts)
                        for comp_src in sel_companions:
                            _, comp_ext = os.path.splitext(comp_src)
                            comp_target = os.path.join(anchor_dir, actual_stem + comp_ext)
                            comp_target = _copy_with_collision(comp_src, comp_target)
                            copied_companions.append(comp_target)
                            print(f"[Replace] copied companion: {comp_src} -> {comp_target}")
                except Exception as e:
                    errors.append(f'Replace copy failed (non-destructive; nothing lost): {e}')
                    new_selected_path = None
                    renamed_to = None

            # ---- Step 3: MOVE non-selected file(s) + their companions to del_target ----
            # Only runs AFTER the copy above succeeded (or copy wasn't required).
            deleted_count = 0
            if not do_rename or new_selected_path is not None:
                for src in to_delete_paths:
                    if not os.path.exists(src):
                        errors.append(f'Not on disk: {src}')
                        continue
                    try:
                        scan_root = _find_scan_root_for_file(src, abs_folder_paths)
                        if scan_root is None:
                            scan_root = os.path.dirname(src)
                        try:
                            relative = os.path.relpath(src, scan_root)
                        except ValueError:
                            relative = os.path.basename(src)
                        dest = os.path.join(del_target, relative)
                        mv = move_with_companions(src, dest, companion_exts)
                        deleted_count += 1
                        print(f"[Replace] moved: {src} -> {mv['video_moved_to']} "
                              f"(+{len(mv['companions_moved'])} companions)")
                        errors.extend(mv.get('errors', []))
                    except Exception as e:
                        errors.append(f'Move failed for {src}: {e}')

                # ---- Step 3b: MOVE original selected + companions to del_target (backup) ----
                if do_rename:
                    try:
                        scan_root = _find_scan_root_for_file(sel_abs, abs_folder_paths)
                        if scan_root is None:
                            scan_root = os.path.dirname(sel_abs)
                        try:
                            relative = os.path.relpath(sel_abs, scan_root)
                        except ValueError:
                            relative = os.path.basename(sel_abs)
                        backup_dest = os.path.join(del_target, relative)
                        mv = move_with_companions(sel_abs, backup_dest, companion_exts)
                        print(f"[Replace] backed up original: {sel_abs} -> {mv['video_moved_to']} "
                              f"(+{len(mv['companions_moved'])} companions)")
                        errors.extend(mv.get('errors', []))
                    except Exception as backup_err:
                        errors.append(f'Backup of original selected failed: {backup_err}')
            else:
                # Copy failed and we're in a rename op — do NOT destroy anchor.
                errors.append('Copy failed — skipped moving non-selected to preserve anchor')

            # ---- Step 4: DB updates ----
            db_failed = False
            try:
                if to_delete_ids and deleted_count > 0:
                    BATCH = 900
                    for i in range(0, len(to_delete_ids), BATCH):
                        chunk = to_delete_ids[i:i + BATCH]
                        ph2 = ','.join('?' * len(chunk))
                        cur.execute(f"DELETE FROM video_hashes WHERE id IN ({ph2})", chunk)
                if do_rename and new_selected_path and selected_id is not None:
                    new_filename = os.path.basename(new_selected_path)
                    new_dir = os.path.dirname(new_selected_path)
                    cur.execute(
                        "UPDATE video_hashes "
                        "SET file_path = ?, filename = ?, dir_path = ? "
                        "WHERE id = ?",
                        (new_selected_path, new_filename, new_dir, selected_id),
                    )
                conn.commit()
            except Exception as db_err:
                db_failed = True
                try:
                    conn.rollback()
                except Exception:
                    pass
                errors.append(f'DB updates failed (files were moved; DB left unchanged): {db_err}')
                import traceback; traceback.print_exc()

            # ---- Step 5: stats repair ----
            repair_summary = None
            if affected_capture:
                try:
                    repair_summary = wf.stats_repair_after_mutation(
                        affected_capture, remove_from_groups=False,
                    )
                except Exception as e:
                    print(f"[Replace] WARN: stats repair failed: {e}")
                    import traceback; traceback.print_exc()
                    errors.append(f'stats repair failed: {e}')

            print(f"[Replace] DONE: deleted={deleted_count}, "
                  f"renamed={bool(renamed_to)}, errors={len(errors)}, db_failed={db_failed}")
            response = {
                'deleted_count':      deleted_count,
                'renamed':            bool(renamed_to),
                'new_selected_path':  new_selected_path or selected_raw,
                'errors':             errors,
                'stats_repair':       repair_summary,
            }
            # If files were moved but DB wasn't updated, that's an
            # inconsistent state — return HTTP 500 so the caller knows to
            # inspect and reconcile. Round-2 review.
            if db_failed:
                return response, 500
            return response
        except Exception as e:
            import traceback; traceback.print_exc()
            return {'error': str(e)}, 500


@ns.route('/replace-batch')
class ReplaceBatchResource(Resource):
    def post(self):
        """Batch Replace — N /replace operations in one transaction,
        SINGLE stats repair at the end. Each op must have exactly 2
        group_file_paths.
        """
        import shutil
        from .companion_files import find_companion_files, move_with_companions

        try:
            data = request.json or {}
            ops = data.get('operations') or []
            if not isinstance(ops, list) or not ops:
                return {'error': "Missing or empty 'operations'"}, 400

            for i, op in enumerate(ops):
                gp = op.get('group_file_paths') or []
                if not isinstance(gp, list) or len(gp) != 2:
                    return {'error': f'Operation {i}: group_file_paths must have exactly 2 entries'}, 400
                if not op.get('selected_file_path') or not op.get('anchor_file_path'):
                    return {'error': f'Operation {i}: missing selected_file_path or anchor_file_path'}, 400

            del_target = settings_manager.get_delete_target_path()
            if not del_target:
                return {'error': 'Delete target path not configured'}, 400
            os.makedirs(del_target, exist_ok=True)

            folder_paths = settings_manager.get_folder_paths() or []
            abs_folder_paths = [os.path.abspath(p) for p in folder_paths]
            companion_exts = settings_manager.get_companion_extensions()
            allowed_roots = _get_allowed_scan_roots()

            wf = get_workflow()
            conn = wf._get_connection()
            cur = conn.cursor()

            # Resolve all video_ids upfront
            all_paths_set: set = set()
            for op in ops:
                for p in op['group_file_paths']:
                    p_abs = os.path.abspath(p)
                    if not _is_path_inside_allowed_scope(p_abs, allowed_roots):
                        return {'error': f'Path not inside allowed scope: {p_abs}'}, 403
                    all_paths_set.add(p_abs)

            all_paths_list = list(all_paths_set)
            id_by_path: dict = {}
            BATCH = 900
            for i in range(0, len(all_paths_list), BATCH):
                chunk = all_paths_list[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(
                    f"SELECT id, file_path FROM video_hashes WHERE file_path IN ({ph})",
                    chunk,
                )
                for vid, fp in cur.fetchall():
                    id_by_path[fp] = vid

            # Pre-capture stats for entire batch
            all_ids_for_capture = list(id_by_path.values())
            affected_capture = None
            try:
                affected_capture = wf.stats_collect_affected_before_mutation(all_ids_for_capture)
            except Exception as e:
                print(f"[Replace Batch] WARN: pre-capture failed: {e}")

            print("=" * 80)
            print(f"[Replace Batch] START: {len(ops)} operation(s)")
            print("=" * 80)

            total_deleted = 0
            total_renamed = 0
            errors_per_op: list = []
            # Track which ops succeeded so we only run DB DELETE for those.
            # Round-2 review: previously DB DELETE ran for every op's video_ids
            # regardless of whether the file move actually succeeded, orphaning
            # files with matching DB rows.
            per_op_success: list = []   # list of dicts: {to_delete_ids, sel_id_to_update, new_path}

            for op_idx, op in enumerate(ops):
                op_errors: list = []
                sel_abs = os.path.abspath(op['selected_file_path'])
                anchor_abs = os.path.abspath(op['anchor_file_path'])
                group_abs = [os.path.abspath(p) for p in op['group_file_paths']]

                if sel_abs not in group_abs or anchor_abs not in group_abs:
                    op_errors.append('selected/anchor not in group_file_paths')
                    errors_per_op.append({'op_index': op_idx, 'errors': op_errors})
                    per_op_success.append({})   # placeholder — no DB writes for this op
                    continue

                do_rename = (sel_abs != anchor_abs)
                to_delete_paths = [p for p in group_abs if p != sel_abs]

                # ---- Step 2: COPY selected FIRST (non-destructive)
                # Round-2 review: previously non-selected files were moved
                # BEFORE the copy — a copy failure destroyed the anchor.
                new_selected_path = None
                copy_ok = True
                if do_rename:
                    try:
                        if not os.path.exists(sel_abs):
                            op_errors.append(f'Selected not on disk: {sel_abs}')
                            copy_ok = False
                        else:
                            anchor_dir = os.path.dirname(anchor_abs)
                            anchor_base_noext = os.path.splitext(os.path.basename(anchor_abs))[0]
                            sel_ext = os.path.splitext(os.path.basename(sel_abs))[1]
                            target_video = os.path.join(anchor_dir, anchor_base_noext + sel_ext)
                            target_video = _copy_with_collision(sel_abs, target_video)
                            new_selected_path = target_video
                            # Round-2 review: derive ACTUAL stem from the possibly-
                            # collision-suffixed target, not from anchor.
                            actual_stem = os.path.splitext(os.path.basename(target_video))[0]
                            print(f"[Replace Batch op {op_idx}] copied: {sel_abs} -> {target_video} "
                                  f"(actual stem = {actual_stem!r})")

                            for comp_src in find_companion_files(sel_abs, companion_exts):
                                _, comp_ext = os.path.splitext(comp_src)
                                comp_target = os.path.join(anchor_dir, actual_stem + comp_ext)
                                _copy_with_collision(comp_src, comp_target)
                    except Exception as e:
                        op_errors.append(f'Copy/rename failed: {e}')
                        new_selected_path = None
                        copy_ok = False

                # ---- Step 3: MOVE non-selected + companions (only if copy ok) ----
                move_ok_count = 0
                if copy_ok:
                    for src in to_delete_paths:
                        if not os.path.exists(src):
                            op_errors.append(f'Not on disk: {src}')
                            continue
                        try:
                            scan_root = _find_scan_root_for_file(src, abs_folder_paths)
                            if scan_root is None:
                                scan_root = os.path.dirname(src)
                            try:
                                relative = os.path.relpath(src, scan_root)
                            except ValueError:
                                relative = os.path.basename(src)
                            dest = os.path.join(del_target, relative)
                            mv = move_with_companions(src, dest, companion_exts)
                            move_ok_count += 1
                            print(f"[Replace Batch op {op_idx}] moved: {src} -> {mv['video_moved_to']}")
                            op_errors.extend(mv.get('errors', []))
                        except Exception as e:
                            op_errors.append(f'Move failed for {src}: {e}')

                    # ---- Step 3b: BACKUP original selected + companions ----
                    if do_rename:
                        try:
                            scan_root = _find_scan_root_for_file(sel_abs, abs_folder_paths)
                            if scan_root is None:
                                scan_root = os.path.dirname(sel_abs)
                            try:
                                relative = os.path.relpath(sel_abs, scan_root)
                            except ValueError:
                                relative = os.path.basename(sel_abs)
                            backup_dest = os.path.join(del_target, relative)
                            # Capture the return value so per-companion move errors
                            # are surfaced. Round-2 review D-low: previously the
                            # returned errors were discarded in the batch path.
                            mv = move_with_companions(sel_abs, backup_dest, companion_exts)
                            op_errors.extend(mv.get('errors', []))
                        except Exception as backup_err:
                            op_errors.append(f'Backup failed: {backup_err}')

                # ---- Count renamed AFTER copy + companion copies + backup all completed ----
                # Round-2 review D-low: previously total_renamed was incremented
                # right after the video copy, before companion copies / backup.
                if copy_ok and do_rename and not op_errors:
                    total_renamed += 1
                total_deleted += move_ok_count

                # ---- Track DB updates ONLY if copy/move succeeded ----
                selected_id = id_by_path.get(sel_abs)
                to_delete_ids = []
                if copy_ok and move_ok_count > 0:
                    to_delete_ids = [id_by_path[p] for p in to_delete_paths if p in id_by_path]
                per_op_success.append({
                    'to_delete_ids': to_delete_ids,
                    'sel_id_to_update': selected_id if (copy_ok and do_rename and new_selected_path is not None) else None,
                    'new_path': new_selected_path,
                })

                if op_errors:
                    errors_per_op.append({'op_index': op_idx, 'errors': op_errors})

            # ---- Step 4: DB updates for successful ops only ----
            # Wrap the whole DB batch in try/except with rollback — a mid-batch
            # SQLite failure previously left the shared connection with a dirty
            # uncommitted transaction. Round-2 review.
            try:
                for op_success in per_op_success:
                    to_delete_ids = op_success.get('to_delete_ids') or []
                    if to_delete_ids:
                        for j in range(0, len(to_delete_ids), 900):
                            chunk = to_delete_ids[j:j + 900]
                            ph = ','.join('?' * len(chunk))
                            cur.execute(f"DELETE FROM video_hashes WHERE id IN ({ph})", chunk)
                    sel_id = op_success.get('sel_id_to_update')
                    new_path = op_success.get('new_path')
                    if sel_id is not None and new_path:
                        cur.execute(
                            "UPDATE video_hashes "
                            "SET file_path = ?, filename = ?, dir_path = ? "
                            "WHERE id = ?",
                            (new_path, os.path.basename(new_path),
                             os.path.dirname(new_path), sel_id),
                        )
                conn.commit()
            except Exception as db_err:
                try:
                    conn.rollback()
                except Exception:
                    pass
                import traceback; traceback.print_exc()
                # Files were moved but DB is unchanged — the caller must know.
                # Round-2 review.
                return {
                    'error': f'DB updates failed (files were moved; DB unchanged): {db_err}',
                    'operations_count': len(ops),
                    'deleted_count':    total_deleted,
                    'renamed_count':    total_renamed,
                    'errors_per_op':    errors_per_op,
                }, 500

            repair_summary = None
            if affected_capture:
                try:
                    repair_summary = wf.stats_repair_after_mutation(
                        affected_capture, remove_from_groups=False,
                    )
                except Exception as e:
                    print(f"[Replace Batch] WARN: stats repair failed: {e}")
                    import traceback; traceback.print_exc()

            print("=" * 80)
            print(f"[Replace Batch] DONE: ops={len(ops)}, deleted={total_deleted}, "
                  f"renamed={total_renamed}, error_ops={len(errors_per_op)}")
            print("=" * 80)
            return {
                'operations_count': len(ops),
                'deleted_count':    total_deleted,
                'renamed_count':    total_renamed,
                'errors_per_op':    errors_per_op,
                'stats_repair':     repair_summary,
            }
        except Exception as e:
            # Round-2 review: outer except missing rollback previously.
            try:
                get_workflow()._get_connection().rollback()
            except Exception:
                pass
            import traceback; traceback.print_exc()
            return {'error': str(e)}, 500


# ===========================================================================
# S7.3: /batch-delete-by-path (recursive)
# ===========================================================================

@ns.route('/batch-delete-by-path')
class BatchDeleteByPathResource(Resource):
    def post(self):
        """Batch delete all duplicate files under a specific path.

        Request:
          {
            "deep_path":    "/path/to/folder",  // required
            "preview_only": true                // default true
          }

        preview_only=true → return matched files list without deleting.
        preview_only=false → actually move to delete_target + clean DB +
                             repair stats + prune newly-empty dirs.
        """
        import shutil
        from .companion_files import move_with_companions

        try:
            data = request.json or {}
            deep_path = data.get('deep_path')
            preview_only = data.get('preview_only', True)
            if not deep_path:
                return {'error': "'deep_path' required"}, 400
            if deep_path.startswith('\\\\') or deep_path.startswith('//'):
                return {'error': 'UNC paths not allowed'}, 400

            # Normalize path: support both absolute and relative-to-scan-root.
            # Round-2 review: previously a relative input like "sub/dir" that
            # didn't match a scan root's tail silently fell back to
            # os.path.abspath() against the process CWD — the wrong folder.
            # Now: absolute paths pass through; relative paths are joined
            # against each configured scan root and must resolve to exactly
            # one existing directory.
            if os.path.isabs(deep_path):
                normalized_path = os.path.abspath(deep_path)
            else:
                folder_paths = settings_manager.get_folder_paths() or []
                matched_paths: list = []
                for folder in folder_paths:
                    folder_abs = os.path.abspath(folder)
                    candidate = os.path.join(folder_abs, deep_path)
                    if os.path.isdir(candidate):
                        matched_paths.append(os.path.abspath(candidate))
                    # Also honor the older "tail matches folder name" shortcut
                    # for backward compat.
                    elif (folder_abs.endswith(os.sep + deep_path)
                            or folder_abs.endswith(deep_path)):
                        matched_paths.append(folder_abs)
                # Deduplicate while preserving order
                seen = set()
                matched_paths = [m for m in matched_paths
                                  if not (m in seen or seen.add(m))]
                if not matched_paths:
                    return {
                        'error': (
                            f"Relative path '{deep_path}' does not resolve under any "
                            f"configured scan folder. Try providing an absolute path."
                        ),
                    }, 400
                elif len(matched_paths) == 1:
                    normalized_path = matched_paths[0]
                else:
                    return {
                        'error': f"Ambiguous path '{deep_path}' matches: {matched_paths}",
                    }, 400
            deep_path = normalized_path

            allowed_roots = _get_allowed_scan_roots()
            if not _is_path_inside_allowed_scope(deep_path, allowed_roots):
                return {'error': 'deep_path is not inside any allowed scope'}, 403

            # SAFETY: deep_path must not equal any configured scan root OR the
            # delete_target itself — otherwise the empty-dir prune below could
            # wipe an entire scan folder or the trash dir. Round-2 review.
            deep_path_real = os.path.realpath(deep_path).rstrip(os.sep)
            _scan_root_reals = [os.path.realpath(r).rstrip(os.sep) for r in allowed_roots]
            _delete_target_real = None
            try:
                _dt = settings_manager.get_delete_target_path()
                if _dt:
                    _delete_target_real = os.path.realpath(_dt).rstrip(os.sep)
            except Exception:
                _delete_target_real = None
            if deep_path_real in _scan_root_reals:
                return {
                    'error': (
                        'Refusing to operate at the top of a configured scan folder — '
                        'give a subdirectory instead. Pruning the scan root itself '
                        'would break future scans.'
                    ),
                }, 400
            if _delete_target_real and deep_path_real == _delete_target_real:
                return {'error': 'deep_path cannot equal the delete_target'}, 400

            print(f"[Batch Delete] deep_path={deep_path}, preview_only={preview_only}")

            wf = get_workflow()
            conn = wf._get_connection()
            cur = conn.cursor()

            # Find all rows under deep_path that participate in similarities.
            # Python-side filter avoids LIKE wildcards.
            cur.execute('''
                SELECT DISTINCT v.file_path FROM video_hashes v
                WHERE EXISTS (
                    SELECT 1 FROM video_similarities s
                    WHERE s.video_id_a = v.id OR s.video_id_b = v.id
                )
            ''')
            all_dup_files = [r[0] for r in cur.fetchall()]
            deep_prefix = deep_path.rstrip(os.sep) + os.sep
            matched_files = [
                f for f in all_dup_files
                if f == deep_path.rstrip(os.sep) or f.startswith(deep_prefix)
            ]
            print(f"[Batch Delete] {len(matched_files)} candidate files under {deep_path}")

            if preview_only:
                return {
                    'matched_files': len(matched_files),
                    'file_list':     matched_files,
                    'preview':       True,
                }

            # Actual deletion
            delete_target = settings_manager.get_delete_target_path()
            if not delete_target:
                return {'error': 'delete_target_path not configured'}, 400
            os.makedirs(delete_target, exist_ok=True)

            folder_paths = settings_manager.get_folder_paths() or []
            abs_folder_paths = [os.path.abspath(p) for p in folder_paths]
            companion_exts = settings_manager.get_companion_extensions()

            # Pre-capture stats
            affected_capture = None
            try:
                video_ids: list = []
                for i in range(0, len(matched_files), 900):
                    chunk = [os.path.abspath(f) for f in matched_files[i:i + 900]]
                    ph = ','.join('?' * len(chunk))
                    cur.execute(f"SELECT id FROM video_hashes WHERE file_path IN ({ph})", chunk)
                    video_ids.extend(r[0] for r in cur.fetchall())
                affected_capture = wf.stats_collect_affected_before_mutation(video_ids)
            except Exception as e:
                print(f"[Batch Delete] WARN: stats pre-capture failed: {e}")

            deleted_count = 0
            failed_count = 0
            companions_total = 0
            # Round-2 review: only DB-delete rows whose file we actually moved.
            # Previously the DELETE ran over the ENTIRE `matched_files` list
            # including files that failed to move (already deleted by another
            # process, EPERM, cross-device error), orphaning them in the DB.
            successfully_moved: list = []
            move_errors: list = []
            # Track the parent directories of moved files, for scoped pruning
            # (Round-2 review: previously we walked deep_path and pruned every
            # empty dir under it, including ones the user intentionally left).
            moved_parent_dirs: set = set()

            for fp in matched_files:
                try:
                    if not os.path.isfile(fp):
                        failed_count += 1
                        move_errors.append(f'Not on disk: {fp}')
                        continue
                    fp_abs = os.path.abspath(fp)
                    scan_root = _find_scan_root_for_file(fp_abs, abs_folder_paths)
                    if scan_root is None:
                        scan_root = os.path.dirname(fp_abs)
                    try:
                        rel = os.path.relpath(fp_abs, scan_root)
                    except ValueError:
                        rel = os.path.basename(fp_abs)
                    dest = os.path.join(delete_target, rel)
                    mv = move_with_companions(fp_abs, dest, companion_exts)
                    deleted_count += 1
                    companions_total += len(mv.get('companions_moved', []))
                    # Track successful move for both DB-DELETE and empty-dir prune
                    successfully_moved.append(fp_abs)
                    moved_parent_dirs.add(os.path.dirname(fp_abs))
                    # Surface any per-companion failures
                    mv_errs = mv.get('errors', []) or []
                    if mv_errs:
                        move_errors.extend(mv_errs)
                except Exception as e:
                    failed_count += 1
                    move_errors.append(f'{fp}: {e}')
                    print(f"[Batch Delete] failed: {fp}: {e}")

            # DB cleanup — only over successfully-moved paths (Round-2 review).
            db_errors: list = []
            try:
                for i in range(0, len(successfully_moved), 900):
                    chunk = successfully_moved[i:i + 900]
                    ph = ','.join('?' * len(chunk))
                    cur.execute(f"DELETE FROM video_hashes WHERE file_path IN ({ph})", chunk)
                conn.commit()
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                import traceback; traceback.print_exc()
                # Round-2 review: previously logged to stdout only, response
                # gave no signal. Now surfaced via `errors` list and 500 status.
                db_errors.append(f'DB DELETE failed (files were still moved): {e}')
                print(f"[Batch Delete] DB cleanup failed: {e}")

            # Stats repair
            repair_summary = None
            if affected_capture and not db_errors:
                try:
                    repair_summary = wf.stats_repair_after_mutation(
                        affected_capture, remove_from_groups=False,
                    )
                except Exception as e:
                    print(f"[Batch Delete] WARN: stats repair failed: {e}")

            # Prune empty dirs — Round-2 review:
            #   - Only walk directories that had a file actually moved out
            #   - Refuse to rmdir any configured scan root, delete_target, or deep_path itself
            #   - Walk each ancestor up to (but NOT including) deep_path
            pruned = 0
            protected_reals = set(_scan_root_reals)
            if _delete_target_real:
                protected_reals.add(_delete_target_real)
            protected_reals.add(deep_path_real)

            def _safe_rmdir(d: str) -> bool:
                try:
                    real = os.path.realpath(d).rstrip(os.sep)
                except Exception:
                    return False
                if real in protected_reals:
                    return False
                try:
                    if os.path.isdir(d) and not os.listdir(d):
                        os.rmdir(d)
                        return True
                except OSError:
                    pass
                return False

            for parent in moved_parent_dirs:
                d = parent
                # Walk upward, but stop just before deep_path_real
                while True:
                    if not d or not os.path.isdir(d):
                        break
                    d_real = os.path.realpath(d).rstrip(os.sep)
                    if d_real in protected_reals or d_real == deep_path_real:
                        break
                    # Only prune if directory is strictly under deep_path
                    if not (d_real == deep_path_real
                            or d_real.startswith(deep_path_real + os.sep)):
                        break
                    if _safe_rmdir(d):
                        pruned += 1
                        d = os.path.dirname(d)
                    else:
                        break

            print(f"[Batch Delete] DONE: deleted={deleted_count}, failed={failed_count}, "
                  f"companions={companions_total}, pruned={pruned}, db_errors={len(db_errors)}")
            response = {
                'deleted':           deleted_count,
                'failed':            failed_count,
                'companions_moved':  companions_total,
                'pruned_dirs':       pruned,
                'preview':           False,
                'stats_repair':      repair_summary,
                'errors':            move_errors + db_errors,
            }
            if db_errors:
                return response, 500
            return response
        except Exception as e:
            import traceback; traceback.print_exc()
            return {'error': str(e)}, 500


# ===========================================================================
# S8: Media endpoints — thumbnail / preview / metadata
# ===========================================================================
#
# `/thumbnail`: serve a JPG. If `t` (seconds) is provided, extract a fresh
# frame on-demand. Otherwise return the pre-generated thumbnail from
# Phase 1's cache (or generate one if missing).
#
# `/preview`:   stream the video file directly. Flask's send_file with
# conditional=True honors HTTP Range requests, so the browser's <video>
# element can seek without downloading the whole file.
#
# `/metadata`:  probe with cv2 and return a metadata dict. No auth of any
# kind — path must be validated by extension whitelist + on-disk check.
# ===========================================================================

# Container → MIME map for /preview. Extensions covered by VIDEO_EXTS.
_VIDEO_MIME_MAP = {
    'mp4':  'video/mp4',
    'm4v':  'video/mp4',
    'webm': 'video/webm',
    'mkv':  'video/x-matroska',
    'mov':  'video/quicktime',
    'avi':  'video/x-msvideo',
    'wmv':  'video/x-ms-wmv',
    'flv':  'video/x-flv',
    'ts':   'video/mp2t',
    'm2ts': 'video/mp2t',
}


def _get_allowed_scan_roots():
    """Return a list of absolute realpath'd roots that ARE allowed to be
    referenced by media/preview endpoints and /delete's move source.

    Sources:
      - settings.folder_paths (the configured scan folders)
      - settings.delete_target_path (files that live in the trash can be
        previewed / re-inspected)
      - settings.thumbnail_cache_dir (so /thumbnail can serve cached JPGs
        that live under this directory)

    Excludes paths that don't exist on disk (they can't be attack targets
    but also can't be legitimate files). All returned entries are
    os.path.realpath'd so they defeat `..`  and symlink tricks.
    """
    raw = []
    raw.extend(settings_manager.get_folder_paths() or [])
    delete_target = settings_manager.get_delete_target_path()
    if delete_target:
        raw.append(delete_target)
    thumb_dir = settings_manager.get_thumbnail_cache_dir()
    if thumb_dir:
        raw.append(thumb_dir)

    out = []
    for p in raw:
        if not p:
            continue
        try:
            rp = os.path.realpath(p)
        except Exception:
            continue
        if rp and rp not in out:
            out.append(rp)
    return out


def _is_path_inside_allowed_scope(candidate_path: str, allowed_roots) -> bool:
    """Return True iff `candidate_path` (after realpath) lives inside one of
    the allow-listed roots.

    Uses os.sep boundary matching so `/foo` never accidentally covers
    `/foobar`. Rejects UNC paths (Windows `\\server\share`) outright —
    combined with the SSRF-adjacent concern on `os.path.isfile('\\\\...')`
    doing an SMB round-trip, we do not want any UNC-shaped input reaching
    the filesystem layer.
    """
    if not candidate_path:
        return False
    # Reject UNC before touching the filesystem (never even isfile-probe them).
    if candidate_path.startswith('\\\\') or candidate_path.startswith('//'):
        return False
    try:
        cp = os.path.realpath(candidate_path)
    except Exception:
        return False
    if cp.startswith('\\\\') or cp.startswith('//'):
        # realpath may resolve to a UNC form on Windows; still reject.
        return False
    for root in allowed_roots:
        if cp == root or cp.startswith(root + os.sep):
            return True
    return False


def _validate_video_path(path: str):
    """Return (ok, error_response_or_None). Common path safety check.

    Now enforces:
      - Non-empty path
      - No UNC prefix (rejects SMB SSRF-adjacent attempts)
      - Path is inside settings.folder_paths / delete_target / thumbnail dir
      - File exists on disk and is a regular file
      - Extension is in VIDEO_EXTS whitelist
    """
    if not path:
        return False, ({'error': "'path' query parameter required"}, 400)
    if path.startswith('\\\\') or path.startswith('//'):
        return False, ({'error': 'UNC paths are not allowed'}, 400)
    allowed_roots = _get_allowed_scan_roots()
    if not _is_path_inside_allowed_scope(path, allowed_roots):
        return False, ({
            'error': (
                'Path is not inside any configured scan folder, delete target, '
                'or thumbnail cache. Configure folder_paths in Settings first.'
            ),
        }, 403)
    if not os.path.isfile(path):
        return False, ({'error': f'File not found: {path}'}, 404)
    if not path.lower().endswith(VIDEO_EXTS):
        return False, ({'error': f'Not a supported video file (allowed: {VIDEO_EXTS})'}, 400)
    return True, None


@ns.route('/thumbnail')
class ThumbnailResource(Resource):
    def get(self):
        """Return a JPG thumbnail.

        Query params:
          path:  absolute path to the video (required)
          t:     seconds into video (optional). If given, extract fresh frame.
        """
        path = request.args.get('path')
        t = request.args.get('t')

        ok, err = _validate_video_path(path)
        if not ok:
            return err

        # Case 1: fresh frame at timestamp t
        if t is not None and t != '':
            try:
                t_sec = float(t)
            except (TypeError, ValueError):
                return {'error': "'t' must be a number"}, 400
            frame = extract_frame_at_cv2(path, t_sec)
            pil = None
            if frame is not None:
                pil = bgr_to_pil(frame, target_width=320)
            else:
                # Fallback via ffmpeg subprocess
                ffmpeg = settings_manager.get_ffmpeg_path()
                timeout = settings_manager.get_frame_extract_timeout_seconds()
                pil = extract_frame_at_ffmpeg_fallback(path, t_sec, ffmpeg, timeout)
            if pil is None:
                return {'error': 'frame extraction failed'}, 500
            buf = io.BytesIO()
            pil.save(buf, format='JPEG', quality=85, optimize=True)
            buf.seek(0)
            return send_file(buf, mimetype='image/jpeg')

        # Case 2: return cached thumbnail (or generate one now if missing)
        thumb_dir = settings_manager.get_thumbnail_cache_dir()
        thumb_path = os.path.join(thumb_dir, thumbnail_filename_for(path))
        if not os.path.isfile(thumb_path):
            pct = settings_manager.get_thumbnail_position_percent()
            ffmpeg = settings_manager.get_ffmpeg_path()
            timeout = settings_manager.get_frame_extract_timeout_seconds()
            if not extract_thumbnail(path, thumb_path,
                                     thumbnail_position_percent=pct,
                                     width=320,
                                     ffmpeg_path=ffmpeg,
                                     ffmpeg_timeout=timeout):
                return {'error': 'thumbnail generation failed'}, 500
        return send_file(thumb_path, mimetype='image/jpeg')


@ns.route('/preview')
class PreviewResource(Resource):
    def get(self):
        """Stream the video file to the browser.

        Query params:
          path:  absolute path to the video (required)

        Flask send_file with conditional=True honors Range requests so the
        <video> element can seek without downloading the full file.
        """
        path = request.args.get('path')
        ok, err = _validate_video_path(path)
        if not ok:
            return err

        ext = os.path.splitext(path)[1].lower().lstrip('.')
        mime = _VIDEO_MIME_MAP.get(ext, 'application/octet-stream')

        try:
            return send_file(path, mimetype=mime, conditional=True)
        except Exception as e:
            return {'error': str(e)}, 500


@ns.route('/metadata')
class MetadataResource(Resource):
    def get(self):
        """Return video metadata (duration, resolution, fps, vcodec, container).

        Query params:
          path:  absolute path to the video (required)
        """
        path = request.args.get('path')
        ok, err = _validate_video_path(path)
        if not ok:
            return err

        try:
            meta = probe_metadata(path)
        except Exception as e:
            import traceback; traceback.print_exc()
            return {'error': f'metadata probe raised: {e}'}, 500
        if meta is None:
            return {'error': 'metadata probe failed (cv2 could not open)'}, 500
        return meta


# ===========================================================================
# S9: Maintenance endpoints — settings / open-folder / cleanup / verify
# ===========================================================================

@ns.route('/settings')
class SettingsResource(Resource):
    # Key allow-list — POST /settings will silently drop any key not listed
    # here. This closes the RCE via arbitrary key write to `ffmpeg_path`
    # (Tier-1 review) while keeping the shallow-merge semantics for
    # documented, well-known keys.
    _ALLOWED_KEYS = {
        'delete_target_path',
        'similarity_threshold',
        'folder_paths',
        'folder_root_paths',
        'exclude_folder_paths',
        'auto_selection_rules',
        'companion_extensions',
        # NOTE: ffmpeg_path is intentionally NOT here. It was originally
        # configurable but that path lets a caller point the subprocess at
        # any binary, which becomes RCE the moment /thumbnail is hit.
        # If you need to override ffmpeg, edit settings.json manually.
        'video_db_path',
        'thumbnail_cache_dir',
        'max_cpu_cores',
        'n_frames',
        'frame_extract_timeout_seconds',
        'thumbnail_position_percent',
        'page_size',
        'phase1',
        'phase2',
    }

    def get(self):
        """Return current settings.json contents + system_cpu_count."""
        from multiprocessing import cpu_count
        s = settings_manager.get_settings()
        s['system_cpu_count'] = cpu_count()
        return s

    def post(self):
        """Update settings via allow-list shallow merge.

        Unknown keys are silently dropped (see `_ALLOWED_KEYS`).
        Nested objects (e.g. `phase1`) are REPLACED wholesale — pass the
        entire nested object even if changing one field.
        """
        data = request.json
        if not data or not isinstance(data, dict):
            return {'error': 'JSON object required'}, 400

        rejected_keys = [k for k in data.keys() if k not in self._ALLOWED_KEYS]
        cleaned = {k: v for k, v in data.items() if k in self._ALLOWED_KEYS}

        current = settings_manager.get_settings()
        current.update(cleaned)
        settings_manager.save_settings(current)
        return {
            'message': 'Settings updated',
            'settings': current,
            'rejected_keys': rejected_keys,
        }


@ns.route('/open-folder')
class OpenFolderResource(Resource):
    def post(self):
        """Open a folder in the OS file manager.

        Request: { "folder_path": "/abs/path" }

        HARDENED (Tier-1 review):
          - Rejects UNC paths (`\\\\server\\share`) — no SMB round-trip via Explorer
          - Rejects paths outside the configured allowed roots
            (folder_paths / delete_target / thumbnail dir)
        """
        data = request.json or {}
        folder_path = data.get('folder_path')
        if not folder_path:
            return {'error': "'folder_path' required"}, 400
        if not isinstance(folder_path, str):
            return {'error': "'folder_path' must be a string"}, 400
        if folder_path.startswith('\\\\') or folder_path.startswith('//'):
            return {'error': 'UNC paths are not allowed'}, 400
        if not os.path.exists(folder_path):
            return {'error': 'Folder not found'}, 404
        if not os.path.isdir(folder_path):
            return {'error': 'Path is not a directory'}, 400
        if not _is_path_inside_allowed_scope(folder_path, _get_allowed_scan_roots()):
            return {
                'error': (
                    'Folder is not inside any configured scan folder / delete target / '
                    'thumbnail dir. Configure folder_paths in Settings first.'
                ),
            }, 403

        try:
            if sys.platform == 'darwin':
                subprocess.Popen(['open', folder_path])
            elif sys.platform.startswith('win'):
                subprocess.Popen(['explorer', folder_path])
            else:
                subprocess.Popen(['xdg-open', folder_path])
            return {'success': True, 'message': 'Folder opened'}
        except Exception as e:
            import traceback; traceback.print_exc()
            return {'error': str(e)}, 500


@ns.route('/cleanup')
class CleanupResource(Resource):
    def post(self):
        """Remove video_hashes rows for files that no longer exist on disk.

        Scans `folder_paths` from settings to determine which files
        currently exist. Anything in the DB that isn't in that set gets
        removed (CASCADE cleans similarities + group memberships +
        whitelist rows).
        """
        try:
            folder_paths = settings_manager.get_folder_paths()
            if not folder_paths:
                return {'error': 'folder_paths not configured'}, 400

            existing_files: set = set()
            for root in folder_paths:
                if not os.path.isdir(root):
                    print(f"[Cleanup] WARNING: path not found or not a dir: {root}")
                    continue
                for dirpath, _, files in os.walk(root):
                    for f in files:
                        if f.lower().endswith(VIDEO_EXTS):
                            existing_files.add(os.path.abspath(os.path.join(dirpath, f)))

            wf = get_workflow()
            cache = VideoHashCache(str(wf.db_path))
            # Pass folder_paths as scope so cleanup_missing_files only
            # considers rows inside the scanned area — a partial FS
            # enumeration cannot wipe unrelated DB rows.
            removed_hashes, removed_whitelist = cache.cleanup_missing_files(
                existing_files, scope_dir_paths=folder_paths,
            )

            print(f"[Cleanup] existing_files={len(existing_files)}, "
                  f"removed_hashes={removed_hashes}")
            return {
                'removed_hashes':    removed_hashes,
                'removed_whitelist': removed_whitelist,   # always 0 (CASCADE)
                'existing_files':    len(existing_files),
                'message': f'Cleanup complete: removed {removed_hashes} rows',
            }
        except Exception as e:
            import traceback; traceback.print_exc()
            return {'error': str(e)}, 500


@ns.route('/verify')
class VerifyResource(Resource):
    def post(self):
        """Given a list of duplicate_groups, return which files are missing.

        Request:
          { "duplicate_groups": [[{"file_path": "..."}, ...], ...] }

        Response:
          {
            "missing_files":        [...],
            "missing_count":        int,
            "affected_groups":      [...],
            "cleaned_groups":       [[...], ...],   # groups with missing removed;
                                                      only kept if ≥2 members remain
            "removed_groups_count": int,
          }
        """
        data = request.json or {}
        groups = data.get('duplicate_groups')
        if not isinstance(groups, list):
            return {'error': 'duplicate_groups (list) required'}, 400

        all_paths: list = []
        path_to_group_idx: dict = {}
        for gi, g in enumerate(groups):
            if not isinstance(g, list):
                continue
            for m in g:
                if not isinstance(m, dict):
                    continue
                fp = m.get('file_path')
                if fp:
                    all_paths.append(fp)
                    path_to_group_idx.setdefault(fp, []).append(gi)

        # Check each path once
        missing_set: set = set()
        for p in set(all_paths):
            if not os.path.isfile(p):
                missing_set.add(p)

        if not missing_set:
            return {
                'missing_files':        [],
                'missing_count':        0,
                'affected_groups':      [],
                'cleaned_groups':       groups,
                'removed_groups_count': 0,
            }

        affected_group_indices: set = set()
        for miss in missing_set:
            for gi in path_to_group_idx.get(miss, []):
                affected_group_indices.add(gi)

        affected_groups: list = []
        cleaned_groups: list = []
        removed_groups_count = 0
        for gi, g in enumerate(groups):
            group_missing = []
            group_remain = []
            for m in g:
                if not isinstance(m, dict):
                    continue
                if m.get('file_path') in missing_set:
                    group_missing.append(m.get('file_path'))
                else:
                    group_remain.append(m)
            if gi in affected_group_indices:
                affected_groups.append({
                    'group_index':     gi,
                    'missing_files':   group_missing,
                    'remaining_files': [m.get('file_path') for m in group_remain],
                })
            if len(group_remain) >= 2:
                cleaned_groups.append(group_remain)
            else:
                removed_groups_count += 1

        print(f"[Verify] missing={len(missing_set)}, "
              f"affected_groups={len(affected_groups)}, "
              f"removed_groups={removed_groups_count}")
        return {
            'missing_files':        sorted(missing_set),
            'missing_count':        len(missing_set),
            'affected_groups':      affected_groups,
            'cleaned_groups':       cleaned_groups,
            'removed_groups_count': removed_groups_count,
        }
