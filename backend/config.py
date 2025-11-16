import json
import os

HOST_URL = 'http://127.0.0.1:5000'
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')
VIDEO_EXTS = ('.mp4', '.webm', '.mov', '.avi', '.mkv')


MANGA_CLASSIFIER_ROOT_PATH = ''
MANGA_CLASSIFIER_TARGET_PATHS = ''
MANGA_CLASSIFIER_DELETE_PATHS = ''
MANGA_CLASSIFIER_CATEGOTY = {}

PHOTO_CLASSIFIER_ROOT_PATH = ''

MANGA_VIEWER_ROOT_PATH = ''
MANGA_VIEWER_SCAN_FOLDER = []
MANGA_VIEWER_IGNORE_SCAN_FOLDER = []
MANGA_VIEWER_HOT_TAGS = []

def refresh_config():
    CONFIG_LOCAL_FILE = "./config_local.json"
    if os.path.exists(CONFIG_LOCAL_FILE):
        with open(CONFIG_LOCAL_FILE, "r", encoding="utf-8") as f:
            try:
                local_config = json.load(f)
                globals().update(local_config)
            except json.JSONDecodeError:
                print("⚠️ config_local.json parse failed.")

refresh_config()