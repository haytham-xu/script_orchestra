import json
import os
import logging
import time

from flask import Flask, jsonify, request
from flask_cors import CORS
from extensions import restx_api


class _SuppressPolling(logging.Filter):
    def filter(self, record):
        return "GET /browser-agent/agent/commands" not in record.getMessage()

logging.getLogger("werkzeug").addFilter(_SuppressPolling())


# ── Tool enable/disable ───────────────────────────────────────────────────────

_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")

def _load_enabled_tools() -> set:
    """Return set of enabled tool keys. Empty set (= all disabled) when file absent."""
    if not os.path.exists(_SETTINGS_PATH):
        return set()
    with open(_SETTINGS_PATH) as f:
        data = json.load(f)
    return set(data.get("enabled", []))

_ENABLED = _load_enabled_tools()

def _on(key: str) -> bool:
    return key in _ENABLED


# ── Conditional imports ───────────────────────────────────────────────────────

# manga-classifier is a sub-tool of manga-viewer; load it when either is enabled.
if _on('manga-classifier') or _on('manga-viewer'):
    import manga_classifier.config_controller
    import manga_classifier.folder_controller
    import manga_classifier.file_controller
    import manga_classifier.settings_controller

if _on('photo-classifier'):
    from photo_classifier import blueprint as photo_classifier_blueprint
else:
    photo_classifier_blueprint = None

if _on('duplicate-finder') or _on('manga-viewer'):
    from duplicate_finder.blueprint import blueprint as duplicate_finder_blueprint
    from duplicate_finder import websocket_service as df_websocket
else:
    duplicate_finder_blueprint = None
    df_websocket = None

if _on('video-duplicate-finder') or _on('manga-viewer'):
    from video_duplicate_finder.blueprint import blueprint as video_duplicate_finder_blueprint
    from video_duplicate_finder import websocket_service as v_df_websocket
else:
    video_duplicate_finder_blueprint = None
    v_df_websocket = None

if _on('roadmap'):
    from roadmap.blueprint import blueprint as roadmap_blueprint
else:
    roadmap_blueprint = None

if _on('clipboard-share'):
    from clipboard_share.blueprint import blueprint as clipboard_share_blueprint
    from clipboard_share import websocket_service as cs_websocket
else:
    clipboard_share_blueprint = None
    cs_websocket = None

if _on('caffeinate'):
    from caffeinate.blueprint import blueprint as caffeinate_blueprint
    from caffeinate import websocket_service as cf_websocket
    from caffeinate.service import get_service as get_caffeinate_service
else:
    caffeinate_blueprint = None
    cf_websocket = None
    get_caffeinate_service = None

if _on('assistant'):
    from assistant.blueprint import blueprint as assistant_blueprint
    from assistant.wake import websocket_service as wake_ws
    from assistant.wake.service import get_service as get_wake_service
else:
    assistant_blueprint = None
    wake_ws = None
    get_wake_service = None

if _on('browser-agent'):
    from browser_agent.blueprint import blueprint as browser_agent_blueprint
    from browser_agent import repository as browser_agent_repo
    from browser_agent import dispatcher as browser_agent_dispatcher
    from browser_agent import websocket_service as ba_websocket
    from browser_agent.service import get_service as get_browser_agent_service
else:
    browser_agent_blueprint = None
    browser_agent_repo = None
    browser_agent_dispatcher = None
    ba_websocket = None
    get_browser_agent_service = None

if _on('memory-curve'):
    from memory_curve.blueprint import blueprint as memory_curve_blueprint
    from memory_curve import repository as memory_curve_repo
else:
    memory_curve_blueprint = None
    memory_curve_repo = None

if _on('knowledge-vault'):
    from knowledge_vault.blueprint import blueprint as knowledge_vault_blueprint
    from knowledge_vault import repository as knowledge_vault_repo
else:
    knowledge_vault_blueprint = None
    knowledge_vault_repo = None

if _on('translator'):
    from translator.blueprint import blueprint as translator_blueprint
    from translator import repository as translator_repo
    from translator import websocket_service as translator_ws
else:
    translator_blueprint = None
    translator_repo = None
    translator_ws = None

if _on('proxy-forward'):
    from proxy_forward.blueprint import blueprint as proxy_forward_blueprint
else:
    proxy_forward_blueprint = None

if _on('relay-proxy'):
    from relay_proxy.blueprint import blueprint as relay_proxy_blueprint
else:
    relay_proxy_blueprint = None

# Dashboard layout is always enabled (it's infrastructure, not a tool)
from dashboard.blueprint import blueprint as dashboard_blueprint

if _on('clean-keyword') or _on('manga-viewer'):
    from clean_keyword.blueprint import blueprint as clean_keyword_blueprint
    from clean_keyword import repository as clean_keyword_repo
else:
    clean_keyword_blueprint = None
    clean_keyword_repo = None

if _on('loans-calc'):
    from loans_calc.blueprint import blueprint as loans_calc_blueprint
else:
    loans_calc_blueprint = None

if _on('compress-image') or _on('manga-viewer'):
    from compress_image.blueprint import blueprint as compress_image_blueprint
else:
    compress_image_blueprint = None

if _on('dedup-folder') or _on('manga-viewer'):
    from dedup_folder.blueprint import blueprint as dedup_folder_blueprint
else:
    dedup_folder_blueprint = None

if _on('file-pipeline') or _on('manga-viewer'):
    from file_pipeline.blueprint import blueprint as file_pipeline_blueprint
    from file_pipeline import repository as file_pipeline_repo
    from file_pipeline import fp_websocket as fp_websocket
else:
    file_pipeline_blueprint = None
    file_pipeline_repo = None
    fp_websocket = None

if _on('file-tracker'):
    from file_tracker.blueprint import blueprint as file_tracker_blueprint
    from file_tracker import repository as file_tracker_repo
else:
    file_tracker_blueprint = None
    file_tracker_repo = None

if _on('apprentice'):
    from apprentice.blueprint import blueprint as apprentice_blueprint
    from apprentice import repository as apprentice_repo
else:
    apprentice_blueprint = None
    apprentice_repo = None

# claude_bridge: Unix-only deps, guarded by both feature flag and import availability
if _on('claude-bridge'):
    try:
        from claude_bridge.blueprint import blueprint as claude_bridge_blueprint
        from claude_bridge import websocket_service as cb_websocket
        from claude_bridge.session_manager import get_manager as get_claude_bridge_manager
        from claude_bridge import repository as claude_bridge_repo
        _claude_bridge_available = True
    except ImportError as _cb_err:
        print(f"[App] claude_bridge disabled: {_cb_err}", flush=True)
        claude_bridge_blueprint = None
        cb_websocket = None
        get_claude_bridge_manager = None
        claude_bridge_repo = None
        _claude_bridge_available = False
else:
    claude_bridge_blueprint = None
    cb_websocket = None
    get_claude_bridge_manager = None
    claude_bridge_repo = None
    _claude_bridge_available = False

if _on('manga-viewer'):
    import manga_viewer.controller
    import manga_viewer.settings_controller
    from manga_viewer.cypress_test_support import register_cypress_test_support
    from manga_viewer import queue_store as manga_viewer_queue_store
    _manga_viewer_available = True
else:
    register_cypress_test_support = None
    manga_viewer_queue_store = None
    _manga_viewer_available = False

if _on('pdf-converter'):
    import pdf_converter.controller

# unzip is a sub-tool of manga-viewer; load it when either is enabled.
if _on('unzip') or _on('manga-viewer'):
    import unzip.controller

if _on('file-git'):
    import file_git.controller
    from file_git import repository_manager as fg_repo_manager
    from file_git import websocket_service as fg_websocket
else:
    fg_repo_manager = None
    fg_websocket = None

# Cypress support is always available (test infrastructure)
from cypress_support.api import cypress_api
from cypress_support.config_manager import ConfigManager


def create_app() -> Flask:
    app = Flask(__name__)

    CORS(app, resources={r"/*": {"origins": "*"}})

    restx_api.init_app(app)

    if _manga_viewer_available and register_cypress_test_support:
        register_cypress_test_support(app)

    if photo_classifier_blueprint:
        app.register_blueprint(photo_classifier_blueprint)
    if duplicate_finder_blueprint:
        app.register_blueprint(duplicate_finder_blueprint)
    if video_duplicate_finder_blueprint:
        app.register_blueprint(video_duplicate_finder_blueprint)
    if roadmap_blueprint:
        app.register_blueprint(roadmap_blueprint)
    if clipboard_share_blueprint:
        app.register_blueprint(clipboard_share_blueprint)
    if caffeinate_blueprint:
        app.register_blueprint(caffeinate_blueprint)
    if assistant_blueprint:
        app.register_blueprint(assistant_blueprint)
    if browser_agent_blueprint:
        app.register_blueprint(browser_agent_blueprint)
    if memory_curve_blueprint:
        app.register_blueprint(memory_curve_blueprint)
    if knowledge_vault_blueprint:
        app.register_blueprint(knowledge_vault_blueprint)
    if translator_blueprint:
        app.register_blueprint(translator_blueprint)
    if proxy_forward_blueprint:
        app.register_blueprint(proxy_forward_blueprint)
    if relay_proxy_blueprint:
        app.register_blueprint(relay_proxy_blueprint)

    app.register_blueprint(dashboard_blueprint)

    if clean_keyword_blueprint:
        app.register_blueprint(clean_keyword_blueprint)
    if loans_calc_blueprint:
        app.register_blueprint(loans_calc_blueprint)
    if compress_image_blueprint:
        app.register_blueprint(compress_image_blueprint)
    if dedup_folder_blueprint:
        app.register_blueprint(dedup_folder_blueprint)
    if file_pipeline_blueprint:
        app.register_blueprint(file_pipeline_blueprint)
    if file_tracker_blueprint:
        app.register_blueprint(file_tracker_blueprint)
    if apprentice_blueprint:
        app.register_blueprint(apprentice_blueprint)
    if _claude_bridge_available:
        app.register_blueprint(claude_bridge_blueprint)

    app.register_blueprint(cypress_api)

    # ── Health check ──────────────────────────────────────────
    @app.route('/health', methods=['GET'])
    def health_check():
        return {'status': 'ok', 'timestamp': time.time()}, 200

    # ── Enabled tools endpoints ───────────────────────────────
    @app.route('/enabled-tools', methods=['GET'])
    def get_enabled_tools():
        # manga-classifier is a sub-tool of manga-viewer: expose it as enabled
        # whenever manga-viewer is loaded, so the frontend nav guard allows navigation.
        effective = set(_ENABLED)
        if 'manga-viewer' in effective:
            # Sub-tools of manga-viewer: auto-enabled when manga-viewer is on.
            effective.update(['manga-classifier', 'unzip', 'duplicate-finder',
                              'video-duplicate-finder', 'clean-keyword',
                              'compress-image', 'dedup-folder', 'file-pipeline'])
        return jsonify({"enabled": list(effective)})

    @app.route('/enabled-tools', methods=['PUT'])
    def put_enabled_tools():
        global _ENABLED
        data = request.get_json(force=True)
        enabled_list = data.get("enabled", [])
        with open(_SETTINGS_PATH, "w") as f:
            json.dump({"enabled": enabled_list}, f, indent=2)
        # Update in-memory set so GET reflects the saved list immediately.
        # Note: newly enabled tools still require a backend restart to load
        # their blueprints; this only ensures the saved list survives a page refresh.
        _ENABLED = set(enabled_list)
        return jsonify({"ok": True})

    # ── WebSocket init ────────────────────────────────────────
    # duplicate_finder owns the canonical socketio; all other tools receive it.
    if df_websocket:
        socketio = df_websocket.init_socketio(app)
    else:
        socketio = None

    if socketio:
        if fg_websocket:
            fg_websocket.socketio = socketio
        if cs_websocket:
            cs_websocket.init_socketio(socketio)
            cs_websocket.register_socketio_events()
        if v_df_websocket:
            v_df_websocket.init_socketio(socketio)
        if translator_ws:
            translator_ws.init_socketio(socketio)
            translator_ws.register_socketio_events()
        if cf_websocket:
            cf_websocket.init_socketio(socketio)
            cf_websocket.register_socketio_events()
        if get_caffeinate_service:
            get_caffeinate_service().register_broadcaster(cf_websocket.broadcast_log_entry)
        if wake_ws:
            wake_ws.init_socketio(socketio)
            wake_ws.register_socketio_events()
        if get_wake_service:
            get_wake_service().register_broadcaster(wake_ws.broadcast_wake_event)
        if ba_websocket:
            ba_websocket.init_socketio(socketio)
            ba_websocket.register_socketio_events()
        if get_browser_agent_service:
            get_browser_agent_service().register_broadcaster(ba_websocket.broadcast_progress)
        if fp_websocket:
            fp_websocket.init_socketio(socketio)
        if _claude_bridge_available and cb_websocket:
            cb_websocket.init_socketio(socketio)
            cb_websocket.register_socketio_events()
            get_claude_bridge_manager().register_broadcaster(cb_websocket.broadcast_event)

    # ── DB init ───────────────────────────────────────────────
    if browser_agent_repo:
        browser_agent_repo.init_db()
    if browser_agent_dispatcher:
        browser_agent_dispatcher.start_background_loop()
    if fg_repo_manager:
        fg_repo_manager.init_db()
    if memory_curve_repo:
        memory_curve_repo.init_db()
    if knowledge_vault_repo:
        knowledge_vault_repo.init_db()
    if translator_repo:
        translator_repo.init_db()
    if manga_viewer_queue_store:
        manga_viewer_queue_store.init_db()
    if clean_keyword_repo:
        clean_keyword_repo.init_db()
    if file_pipeline_repo:
        file_pipeline_repo.init_db()
    if file_tracker_repo:
        file_tracker_repo.init_db()
    if apprentice_repo:
        apprentice_repo.init_db()
    if claude_bridge_repo:
        claude_bridge_repo.init_db()

    return app, socketio


def check_cypress_snapshots():
    """Check for unrestored Cypress config snapshots on startup"""
    try:
        config_manager = ConfigManager()
        result = config_manager.check_all_snapshots()

        if result['count'] > 0:
            print("\n" + "="*60)
            print("WARNING: Found unrestored Cypress config snapshots!")
            print("="*60)
            print("This may indicate a previous test run failed.\n")
            for snap in result['unrestored']:
                print(f"  - {snap['tool']}: {snap['snapshot_time']}")
            print("\nRestore with:")
            print("  python backend/cypress_support/restore_config.py --all")
            print("="*60 + "\n")
    except Exception as e:
        print(f"Failed to check Cypress snapshots: {e}")


if __name__ == "__main__":
    check_cypress_snapshots()

    app, socketio = create_app()
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '50001'))

    debug_flag = os.environ.get('FLASK_DEBUG', '1') == '1'

    if socketio:
        print(f"[App] Starting with WebSocket support on {host}:{port} (debug={debug_flag})")
        socketio.run(app, debug=debug_flag, host=host, port=port, allow_unsafe_werkzeug=True)
    else:
        print(f"[App] Starting without WebSocket on {host}:{port} (install flask-socketio to enable)")
        app.run(debug=debug_flag, host=host, port=port)
