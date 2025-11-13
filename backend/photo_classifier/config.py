import json
import os

HOST_URL = 'http://127.0.0.1:5000'
ROOT_PATH = ''

IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')
VIDEO_EXTS = ('.mp4', '.webm', '.mov', '.avi', '.mkv')

# try:
#     from photo_classifier.config_local import *
# except ImportError:
#     print("⚠️ Don't find config_local.py, use the defaut value.")

# CONFIG_LOCAL_FILE = os.path.join(os.path.dirname(__file__), "config_local.json")
CONFIG_LOCAL_FILE = "./photo_classifier/config_local.json"

def refresh_config():
    if os.path.exists(CONFIG_LOCAL_FILE):
        with open(CONFIG_LOCAL_FILE, "r", encoding="utf-8") as f:
            try:
                local_config = json.load(f)
                globals().update(local_config)
                print("==> Hi: ", local_config)
            except json.JSONDecodeError:
                print("⚠️ config_local.json parse failed.")

refresh_config()
