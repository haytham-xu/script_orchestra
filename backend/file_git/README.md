# File-Git - Encrypted Cloud Backup

Git-style file backup tool with encryption support for Baidu Cloud.

## Features

- **Multi-Repository Management**: Manage multiple backup repositories
- **Encryption Support**: AES-256-CBC encryption for sensitive files
- **Git-style Operations**: push/pull/verify/diff commands
- **Async Processing**: Redis-based queue with thread pool
- **Offline Mode**: Use local cache to reduce API calls

## Architecture

### Multi-Repository Design

- **Global Registry**: `repos.json` tracks all repositories
- **Per-Repo Config**: Each repo's `.fgit/config.json` stores detailed settings
- **Isolation**: Each repository is independent with its own buffer/trash/logs

### Repository Structure

```
/path/to/repo/
├── .fgit/
│   ├── config.json       # Repository configuration
│   ├── cloud_index.json  # Cached cloud file index
│   ├── local.json        # Local file index
│   ├── buffer/           # Temporary encryption/decryption folder
│   ├── trash/            # Deleted files (by date)
│   └── action/           # Operation logs (by date_action)
└── [user files]
```

## API Endpoints

### Repository Management

- `GET /file-git/repos` - List all repositories
- `POST /file-git/repos` - Add new repository
- `DELETE /file-git/repos/:id` - Delete repository

### Repository Operations (TODO)

- `POST /file-git/:id/push` - Push changes to cloud
- `POST /file-git/:id/pull` - Pull changes from cloud
- `GET /file-git/:id/status` - Get operation status

## System Dependencies

- **Redis** (required for queue management)
  - macOS: `brew install redis && brew services start redis`
  - Windows: Download from https://redis.io/download
  - Linux: `apt-get install redis-server`

## Configuration

Each repository requires:
- **Mode**: `ORIGINAL` or `ENCRYPTED` (cannot be changed after creation)
- **Password**: Required for ENCRYPTED mode
- **Local Path**: Absolute path to local folder
- **Remote Path**: Baidu Cloud folder path
- **Baidu Credentials**: app_id, secret_key, app_key, sign_code, refresh_token, access_token

## Notes

- Repository mode (ORIGINAL/ENCRYPTED) is immutable after creation
- Deleting a repository does NOT delete the `.fgit` folder (manual cleanup required)
- Each repository operates independently
