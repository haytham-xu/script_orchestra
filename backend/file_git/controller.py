"""
File-Git Controller — RESTful API for repository management (§3.7, §3.8).

Endpoints:
    /file-git/repos                          list, add
    /file-git/repos/<id>                     get, delete
    /file-git/repos/<id>/open-folder         POST — reveal in file manager
    /file-git/repos/<id>/status              GET  — lock + queue snapshot
    /file-git/repos/<id>/push                POST — CommandService.push
    /file-git/repos/<id>/pull                POST — CommandService.pull
    /file-git/repos/<id>/resume              POST — CommandService.queue
    /file-git/repos/<id>/config              GET, PUT — read/patch .fgit/config.json
    /file-git/settings                       GET, PUT — global settings
"""
import json
import os
import platform
import subprocess
from flask import request
from flask import Response
from flask_restx import Namespace, Resource

from extensions import restx_api
from .command import (
    command_pull,
    command_push,
    command_queue,
    command_manual_upload,
    command_post_manual_upload,
    command_pre_manual_download,
    command_post_manual_download,
    command_diff,
    command_rebuild_local_index,
    command_rebuild_cloud_index,
    estimate_rebuild_cloud_index,
    command_cleanup,
)
from .repository_manager import RepositoryManager
from .service import QueueService
from .service import sync_filter_service as SyncFilterService
from .settings_manager import SettingsManager
from . import baidu_oauth

ns = Namespace("")


def _ok(payload: dict) -> tuple:
    return {"success": True, **payload}, 200


def _err(msg: str, status: int = 500) -> tuple:
    return {"success": False, "error": msg}, status


@ns.route('/file-git/repos')
class ReposListResource(Resource):
    def get(self):
        try:
            return _ok({"repos": RepositoryManager.list_repos()})
        except Exception as exc:
            return _err(str(exc))

    def post(self):
        try:
            data = request.get_json() or {}
            local_path = data.get('local_path')
            mode = data.get('mode')
            skip_init = data.get('skip_init', False)

            if not local_path:
                return _err("Missing 'local_path' parameter", 400)
            if not mode:
                return _err("Missing 'mode' parameter", 400)

            repo = RepositoryManager.add_repo(local_path, mode, skip_init)
            action = "imported" if skip_init else "added"
            return _ok({
                "repo": repo,
                "message": f"Repository '{repo['name']}' {action} successfully",
            })
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>')
class RepoResource(Resource):
    def get(self, repo_id):
        try:
            repo = RepositoryManager.get_repo_by_id(repo_id)
            if not repo:
                return _err("Repository not found", 404)
            return _ok({"repo": repo})
        except Exception as exc:
            return _err(str(exc))

    def delete(self, repo_id):
        try:
            if not RepositoryManager.delete_repo(repo_id):
                return _err("Repository not found", 404)
            return _ok({"message": "Repository deleted successfully"})
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/open-folder')
class RepoOpenFolderResource(Resource):
    def post(self, repo_id):
        try:
            repo = RepositoryManager.get_repo_by_id(repo_id)
            if not repo:
                return _err("Repository not found", 404)

            system = platform.system()
            local_path = repo['local_path']
            if system == 'Darwin':
                subprocess.Popen(['open', local_path])
            elif system == 'Windows':
                subprocess.Popen(['explorer', local_path])
            elif system == 'Linux':
                subprocess.Popen(['xdg-open', local_path])
            else:
                return _err(f"Unsupported OS: {system}", 400)
            return _ok({"message": "Folder opened successfully"})
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/status')
class RepoStatusResource(Resource):
    def get(self, repo_id):
        try:
            repo = RepositoryManager.get_repo_by_id(repo_id)
            if not repo:
                return _err("Repository not found", 404)
            qstate = QueueService.load(repo['local_path'])

            # Count pending_upload entries so UI can show a red-dot hint
            # while a manual upload session is open.
            pending_upload_count = 0
            pending_path = os.path.join(
                repo['local_path'], '.fgit', 'pending_upload.json'
            )
            if os.path.isfile(pending_path):
                try:
                    with open(pending_path, 'r', encoding='utf-8') as f:
                        pending_data = json.load(f)
                    pending_upload_count = len(pending_data.get('entries', []))
                except Exception:
                    pending_upload_count = 0

            return _ok({
                "repo": repo,
                "queue": {
                    "lock": qstate.lock,
                    "action_folder": qstate.action_folder,
                    "action_type": qstate.action_type,
                    "pending_count": len(qstate.queue),
                    "pending_upload_count": pending_upload_count,
                },
            })
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/config')
class RepoConfigResource(Resource):
    """Read / patch .fgit/config.json. The UI uses this to set password,
    remote_path, and cloud credentials after repo creation (§S1)."""

    def get(self, repo_id):
        try:
            repo = RepositoryManager.get_repo_by_id(repo_id)
            if not repo:
                return _err("Repository not found", 404)
            cfg = _load_repo_config(repo['local_path'])
            # Never echo the password back verbatim; return a bool flag
            safe = dict(cfg)
            safe['password_set'] = bool(cfg.get('password'))
            safe.pop('password', None)
            return _ok({"config": safe})
        except Exception as exc:
            return _err(str(exc))

    def put(self, repo_id):
        try:
            repo = RepositoryManager.get_repo_by_id(repo_id)
            if not repo:
                return _err("Repository not found", 404)
            data = request.get_json() or {}
            if not isinstance(data, dict):
                return _err("body must be an object", 400)

            cfg = _load_repo_config(repo['local_path'])

            # Mode is immutable
            if 'mode' in data and data['mode'] != cfg.get('mode'):
                return _err("mode is immutable after creation", 400)

            # Merge shallow keys; baidu_cloud is a nested object we merge too
            for k, v in data.items():
                if k == 'baidu_cloud' and isinstance(v, dict):
                    cfg.setdefault('baidu_cloud', {}).update(v)
                elif k == 'mode':
                    continue
                else:
                    cfg[k] = v

            _save_repo_config(repo['local_path'], cfg)
            RepositoryManager.update_last_updated(repo_id)
            return _ok({"message": "Config updated"})
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/push')
class RepoPushResource(Resource):
    def post(self, repo_id):
        try:
            result = command_push(repo_id)
            payload = {
                "message": result.message,
                "action_folder": result.action_folder,
                "uploaded": result.counters.uploaded,
                "remote_deleted": result.counters.remote_deleted,
                "errors": result.counters.errors,
            }
            return (_ok(payload) if result.ok
                    else ({"success": False, "error": result.message, **payload}, 500))
        except LookupError as exc:
            return _err(str(exc), 404)
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/pull')
class RepoPullResource(Resource):
    def post(self, repo_id):
        try:
            result = command_pull(repo_id)
            payload = {
                "message": result.message,
                "action_folder": result.action_folder,
                "downloaded": result.counters.downloaded,
                "local_deleted": result.counters.local_deleted,
                "errors": result.counters.errors,
            }
            return (_ok(payload) if result.ok
                    else ({"success": False, "error": result.message, **payload}, 500))
        except LookupError as exc:
            return _err(str(exc), 404)
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/resume')
class RepoResumeResource(Resource):
    def post(self, repo_id):
        try:
            result = command_queue(repo_id)
            payload = {
                "message": result.message,
                "action_folder": result.action_folder,
                "uploaded": result.counters.uploaded,
                "downloaded": result.counters.downloaded,
                "local_deleted": result.counters.local_deleted,
                "remote_deleted": result.counters.remote_deleted,
                "errors": result.counters.errors,
            }
            return (_ok(payload) if result.ok
                    else ({"success": False, "error": result.message, **payload}, 500))
        except LookupError as exc:
            return _err(str(exc), 404)
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/manual-upload')
class RepoManualUploadResource(Resource):
    def post(self, repo_id):
        try:
            data = request.get_json(silent=True) or {}
            subpath = data.get('subpath', '')
            result = command_manual_upload(repo_id, subpath=subpath)
            payload = {
                "message": result.message,
                "action_folder": result.action_folder,
                "buffer_dir": result.buffer_dir,
                "file_count": result.file_count,
            }
            return (_ok(payload) if result.ok
                    else ({"success": False, "error": result.message, **payload}, 400))
        except LookupError as exc:
            return _err(str(exc), 404)
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/post-manual-upload')
class RepoPostManualUploadResource(Resource):
    def post(self, repo_id):
        try:
            result = command_post_manual_upload(repo_id)
            payload = {
                "message": result.message,
                "action_folder": result.action_folder,
                "confirmed": result.confirmed,
                "missing": result.missing,
            }
            return (_ok(payload) if result.ok
                    else ({"success": False, "error": result.message, **payload}, 500))
        except LookupError as exc:
            return _err(str(exc), 404)
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/pre-manual-download')
class RepoPreManualDownloadResource(Resource):
    def post(self, repo_id):
        try:
            result = command_pre_manual_download(repo_id)
            payload = {
                "message": result.message,
                "action_folder": result.action_folder,
                "buffer_dir": result.buffer_dir,
            }
            return (_ok(payload) if result.ok
                    else ({"success": False, "error": result.message, **payload}, 400))
        except LookupError as exc:
            return _err(str(exc), 404)
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/post-manual-download')
class RepoPostManualDownloadResource(Resource):
    def post(self, repo_id):
        try:
            result = command_post_manual_download(repo_id)
            payload = {
                "message": result.message,
                "action_folder": result.action_folder,
                "decrypted": result.decrypted,
                "unmapped": result.unmapped,
            }
            return (_ok(payload) if result.ok
                    else ({"success": False, "error": result.message, **payload}, 500))
        except LookupError as exc:
            return _err(str(exc), 404)
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/diff')
class RepoDiffResource(Resource):
    def get(self, repo_id):
        try:
            result = command_diff(repo_id)
            return _ok({
                "message": result.message,
                "added": result.added,
                "modified": result.modified,
                "deleted": result.deleted,
                "total_local": result.total_local,
                "total_cloud": result.total_cloud,
            })
        except LookupError as exc:
            return _err(str(exc), 404)
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/rebuild-local-index')
class RepoRebuildLocalIndexResource(Resource):
    def post(self, repo_id):
        try:
            result = command_rebuild_local_index(repo_id)
            return _ok({"message": result.message, "count": result.count})
        except LookupError as exc:
            return _err(str(exc), 404)
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/rebuild-cloud-index')
class RepoRebuildCloudIndexResource(Resource):
    def get(self, repo_id):
        """Estimate — used by UI to build the confirmation dialog."""
        try:
            estimate = estimate_rebuild_cloud_index(repo_id)
            return _ok({
                "message": estimate.message,
                "remote_root": estimate.remote_root,
                "approximate_file_count": estimate.approximate_file_count,
            })
        except LookupError as exc:
            return _err(str(exc), 404)
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:
            return _err(str(exc))

    def post(self, repo_id):
        try:
            result = command_rebuild_cloud_index(repo_id)
            return _ok({
                "message": result.message,
                "count": result.count,
                "unknown": result.unknown,
            })
        except LookupError as exc:
            return _err(str(exc), 404)
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/cleanup')
class RepoCleanupResource(Resource):
    def get(self, repo_id):
        """Dry-run: what would be removed?"""
        try:
            mode = request.args.get('mode', 'expired')
            result = command_cleanup(repo_id, mode=mode, dry_run=True)
            return _ok({
                "message": result.message,
                "trash_candidates": result.trash_candidates,
                "action_candidates": result.action_candidates,
            })
        except LookupError as exc:
            return _err(str(exc), 404)
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:
            return _err(str(exc))

    def post(self, repo_id):
        try:
            data = request.get_json(silent=True) or {}
            mode = data.get('mode', 'expired')
            result = command_cleanup(repo_id, mode=mode, dry_run=False)
            return _ok({
                "message": result.message,
                "trash_removed": result.trash_removed,
                "action_removed": result.action_removed,
            })
        except LookupError as exc:
            return _err(str(exc), 404)
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/settings')
class SettingsResource(Resource):
    def get(self):
        try:
            return _ok({"settings": SettingsManager.get_settings()})
        except Exception as exc:
            return _err(str(exc))

    def put(self):
        try:
            data = request.get_json()
            if not data:
                return _err("Missing settings data", 400)
            return _ok({
                "settings": SettingsManager.update_settings(data),
                "message": "Settings updated successfully",
            })
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/baidu/auth-url')
class BaiduAuthUrlResource(Resource):
    def get(self):
        try:
            return _ok({"url": baidu_oauth.build_auth_url()})
        except Exception as exc:
            return _err(str(exc), 400)


@ns.route('/file-git/baidu/callback')
class BaiduCallbackResource(Resource):
    def get(self):
        # Baidu redirects here with ?code=... after the user authorizes.
        code = request.args.get('code', '')
        if not code:
            return _err("Missing code", 400)
        try:
            baidu_oauth.exchange_code(code)
            body = (
                "<html><body style='font-family:sans-serif;padding:40px'>"
                "<h2>✓ Baidu connected</h2>"
                "<p>You can close this window and return to File-Git.</p>"
                "<script>"
                "try{window.parent&&window.parent.postMessage("
                "{type:'baidu-oauth',status:'ok'},'*');}catch(e){}"
                "try{if(window.opener)window.opener.postMessage("
                "{type:'baidu-oauth',status:'ok'},'*');}catch(e){}"
                "setTimeout(function(){try{window.close();}catch(e){}},800);"
                "</script>"
                "</body></html>")
            return Response(body, mimetype='text/html')
        except Exception as exc:
            body = (
                f"<html><body style='font-family:sans-serif;padding:40px'>"
                f"<h2>Connection failed</h2><pre>{exc}</pre>"
                f"<script>try{{window.parent&&window.parent.postMessage("
                f"{{type:'baidu-oauth',status:'error'}},'*');}}catch(e){{}}</script>"
                f"</body></html>")
            return Response(body, mimetype='text/html', status=500)


@ns.route('/file-git/baidu/status')
class BaiduStatusResource(Resource):
    def get(self):
        try:
            return _ok(baidu_oauth.get_status())
        except Exception as exc:
            return _err(str(exc))


def _repo_root_or_none(repo_id: str):
    repo = RepositoryManager.get_repo_by_id(repo_id)
    return repo['local_path'] if repo else None


@ns.route('/file-git/repos/<string:repo_id>/sync-filter')
class SyncFilterResource(Resource):
    def get(self, repo_id):
        root = _repo_root_or_none(repo_id)
        if not root:
            return _err("repo not found", 404)
        try:
            SyncFilterService.refresh_defaults(root)
            return _ok({
                "filter": SyncFilterService.load(root),
                "children": SyncFilterService.list_children(root, ""),
            })
        except Exception as exc:
            return _err(str(exc))

    def put(self, repo_id):
        root = _repo_root_or_none(repo_id)
        if not root:
            return _err("repo not found", 404)
        try:
            data = request.get_json() or {}
            filt = SyncFilterService.load(root)
            filt["checked_prefixes"] = data.get("checked_prefixes", filt["checked_prefixes"])
            filt["unchecked_overrides"] = data.get("unchecked_overrides", filt["unchecked_overrides"])
            SyncFilterService.save(root, filt)
            return _ok({"filter": filt, "message": "Sync filter saved (applies on next push/pull)"})
        except Exception as exc:
            return _err(str(exc))


@ns.route('/file-git/repos/<string:repo_id>/sync-filter/children')
class SyncFilterChildrenResource(Resource):
    def get(self, repo_id):
        root = _repo_root_or_none(repo_id)
        if not root:
            return _err("repo not found", 404)
        try:
            parent = request.args.get('path', '')
            return _ok({"children": SyncFilterService.list_children(root, parent)})
        except Exception as exc:
            return _err(str(exc))


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _load_repo_config(local_path: str) -> dict:
    path = os.path.join(local_path, '.fgit', 'config.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_repo_config(local_path: str, cfg: dict) -> None:
    path = os.path.join(local_path, '.fgit', 'config.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


restx_api.add_namespace(ns)
