"""Browser Agent — REST controller.

Endpoints (relative to the blueprint prefix /browser-agent):
  POST   /tabs               ingest tab URLs from the extension
  GET    /tasks              list the download queue
  POST   /tasks/<id>/retry   reset a task to TODO
  DELETE /tasks/<id>         remove a task
  GET    /settings           read settings
  PUT    /settings           update settings
"""
from flask_restx import Namespace, Resource
from flask import request
from urllib.parse import urlparse

from . import repository, settings_manager, agent_bridge, download_ssmh, download_jm, captcha_solver
from .entity import Status
from .service import get_service

ns = Namespace("")


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
        return {"commands": agent_bridge.drain_pending()}, 200


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
