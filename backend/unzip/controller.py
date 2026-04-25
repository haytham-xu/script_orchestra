"""
Unzip Controller
REST API endpoints for archive extraction
"""
from flask import request, jsonify
from flask_restx import Namespace, Resource
from extensions import restx_api
from unzip.service import UnzipService
from unzip.config import PASSWORD_LIST

ns = Namespace("")


@ns.route("/unzip/extract")
class UnzipExtractResource(Resource):
    def post(self):
        """
        Extract archive(s) from a file or folder path

        Request body (JSON):
        {
            "path": "/path/to/archive.zip"  // or folder path
        }

        Response:
        {
            "success": 2,
            "failed": 1,
            "message": "Extracted 2 archive(s) successfully, 1 failed"
        }
        """
        data = request.get_json()

        print(f"[Unzip] Received request: {data}")

        if not data or 'path' not in data:
            return {"error": "Missing 'path' parameter in request body"}, 400

        input_path = data['path']

        if not input_path or not isinstance(input_path, str):
            return {"error": "'path' must be a non-empty string"}, 400

        try:
            # Initialize service with password list from config
            print(f"[Unzip] Initializing service with {len(PASSWORD_LIST)} passwords")
            service = UnzipService(password_list=PASSWORD_LIST)

            # Extract based on input path type
            print(f"[Unzip] Processing path: {input_path}")
            result = service.extract_from_path(input_path)

            print(f"[Unzip] Extraction complete. Result: {result}")
            return jsonify(result)

        except Exception as e:
            print(f"[Unzip] Error: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}, 500


restx_api.add_namespace(ns)
