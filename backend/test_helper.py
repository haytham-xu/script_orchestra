"""
Test Helper for Photo Classifier E2E Tests

This script provides utilities to:
1. Create test directories and dummy image files
2. Clean up test data after tests
3. Verify file movements after operations
"""

import os
import shutil
import sys
from pathlib import Path
from PIL import Image
import json

# Base test directory
BACKEND_DIR = Path(__file__).parent.parent.parent
TEST_BASE_DIR = BACKEND_DIR / "photo_classifier" / "tmp"


def create_test_directory(test_name: str) -> str:
    """
    Create a test directory under backend/photo_classifier/tmp

    Args:
        test_name: Name of the test (will be used as folder name)

    Returns:
        Absolute path to the created test directory
    """
    # Ensure tmp directory exists
    TEST_BASE_DIR.mkdir(parents=True, exist_ok=True)

    # Create test-specific directory
    test_dir = TEST_BASE_DIR / test_name
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)

    return str(test_dir.absolute())


def create_dummy_images(test_dir: str, count: int, prefix: str = "test_image") -> list:
    """
    Create dummy image files for testing

    Args:
        test_dir: Directory where images should be created
        count: Number of images to create
        prefix: Prefix for image filenames

    Returns:
        List of created image file paths
    """
    test_path = Path(test_dir)
    image_paths = []

    for i in range(count):
        filename = f"{prefix}_{i+1:03d}.jpg"
        filepath = test_path / filename

        # Create a simple colored image (different color for each image)
        # This makes each image unique
        img = Image.new('RGB', (800, 600), color=(100 + i * 20, 150 + i * 15, 200 + i * 10))
        img.save(filepath, 'JPEG')

        image_paths.append(str(filepath.absolute()))

    return image_paths


def cleanup_test_data(test_name: str = None):
    """
    Clean up test data

    Args:
        test_name: Specific test directory to clean. If None, clean entire tmp folder
    """
    if test_name:
        test_dir = TEST_BASE_DIR / test_name
        if test_dir.exists():
            shutil.rmtree(test_dir)
    else:
        if TEST_BASE_DIR.exists():
            shutil.rmtree(TEST_BASE_DIR)


def verify_file_distribution(test_dir: str) -> dict:
    """
    Verify file distribution in category folders

    Args:
        test_dir: Test directory to check

    Returns:
        Dictionary with category counts: {'best': 1, 'better': 2, 'normal': 3, ...}
    """
    test_path = Path(test_dir)
    categories = ['best', 'better', 'normal', 'del']

    result = {}
    for category in categories:
        category_path = test_path / category
        if category_path.exists() and category_path.is_dir():
            files = [f for f in category_path.iterdir() if f.is_file()]
            result[category] = len(files)
        else:
            result[category] = 0

    # Count remaining files in root
    root_files = [f for f in test_path.iterdir() if f.is_file()]
    result['remaining'] = len(root_files)

    return result


def main():
    """
    Command-line interface for test helper

    Usage:
        python test_helper.py create_dir <test_name>
        python test_helper.py create_images <test_dir> <count>
        python test_helper.py cleanup [test_name]
        python test_helper.py verify <test_dir>
    """
    if len(sys.argv) < 2:
        print("Usage: python test_helper.py <command> [args...]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "create_dir":
        test_name = sys.argv[2] if len(sys.argv) > 2 else "default_test"
        test_dir = create_test_directory(test_name)
        print(json.dumps({"test_dir": test_dir}))

    elif command == "create_images":
        test_dir = sys.argv[2]
        count = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        image_paths = create_dummy_images(test_dir, count)
        print(json.dumps({"image_paths": image_paths}))

    elif command == "cleanup":
        test_name = sys.argv[2] if len(sys.argv) > 2 else None
        cleanup_test_data(test_name)
        print(json.dumps({"status": "cleaned"}))

    elif command == "verify":
        test_dir = sys.argv[2]
        result = verify_file_distribution(test_dir)
        print(json.dumps(result))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
