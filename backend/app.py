from flask import Flask
from flask_cors import CORS
from extensions import restx_api

import manga_classifier.config_controller
import manga_classifier.folder_controller
import manga_classifier.file_controller

# Import photo_classifier as independent module (using Blueprint)
from photo_classifier import blueprint as photo_classifier_blueprint

# Import duplicate_finder tool
from duplicate_finder.blueprint import blueprint as duplicate_finder_blueprint

# Import roadmap tool
from roadmap.blueprint import blueprint as roadmap_blueprint

import manga_viewer.controller
import manga_viewer.settings_controller

import pdf_converter.controller

import unzip.controller

import file_git.controller

# Import websocket services from both tools
from file_git import websocket_service as fg_websocket
from duplicate_finder import websocket_service as df_websocket

# Import test API for Cypress testing
from test_api import test_api

def create_app() -> Flask:
    app = Flask(__name__)

    CORS(app, resources={r"/*": {"origins": "*"}})

    restx_api.init_app(app)

    # Register photo_classifier blueprint
    app.register_blueprint(photo_classifier_blueprint)

    # Register duplicate_finder blueprint
    app.register_blueprint(duplicate_finder_blueprint)

    # Register roadmap blueprint
    app.register_blueprint(roadmap_blueprint)

    # Register test API blueprint
    app.register_blueprint(test_api)

    # Initialize WebSocket using duplicate_finder's init (both are identical)
    # This creates a single shared socketio instance for all tools
    socketio = df_websocket.init_socketio(app)

    # Share the same socketio instance with file_git
    if socketio:
        fg_websocket.socketio = socketio

    return app, socketio

if __name__ == "__main__":
    app, socketio = create_app()
    # Use port 5001 to avoid conflict with macOS AirPlay (port 5000)

    if socketio:
        # Run with SocketIO if available
        print("[App] Starting with WebSocket support")
        socketio.run(app, debug=True, port=5001)
    else:
        # Fallback to regular Flask if SocketIO not available
        print("[App] Starting without WebSocket (install flask-socketio to enable)")
        app.run(debug=True, port=5001)
