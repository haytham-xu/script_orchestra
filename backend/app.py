from flask import Flask
from flask_cors import CORS
from extensions import restx_api

import manga_classifier.config_controller
import manga_classifier.folder_controller
import manga_classifier.file_controller

import photo_classifier.file_controller
import photo_classifier.folder_controller

import manga_viewer.controller

import pdf_converter.controller

import unzip.controller

def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)
    restx_api.init_app(app)
    return app

if __name__ == "__main__":
    app = create_app()
    # Use port 5001 to avoid conflict with macOS AirPlay (port 5000)
    app.run(debug=True, port=5001)
