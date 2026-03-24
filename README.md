# Nextcloud File Sync

A Python utility for syncing files from a Nextcloud WebDAV server to a local directory.

## Features

- WebDAV integration with Nextcloud servers
- Incremental sync using ETags (only downloads changed files)
- Parallel downloads with ThreadPoolExecutor
- Preserves remote directory structure locally

## Requirements

- Python 3.14+
- uv package manager

## Installation

```bash
uv sync
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
NEXTLOUD_URL=https://nextcloud.ru/
NEXTLOUD_SYNC_PATHS=path/to/your/dir,another/path
NEXTLOUD_USER=login
NEXTLOUD_PASSWORD=pass
LOCAL_ASSETS_PATH=~/local/assets/path или Z://windows/path
```

### Multiple Sync Paths

Specify multiple remote paths separated by commas:

```bash
NEXTLOUD_SYNC_PATHS=/Shared/Content/playerPublic/assets,/Shared/Content/other,/Shared/another/path
```

## Usage

```python
from main import NextcloudSync

sync = NextcloudSync()
sync.sync()
```

Or run directly:

```bash
uv run main.py
```

## How It Works

1. Connects to Nextcloud via WebDAV at `https://nextcloud.ru/remote.php/webdav`
2. Iterates over all configured remote paths (comma-separated)
3. Recursively lists all files in each remote path
4. Checks local files against remote ETags stored in `.sync_etags.json`
5. Downloads only new or modified files using 8 parallel workers
6. Preserves directory structure in the local assets folder
