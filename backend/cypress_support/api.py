"""
Cypress Test API Blueprint

Provides all API endpoints for Cypress E2E testing:
1. Create test directories and media files
2. Check file existence (wait for file system sync)
3. Verify file distribution
4. Clean up test data

All APIs include robust file system checks to prevent race conditions.
"""

from flask import Blueprint, request, jsonify
from pathlib import Path
import shutil
import time
import os
from .media_generator import MediaGenerator
from .config_manager import ConfigManager

# Create Blueprint
cypress_api = Blueprint('cypress_api', __name__, url_prefix='/api/cypress')

# Base test directory
BACKEND_DIR = Path(__file__).parent.parent
TEST_BASE_DIR = BACKEND_DIR / "cypress_test_data" / "photo_classifier"


@cypress_api.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for Cypress to verify backend is ready

    Response:
        {
            "status": "ok",
            "message": "Cypress API is ready"
        }
    """
    return jsonify({
        'status': 'ok',
        'message': 'Cypress API is ready'
    })


@cypress_api.route('/create-test-dir', methods=['POST'])
def create_test_directory():
    """
    Create a test directory under backend/photo_classifier/tmp/cypress_tests

    Request JSON:
        {
            "test_name": "test_case_1"
        }

    Response:
        {
            "test_dir": "/absolute/path/to/test/dir",
            "exists": true
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

    # Verify directory actually exists (file system sync check)
    max_retries = 5
    for i in range(max_retries):
        if test_dir.exists() and test_dir.is_dir():
            return jsonify({
                'test_dir': str(test_dir.absolute()),
                'exists': True
            })
        time.sleep(0.1)

    return jsonify({
        'error': 'Failed to create directory after retries',
        'test_dir': str(test_dir.absolute()),
        'exists': False
    }), 500


@cypress_api.route('/create-media', methods=['POST'])
def create_test_media():
    """
    Create test images and videos

    Request JSON:
        {
            "test_dir": "/path/to/test/dir",
            "images": 5,      // number of images to create
            "videos": 2,      // number of videos to create
            "prefix": "test"  // optional filename prefix
        }

    Response:
        {
            "image_paths": ["/path/to/img1.jpg", ...],
            "video_paths": ["/path/to/vid1.mp4", ...],
            "total_created": 7,
            "all_verified": true
        }
    """
    data = request.json
    test_dir = Path(data.get('test_dir'))
    num_images = data.get('images', 0)
    num_videos = data.get('videos', 0)
    prefix = data.get('prefix', 'test')
    test_name = data.get('test_name', 'unknown')

    if not test_dir.exists():
        return jsonify({'error': 'Test directory does not exist'}), 400

    image_paths = []
    video_paths = []
    total_files = num_images + num_videos
    file_index = 1

    # Create images
    for i in range(num_images):
        filename = f"{prefix}_image_{file_index:03d}.jpg"
        filepath = test_dir / filename

        metadata = {
            'test_name': test_name,
            'filename': filename,
            'file_index': file_index,
            'total_files': total_files
        }

        if MediaGenerator.create_test_image(str(filepath), metadata):
            image_paths.append(str(filepath.absolute()))

        file_index += 1

    # Create videos
    for i in range(num_videos):
        filename = f"{prefix}_video_{file_index:03d}.mp4"
        filepath = test_dir / filename

        metadata = {
            'test_name': test_name,
            'filename': filename,
            'file_index': file_index,
            'total_files': total_files
        }

        if MediaGenerator.create_test_video(str(filepath), metadata, duration=3):
            video_paths.append(str(filepath.absolute()))

        file_index += 1

    # Verify all files exist (file system sync check)
    all_paths = image_paths + video_paths
    all_verified = _verify_files_exist(all_paths)

    return jsonify({
        'image_paths': image_paths,
        'video_paths': video_paths,
        'total_created': len(all_paths),
        'all_verified': all_verified
    })


@cypress_api.route('/check-files', methods=['POST'])
def check_files_exist():
    """
    Check if specific files exist in the file system
    Useful for waiting until file system has synced

    Request JSON:
        {
            "file_paths": ["/path/to/file1.jpg", "/path/to/file2.mp4"],
            "wait_timeout": 5000  // optional, milliseconds to wait (default 5000)
        }

    Response:
        {
            "all_exist": true,
            "files": {
                "/path/to/file1.jpg": true,
                "/path/to/file2.mp4": true
            },
            "missing": [],
            "wait_time_ms": 150
        }
    """
    data = request.json
    file_paths = data.get('file_paths', [])
    wait_timeout = data.get('wait_timeout', 5000) / 1000  # convert to seconds

    start_time = time.time()
    check_interval = 0.1  # 100ms

    # Keep checking until timeout or all files exist
    while (time.time() - start_time) < wait_timeout:
        file_status = {}
        missing = []

        for file_path in file_paths:
            exists = Path(file_path).exists()
            file_status[file_path] = exists
            if not exists:
                missing.append(file_path)

        if not missing:
            # All files exist
            wait_time_ms = int((time.time() - start_time) * 1000)
            return jsonify({
                'all_exist': True,
                'files': file_status,
                'missing': [],
                'wait_time_ms': wait_time_ms
            })

        time.sleep(check_interval)

    # Timeout reached
    wait_time_ms = int((time.time() - start_time) * 1000)
    file_status = {fp: Path(fp).exists() for fp in file_paths}
    missing = [fp for fp, exists in file_status.items() if not exists]

    return jsonify({
        'all_exist': False,
        'files': file_status,
        'missing': missing,
        'wait_time_ms': wait_time_ms
    })


@cypress_api.route('/check-directory', methods=['POST'])
def check_directory():
    """
    Check if directory exists and contains expected number of files

    Request JSON:
        {
            "directory": "/path/to/dir",
            "expected_files": 5,  // optional
            "wait_timeout": 5000  // optional, milliseconds
        }

    Response:
        {
            "exists": true,
            "file_count": 5,
            "files": ["file1.jpg", "file2.mp4", ...],
            "matches_expected": true
        }
    """
    data = request.json
    directory = Path(data.get('directory'))
    expected_files = data.get('expected_files')
    wait_timeout = data.get('wait_timeout', 5000) / 1000

    start_time = time.time()
    check_interval = 0.1

    while (time.time() - start_time) < wait_timeout:
        if directory.exists() and directory.is_dir():
            files = [f.name for f in directory.iterdir() if f.is_file()]
            file_count = len(files)

            matches_expected = (expected_files is None) or (file_count == expected_files)

            if matches_expected or (time.time() - start_time) >= wait_timeout:
                return jsonify({
                    'exists': True,
                    'file_count': file_count,
                    'files': sorted(files),
                    'matches_expected': matches_expected
                })

        time.sleep(check_interval)

    # Timeout or not found
    return jsonify({
        'exists': directory.exists(),
        'file_count': 0,
        'files': [],
        'matches_expected': False
    })


@cypress_api.route('/verify-distribution', methods=['POST'])
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
            "remaining": 0,
            "total": 6
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

    # Count remaining files in root (images and videos)
    media_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.mp4', '.mov', '.avi', '.mkv', '.webm']
    root_files = [f for f in test_dir.iterdir()
                  if f.is_file() and f.suffix.lower() in media_extensions]
    result['remaining'] = len(root_files)

    # Calculate total
    result['total'] = sum(result.values())

    return jsonify(result)


@cypress_api.route('/cleanup', methods=['POST'])
def cleanup_test_data():
    """
    Clean up test data

    Request JSON:
        {
            "test_name": "test_case_1"  // optional, if not provided, clean entire cypress_tests folder
        }

    Response:
        {
            "status": "cleaned",
            "message": "Test data cleaned successfully",
            "path": "/path/that/was/cleaned"
        }
    """
    data = request.json or {}
    test_name = data.get('test_name')

    try:
        path_cleaned = None  # 初始化变量

        if test_name:
            test_dir = TEST_BASE_DIR / test_name
            print(f"[Cypress API] Cleaning test directory: {test_dir}")
            if test_dir.exists():
                shutil.rmtree(test_dir)
            path_cleaned = str(test_dir.absolute())
        else:
            print(f"[Cypress API] Cleaning entire test base: {TEST_BASE_DIR}")
            if TEST_BASE_DIR.exists():
                shutil.rmtree(TEST_BASE_DIR)
            path_cleaned = str(TEST_BASE_DIR.absolute())

        print(f"[Cypress API] Cleanup successful: {path_cleaned}")
        return jsonify({
            'status': 'cleaned',
            'message': f'Test data cleaned successfully{" for " + test_name if test_name else ""}',
            'path': path_cleaned
        })
    except Exception as e:
        print(f"[Cypress API] Cleanup error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e)
        }), 500


# Helper functions

def _verify_files_exist(file_paths, max_wait=2.0):
    """
    Verify all files exist, waiting up to max_wait seconds

    Args:
        file_paths: List of file paths to check
        max_wait: Maximum seconds to wait

    Returns:
        True if all files exist, False otherwise
    """
    start_time = time.time()
    check_interval = 0.1

    while (time.time() - start_time) < max_wait:
        all_exist = all(Path(fp).exists() for fp in file_paths)
        if all_exist:
            return True
        time.sleep(check_interval)

    return all(Path(fp).exists() for fp in file_paths)


# Configuration Management APIs

config_manager = ConfigManager()


@cypress_api.route('/config/snapshot', methods=['POST'])
def save_config_snapshot():
    """
    Save current configuration as snapshot

    Request JSON:
        {
            "tool": "photo_classifier"
        }

    Response:
        {
            "snapshot_path": "/path/to/.cypress_snapshot.json",
            "snapshot_created": true,
            "timestamp": "2026-05-15T14:30:00Z"
        }
    """
    data = request.json
    tool = data.get('tool')

    if not tool:
        return jsonify({'error': 'tool parameter is required'}), 400

    try:
        result = config_manager.save_snapshot(tool)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@cypress_api.route('/config/set-test', methods=['POST'])
def set_test_config():
    """
    Set test configuration

    Request JSON:
        {
            "tool": "photo_classifier",
            "test_config": {
                "rootPath": "/path/to/cypress_test_data"
            }
        }

    Response:
        {
            "config_updated": true,
            "settings_path": "/path/to/settings.json"
        }
    """
    data = request.json
    tool = data.get('tool')
    test_config = data.get('test_config')

    if not tool or not test_config:
        return jsonify({'error': 'tool and test_config parameters are required'}), 400

    try:
        result = config_manager.set_test_config(tool, test_config)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@cypress_api.route('/config/restore', methods=['POST'])
def restore_config():
    """
    Restore configuration from snapshot

    Request JSON:
        {
            "tool": "photo_classifier"
        }

    Response:
        {
            "config_restored": true,
            "snapshot_deleted": true,
            "restored_from": "2026-05-15T14:30:00Z"
        }
    """
    data = request.json
    tool = data.get('tool')

    if not tool:
        return jsonify({'error': 'tool parameter is required'}), 400

    try:
        result = config_manager.restore_snapshot(tool)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@cypress_api.route('/config/check-snapshot', methods=['GET'])
def check_config_snapshot():
    """
    Check if snapshot exists for a tool

    Query Parameters:
        tool: Tool name (e.g., "photo_classifier")

    Response:
        {
            "has_snapshot": true,
            "tool": "photo_classifier",
            "snapshot_path": "/path/to/.cypress_snapshot.json",
            "snapshot_time": "2026-05-15T14:30:00Z"
        }
    """
    tool = request.args.get('tool')

    if not tool:
        return jsonify({'error': 'tool parameter is required'}), 400

    try:
        result = config_manager.check_snapshot(tool)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@cypress_api.route('/config/check-all-snapshots', methods=['GET'])
def check_all_snapshots():
    """
    Check for unrestored snapshots across all tools

    Response:
        {
            "unrestored": [
                {
                    "tool": "photo_classifier",
                    "snapshot_path": "/path/to/.cypress_snapshot.json",
                    "snapshot_time": "2026-05-15T14:30:00Z"
                }
            ],
            "count": 1
        }
    """
    try:
        result = config_manager.check_all_snapshots()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@cypress_api.route('/config/restore-all', methods=['POST'])
def restore_all_configs():
    """
    Restore all unrestored snapshots

    Response:
        {
            "restored": [
                {"tool": "photo_classifier", "success": true}
            ],
            "count": 1
        }
    """
    try:
        result = config_manager.restore_all_snapshots()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
