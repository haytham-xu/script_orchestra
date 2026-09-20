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


_VALID_GROUP_SCOPES = ("live", "archive", "shelf")


def _normalize_group_scope(value, default="archive"):
    """Return a valid group scope, or None if an explicit invalid value was given."""
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    return text if text in _VALID_GROUP_SCOPES else None


@ns.route("/tabs")
class TabsResource(Resource):
    # DEPRECATED: used by the old Download Queue UI (BrowserAgentView). No longer called.
    def post(self):
        data = request.json or {}
        tabs = data.get("tabs", [])
        if not isinstance(tabs, list):
            return {"error": "tabs must be a list of URLs"}, 400
        result = get_service().store_tabs(tabs)
        return {"message": "Tabs received", **result}, 202


@ns.route("/tasks")
class TasksResource(Resource):
    # DEPRECATED: used by the old Download Queue UI (BrowserAgentView). No longer called.
    def get(self):
        return {"tasks": [t.to_dict() for t in repository.get_all()]}, 200


@ns.route("/tasks/<int:task_id>/retry")
class TaskRetryResource(Resource):
    # DEPRECATED: used by the old Download Queue UI (BrowserAgentView). No longer called.
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
    # DEPRECATED: used by the old Download Queue UI (BrowserAgentView). No longer called.
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
        logger.debug(
            "tab_archive.api.snapshot scope=%s query_len=%s",
            scope,
            len(query),
        )

        if scope not in ("all", "live", "archive"):
            return {"error": "scope must be one of: all, live, archive"}, 400

        try:
            result = get_tab_archive_service().get_snapshot(
                query=query,
                scope=scope,
                include_live_urls=include_live_urls,
            )
            return result, 200
        except Exception as e:
            logger.exception("tab_archive.api.snapshot_failed")
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


@ns.route("/tab-archive/group-tree")
class TabArchiveGroupTreeResource(Resource):
    def get(self):
        scope = _normalize_group_scope(request.args.get("scope"))
        if scope is None:
            return {"error": "invalid scope"}, 400
        svc = get_tab_archive_service()
        fn = {"live": svc.live_get_group_tree, "archive": svc.archive_get_group_tree, "shelf": svc.shelf_get_group_tree}[scope]
        return {"tree": fn()}, 200


@ns.route("/tab-archive/groups")
class TabArchiveGroupsResource(Resource):
    def get(self):
        scope = _normalize_group_scope(request.args.get("scope"))
        if scope is None:
            return {"error": "invalid scope"}, 400
        parent_id = request.args.get("parent_id")
        if parent_id is not None:
            parent_id = int(parent_id)
        svc = get_tab_archive_service()
        fn = {"live": svc.live_list_groups, "archive": svc.archive_list_groups, "shelf": svc.shelf_list_groups}[scope]
        return {"groups": fn(parent_id)}, 200

    def post(self):
        data = request.json or {}
        name = str(data.get("name") or "").strip()
        if not name:
            return {"error": "name is required"}, 400
        scope = _normalize_group_scope(data.get("scope"))
        if scope is None:
            return {"error": "invalid scope"}, 400
        parent_id = data.get("parent_id")
        if parent_id is not None:
            parent_id = int(parent_id)
        display_order = data.get("display_order")
        if display_order is not None:
            display_order = float(display_order)
        bookmark_id = str(data.get("bookmark_id") or "").strip() or None
        svc = get_tab_archive_service()
        try:
            if scope == "shelf":
                group = svc.shelf_create_group(name, parent_id, display_order, bookmark_id)
            elif scope == "live":
                group = svc.live_create_group(name, parent_id, display_order)
            else:
                group = svc.archive_create_group(name, parent_id, display_order)
            return {"group": group}, 200
        except ValueError as e:
            return {"error": str(e)}, 400


@ns.route("/tab-archive/groups/<int:group_id>")
class TabArchiveGroupResource(Resource):
    def patch(self, group_id: int):
        data = request.json or {}
        scope = _normalize_group_scope(data.get("scope"))
        if scope is None:
            return {"error": "invalid scope"}, 400
        name = data.get("name")
        new_parent_id = data.get("new_parent_id", "UNSET")
        new_display_order = data.get("new_display_order")

        svc = get_tab_archive_service()
        rename_fn = {"live": svc.live_rename_group, "archive": svc.archive_rename_group, "shelf": svc.shelf_rename_group}[scope]
        move_fn = {"live": svc.live_move_group, "archive": svc.archive_move_group, "shelf": svc.shelf_move_group}[scope]
        group = None

        if name is not None:
            name = str(name).strip()
            if not name:
                return {"error": "name must not be empty"}, 400
            try:
                group = rename_fn(group_id, name)
                if group is None:
                    return {"error": "group not found"}, 404
            except ValueError as e:
                return {"error": str(e)}, 400

        if new_parent_id != "UNSET" and new_display_order is not None:
            pid = int(new_parent_id) if new_parent_id is not None else None
            group = move_fn(group_id, pid, float(new_display_order))
            if group is None:
                return {"error": "group not found"}, 404

        if group is None:
            return {"error": "no update fields provided"}, 400
        return {"group": group}, 200

    def delete(self, group_id: int):
        scope = _normalize_group_scope(request.args.get("scope") or (request.json or {}).get("scope"))
        if scope is None:
            return {"error": "invalid scope"}, 400
        svc = get_tab_archive_service()
        delete_fn = {"live": svc.live_delete_group, "archive": svc.archive_delete_group, "shelf": svc.shelf_delete_group}[scope]
        ok = delete_fn(group_id)
        if not ok:
            return {"error": "group not found"}, 404
        return {"deleted": True}, 200


@ns.route("/tab-archive/records/<int:record_id>/group")
class TabArchiveRecordGroupResource(Resource):
    def patch(self, record_id: int):
        data = request.json or {}
        raw_gid = data.get("group_id")
        group_id = int(raw_gid) if raw_gid is not None else None
        result = get_tab_archive_service().set_archive_record_group(record_id, group_id)
        if result is None:
            return {"error": "record not found"}, 404
        return {"record": result}, 200


@ns.route("/tab-archive/live-tabs/set-group")
class TabArchiveLiveTabGroupResource(Resource):
    def post(self):
        data = request.json or {}
        tab_ids = data.get("tab_ids") or []
        if not isinstance(tab_ids, list):
            return {"error": "tab_ids must be a list"}, 400
        raw_gid = data.get("group_id")
        group_id = int(raw_gid) if raw_gid is not None else None
        result = get_tab_archive_service().set_live_tabs_group(tab_ids, group_id)
        return result, 200


@ns.route("/tab-archive/live-tabs/<int:tab_id>/order")
class TabArchiveLiveTabOrderResource(Resource):
    def patch(self, tab_id: int):
        data = request.json or {}
        raw_gid = data.get("group_id")
        group_id = int(raw_gid) if raw_gid is not None else None
        raw_order = data.get("display_order")
        if raw_order is None:
            return {"error": "display_order is required"}, 400
        try:
            display_order = float(raw_order)
        except (TypeError, ValueError):
            return {"error": "display_order must be a number"}, 400
        get_tab_archive_service().set_live_tab_group_and_order(tab_id, group_id, display_order)
        return {"ok": True}, 200


@ns.route("/tab-archive/live-tabs/batch-order")
class TabArchiveLiveTabBatchOrderResource(Resource):
    def patch(self):
        data = request.json or {}
        items = data.get("items")
        if not isinstance(items, list) or not items:
            return {"error": "items must be a non-empty list"}, 400
        validated = []
        for item in items:
            tab_id = item.get("tab_id")
            raw_gid = item.get("group_id")
            raw_order = item.get("display_order")
            if not isinstance(tab_id, int) or raw_order is None:
                return {"error": f"each item needs tab_id (int) and display_order"}, 400
            try:
                validated.append({
                    "tab_id": int(tab_id),
                    "group_id": int(raw_gid) if raw_gid is not None else None,
                    "display_order": float(raw_order),
                })
            except (TypeError, ValueError):
                return {"error": "invalid item values"}, 400
        get_tab_archive_service().batch_set_live_tab_orders(validated)
        return {"ok": True, "updated": len(validated)}, 200


@ns.route("/tab-archive/live-tabs/<int:tab_id>/custom-header")
class TabArchiveLiveTabCustomHeaderResource(Resource):
    def patch(self, tab_id: int):
        data = request.json or {}
        custom_header = data.get("custom_header")
        if custom_header is not None and not isinstance(custom_header, str):
            return {"error": "custom_header must be a string or null"}, 400
        get_tab_archive_service().set_live_tab_custom_header(tab_id, custom_header or None)
        return {"ok": True}, 200


@ns.route("/tab-archive/live-tabs/group-as-window")
class TabArchiveGroupAsWindowResource(Resource):
    def post(self):
        data = request.json or {}
        window_id = data.get("window_id")
        group_name = str(data.get("group_name") or "").strip()
        if not isinstance(window_id, int) or not group_name:
            return {"error": "window_id (int) and group_name are required"}, 400
        try:
            result = get_tab_archive_service().group_as_window(window_id, group_name)
            return result, 200
        except ValueError as e:
            return {"error": str(e)}, 400


@ns.route("/tab-archive/live-tabs/sort-by-group")
class TabArchiveSortByGroupResource(Resource):
    def post(self):
        data = request.json or {}
        window_id = data.get("window_id")
        if window_id is not None:
            window_id = int(window_id)
        try:
            result = get_tab_archive_service().sort_live_by_group(window_id)
            return result, 200
        except ValueError as e:
            return {"error": str(e)}, 400
        except Exception:
            logger.exception("tab_archive.api.sort_by_group_failed")
            return {"error": "sort_by_group failed"}, 500


@ns.route("/tab-archive/live-tabs/split-by-groups")
class TabArchiveSplitByGroupsResource(Resource):
    def post(self):
        try:
            result = get_tab_archive_service().split_live_by_groups()
            return result, 200
        except Exception:
            logger.exception("tab_archive.api.split_by_groups_failed")
            return {"error": "split_by_groups failed"}, 500


@ns.route("/tab-archive/records/reorder")
class TabArchiveRecordReorderResource(Resource):
    def post(self):
        data = request.json or {}
        record_id = data.get("record_id")
        display_order = data.get("display_order")
        if not isinstance(record_id, int) or display_order is None:
            return {"error": "record_id (int) and display_order are required"}, 400
        get_tab_archive_service().set_archive_record_order(record_id, float(display_order))
        return {"ok": True}, 200


@ns.route("/tab-archive/live-tabs/record-activations")
class TabArchiveRecordActivationsResource(Resource):
    def post(self):
        data = request.json or {}
        activations = data.get("activations") or []
        if not isinstance(activations, list):
            return {"error": "activations must be a list"}, 400
        get_tab_archive_service().record_activations(activations)
        return {"ok": True, "count": len(activations)}, 200


@ns.route("/tab-archive/live-tabs/move-tab")
class TabArchiveMoveTabResource(Resource):
    def post(self):
        data = request.json or {}
        tab_id = data.get("tab_id")
        index = data.get("index")
        if not isinstance(tab_id, int) or tab_id <= 0:
            return {"error": "tab_id must be a positive integer"}, 400
        if not isinstance(index, int) or index < 0:
            return {"error": "index must be a non-negative integer"}, 400
        window_id = data.get("window_id")
        if window_id is not None:
            window_id = int(window_id)
        try:
            result = get_tab_archive_service().move_live_tab(tab_id, index, window_id)
            return {"ok": True, **result}, 200
        except RuntimeError as exc:
            return {"error": str(exc)}, 400


@ns.route("/tab-archive/shelf")
class TabArchiveShelfResource(Resource):
    def get(self):
        return get_tab_archive_service().get_shelf_snapshot(), 200


@ns.route("/tab-archive/shelf/items")
class TabArchiveShelfItemsResource(Resource):
    def post(self):
        data = request.json or {}
        url = str(data.get("url") or "").strip()
        if not url:
            return {"error": "url is required"}, 400
        group_id = data.get("group_id")
        if group_id is not None:
            group_id = int(group_id)
        display_order = data.get("display_order")
        if display_order is not None:
            display_order = float(display_order)
        item = get_tab_archive_service().create_shelf_item(
            url=url,
            title=data.get("title"),
            favicon_url=data.get("favicon_url"),
            group_id=group_id,
            bookmark_id=data.get("bookmark_id"),
            display_order=display_order,
        )
        return {"item": item}, 200


@ns.route("/tab-archive/shelf/items/<int:item_id>")
class TabArchiveShelfItemResource(Resource):
    def delete(self, item_id: int):
        ok = get_tab_archive_service().delete_shelf_item(item_id)
        if not ok:
            return {"error": "item not found"}, 404
        return {"deleted": True}, 200

    def patch(self, item_id: int):
        data = request.json or {}
        did_update = False

        if "group_id" in data:
            raw_group = data.get("group_id")
            group_id = int(raw_group) if raw_group is not None else None
            get_tab_archive_service().set_shelf_item_group(item_id, group_id)
            did_update = True

        display_order = data.get("display_order")
        if display_order is not None:
            get_tab_archive_service().set_shelf_item_order(item_id, float(display_order))
            did_update = True

        if not did_update:
            return {"error": "display_order or group_id is required"}, 400
        return {"ok": True}, 200


@ns.route("/tab-archive/shelf/sync-from-bookmarks")
class TabArchiveShelfSyncFromBookmarksResource(Resource):
    def post(self):
        data = request.json or {}
        bookmark_nodes = data.get("bookmark_nodes") or []
        if not isinstance(bookmark_nodes, list):
            return {"error": "bookmark_nodes must be a list"}, 400
        result = get_tab_archive_service().sync_shelf_from_bookmarks(bookmark_nodes)
        return result, 200


@ns.route("/tab-archive/shelf/export-bookmarks")
class TabArchiveShelfExportBookmarksResource(Resource):
    def get(self):
        items = get_tab_archive_service().get_shelf_items_as_bookmark_tree()
        return {"items": items}, 200


@ns.route("/tab-archive/shelf/sync-from-browser-bookmarks")
class TabArchiveShelfSyncFromBrowserResource(Resource):
    def post(self):
        result = get_tab_archive_service().sync_shelf_from_browser_bookmarks()
        if "error" in result:
            return result, 502
        return result, 200


@ns.route("/tab-archive/shelf/export-to-browser-bookmarks")
class TabArchiveShelfExportToBrowserResource(Resource):
    def post(self):
        result = get_tab_archive_service().export_shelf_to_browser_bookmarks()
        if "error" in result:
            return result, 502
        return result, 200


@ns.route("/tab-archive/shelf/items/<int:item_id>/open")
class TabArchiveShelfItemOpenResource(Resource):
    def post(self, item_id: int):
        data = request.json or {}
        destination = data.get("destination", "current_window")
        result = get_tab_archive_service().open_shelf_item(item_id, destination=destination)
        if result.get("error") and not result.get("ok"):
            code = 404 if result["error"] == "item not found" else 502
            return result, code
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

