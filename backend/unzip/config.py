"""
Unzip Module Configuration
"""
import os

# Base directory for unzip module
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Default password list (empty password = no password)
PASSWORD_LIST = [""]

# Try to import local configuration (not tracked in git)
try:
    from unzip.config_local import PASSWORD_LIST as LOCAL_PASSWORD_LIST
    PASSWORD_LIST = LOCAL_PASSWORD_LIST
    print(f"Loaded {len(LOCAL_PASSWORD_LIST)} passwords from config_local.py")
except ImportError:
    print("No local password config found. Using default (no password only).")
    pass

# Supported archive formats
SUPPORTED_FORMATS = {
    '.zip': 'ZIP',
    '.rar': 'RAR',
    '.7z': '7Z'
}
