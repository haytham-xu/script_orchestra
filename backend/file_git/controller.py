"""
File-Git Controller - RESTful API for repository management
"""
import os
from flask import request
from flask_restx import Namespace, Resource
from extensions import restx_api
from .repository_manager import RepositoryManager
from .settings_manager import SettingsManager
from .file_index_service import FileIndexService
from .sync_service import SyncService

ns = Namespace("")


@ns.route('/file-git/repos')
class ReposListResource(Resource):
    def get(self):
        """List all repositories"""
        try:
            repos = RepositoryManager.list_repos()
            return {
                "success": True,
                "repos": repos
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }, 500

    def post(self):
        """Add new repository"""
        try:
            data = request.get_json()

            if not data or 'local_path' not in data:
                return {
                    "success": False,
                    "error": "Missing 'local_path' parameter"
                }, 400

            if 'mode' not in data:
                return {
                    "success": False,
                    "error": "Missing 'mode' parameter"
                }, 400

            local_path = data['local_path']
            mode = data['mode']
            skip_init = data.get('skip_init', False)  # Optional: default False

            repo = RepositoryManager.add_repo(local_path, mode, skip_init)

            action = "imported" if skip_init else "added"
            return {
                "success": True,
                "repo": repo,
                "message": f"Repository '{repo['name']}' {action} successfully"
            }

        except ValueError as e:
            return {
                "success": False,
                "error": str(e)
            }, 400
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }, 500


@ns.route('/file-git/repos/<string:repo_id>')
class RepoResource(Resource):
    def get(self, repo_id):
        """Get repository details"""
        try:
            repo = RepositoryManager.get_repo_by_id(repo_id)
            if not repo:
                return {
                    "success": False,
                    "error": "Repository not found"
                }, 404

            return {
                "success": True,
                "repo": repo
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }, 500

    def delete(self, repo_id):
        """Delete repository from registry"""
        try:
            success = RepositoryManager.delete_repo(repo_id)

            if not success:
                return {
                    "success": False,
                    "error": "Repository not found"
                }, 404

            return {
                "success": True,
                "message": "Repository deleted successfully"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }, 500


@ns.route('/file-git/repos/<string:repo_id>/open-folder')
class RepoOpenFolderResource(Resource):
    def post(self, repo_id):
        """Open repository folder in system file manager"""
        try:
            import subprocess
            import platform

            repo = RepositoryManager.get_repo_by_id(repo_id)
            if not repo:
                return {
                    "success": False,
                    "error": "Repository not found"
                }, 404

            local_path = repo['local_path']

            # Open folder based on OS
            system = platform.system()
            if system == 'Darwin':  # macOS
                subprocess.Popen(['open', local_path])
            elif system == 'Windows':
                subprocess.Popen(['explorer', local_path])
            elif system == 'Linux':
                subprocess.Popen(['xdg-open', local_path])
            else:
                return {
                    "success": False,
                    "error": f"Unsupported operating system: {system}"
                }, 400

            return {
                "success": True,
                "message": "Folder opened successfully"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }, 500


@ns.route('/file-git/repos/<string:repo_id>/status')
class RepoStatusResource(Resource):
    def get(self, repo_id):
        """Get repository file status (added/modified/deleted)"""
        try:
            repo = RepositoryManager.get_repo_by_id(repo_id)
            if not repo:
                return {
                    "success": False,
                    "error": "Repository not found"
                }, 404

            local_path = repo['local_path']

            # Scan and compare files
            status = FileIndexService.get_repo_status(local_path)

            return {
                "success": True,
                "status": status
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }, 500


@ns.route('/file-git/settings')
class SettingsResource(Resource):
    def get(self):
        """Get global settings"""
        try:
            settings = SettingsManager.get_settings()
            return {
                "success": True,
                "settings": settings
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }, 500

    def put(self):
        """Update global settings"""
        try:
            data = request.get_json()
            if not data:
                return {
                    "success": False,
                    "error": "Missing settings data"
                }, 400

            settings = SettingsManager.update_settings(data)
            return {
                "success": True,
                "settings": settings,
                "message": "Settings updated successfully"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }, 500


@ns.route('/file-git/repos/<string:repo_id>/push')
class RepoPushResource(Resource):
    def post(self, repo_id):
        """Push changes to cloud"""
        try:
            repo = RepositoryManager.get_repo_by_id(repo_id)
            if not repo:
                return {
                    "success": False,
                    "error": "Repository not found"
                }, 404

            # Update status to syncing
            RepositoryManager.update_status(repo_id, 'syncing')

            local_path = repo['local_path']

            # Read remote path from config
            config_path = os.path.join(local_path, '.fgit', 'config.json')
            if not os.path.exists(config_path):
                RepositoryManager.update_status(repo_id, 'error')
                return {
                    "success": False,
                    "error": "Repository not configured. Please set remote_path in config.json"
                }, 400

            import json
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            remote_path = config.get('remote_path')
            if not remote_path:
                RepositoryManager.update_status(repo_id, 'error')
                return {
                    "success": False,
                    "error": "remote_path not configured in config.json"
                }, 400

            # Get changes
            status = FileIndexService.get_repo_status(local_path)

            # Check if there are any changes
            has_changes = (
                len(status['added']) > 0 or
                len(status['modified']) > 0 or
                len(status['deleted']) > 0
            )

            if not has_changes:
                RepositoryManager.update_status(repo_id, 'ready')
                return {
                    "success": True,
                    "message": "No changes to push",
                    "uploaded": 0,
                    "deleted": 0
                }

            # Push changes
            result = SyncService.push_changes(local_path, remote_path, status, repo_id)

            # Update repository status
            if result['success']:
                RepositoryManager.update_status(repo_id, 'ready')
                RepositoryManager.update_last_updated(repo_id)
            else:
                RepositoryManager.update_status(repo_id, 'error')

            return {
                "success": result['success'],
                "uploaded": result['uploaded'],
                "deleted": result['deleted'],
                "errors": result['errors'],
                "message": f"Push complete: {result['uploaded']} uploaded, {result['deleted']} deleted"
            }

        except Exception as e:
            RepositoryManager.update_status(repo_id, 'error')
            return {
                "success": False,
                "error": str(e)
            }, 500


@ns.route('/file-git/repos/<string:repo_id>/pull')
class RepoPullResource(Resource):
    def post(self, repo_id):
        """Pull changes from cloud"""
        try:
            repo = RepositoryManager.get_repo_by_id(repo_id)
            if not repo:
                return {
                    "success": False,
                    "error": "Repository not found"
                }, 404

            repo_path = repo['local_path']
            remote_root = repo['remote_path']

            if not remote_root:
                return {
                    "success": False,
                    "error": "remote_path not configured"
                }, 400

            # Update status to syncing
            RepositoryManager.update_status(repo_id, 'syncing')

            # Pull changes from cloud
            result = SyncService.pull_changes(repo_path, remote_root, repo_id)

            # Update status based on result
            if result['success']:
                RepositoryManager.update_status(repo_id, 'ready')
                RepositoryManager.update_last_updated(repo_id)

                return {
                    "success": True,
                    "message": f"Pulled {result['downloaded']} files, deleted {result['deleted']} local files",
                    "downloaded": result['downloaded'],
                    "deleted": result['deleted']
                }
            else:
                RepositoryManager.update_status(repo_id, 'error')
                return {
                    "success": False,
                    "error": result.get('error', 'Pull failed'),
                    "downloaded": result.get('downloaded', 0),
                    "deleted": result.get('deleted', 0),
                    "errors": result.get('errors', [])
                }, 500

        except Exception as e:
            RepositoryManager.update_status(repo_id, 'error')
            return {
                "success": False,
                "error": str(e)
            }, 500


restx_api.add_namespace(ns)
