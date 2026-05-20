#!/usr/bin/env python3
"""
Quick test script to verify Cypress Support API is working

Usage:
    python backend/cypress_support/test_api_manual.py
"""

import requests
import json
import time

BASE_URL = "http://localhost:5001/api/cypress"

def print_header(text):
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60)

def test_health_check():
    print_header("1. Health Check")
    response = requests.get(f"{BASE_URL}/health")
    data = response.json()
    print(f"Status: {data['status']}")
    print(f"Message: {data['message']}")
    assert data['status'] == 'ok'
    print("✅ Health check passed")

def test_create_directory():
    print_header("2. Create Test Directory")
    response = requests.post(f"{BASE_URL}/create-test-dir", json={
        "test_name": "manual_test_001"
    })
    data = response.json()
    print(f"Test Dir: {data['test_dir']}")
    print(f"Exists: {data['exists']}")
    assert data['exists'] == True
    print("✅ Directory created successfully")
    return data['test_dir']

def test_create_images(test_dir):
    print_header("3. Create Test Images")
    response = requests.post(f"{BASE_URL}/create-media", json={
        "test_dir": test_dir,
        "images": 3,
        "videos": 0,
        "prefix": "img",
        "test_name": "manual_test_001"
    })
    data = response.json()
    print(f"Images Created: {len(data['image_paths'])}")
    print(f"Videos Created: {len(data['video_paths'])}")
    print(f"Total: {data['total_created']}")
    print(f"All Verified: {data['all_verified']}")
    assert len(data['image_paths']) == 3
    assert data['all_verified'] == True
    print("✅ Images created and verified")
    return data['image_paths']

def test_create_videos(test_dir):
    print_header("4. Create Test Videos")
    response = requests.post(f"{BASE_URL}/create-media", json={
        "test_dir": test_dir,
        "images": 0,
        "videos": 2,
        "prefix": "vid",
        "test_name": "manual_test_001"
    })
    data = response.json()
    print(f"Images Created: {len(data['image_paths'])}")
    print(f"Videos Created: {len(data['video_paths'])}")
    print(f"Total: {data['total_created']}")
    print(f"All Verified: {data['all_verified']}")
    assert len(data['video_paths']) == 2
    assert data['all_verified'] == True
    print("✅ Videos created and verified")
    return data['video_paths']

def test_check_files(file_paths):
    print_header("5. Check Files Exist")
    response = requests.post(f"{BASE_URL}/check-files", json={
        "file_paths": file_paths,
        "wait_timeout": 5000
    })
    data = response.json()
    print(f"All Exist: {data['all_exist']}")
    print(f"Wait Time: {data['wait_time_ms']}ms")
    print(f"Missing: {data['missing']}")
    assert data['all_exist'] == True
    print("✅ All files verified")

def test_check_directory(test_dir):
    print_header("6. Check Directory")
    response = requests.post(f"{BASE_URL}/check-directory", json={
        "directory": test_dir,
        "expected_files": 5,
        "wait_timeout": 5000
    })
    data = response.json()
    print(f"Exists: {data['exists']}")
    print(f"File Count: {data['file_count']}")
    print(f"Files: {', '.join(data['files'])}")
    print(f"Matches Expected: {data['matches_expected']}")
    assert data['matches_expected'] == True
    print("✅ Directory check passed")

def test_cleanup():
    print_header("7. Cleanup Test Data")
    response = requests.post(f"{BASE_URL}/cleanup", json={
        "test_name": "manual_test_001"
    })
    data = response.json()
    print(f"Status: {data['status']}")
    print(f"Message: {data['message']}")
    print(f"Path: {data['path']}")
    assert data['status'] == 'cleaned'
    print("✅ Cleanup successful")

def main():
    print("\n🚀 Testing Cypress Support API")
    print("=" * 60)
    print("Make sure backend is running on http://localhost:5001")
    print("=" * 60)

    try:
        # Test sequence
        test_health_check()
        test_dir = test_create_directory()
        image_paths = test_create_images(test_dir)
        video_paths = test_create_videos(test_dir)
        all_paths = image_paths + video_paths
        test_check_files(all_paths)
        test_check_directory(test_dir)
        test_cleanup()

        # Success
        print("\n" + "="*60)
        print("  ✅ ALL TESTS PASSED!")
        print("="*60)
        print("\nCypress Support API is working correctly.")
        print("You can now run Cypress E2E tests.\n")

    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to backend")
        print("   Make sure Flask is running: python backend/app.py")
        exit(1)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    main()
