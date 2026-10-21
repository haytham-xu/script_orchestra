"""File-Git command layer (REQUIREMENTS §3.7)."""
from .context import RepoContext, build_context
from .push import command_push, PushResult
from .pull import command_pull, PullResult
from .queue import command_queue, QueueResult
from .manual_upload import command_manual_upload, ManualUploadResult
from .post_manual_upload import command_post_manual_upload, PostManualUploadResult
from .abandon_manual_upload import command_abandon_manual_upload
from .pre_manual_download import command_pre_manual_download, PreManualDownloadResult
from .post_manual_download import command_post_manual_download, PostManualDownloadResult
from .download_scan import (
    command_download_scan,
    download_scan_children,
    DownloadScanResult,
)
from .diff import command_diff, DiffCommandResult
from .rebuild_local_index import command_rebuild_local_index, RebuildLocalIndexResult
from .rebuild_cloud_index import (
    command_rebuild_cloud_index,
    estimate_rebuild_cloud_index,
    RebuildCloudIndexResult,
    RebuildEstimate,
)
from .cleanup import command_cleanup, CleanupResult
from .stop import command_stop, StopResult

__all__ = [
    "RepoContext",
    "build_context",
    "command_push",
    "command_pull",
    "command_queue",
    "command_manual_upload",
    "command_post_manual_upload",
    "command_abandon_manual_upload",
    "command_pre_manual_download",
    "command_post_manual_download",
    "command_download_scan",
    "download_scan_children",
    "command_diff",
    "command_rebuild_local_index",
    "command_rebuild_cloud_index",
    "estimate_rebuild_cloud_index",
    "command_cleanup",
    "command_stop",
    "PushResult",
    "PullResult",
    "QueueResult",
    "ManualUploadResult",
    "PostManualUploadResult",
    "PreManualDownloadResult",
    "PostManualDownloadResult",
    "DownloadScanResult",
    "DiffCommandResult",
    "RebuildLocalIndexResult",
    "RebuildCloudIndexResult",
    "RebuildEstimate",
    "CleanupResult",
    "StopResult",
]
