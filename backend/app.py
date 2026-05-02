from flask import Flask
from flask_cors import CORS
from extensions import restx_api

import manga_classifier.config_controller
import manga_classifier.folder_controller
import manga_classifier.file_controller

# Import photo_classifier as independent module (using Blueprint)
from photo_classifier import blueprint as photo_classifier_blueprint

import manga_viewer.controller

import pdf_converter.controller

import unzip.controller

import file_git.controller
from file_git.websocket_service import init_socketio

def create_app() -> Flask:
    app = Flask(__name__)

    CORS(app, resources={r"/*": {"origins": "*"}})

    restx_api.init_app(app)

    # Register photo_classifier blueprint
    app.register_blueprint(photo_classifier_blueprint)

    # Initialize WebSocket (optional - will gracefully fail if not installed)
    socketio = init_socketio(app)

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
