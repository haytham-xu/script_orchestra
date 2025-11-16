
from manga_viewer.model.metadata import Metadata
from manga_viewer.model.folder import Folder
from typing import Dict

class MangaIndex:
    def __init__(self):
        self.metadata: Metadata = Metadata()
        self.folders: Dict[str, Folder] = {}  # key = folder id

    def to_dict(self):
        return {
            "metadata": self.metadata.to_dict(),
            "folders": {fid: f.to_dict() for fid, f in self.folders.items()}
        }

    @staticmethod
    def from_dict(d: Dict):
        manga_index = MangaIndex()
        manga_index.metadata = Metadata.from_dict(d.get("metadata", {}))
        raw_folders = d.get("folders", {})
        for folder_id, folder_instance in raw_folders.items():
            manga_index.folders[folder_id] = Folder.from_dict(folder_instance)
        return manga_index
