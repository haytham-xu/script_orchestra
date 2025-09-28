from flask import Flask
from flask_cors import CORS
from extensions import restx_api

import manga_classifier.manga_classifier

def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)
    restx_api.init_app(app)
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
