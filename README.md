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
NEXTLOUD_USER=your_login
NEXTLOUD_PASSWORD=your_password
NEXTLOUD_REMOTE_PATH=/Shared/Content/playerPublic/assets
LOCAL_ASSETS_PATH=./assets
```

## Usage

```python
from sync import NextcloudSync

sync = NextcloudSync()
sync.sync()
```

Or run directly:

```bash
uv run main.py
```

## How It Works

1. Connects to Nextcloud via WebDAV at `https://nextcloud.1t.ru/remote.php/webdav`
2. Recursively lists all files in the configured remote path
3. Checks local files against remote ETags stored in `.sync_etags.json`
4. Downloads only new or modified files using 8 parallel workers
5. Preserves directory structure in the local assets folder
