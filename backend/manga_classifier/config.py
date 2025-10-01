HOST_URL = 'http://127.0.0.1:5000'
ROOT_PATH = ''
TARGET_PATHS = ''
DELETE_PATHS = ''
CATEGOTY = {}

IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')
VIDEO_EXTS = ('.mp4', '.webm', '.mov', '.avi', '.mkv')

try:
    from manga_classifier.config_local import *
except ImportError:
    print("⚠️ Don't find config_local.py, use the defaut value.")
