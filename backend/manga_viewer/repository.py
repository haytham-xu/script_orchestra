import os
import json
import uuid
from basic.flex_sort import flex_natsort
from manga_viewer.model.metadata import Metadata
from manga_viewer.model.manga_index import MangaIndex
from manga_viewer.model.folder import Folder
from manga_viewer.model.tag import Tag
from manga_viewer.settings_manager import settings_manager
from manga_viewer import config
from urllib.parse import quote

class Repository:
    manga_index: MangaIndex = None

    @staticmethod
    def get_index_path():
        """Index file path, derived from root_path: <root>/.manga_index/manga_index.json."""
        index_dir = settings_manager.get_index_path_derived()
        if not index_dir:
            raise ValueError("Root path not configured in settings")
        return os.path.join(index_dir, "manga_index.json")

    @staticmethod
    def get_scan_targets():
        """Derive the scan source from category main×sub combinations.

        For every (main, sub) pair, the target dir is
        ``<root>/<main.path>/<sub.path>``. Only existing directories are
        returned (missing combinations are silently skipped), and any dir in
        ignore_scan_folders is excluded.

        Returns a list of (dir_path, main_key, sub_key).
        """
        root = Repository.get_root_path()
        if not root:
            return []
        cats = settings_manager.get_categories()
        ignore = {os.path.normcase(os.path.abspath(p))
                  for p in Repository.get_ignore_scan_paths() if p}
        targets = []
        for m in cats.get("main", []):
            if not m.get("path"):
                continue
            for s in cats.get("sub", []):
                if not s.get("path"):
                    continue
                combo = os.path.join(root, m["path"], s["path"])
                if not os.path.isdir(combo):
                    continue  # silently skip missing combos
                if os.path.normcase(os.path.abspath(combo)) in ignore:
                    continue
                targets.append((combo, m["key"], s["key"]))
        return targets

    @staticmethod
    def get_ignore_scan_paths():
        """Get ignore scan paths from settings."""
        return settings_manager.get_setting('paths.ignore_scan_folders', [])

    @staticmethod
    def get_root_path():
        """Get root path from settings."""
        return settings_manager.get_setting('paths.root_path', '')

    @staticmethod
    def load_index():
        index_path = Repository.get_index_path()
        if not os.path.exists(index_path):
            Repository.manga_index = MangaIndex()
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            Repository.manga_index = MangaIndex.from_dict(data)
        except (json.JSONDecodeError, OSError):
            Repository.manga_index = MangaIndex()
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(
                    Repository.manga_index.to_dict(), f, ensure_ascii=False, indent=2
                )

    @staticmethod
    def save_index():
        index_path = Repository.get_index_path()
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        with open(index_path, "w", encoding="utf-8") as f:
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
                ) or lower.endswith(config.PDF_EXTS):
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

        root_abs = os.path.abspath(Repository.get_root_path())

        root_files = [f for f in entries if os.path.isfile(os.path.join(folder_path, f))]
        for fname in flex_natsort(root_files):
            lower = fname.lower()
            if lower.endswith(config.IMAGE_EXTS) or lower.endswith(config.VIDEO_EXTS) or lower.endswith(config.PDF_EXTS):
                full_path = os.path.join(folder_path, fname)
                try:
                    rel_path = os.path.relpath(full_path, root_abs)
                    rel_for_url = rel_path.replace(os.sep, "/")
                    file_url = f"{config.HOST_URL}/manga-viewer/file/{quote(rel_for_url)}"
                    file_list.append(file_url)
                except OSError:
                    pass

        subdirs = [d for d in entries if os.path.isdir(os.path.join(folder_path, d))]
        for dname in flex_natsort(subdirs):
            subdir_path = os.path.join(folder_path, dname)
            try:
                sub_entries = os.listdir(subdir_path)
            except OSError:
                continue
            sub_files = [
                sf for sf in sub_entries if os.path.isfile(os.path.join(subdir_path, sf))
            ]
            for sf in flex_natsort(sub_files):
                lower = sf.lower()
                if lower.endswith(config.IMAGE_EXTS) or lower.endswith(config.VIDEO_EXTS) or lower.endswith(config.PDF_EXTS):
                    full_path = os.path.join(subdir_path, sf)
                    try:
                        rel_path = os.path.relpath(full_path, root_abs)
                        rel_for_url = rel_path.replace(os.sep, "/")
                        file_url = f"{config.HOST_URL}/manga-viewer/file/{quote(rel_for_url)}"
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

        # Scan source is derived from category main×sub combinations. Each
        # combo dir's direct children are manga folders, and their category
        # is known from the combo itself (no inference needed).
        # existing: list of (manga_path, main_key, sub_key)
        existing = []
        existing_paths = []
        # Normalize ignore entries the same way we normalize scanned paths, so
        # the comparison is case-insensitive and separator/abspath-consistent
        # (Windows filesystems are case-insensitive; users may enter forward
        # slashes or relative paths).
        ignore = {os.path.normcase(os.path.abspath(p))
                  for p in Repository.get_ignore_scan_paths() if p}
        for combo_dir, main_key, sub_key in Repository.get_scan_targets():
            for a_name in os.listdir(combo_dir):
                a_folder_path = os.path.join(combo_dir, a_name)
                if (os.path.isdir(a_folder_path)
                        and os.path.normcase(os.path.abspath(a_folder_path)) not in ignore):
                    existing.append((a_folder_path, main_key, sub_key))
                    existing_paths.append(a_folder_path)

        for folder_id, folder_instance in list(Repository.manga_index.folders.items()):
            if folder_instance.path not in existing_paths:
                del Repository.manga_index.folders[folder_id]

        for a_folder_path, main_key, sub_key in existing:
            if a_folder_path in path_id_map:
                # Existing folder: refresh metrics only, never overwrite tags
                # (protects user's manual classification / labels).
                folder_id = path_id_map[a_folder_path]
                folder_instance = Repository.manga_index.folders[folder_id]
                size, number = Repository.get_size_number(a_folder_path)
                folder_instance.size = size
                folder_instance.number = number
                folder_instance.file_list = Repository.get_files_url_list(a_folder_path)
            else:
                # New folder: category is inferred from the combo dir it lives in.
                size, number = Repository.get_size_number(a_folder_path)
                folder_id = str(uuid.uuid4())
                new_folder = Folder(
                    id_=folder_id,
                    name=os.path.basename(a_folder_path),
                    path=a_folder_path,
                    file_list=Repository.get_files_url_list(a_folder_path),
                    size=size,
                    number=number,
                    initialized=bool(main_key or sub_key),
                    tags=Tag(category_main=main_key, category_sub=sub_key),
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
