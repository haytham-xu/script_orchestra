"""
Manga Viewer Configuration

Tool-specific configuration file for manga viewer module.
All user settings are managed through manga_viewer_settings.json
"""
from . import settings_manager

# API Configuration
HOST_URL = 'http://127.0.0.1:5001'

# File type extensions
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')
VIDEO_EXTS = ('.mp4', '.webm', '.mov', '.avi', '.mkv')
PDF_EXTS = ('.pdf',)
