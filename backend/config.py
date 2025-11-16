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

try:
    from config_local import *
except ImportError:
    print("⚠️ Don't find config_local.py, use the defaut value.")
