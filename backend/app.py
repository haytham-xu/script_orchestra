from flask import Flask
from flask_cors import CORS
from extensions import restx_api
import time

# Import photo_classifier as independent module (using Blueprint)
from photo_classifier import blueprint as photo_classifier_blueprint

# Import duplicate_finder tool
from duplicate_finder.blueprint import blueprint as duplicate_finder_blueprint

# Import roadmap tool
from roadmap.blueprint import blueprint as roadmap_blueprint

# Import clipboard_share tool
from clipboard_share.blueprint import blueprint as clipboard_share_blueprint

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

    # Register roadmap blueprint
    app.register_blueprint(roadmap_blueprint)

    # Register clipboard_share blueprint
    app.register_blueprint(clipboard_share_blueprint)

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

    # Share the same socketio instance with file_git and clipboard_share
    if socketio:
        fg_websocket.socketio = socketio
        cs_websocket.init_socketio(socketio)
        cs_websocket.register_socketio_events()

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
    # Use port 5001 to avoid conflict with macOS AirPlay (port 5000)
    # Bind to 0.0.0.0 to allow access from other devices on LAN

    if socketio:
        # Run with SocketIO if available
        print("[App] Starting with WebSocket support on 0.0.0.0:5001")
        socketio.run(app, debug=True, host='0.0.0.0', port=5001, allow_unsafe_werkzeug=True)
    else:
        # Fallback to regular Flask if SocketIO not available
        print("[App] Starting without WebSocket on 0.0.0.0:5001 (install flask-socketio to enable)")
        app.run(debug=True, host='0.0.0.0', port=5001)
