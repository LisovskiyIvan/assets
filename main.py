import os
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class NextcloudSync:
    def __init__(self):
        remote_path = os.getenv(
            "NEXTLOUD_REMOTE_PATH", "/Shared/Content/playerPublic/assets"
        )
        self.base_url = "https://nextcloud.1t.ru/remote.php/webdav"
        self.remote_dir = remote_path.strip("/")
        self.user = os.getenv("NEXTLOUD_USER", "")
        self.password = os.getenv("NEXTLOUD_PASSWORD", "")
        self.local_path = Path(
            os.path.expanduser(os.getenv("LOCAL_ASSETS_PATH", "./assets"))
        )

        if not all([self.user, self.password, self.remote_dir]):
            raise ValueError(
                "Missing required env vars: NEXTLOUD_URL, NEXTLOUD_USER, NEXTLOUD_PASSWORD"
            )

        self.local_path.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.auth = (self.user, self.password)

    def _get_file_hash(self, filepath: Path) -> str:
        if not filepath.exists():
            return ""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _get_remote_hash(self, remote_path: str) -> Optional[str]:
        url = f"{self.base_url}/{self.remote_dir}/{remote_path}"
        response = self.session.get(url)
        if response.status_code == 200:
            return hashlib.sha256(response.content).hexdigest()
        return None

    def list_remote_files(self, prefix: str = "") -> dict:
        url = f"{self.base_url}/{self.remote_dir}"
        if prefix:
            url = f"{self.base_url}/{prefix}"

        response = self.session.request("PROPFIND", url, headers={"Depth": "infinity"})
        if response.status_code not in (207, 200):
            logger.error(f"PROPFIND failed: {response.status_code}")
            return {}

        files = {}
        import xml.etree.ElementTree as ET

        root = ET.fromstring(response.content)

        ns = {"d": "DAV:"}
        for response_elem in root.findall(".//d:response", ns):
            href = response_elem.find("d:href", ns)
            resourcetype = response_elem.find("d:resourcetype", ns)
            getetag = response_elem.find("d:getetag", ns)

            if href is None:
                continue

            href_text = href.text or ""
            if "/assets/" in href_text:
                path = href_text.split("/assets/", 1)[1]
            else:
                path = href_text.replace(self.base_url, "").strip("/")

            is_collection = (
                resourcetype is not None
                and resourcetype.find("d:collection", ns) is not None
            )

            if not is_collection and path and not path.endswith("/"):
                etag = getetag.text.strip('"') if getetag is not None else None
                files[path] = etag

        return files

    def download_file(self, remote_path: str) -> bool:
        url = f"{self.base_url}/{self.remote_dir}/{remote_path}"
        local_file = self.local_path / remote_path

        try:
            response = self.session.get(url, timeout=60)
            if response.status_code != 200:
                logger.error(
                    f"Failed to download {remote_path}: {response.status_code}"
                )
                return False

            local_file.parent.mkdir(parents=True, exist_ok=True)
            with open(local_file, "wb") as f:
                f.write(response.content)

            logger.info(f"Downloaded: {remote_path}")
            return True
        except Exception as e:
            logger.error(f"Error downloading {remote_path}: {e}")
            return False

    def sync(self):
        logger.info(
            f"Syncing from {self.base_url}/{self.remote_dir} to {self.local_path}"
        )

        remote_files = self.list_remote_files()
        logger.info(f"Found {len(remote_files)} remote files")

        to_download = []
        etag_file = self.local_path / ".sync_etags.json"

        import json

        local_etags = {}
        if etag_file.exists():
            local_etags = json.loads(etag_file.read_text())

        for remote_path, remote_etag in remote_files.items():
            local_file = self.local_path / remote_path

            if not local_file.exists():
                to_download.append(remote_path)
                continue

            local_etag = local_etags.get(remote_path)
            if remote_etag and local_etag != remote_etag:
                to_download.append(remote_path)

        logger.info(f"Need to download {len(to_download)} files")

        if not to_download:
            logger.info("All files are up to date")
            return

        downloaded = 0
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(self.download_file, path): path for path in to_download
            }

            for future in as_completed(futures):
                if future.result():
                    downloaded += 1

        import json

        new_etags = {
            path: remote_files[path] for path in to_download if remote_files[path]
        }
        if new_etags:
            local_etags.update(new_etags)
            etag_file.write_text(json.dumps(local_etags))

        logger.info(f"Synced {downloaded}/{len(to_download)} files")


if __name__ == "__main__":
    sync = NextcloudSync()
    sync.sync()
