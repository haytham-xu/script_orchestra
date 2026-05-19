"""
Unzip Service - Archive Extraction Logic (Simplified)
"""
import os
import zipfile
import rarfile
import py7zr
import shutil
from typing import List, Dict


class UnzipService:
    """Service for extracting compressed archives"""

    def __init__(self, password_list: List[str] = None):
        """
        Initialize UnzipService

        Args:
            password_list: List of passwords to try for encrypted archives
        """
        self.password_list = password_list or [""]
        self._check_unrar_availability()

    def _check_unrar_availability(self):
        """Check if UnRAR is available in the system"""
        self.unrar_available = shutil.which('unrar') is not None
        if not self.unrar_available:
            print("WARNING: UnRAR not found in system PATH. RAR extraction will fail.")

    @staticmethod
    def is_archive_file(file_path: str) -> bool:
        """Check if file is a supported archive"""
        ext = os.path.splitext(file_path)[1].lower()
        return ext in ['.zip', '.rar', '.7z']

    @staticmethod
    def get_extract_folder_path(archive_path: str) -> str:
        """
        Get target extraction folder path with conflict handling

        Args:
            archive_path: Full path to the archive file

        Returns:
            Target folder path (with suffix if conflict exists)
        """
        base_dir = os.path.dirname(archive_path)
        base_name = os.path.splitext(os.path.basename(archive_path))[0]

        target_folder = os.path.join(base_dir, base_name)
        if not os.path.exists(target_folder):
            return target_folder

        suffix = 1
        while True:
            target_folder = os.path.join(base_dir, f"{base_name}_{suffix}")
            if not os.path.exists(target_folder):
                return target_folder
            suffix += 1

    @staticmethod
    def count_extracted_files(folder_path: str) -> int:
        """Count total files in extracted folder (recursive)"""
        if not os.path.exists(folder_path):
            return 0

        total_files = 0
        for root, dirs, files in os.walk(folder_path):
            total_files += len(files)
        return total_files

    def _extract_zip_with_encoding(self, archive_path: str, target_folder: str, password: str = None):
        """
        Extract ZIP with encoding fallback for Chinese filenames

        Try UTF-8 first, then fall back to GBK for Windows-created ZIPs
        """
        pwd = password.encode('utf-8') if password else None

        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            for file_info in zip_ref.infolist():
                original_name = file_info.filename

                # Try to decode filename correctly
                try:
                    # Check if filename is UTF-8 encoded (flag_bits & 0x800)
                    if file_info.flag_bits & 0x800:
                        # UTF-8 encoded, use as-is
                        filename = file_info.filename
                        print(f"[Unzip] UTF-8 flag detected: {filename}")
                    else:
                        # Non-UTF-8, try GBK (for Chinese Windows)
                        try:
                            filename = file_info.filename.encode('cp437').decode('gbk')
                            print(f"[Unzip] GBK decode: {original_name} → {filename}")
                        except:
                            # If GBK fails, try UTF-8 anyway
                            try:
                                filename = file_info.filename.encode('cp437').decode('utf-8')
                                print(f"[Unzip] UTF-8 decode: {original_name} → {filename}")
                            except:
                                # Last resort: use original
                                filename = file_info.filename
                                print(f"[Unzip] Using original: {filename}")
                except Exception as e:
                    filename = file_info.filename
                    print(f"[Unzip] Decode error, using original: {filename} ({e})")

                # Extract file
                source = zip_ref.open(file_info, pwd=pwd)
                target_path = os.path.join(target_folder, filename)

                # Create directory if needed
                target_dir = os.path.dirname(target_path)
                if target_dir:
                    os.makedirs(target_dir, exist_ok=True)

                # Write file (skip directories)
                if not file_info.is_dir():
                    with open(target_path, 'wb') as target:
                        target.write(source.read())

    @staticmethod
    def _remove_macosx_folder(folder_path: str):
        """Remove __MACOSX metadata folder created by macOS"""
        macosx_path = os.path.join(folder_path, '__MACOSX')
        if os.path.exists(macosx_path):
            print(f"[Unzip] Removing __MACOSX folder: {macosx_path}")
            shutil.rmtree(macosx_path)


    def extract_archive(self, archive_path: str, delete_after_extract: bool = True) -> Dict:
        """
        Extract a single archive file

        Args:
            archive_path: Path to archive file
            delete_after_extract: If True, delete the archive file after successful extraction (default: True)

        Returns:
            Result dictionary with success status
        """
        if not os.path.exists(archive_path):
            return {
                "success": False,
                "archivePath": archive_path,
                "error": "File not found"
            }

        if not self.is_archive_file(archive_path):
            return {
                "success": False,
                "archivePath": archive_path,
                "error": "Not a supported archive format"
            }

        target_folder = self.get_extract_folder_path(archive_path)
        os.makedirs(target_folder, exist_ok=True)

        file_ext = os.path.splitext(archive_path)[1].lower()

        # Try extraction with password list
        for idx, password in enumerate(self.password_list):
            try:
                if file_ext == ".zip":
                    # Try to extract with encoding fallback for Chinese filenames
                    self._extract_zip_with_encoding(archive_path, target_folder, password)

                elif file_ext == ".rar":
                    if not self.unrar_available:
                        return {
                            "success": False,
                            "archivePath": archive_path,
                            "error": "UnRAR not installed"
                        }
                    with rarfile.RarFile(archive_path, 'r') as rar_ref:
                        rar_ref.extractall(target_folder, pwd=password if password else None)

                elif file_ext == ".7z":
                    with py7zr.SevenZipFile(archive_path, mode='r', password=password if password else None) as sz_ref:
                        sz_ref.extractall(target_folder)

                # Remove __MACOSX folder if exists
                self._remove_macosx_folder(target_folder)

                # Count extracted files
                file_count = self.count_extracted_files(target_folder)

                # Only delete archive if extraction was successful AND files were actually extracted
                deleted = False
                if delete_after_extract and file_count > 0:
                    try:
                        os.remove(archive_path)
                        deleted = True
                        print(f"[Unzip] Deleted original archive: {archive_path} (extracted {file_count} files)")
                    except Exception as e:
                        print(f"[Unzip] Warning: Failed to delete archive: {e}")
                elif delete_after_extract and file_count == 0:
                    print(f"[Unzip] Warning: Archive extracted 0 files, keeping original: {archive_path}")

                # Extraction successful
                return {
                    "success": True,
                    "archivePath": archive_path,
                    "outputFolder": target_folder,
                    "fileCount": file_count,
                    "deleted": deleted
                }

            except (RuntimeError, rarfile.BadRarFile, py7zr.exceptions.Bad7zFile) as e:
                # Wrong password or corrupted file, try next password
                continue
            except Exception as e:
                # Other errors
                return {
                    "success": False,
                    "archivePath": archive_path,
                    "error": str(e)
                }

        # All passwords failed
        return {
            "success": False,
            "archivePath": archive_path,
            "error": "Password required or incorrect password"
        }

    def extract_from_path(self, input_path: str, delete_after_extract: bool = True) -> Dict:
        """
        Extract archive(s) from file or folder path

        Args:
            input_path: Path to archive file or folder
            delete_after_extract: If True, delete archive files after successful extraction (default: True)

        Returns:
            Summary dictionary
        """
        if not os.path.exists(input_path):
            return {
                "success": 0,
                "failed": 0,
                "message": f"Path not found: {input_path}"
            }

        archive_files = []

        # Case 1: Input is a file
        if os.path.isfile(input_path):
            if self.is_archive_file(input_path):
                archive_files.append(input_path)
            else:
                return {
                    "success": 0,
                    "failed": 0,
                    "message": f"Not a supported archive: {input_path}"
                }

        # Case 2: Input is a folder (scan only current level, no recursion)
        elif os.path.isdir(input_path):
            for filename in os.listdir(input_path):
                file_path = os.path.join(input_path, filename)
                if os.path.isfile(file_path) and self.is_archive_file(file_path):
                    archive_files.append(file_path)

            if len(archive_files) == 0:
                return {
                    "success": 0,
                    "failed": 0,
                    "message": f"No archives found in folder: {input_path}"
                }

        # Extract all found archives
        success_count = 0
        failed_count = 0

        for archive_path in archive_files:
            print(f"[Unzip] Extracting: {archive_path}")
            result = self.extract_archive(archive_path, delete_after_extract)

            if result["success"]:
                success_count += 1
                print(f"[Unzip] ✓ Success: {archive_path}")
            else:
                failed_count += 1
                print(f"[Unzip] ✗ Failed: {archive_path} - {result.get('error', 'Unknown error')}")

        # Build summary message
        if failed_count == 0:
            message = f"Successfully extracted {success_count} archive(s)"
        elif success_count == 0:
            message = f"Failed to extract {failed_count} archive(s)"
        else:
            message = f"Extracted {success_count} archive(s), {failed_count} failed"

        return {
            "success": success_count,
            "failed": failed_count,
            "message": message
        }
