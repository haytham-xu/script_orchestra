"""
Test API for Cypress E2E Testing

This module provides API endpoints for test data management:
- Create test directories
- Generate test images
- Clean up test data
- Verify file distribution
"""

from flask import Blueprint, request, jsonify
from pathlib import Path
from PIL import Image
import shutil
import os

# Create Blueprint
test_api = Blueprint('test_api', __name__, url_prefix='/api/test')

# Base test directory
BACKEND_DIR = Path(__file__).parent
TEST_BASE_DIR = BACKEND_DIR / "photo_classifier" / "tmp"


@test_api.route('/create-dir', methods=['POST'])
def create_test_directory():
    """
    Create a test directory under backend/photo_classifier/tmp

    Request JSON:
        {
            "test_name": "test_case_1"
        }

    Response:
        {
            "test_dir": "/absolute/path/to/test/dir"
        }
    """
    data = request.json
    test_name = data.get('test_name', 'default_test')

    # Ensure tmp directory exists
    TEST_BASE_DIR.mkdir(parents=True, exist_ok=True)

    # Create test-specific directory
    test_dir = TEST_BASE_DIR / test_name
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)

    return jsonify({
        'test_dir': str(test_dir.absolute())
    })


@test_api.route('/create-images', methods=['POST'])
def create_test_images():
    """
    Create dummy image files for testing

    Request JSON:
        {
            "test_dir": "/path/to/test/dir",
            "count": 5,
            "prefix": "test_image"  # optional
        }

    Response:
        {
            "image_paths": ["/path/to/image1.jpg", ...]
        }
    """
    data = request.json
    test_dir = Path(data.get('test_dir'))
    count = data.get('count', 5)
    prefix = data.get('prefix', 'test_image')

    if not test_dir.exists():
        return jsonify({'error': 'Test directory does not exist'}), 400

    image_paths = []

    for i in range(count):
        filename = f"{prefix}_{i+1:03d}.jpg"
        filepath = test_dir / filename

        # Create a simple colored image (different color for each image)
        # This makes each image unique
        img = Image.new('RGB', (800, 600), color=(100 + i * 20, 150 + i * 15, 200 + i * 10))
        img.save(filepath, 'JPEG')

        image_paths.append(str(filepath.absolute()))

    return jsonify({
        'image_paths': image_paths
    })


@test_api.route('/cleanup', methods=['POST'])
def cleanup_test_data():
    """
    Clean up test data

    Request JSON:
        {
            "test_name": "test_case_1"  # optional, if not provided, clean entire tmp folder
        }

    Response:
        {
            "status": "cleaned",
            "message": "Test data cleaned successfully"
        }
    """
    data = request.json or {}
    test_name = data.get('test_name')

    try:
        if test_name:
            test_dir = TEST_BASE_DIR / test_name
            if test_dir.exists():
                shutil.rmtree(test_dir)
        else:
            if TEST_BASE_DIR.exists():
                shutil.rmtree(TEST_BASE_DIR)

        return jsonify({
            'status': 'cleaned',
            'message': f'Test data cleaned successfully{" for " + test_name if test_name else ""}'
        })
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500


@test_api.route('/verify', methods=['POST'])
def verify_file_distribution():
    """
    Verify file distribution in category folders

    Request JSON:
        {
            "test_dir": "/path/to/test/dir"
        }

    Response:
        {
            "best": 1,
            "better": 2,
            "normal": 3,
            "del": 0,
            "remaining": 0
        }
    """
    data = request.json
    test_dir = Path(data.get('test_dir'))

    if not test_dir.exists():
        return jsonify({'error': 'Test directory does not exist'}), 400

    categories = ['best', 'better', 'normal', 'del']
    result = {}

    for category in categories:
        category_path = test_dir / category
        if category_path.exists() and category_path.is_dir():
            files = [f for f in category_path.iterdir() if f.is_file()]
            result[category] = len(files)
        else:
            result[category] = 0

    # Count remaining files in root
    root_files = [f for f in test_dir.iterdir() if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png']]
    result['remaining'] = len(root_files)

    return jsonify(result)
