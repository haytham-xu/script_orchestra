import os

from flask import Flask
from flask_cors import CORS
from extensions import restx_api
import time

import manga_classifier.config_controller
import manga_classifier.folder_controller
import manga_classifier.file_controller
import manga_classifier.settings_controller

# Import photo_classifier as independent module (using Blueprint)
from photo_classifier import blueprint as photo_classifier_blueprint

# Import duplicate_finder tool
from duplicate_finder.blueprint import blueprint as duplicate_finder_blueprint

# Import video_duplicate_finder tool (independent of duplicate_finder per D-11)
from video_duplicate_finder.blueprint import blueprint as video_duplicate_finder_blueprint

# Import roadmap tool
from roadmap.blueprint import blueprint as roadmap_blueprint

# Import clipboard_share tool
from clipboard_share.blueprint import blueprint as clipboard_share_blueprint

# Import caffeinate tool
from caffeinate.blueprint import blueprint as caffeinate_blueprint

# Import assistant tool
from assistant.blueprint import blueprint as assistant_blueprint

# Import browser_agent tool
from browser_agent.blueprint import blueprint as browser_agent_blueprint
from browser_agent import repository as browser_agent_repo
from browser_agent import dispatcher as browser_agent_dispatcher
from browser_agent import websocket_service as ba_websocket
from browser_agent.service import get_service as get_browser_agent_service

# Import memory_curve tool
from memory_curve.blueprint import blueprint as memory_curve_blueprint
from memory_curve import repository as memory_curve_repo

# Import knowledge_vault tool
from knowledge_vault.blueprint import blueprint as knowledge_vault_blueprint
from knowledge_vault import repository as knowledge_vault_repo

# Import translator tool
from translator.blueprint import blueprint as translator_blueprint
from translator import repository as translator_repo
from translator import websocket_service as translator_ws

# Import proxy forward tool
from proxy_forward.blueprint import blueprint as proxy_forward_blueprint

# Import relay proxy tool
from relay_proxy.blueprint import blueprint as relay_proxy_blueprint

# Import dashboard layout module (Launchpad-style layout persistence)
from dashboard.blueprint import blueprint as dashboard_blueprint

# Import claude_bridge tool (remote Claude Code agent). It depends on the
# Unix-only `pty`/`termios` stack, so on Windows we skip the import instead
# of failing the whole app.
try:
    from claude_bridge.blueprint import blueprint as claude_bridge_blueprint
    from claude_bridge import websocket_service as cb_websocket
    from claude_bridge.session_manager import get_manager as get_claude_bridge_manager
    _claude_bridge_available = True
except ImportError as _cb_err:
    print(f"[App] claude_bridge disabled: {_cb_err}", flush=True)
    claude_bridge_blueprint = None
    cb_websocket = None
    get_claude_bridge_manager = None
    _claude_bridge_available = False

import manga_viewer.controller
import manga_viewer.settings_controller
from manga_viewer.cypress_test_support import register_cypress_test_support

import pdf_converter.controller

import unzip.controller

import file_git.controller

# Import websocket services from both tools
from file_git import websocket_service as fg_websocket
from duplicate_finder import websocket_service as df_websocket
from clipboard_share import websocket_service as cs_websocket
from video_duplicate_finder import websocket_service as v_df_websocket
from caffeinate import websocket_service as cf_websocket
from caffeinate.service import get_service as get_caffeinate_service

# Wake-word listener (assistant sub-module)
from assistant.wake import websocket_service as wake_ws
from assistant.wake.service import get_service as get_wake_service

# Import Cypress support API for E2E testing
from cypress_support.api import cypress_api
from cypress_support.config_manager import ConfigManager

def create_app() -> Flask:
    app = Flask(__name__)

    CORS(app, resources={r"/*": {"origins": "*"}})

    restx_api.init_app(app)

    # Register manga viewer cypress test support
    register_cypress_test_support(app)

    # Register photo_classifier blueprint
    app.register_blueprint(photo_classifier_blueprint)

    # Register duplicate_finder blueprint
    app.register_blueprint(duplicate_finder_blueprint)

    # Register video_duplicate_finder blueprint (independent tool per D-11)
    app.register_blueprint(video_duplicate_finder_blueprint)

    # Register roadmap blueprint
    app.register_blueprint(roadmap_blueprint)

    # Register clipboard_share blueprint
    app.register_blueprint(clipboard_share_blueprint)

    # Register caffeinate blueprint
    app.register_blueprint(caffeinate_blueprint)

    # Register assistant blueprint
    app.register_blueprint(assistant_blueprint)

    # Register browser_agent blueprint
    app.register_blueprint(browser_agent_blueprint)

    # Register memory_curve blueprint
    app.register_blueprint(memory_curve_blueprint)

    # Register knowledge_vault blueprint
    app.register_blueprint(knowledge_vault_blueprint)

    # Register translator blueprint
    app.register_blueprint(translator_blueprint)

    # Register proxy forward blueprint
    app.register_blueprint(proxy_forward_blueprint)

    # Register relay proxy blueprint
    app.register_blueprint(relay_proxy_blueprint)

    # Register dashboard layout blueprint
    app.register_blueprint(dashboard_blueprint)

    # Register claude_bridge blueprint (only if the Unix-only deps loaded)
    if _claude_bridge_available:
        app.register_blueprint(claude_bridge_blueprint)

    # Register Cypress support API blueprint
    app.register_blueprint(cypress_api)

    # Health check endpoint
    @app.route('/health', methods=['GET'])
    def health_check():
        return {
            'status': 'ok',
            'timestamp': time.time()
        }, 200

    # Initialize WebSocket using duplicate_finder's init (both are identical)
    # This creates a single shared socketio instance for all tools
    socketio = df_websocket.init_socketio(app)

    # Share the same socketio instance with file_git, clipboard_share, and
    # video_duplicate_finder (pass-in mode per D-16 — video module doesn't
    # create its own SocketIO, just receives the shared instance).
    if socketio:
        fg_websocket.socketio = socketio
        cs_websocket.init_socketio(socketio)
        cs_websocket.register_socketio_events()
        v_df_websocket.init_socketio(socketio)
        translator_ws.init_socketio(socketio)
        translator_ws.register_socketio_events()
        cf_websocket.init_socketio(socketio)
        cf_websocket.register_socketio_events()
        get_caffeinate_service().register_broadcaster(cf_websocket.broadcast_log_entry)

        wake_ws.init_socketio(socketio)
        wake_ws.register_socketio_events()
        get_wake_service().register_broadcaster(wake_ws.broadcast_wake_event)

        ba_websocket.init_socketio(socketio)
        ba_websocket.register_socketio_events()
        get_browser_agent_service().register_broadcaster(ba_websocket.broadcast_progress)

        if _claude_bridge_available:
            cb_websocket.init_socketio(socketio)
            cb_websocket.register_socketio_events()
            get_claude_bridge_manager().register_broadcaster(cb_websocket.broadcast_event)

    # Initialize browser_agent DB and start its background download dispatcher.
    browser_agent_repo.init_db()
    browser_agent_dispatcher.start_background_loop()

    # Initialize memory_curve DB.
    memory_curve_repo.init_db()

    # Initialize knowledge_vault DB.
    knowledge_vault_repo.init_db()

    # Initialize translator DB.
    translator_repo.init_db()

    return app, socketio

def check_cypress_snapshots():
    """Check for unrestored Cypress config snapshots on startup"""
    try:
        config_manager = ConfigManager()
        result = config_manager.check_all_snapshots()

        if result['count'] > 0:
            print("\n" + "="*60)
            print("⚠️  WARNING: Found unrestored Cypress config snapshots!")
            print("="*60)
            print("This may indicate a previous test run failed.\n")
            for snap in result['unrestored']:
                print(f"  - {snap['tool']}: {snap['snapshot_time']}")
            print("\nRestore with:")
            print("  python backend/cypress_support/restore_config.py --all")
            print("="*60 + "\n")
    except Exception as e:
        # Don't block startup if check fails
        print(f"⚠️  Failed to check Cypress snapshots: {e}")

if __name__ == "__main__":
    # Check for unrestored snapshots
    check_cypress_snapshots()

    app, socketio = create_app()
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '50001'))

    # Use a dedicated backend port to keep frontend/backend ports separated.
    # Bind to 0.0.0.0 to allow access from other devices on LAN

    debug_flag = os.environ.get('FLASK_DEBUG', '1') == '1'

    if socketio:
        # Run with SocketIO if available
        print(f"[App] Starting with WebSocket support on {host}:{port} (debug={debug_flag})")
        socketio.run(app, debug=debug_flag, host=host, port=port, allow_unsafe_werkzeug=True)
    else:
        # Fallback to regular Flask if SocketIO not available
        print(f"[App] Starting without WebSocket on {host}:{port} (install flask-socketio to enable)")
        app.run(debug=debug_flag, host=host, port=port)
