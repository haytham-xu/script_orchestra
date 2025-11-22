
from manga_viewer.repository import Repository
import os
import config

if __name__ == "__main__":
    index_path = os.path.join(config.MANGA_VIEWER_INDEX_PATH, "manga_index.json")
    if os.path.exists(index_path):
        os.remove(index_path)
    Repository.refresh_index()

