"""
Photo Classifier Configuration

Independent configuration file for photo classifier module.
All user settings are managed through user_settings.json
"""
from . import settings_manager

# API Configuration
HOST_URL = 'http://127.0.0.1:5001'

# File type extensions
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.heic')
VIDEO_EXTS = ('.mp4', '.webm', '.mov', '.avi', '.mkv')

# Root path - dynamically loaded from user_settings.json
def get_root_path():
    """Get root path dynamically from settings"""
    return settings_manager.get_root_path()

# For backward compatibility
PHOTO_CLASSIFIER_ROOT_PATH = get_root_path()
