import os
import json
import uuid
import config
from basic.flex_sort import flex_natsort
from manga_viewer.model.metadata import Metadata
from manga_viewer.model.manga_index import MangaIndex
from manga_viewer.model.folder import Folder
from manga_viewer.model.tag import Tag
from urllib.parse import quote


class Repository:
    manga_index: MangaIndex = None
    index_path = os.path.join(config.MANGA_VIEWER_ROOT_PATH, "manga_index.json")
    scan_paths = config.MANGA_VIEWER_SCAN_FOLDER
    ignore_scan_paths = config.MANGA_VIEWER_IGNORE_SCAN_FOLDER

    @staticmethod
    def load_index():
        if not os.path.exists(Repository.index_path):
            Repository.manga_index = MangaIndex()
        try:
            with open(Repository.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            Repository.manga_index = MangaIndex.from_dict(data)
        except (json.JSONDecodeError, OSError):
            Repository.manga_index = MangaIndex()
            with open(Repository.index_path, "w", encoding="utf-8") as f:
                json.dump(
                    Repository.manga_index.to_dict(), f, ensure_ascii=False, indent=2
                )

    @staticmethod
    def save_index():
        os.makedirs(os.path.dirname(Repository.index_path), exist_ok=True)
        with open(Repository.index_path, "w", encoding="utf-8") as f:
            json.dump(Repository.manga_index.to_dict(), f, ensure_ascii=False, indent=2)

    @staticmethod
    def get_size_number(folder_path: str):
        total_size = 0
        total_files = 0
        for base_path, _, files in os.walk(folder_path):
            for a_file_name in files:
                lower = a_file_name.lower()
                if lower.endswith(config.IMAGE_EXTS) or lower.endswith(
                    config.VIDEO_EXTS
                ):
                    a_file_path = os.path.join(base_path, a_file_name)
                    try:
                        a_file_stats = os.stat(a_file_path)
                        total_size += a_file_stats.st_size
                        total_files += 1
                    except OSError:
                        pass
        return total_size, total_files

    @staticmethod
    def get_files_url_list(folder_path: str):
        file_list = []
        if not os.path.isdir(folder_path):
            return file_list

        try:
            entries = os.listdir(folder_path)
        except OSError:
            return file_list

        root_files = [
            f for f in entries if os.path.isfile(os.path.join(folder_path, f))
        ]
        for fname in flex_natsort(root_files):
            lower = fname.lower()
            if lower.endswith(config.IMAGE_EXTS) or lower.endswith(config.VIDEO_EXTS):
                full_path = os.path.join(folder_path, fname)
                try:
                    rel_for_url = full_path.lstrip(os.sep)
                    file_url = (
                        f"{config.HOST_URL}/manga-viewer/file/{quote(rel_for_url)}"
                    )
                    file_list.append(file_url)
                except OSError:
                    pass

        subdirs = [d for d in entries if os.path.isdir(os.path.join(folder_path, d))]
        print(flex_natsort(subdirs))
        for dname in flex_natsort(subdirs):
            subdir_path = os.path.join(folder_path, dname)
            try:
                sub_entries = os.listdir(subdir_path)
            except OSError:
                continue
            sub_files = [
                sf
                for sf in sub_entries
                if os.path.isfile(os.path.join(subdir_path, sf))
            ]
            for sf in flex_natsort(sub_files):
                lower = sf.lower()
                if lower.endswith(config.IMAGE_EXTS) or lower.endswith(
                    config.VIDEO_EXTS
                ):
                    full_path = os.path.join(subdir_path, sf)
                    try:
                        rel_for_url = full_path.lstrip(os.sep)
                        file_url = (
                            f"{config.HOST_URL}/manga-viewer/file/{quote(rel_for_url)}"
                        )
                        file_list.append(file_url)
                    except OSError:
                        pass

        return file_list

    # refresh will sepend lots of time, so only run manually.
    @staticmethod
    def refresh_index():
        Repository.load_index()

        path_id_map = {
            folder_instance.path: folder_id
            for folder_id, folder_instance in Repository.manga_index.folders.items()
        }

        existing_paths = []
        for to_scan_path in Repository.scan_paths:
            if not to_scan_path or not os.path.isdir(to_scan_path):
                continue
            for a_name in os.listdir(to_scan_path):
                a_folder_path = os.path.join(to_scan_path, a_name)
                if (
                    os.path.isdir(a_folder_path)
                    and a_folder_path not in Repository.ignore_scan_paths
                ):
                    existing_paths.append(a_folder_path)

        for folder_id, folder_instance in list(Repository.manga_index.folders.items()):
            if folder_instance.path not in existing_paths:
                del Repository.manga_index.folders[folder_id]

        for a_folder_path in existing_paths:
            if a_folder_path in path_id_map:

                folder_id = path_id_map[a_folder_path]
                folder_instance = Repository.manga_index.folders[folder_id]
                size, number = Repository.get_size_number(a_folder_path)
                folder_instance.size = size
                folder_instance.number = number
                folder_instance.file_list = Repository.get_files_url_list(a_folder_path)
            else:
                size, number = Repository.get_size_number(a_folder_path)
                folder_id = str(uuid.uuid4())
                new_folder = Folder(
                    id_=folder_id,
                    name=os.path.basename(a_folder_path),
                    path=a_folder_path,
                    file_list=Repository.get_files_url_list(a_folder_path),
                    size=size,
                    number=number,
                    initialized=False,
                    tags=Tag(),
                )
                Repository.manga_index.folders[folder_id] = new_folder
                path_id_map[a_folder_path] = folder_id

        auth_set, cat_main_set, cat_sub_set = set(), set(), set()
        for folder_instance in Repository.manga_index.folders.values():
            for a_auth in folder_instance.tags.auth:
                auth_set.add(a_auth)
            if folder_instance.tags.category_main:
                cat_main_set.add(folder_instance.tags.category_main)
            if folder_instance.tags.category_sub:
                cat_sub_set.add(folder_instance.tags.category_sub)
        Repository.manga_index.metadata = Metadata(
            auth=sorted(auth_set),
            category_main=sorted(cat_main_set),
            category_sub=sorted(cat_sub_set),
        )
        Repository.save_index()

    @staticmethod
    def update_folder(folder_id: str, new_folder_instance: Folder):
        db_folder_index = Repository.manga_index.folders.get(folder_id)
        if not db_folder_index:
            return

        # update name and path
        if (
            new_folder_instance.name
            and new_folder_instance.name != db_folder_index.name
        ):
            old_path = db_folder_index.path
            parent = os.path.dirname(old_path)
            new_path = os.path.join(parent, new_folder_instance.name)
            if os.path.exists(new_path):
                return
            try:
                os.rename(old_path, new_path)
            except OSError:
                raise Exception("Failed to rename folder.")
            db_folder_index.name = new_folder_instance.name
            db_folder_index.path = new_path

        # update tags
        if hasattr(new_folder_instance, "tags") and new_folder_instance.tags:
            for k, v in vars(new_folder_instance.tags).items():
                if hasattr(db_folder_index.tags, k):
                    setattr(db_folder_index.tags, k, v)

        # update metadata
        size, number = Repository.get_size_number(db_folder_index.path)
        db_folder_index.size = size
        db_folder_index.number = number
        db_folder_index.file_list = Repository.get_files_url_list(db_folder_index.path)

        # update metadata
        auth_set, cat_main_set, cat_sub_set = set(), set(), set()
        for folder_instance in Repository.manga_index.folders.values():
            for a_auth in folder_instance.tags.auth:
                auth_set.add(a_auth)
            if folder_instance.tags.category_main:
                cat_main_set.add(folder_instance.tags.category_main)
            if folder_instance.tags.category_sub:
                cat_sub_set.add(folder_instance.tags.category_sub)
        Repository.manga_index.metadata = Metadata(
            auth=sorted(auth_set),
            category_main=sorted(cat_main_set),
            category_sub=sorted(cat_sub_set),
        )

        Repository.save_index()
