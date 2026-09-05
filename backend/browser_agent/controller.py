"""Browser Agent — REST controller.

Endpoints (relative to the blueprint prefix /browser-agent):
  POST   /tabs               ingest tab URLs from the extension
  GET    /tasks              list the download queue
  POST   /tasks/<id>/retry   reset a task to TODO
  DELETE /tasks/<id>         remove a task
  GET    /settings           read settings
  PUT    /settings           update settings
"""
import logging

from flask_restx import Namespace, Resource
from flask import request

from . import repository, settings_manager, agent_bridge, download_ssmh, download_jm, captcha_solver
from .entity import Status
from .service import get_service
from .tab_archive_service import get_tab_archive_service

ns = Namespace("")
logger = logging.getLogger(__name__)


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    return default


@ns.route("/tabs")
class TabsResource(Resource):
    def post(self):
        data = request.json or {}
        tabs = data.get("tabs", [])
        if not isinstance(tabs, list):
            return {"error": "tabs must be a list of URLs"}, 400
        result = get_service().store_tabs(tabs)
        return {"message": "Tabs received", **result}, 202


@ns.route("/tasks")
class TasksResource(Resource):
    def get(self):
        return {"tasks": [t.to_dict() for t in repository.get_all()]}, 200


@ns.route("/tasks/<int:task_id>/retry")
class TaskRetryResource(Resource):
    def post(self, task_id):
        tab = repository.get_by_id(task_id)
        if tab is None:
            return {"error": "task not found"}, 404
        tab.status = Status.TODO.value
        tab.retry_times = 0
        repository.update_browser_tab(tab)
        return {"message": "task reset to TODO"}, 200


@ns.route("/tasks/<int:task_id>")
class TaskResource(Resource):
    def delete(self, task_id):
        if repository.get_by_id(task_id) is None:
            return {"error": "task not found"}, 404
        repository.delete_by_id(task_id)
        return {"message": "task deleted"}, 200


@ns.route("/settings")
class SettingsResource(Resource):
    def get(self):
        return {"settings": settings_manager.load_settings()}, 200

    def put(self):
        data = request.json or {}
        if not isinstance(data, dict):
            return {"error": "Body must be a JSON object"}, 400
        try:
            current = settings_manager.load_settings()
            updated = settings_manager.validate_and_normalize(data, current)
            settings_manager.save_settings(updated)
            return {"message": "Settings updated", "settings": updated}, 200
        except ValueError as e:
            return {"error": str(e)}, 400
        except Exception as e:
            return {"error": f"Failed to update settings: {e}"}, 500


# --- Extension bridge ------------------------------------------------------
# The extension polls /agent/commands for RPC-style requests and posts back
# results at /agent/results/<id>. Web UI code should not touch these.

@ns.route("/agent/commands")
class AgentCommandsResource(Resource):
    def get(self):
        extension_version = (request.args.get("extension_version") or "").strip() or None
        raw_capabilities = request.args.get("capabilities") or ""
        capabilities = [value.strip() for value in raw_capabilities.split(",") if value.strip()]
        return {
            "commands": agent_bridge.drain_pending(
                extension_version=extension_version,
                capabilities=capabilities,
            )
        }, 200


@ns.route("/agent/results/<string:cmd_id>")
class AgentResultResource(Resource):
    def post(self, cmd_id: str):
        data = request.json or {}
        result = data.get("result")
        error = data.get("error")
        ok = agent_bridge.submit_result(cmd_id, result=result, error=error)
        if not ok:
            return {"error": "no such command (already timed out or unknown)"}, 404
        return {"message": "ok"}, 200


@ns.route("/agent/status")
class AgentStatusResource(Resource):
    def get(self):
        return agent_bridge.extension_status(), 200


# --- Tools ------------------------------------------------------------------

@ns.route("/tab-dedup/list-tabs")
class TabDedupListResource(Resource):
    def post(self):
        result, err = agent_bridge.enqueue_and_wait("list_tabs")
        if err:
            return {"error": err}, 504
        return result, 200


@ns.route("/tab-dedup/close-tabs")
class TabDedupCloseResource(Resource):
    def post(self):
        data = request.json or {}
        tab_ids = data.get("tab_ids") or []
        if not isinstance(tab_ids, list) or not all(isinstance(t, int) for t in tab_ids):
            return {"error": "tab_ids must be a list of integers"}, 400
        if not tab_ids:
            return {"closed": 0}, 200
        result, err = agent_bridge.enqueue_and_wait("close_tabs", {"tab_ids": tab_ids})
        if err:
            return {"error": err}, 504
        return result, 200


@ns.route("/tab-dedup/merge-tabs")
class TabDedupMergeResource(Resource):
    def post(self):
        """Move all tabs into a single window (the one with the most tabs)."""
        result, err = agent_bridge.enqueue_and_wait("merge_tabs")
        if err:
            return {"error": err}, 504
        return result, 200


@ns.route("/tab-dedup/group-tabs")
class TabDedupGroupResource(Resource):
    def post(self):
        """Reorder tabs in the focused window so same-domain tabs are adjacent."""
        result, err = agent_bridge.enqueue_and_wait("group_tabs_by_domain")
        if err:
            return {"error": err}, 504
        return result, 200


# --- Tab archive ------------------------------------------------------------

@ns.route("/tab-archive/snapshot")
class TabArchiveSnapshotResource(Resource):
    def get(self):
        query = (request.args.get("q") or "").strip()
        scope = (request.args.get("scope") or "all").strip().lower()
        include_live_urls = _as_bool(request.args.get("include_live_urls"), default=False)
        sort_by = (request.args.get("sort_by") or "heat").strip().lower()
        sort_order = (request.args.get("sort_order") or "desc").strip().lower()
        semantic = _as_bool(request.args.get("semantic"), default=False)
        semantic_top_k = request.args.get("semantic_top_k")
        logger.debug(
            "tab_archive.api.snapshot scope=%s query_len=%s sort_by=%s sort_order=%s semantic=%s",
            scope,
            len(query),
            sort_by,
            sort_order,
            semantic,
        )

        if scope not in ("all", "live", "archive"):
            return {"error": "scope must be one of: all, live, archive"}, 400
        if sort_by not in ("relevance", "heat", "last_opened", "last_archived", "open_count", "title"):
            return {
                "error": "sort_by must be one of: relevance, heat, last_opened, last_archived, open_count, title"
            }, 400
        if sort_order not in ("asc", "desc"):
            return {"error": "sort_order must be one of: asc, desc"}, 400

        try:
            semantic_top_k_value = int(semantic_top_k) if semantic_top_k not in (None, "") else None
            result = get_tab_archive_service().get_snapshot(
                query=query,
                scope=scope,
                include_live_urls=include_live_urls,
                sort_by=sort_by,
                sort_order=sort_order,
                semantic=semantic,
                semantic_top_k=semantic_top_k_value,
            )
            return result, 200
        except ValueError:
            return {"error": "semantic_top_k must be an integer"}, 400
        except Exception as e:
            logger.exception("tab_archive.api.snapshot_failed")
            return {"error": str(e)}, 500


@ns.route("/tab-archive/archive-safe-preview")
class TabArchiveSafePreviewResource(Resource):
    def post(self):
        data = request.json or {}
        include_pinned = _as_bool(data.get("include_pinned"), default=False)
        try:
            result = get_tab_archive_service().preview_safe_archive(include_pinned=include_pinned)
            return result, 200
        except Exception as e:
            return {"error": str(e)}, 500


@ns.route("/tab-archive/archive-selected")
class TabArchiveSelectedResource(Resource):
    def post(self):
        data = request.json or {}
        tab_ids = data.get("tab_ids") or []
        if not isinstance(tab_ids, list) or not all(isinstance(x, int) for x in tab_ids):
            return {"error": "tab_ids must be a list of integers"}, 400

        try:
            result = get_tab_archive_service().archive_selected(tab_ids)
            return result, 200
        except Exception as e:
            return {"error": str(e)}, 500


@ns.route("/tab-archive/archive-safe-run")
class TabArchiveSafeRunResource(Resource):
    def post(self):
        data = request.json or {}
        include_pinned = _as_bool(data.get("include_pinned"), default=False)
        try:
            result = get_tab_archive_service().archive_safe_all(include_pinned=include_pinned)
            return result, 200
        except Exception as e:
            return {"error": str(e)}, 500


@ns.route("/tab-archive/restore")
class TabArchiveRestoreResource(Resource):
    def post(self):
        data = request.json or {}
        record_ids = data.get("record_ids") or []
        destination = (data.get("destination") or "new_window").strip()
        logger.info(
            "tab_archive.api.restore requested=%s destination=%s",
            len(record_ids) if isinstance(record_ids, list) else -1,
            destination,
        )

        if not isinstance(record_ids, list) or not all(isinstance(x, int) for x in record_ids):
            return {"error": "record_ids must be a list of integers"}, 400

        try:
            result = get_tab_archive_service().restore_records(record_ids, destination=destination)
            return result, 200
        except ValueError as e:
            return {"error": str(e)}, 400
        except Exception as e:
            logger.exception("tab_archive.api.restore_failed")
            return {"error": str(e)}, 500


@ns.route("/tab-archive/records/<int:record_id>")
class TabArchiveRecordResource(Resource):
    def patch(self, record_id: int):
        data = request.json or {}
        if not isinstance(data, dict):
            return {"error": "Body must be a JSON object"}, 400

        patch = {}
        if "title" in data:
            patch["title"] = data.get("title")
        if "comment" in data:
            patch["comment"] = data.get("comment")
        if "eternal" in data:
            patch["eternal"] = _as_bool(data.get("eternal"), default=False)

        if not patch:
            return {"error": "No editable fields provided"}, 400

        result = get_tab_archive_service().update_record(record_id, patch)
        if result is None:
            return {"error": "record not found"}, 404
        return {"record": result}, 200

    def delete(self, record_id: int):
        ok = get_tab_archive_service().delete_record(record_id)
        if not ok:
            return {"error": "record not found"}, 404
        return {"deleted": True}, 200


@ns.route("/tab-archive/records/<int:record_id>/labels")
class TabArchiveRecordLabelsResource(Resource):
    def put(self, record_id: int):
        data = request.json or {}
        label_ids = data.get("label_ids") or []
        if not isinstance(label_ids, list) or not all(isinstance(x, int) for x in label_ids):
            return {"error": "label_ids must be a list of integers"}, 400

        result = get_tab_archive_service().set_record_labels(record_id, label_ids)
        if result is None:
            return {"error": "record not found"}, 404
        return {"record": result}, 200


@ns.route("/tab-archive/records/replace-url")
class TabArchiveReplaceUrlResource(Resource):
    def post(self):
        data = request.json or {}
        find = str(data.get("find") or "").strip()
        replace = str(data.get("replace") or "")
        preview = _as_bool(data.get("preview"), default=False)
        record_ids_raw = data.get("record_ids")

        if not find:
            return {"error": "find must not be empty"}, 400

        record_ids = None
        if record_ids_raw is not None:
            if not isinstance(record_ids_raw, list) or not all(isinstance(x, int) for x in record_ids_raw):
                return {"error": "record_ids must be a list of integers"}, 400
            record_ids = record_ids_raw

        try:
            result = get_tab_archive_service().replace_url(
                find=find,
                replace=replace,
                record_ids=record_ids,
                preview=preview,
            )
            return result, 200
        except Exception as e:
            logger.exception("tab_archive.api.replace_url_failed")
            return {"error": str(e)}, 500


@ns.route("/tab-archive/labels")
class TabArchiveLabelsResource(Resource):
    def get(self):
        return {"labels": get_tab_archive_service().list_labels()}, 200

    def post(self):
        data = request.json or {}
        name = str(data.get("name") or "").strip()
        if not name:
            return {"error": "name is required"}, 400
        try:
            label = get_tab_archive_service().create_label(name)
            return {"label": label}, 200
        except ValueError as e:
            return {"error": str(e)}, 400


@ns.route("/tab-archive/labels/<int:label_id>")
class TabArchiveLabelResource(Resource):
    def delete(self, label_id: int):
        ok = get_tab_archive_service().delete_label(label_id)
        if not ok:
            return {"error": "label not found"}, 404
        return {"deleted": True}, 200


@ns.route("/tab-archive/health-check")
class TabArchiveHealthCheckResource(Resource):
    """Compatibility synchronous endpoint."""
    def post(self):
        data = request.json or {}
        record_ids = data.get("record_ids")
        limit = data.get("limit", 200)
        logger.info(
            "tab_archive.api.health_check_sync requested=%s limit=%s",
            len(record_ids) if isinstance(record_ids, list) else 0,
            limit,
        )

        if record_ids is not None:
            if not isinstance(record_ids, list) or not all(isinstance(x, int) for x in record_ids):
                return {"error": "record_ids must be a list of integers"}, 400

        try:
            result = get_tab_archive_service().check_health(record_ids=record_ids, limit=int(limit))
            return result, 200
        except Exception as e:
            logger.exception("tab_archive.api.health_check_sync_failed")
            return {"error": str(e)}, 500


@ns.route("/tab-archive/health-check/start")
class TabArchiveHealthCheckStartResource(Resource):
    def post(self):
        data = request.json or {}
        record_ids = data.get("record_ids")
        limit = data.get("limit", 200)
        batch_size = data.get("batch_size", 20)
        logger.info(
            "tab_archive.api.health_check_start requested=%s limit=%s batch_size=%s",
            len(record_ids) if isinstance(record_ids, list) else 0,
            limit,
            batch_size,
        )

        if record_ids is not None:
            if not isinstance(record_ids, list) or not all(isinstance(x, int) for x in record_ids):
                return {"error": "record_ids must be a list of integers"}, 400

        try:
            job = get_tab_archive_service().start_health_check(
                record_ids=record_ids,
                limit=int(limit),
                batch_size=int(batch_size),
            )
            return {"job": job}, 202
        except RuntimeError as e:
            message = str(e)
            if message.startswith("health_check_job_already_running:"):
                running_job_id = message.split(":", 1)[1] if ":" in message else ""
                return {
                    "error": "health-check job is already running",
                    "running_job_id": running_job_id,
                }, 409
            return {"error": message}, 500
        except ValueError:
            return {"error": "limit and batch_size must be integers"}, 400
        except Exception as e:
            logger.exception("tab_archive.api.health_check_start_failed")
            return {"error": str(e)}, 500


@ns.route("/tab-archive/health-check/status")
class TabArchiveHealthCheckStatusResource(Resource):
    def get(self):
        job_id = (request.args.get("job_id") or "").strip() or None
        result = get_tab_archive_service().get_health_check_status(job_id=job_id)
        return result, 200


@ns.route("/tab-archive/health-check/cancel")
class TabArchiveHealthCheckCancelResource(Resource):
    def post(self):
        data = request.json or {}
        raw_job_id = data.get("job_id")
        job_id = str(raw_job_id).strip() if raw_job_id not in (None, "") else None
        logger.info("tab_archive.api.health_check_cancel job_id=%s", job_id or "<current>")
        result = get_tab_archive_service().cancel_health_check(job_id=job_id)
        return result, 200


# --- Download SSMH --------------------------------------------------------

@ns.route("/download-ssmh/scan")
class DownloadSSMHScanResource(Resource):
    def post(self):
        """Ask the extension for the current tab list, filter to Type-1
        source-URL candidates, return them."""
        result, err = agent_bridge.enqueue_and_wait("list_tabs")
        if err:
            return {"error": err}, 504
        cfg = settings_manager.load_settings().get("downloadSSMH", {}) or {}
        tab_urls = [t.get("url", "") for t in (result or {}).get("tabs", [])]
        candidates = download_ssmh.scan(tab_urls, cfg)
        return {"candidates": candidates, "total_tabs": len(tab_urls)}, 200


@ns.route("/download-ssmh/execute")
class DownloadSSMHExecuteResource(Resource):
    def post(self):
        data = request.json or {}
        urls = data.get("urls") or []
        if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
            return {"error": "urls must be a list of strings"}, 400
        if not urls:
            return {"error": "no URLs provided"}, 400
        result = download_ssmh.start_job(urls)
        if "error" in result:
            return result, 409
        return result, 202


@ns.route("/download-ssmh/status")
class DownloadSSMHStatusResource(Resource):
    def get(self):
        return download_ssmh.get_status(), 200


# --- Download Type 2 --------------------------------------------------------

@ns.route("/download-jm/check-auth")
class DownloadJMCheckAuthResource(Resource):
    def get(self):
        return download_jm.check_authenticated(), 200


@ns.route("/download-jm/scan")
class DownloadJMScanResource(Resource):
    def post(self):
        result, err = agent_bridge.enqueue_and_wait("list_tabs")
        if err:
            return {"error": err}, 504
        cfg = settings_manager.load_settings().get("downloadJM", {}) or {}
        tab_urls = [t.get("url", "") for t in (result or {}).get("tabs", [])]
        candidates = download_jm.scan(tab_urls, cfg)
        return {"candidates": candidates, "total_tabs": len(tab_urls)}, 200


@ns.route("/download-jm/execute")
class DownloadJMExecuteResource(Resource):
    def post(self):
        data = request.json or {}
        urls = data.get("urls") or []
        if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
            return {"error": "urls must be a list of strings"}, 400
        if not urls:
            return {"error": "no URLs provided"}, 400
        result = download_jm.start_job(urls)
        if "error" in result:
            return result, 409
        return result, 202


@ns.route("/download-jm/status")
class DownloadJMStatusResource(Resource):
    def get(self):
        return download_jm.get_status(), 200


@ns.route("/download-jm/submit-captcha")
class DownloadJMSubmitCaptchaResource(Resource):
    def post(self):
        data = request.json or {}
        answer = data.get("answer", "")
        if not isinstance(answer, str) or not answer.strip():
            return {"error": "answer must be a non-empty string"}, 400
        result = download_jm.submit_captcha_answer(answer.strip())
        if "error" in result:
            return result, 409
        return result, 200


# --- Captcha training (feeds the template solver) ---------------------------

@ns.route("/captcha-training/list")
class CaptchaTrainingListResource(Resource):
    def get(self):
        return {
            "samples": captcha_solver.list_training_samples(),
            "template_counts": captcha_solver.get_templates_summary(),
        }, 200


@ns.route("/captcha-training/save")
class CaptchaTrainingSaveResource(Resource):
    def post(self):
        data = request.json or {}
        filename = (data.get("filename") or "").strip()
        expression = (data.get("expression") or "").strip()
        if not filename or not expression:
            return {"error": "filename and expression required"}, 400
        result = captcha_solver.label_and_learn(filename, expression)
        if "error" in result:
            return result, 400
        return result, 200


@ns.route("/captcha-training/delete")
class CaptchaTrainingDeleteResource(Resource):
    def post(self):
        data = request.json or {}
        filename = (data.get("filename") or "").strip()
        if not filename:
            return {"error": "filename required"}, 400
        ok = captcha_solver.delete_training_sample(filename)
        return ({"deleted": True} if ok else {"error": "not found"}), (200 if ok else 404)
