from flask_restx import Namespace, Resource
from flask import send_file, request
from . import config
import os
from PIL import Image
import hashlib
from pathlib import Path

ns = Namespace("")

# Cache directory for thumbnails
CACHE_DIR = Path(__file__).parent / '.thumbnail_cache'
CACHE_DIR.mkdir(exist_ok=True)

def get_thumbnail_cache_path(file_path: str, size: int) -> Path:
    """Generate cache file path based on original file path and size"""
    # Create a hash of the file path and modification time
    stat = os.stat(file_path)
    cache_key = f"{file_path}_{stat.st_mtime}_{size}"
    cache_hash = hashlib.md5(cache_key.encode()).hexdigest()
    return CACHE_DIR / f"{cache_hash}.jpg"

@ns.route("/file/<path:filepath>")
class FileResource(Resource):

    def get(self, filepath):
        # Support dynamic root path from query parameter
        root_path = request.args.get('rootPath') or config.get_root_path()
        thumbnail = request.args.get('thumbnail', 'false').lower() == 'true'
        thumbnail_size = int(request.args.get('size', '300'))

        if not root_path:
            return {"error": "Root path not configured"}, 400

        # Prevent path traversal attacks
        # Normalize the path and ensure it doesn't escape the root directory
        filepath = os.path.normpath(filepath)
        if filepath.startswith('..') or os.path.isabs(filepath):
            return {"error": "Invalid file path"}, 400

        file_path = os.path.join(root_path, filepath)

        # Double check the resolved path is within the root directory
        real_root = os.path.realpath(root_path)
        real_path = os.path.realpath(file_path)
        if not real_path.startswith(real_root):
            return {"error": "Access denied"}, 403

        if not os.path.exists(file_path):
            return {"error": "File not found"}, 404

        if not os.path.isfile(file_path):
            return {"error": "Not a file"}, 400

        # If thumbnail is requested and file is an image
        if thumbnail and file_path.lower().endswith(config.IMAGE_EXTS):
            try:
                # Check cache first
                cache_path = get_thumbnail_cache_path(file_path, thumbnail_size)
                if cache_path.exists():
                    return send_file(str(cache_path), mimetype='image/jpeg')

                # Generate thumbnail
                img = Image.open(file_path)

                # Convert RGBA to RGB if needed
                if img.mode == 'RGBA':
                    img = img.convert('RGB')

                # Resize maintaining aspect ratio
                img.thumbnail((thumbnail_size, thumbnail_size), Image.Resampling.LANCZOS)

                # Save to cache
                img.save(str(cache_path), 'JPEG', quality=85)

                # Return cached file
                return send_file(str(cache_path), mimetype='image/jpeg')
            except Exception as e:
                # If thumbnail generation fails, fall back to original file
                print(f"Thumbnail generation failed: {e}")
                return send_file(file_path)

        # send_file already returns a Response object, no need to wrap it
        return send_file(file_path)
