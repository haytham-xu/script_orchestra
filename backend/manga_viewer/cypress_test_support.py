"""
Cypress Test Support for Manga Viewer
Provides helper endpoints for E2E testing
"""
from flask import request, jsonify
from flask_restx import Namespace, Resource
import os
import shutil
import json
import tempfile
from pathlib import Path
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

api = Namespace("", description="Manga Viewer Cypress test support endpoints")


def create_test_image(path: str, width=800, height=600, color='blue'):
    """Create a test image file"""
    img = Image.new('RGB', (width, height), color=color)
    img.save(path)


def create_test_pdf(path: str, num_pages=1):
    """Create a test PDF file"""
    c = canvas.Canvas(path, pagesize=letter)
    for i in range(num_pages):
        c.drawString(100, 750, f"Test PDF Page {i + 1}")
        c.showPage()
    c.save()


def create_test_video_placeholder(path: str):
    """Create a placeholder file for video (Cypress tests won't actually play videos)"""
    with open(path, 'wb') as f:
        f.write(b'FAKE_VIDEO_DATA')


@api.route("/manga-viewer/cypress/test-mode")
class TestModeResource(Resource):
    def post(self):
        """
        Enable test mode
        - Save current settings snapshot
        - Switch to test configuration
        """
        data = request.json or {}
        root_path = data.get('rootPath', '')

        if not root_path:
            return {"error": "rootPath is required"}, 400

        # Save current config to snapshot (backend handles this via settings_manager)
        # For now, just acknowledge
        return {
            "message": "Test mode enabled",
            "rootPath": root_path
        }, 200

    def delete(self):
        """
        Disable test mode
        - Restore original settings
        - Clean up test data
        """
        return {
            "message": "Test mode disabled"
        }, 200


@api.route("/manga-viewer/cypress/setup-test")
class SetupTestResource(Resource):
    def post(self):
        """
        Setup test data for manga viewer

        Request body:
        {
          "testName": "unique_test_identifier",
          "testRootPath": "/path/to/test/root",
          "structure": {
            "scan": {
              "[Artist1]Work1": {
                "images": 3,
                "pdfs": 1,
                "videos": 0
              }
            },
            "category": {
              "main_folder_1": {
                "main_cat_1_sub_cat_1": {
                  "[Artist2]Work2": {
                    "images": 5,
                    "pdfs": 0
                  }
                }
              }
            }
          }
        }

        Returns:
        {
          "testDir": "/path/to/test/root",
          "folders": {
            "scan": ["/path/to/scan/folder1", ...],
            "category": ["/path/to/category/folder1", ...]
          }
        }
        """
        data = request.json or {}
        test_name = data.get('testName', '')
        test_root_path = data.get('testRootPath', '')
        structure = data.get('structure', {})

        if not test_name or not test_root_path:
            return {"error": "testName and testRootPath are required"}, 400

        # Create test directory structure
        test_root = Path(test_root_path)
        test_root.mkdir(parents=True, exist_ok=True)

        result_folders = {
            "scan": [],
            "category": [],
            "to_del": []
        }

        # Create folders based on structure
        for section_name, section_data in structure.items():
            if section_name in ["scan", "to_del"]:
                # Direct folders under scan/to_del
                section_path = test_root / section_name
                section_path.mkdir(parents=True, exist_ok=True)

                for folder_name, folder_config in section_data.items():
                    folder_path = section_path / folder_name
                    folder_path.mkdir(parents=True, exist_ok=True)

                    # Create images
                    num_images = folder_config.get('images', 0)
                    for i in range(num_images):
                        img_path = folder_path / f"img_{i+1:03d}.jpg"
                        create_test_image(str(img_path))

                    # Create PDFs
                    num_pdfs = folder_config.get('pdfs', 0)
                    num_pdf_pages = folder_config.get('pdfPages', 1)
                    for i in range(num_pdfs):
                        pdf_path = folder_path / f"doc_{i+1}.pdf"
                        create_test_pdf(str(pdf_path), num_pages=num_pdf_pages)

                    # Create videos (placeholders)
                    num_videos = folder_config.get('videos', 0)
                    for i in range(num_videos):
                        video_path = folder_path / f"video_{i+1}.mp4"
                        create_test_video_placeholder(str(video_path))

                    result_folders[section_name].append(str(folder_path))

            elif section_name == "category":
                # Nested structure: category/main_folder/sub_folder/work_folder
                for main_folder, main_data in section_data.items():
                    for sub_folder, sub_data in main_data.items():
                        sub_path = test_root / "category" / main_folder / sub_folder
                        sub_path.mkdir(parents=True, exist_ok=True)

                        for folder_name, folder_config in sub_data.items():
                            folder_path = sub_path / folder_name
                            folder_path.mkdir(parents=True, exist_ok=True)

                            # Create files
                            num_images = folder_config.get('images', 0)
                            for i in range(num_images):
                                img_path = folder_path / f"img_{i+1:03d}.jpg"
                                create_test_image(str(img_path))

                            num_pdfs = folder_config.get('pdfs', 0)
                            num_pdf_pages = folder_config.get('pdfPages', 1)
                            for i in range(num_pdfs):
                                pdf_path = folder_path / f"doc_{i+1}.pdf"
                                create_test_pdf(str(pdf_path), num_pages=num_pdf_pages)

                            num_videos = folder_config.get('videos', 0)
                            for i in range(num_videos):
                                video_path = folder_path / f"video_{i+1}.mp4"
                                create_test_video_placeholder(str(video_path))

                            result_folders["category"].append(str(folder_path))

        return {
            "testDir": str(test_root),
            "folders": result_folders
        }, 200


@api.route("/manga-viewer/cypress/cleanup-test")
class CleanupTestResource(Resource):
    def post(self):
        """
        Clean up test data

        Request body:
        {
          "testDir": "/path/to/test/root"
        }
        """
        data = request.json or {}
        test_dir = data.get('testDir', '')

        if not test_dir:
            return {"error": "testDir is required"}, 400

        if os.path.exists(test_dir):
            try:
                shutil.rmtree(test_dir)
                return {"message": "Test data cleaned up"}, 200
            except Exception as e:
                return {"error": f"Failed to clean up test data: {str(e)}"}, 500

        return {"message": "Test directory does not exist"}, 200


@api.route("/manga-viewer/cypress/verify-folder-exists")
class VerifyFolderExistsResource(Resource):
    def post(self):
        """
        Verify if a folder exists

        Request body:
        {
          "folderPath": "/path/to/folder"
        }

        Returns:
        {
          "exists": true/false
        }
        """
        data = request.json or {}
        folder_path = data.get('folderPath', '')

        if not folder_path:
            return {"error": "folderPath is required"}, 400

        exists = os.path.exists(folder_path) and os.path.isdir(folder_path)

        return {
            "exists": exists,
            "folderPath": folder_path
        }, 200


@api.route("/manga-viewer/cypress/verify-folder-location")
class VerifyFolderLocationResource(Resource):
    def post(self):
        """
        Verify if a folder is in expected location

        Request body:
        {
          "folderName": "folder_name",
          "expectedParentPath": "/expected/parent/path"
        }

        Returns:
        {
          "found": true/false,
          "actualPath": "/actual/path" or null
        }
        """
        data = request.json or {}
        folder_name = data.get('folderName', '')
        expected_parent_path = data.get('expectedParentPath', '')

        if not folder_name or not expected_parent_path:
            return {"error": "folderName and expectedParentPath are required"}, 400

        expected_path = os.path.join(expected_parent_path, folder_name)
        found = os.path.exists(expected_path) and os.path.isdir(expected_path)

        return {
            "found": found,
            "folderName": folder_name,
            "expectedPath": expected_path,
            "actualPath": expected_path if found else None
        }, 200


@api.route("/manga-viewer/cypress/count-files")
class CountFilesResource(Resource):
    def post(self):
        """
        Count files in a folder

        Request body:
        {
          "folderPath": "/path/to/folder",
          "extensions": [".jpg", ".png", ".pdf"]  // optional
        }

        Returns:
        {
          "count": 10,
          "files": [...]
        }
        """
        data = request.json or {}
        folder_path = data.get('folderPath', '')
        extensions = data.get('extensions', [])

        if not folder_path:
            return {"error": "folderPath is required"}, 400

        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            return {"error": "Folder does not exist"}, 404

        files = []
        for root, dirs, filenames in os.walk(folder_path):
            for filename in filenames:
                file_path = os.path.join(root, filename)
                if extensions:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in extensions:
                        files.append(file_path)
                else:
                    files.append(file_path)

        return {
            "count": len(files),
            "files": files
        }, 200


def register_cypress_test_support(app):
    """Register cypress test support namespace"""
    from extensions import restx_api
    restx_api.add_namespace(api)
