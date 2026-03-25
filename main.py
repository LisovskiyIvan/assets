import os
import hashlib
import json
import logging
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
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
        self.nextcloud_url_base = os.getenv("NEXTLOUD_URL", "https://nextcloud.ru/")
        self.nextcloud_url_base += "remote.php/webdav"
        self.local_base = Path(
            os.path.expanduser(os.getenv("LOCAL_ASSETS_PATH", "./assets"))
        )
        self.urls_to_check = [
            path.strip()
            for path in os.getenv(
                "NEXTLOUD_SYNC_PATHS", "/Shared/Content/playerPublic/assets"
            ).split(",")
        ]
        self.user = os.getenv("NEXTLOUD_USER", "")
        self.password = os.getenv("NEXTLOUD_PASSWORD", "")

        if not all([self.user, self.password]):
            raise ValueError(
                "Missing required env vars: NEXTLOUD_USER, NEXTLOUD_PASSWORD"
            )

        self.local_base.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.auth = (self.user, self.password)

    def list_remote_files(self, remote_path: str) -> dict:
        url = f"{self.nextcloud_url_base}/{remote_path.strip('/')}"

        response = self.session.request("PROPFIND", url, headers={"Depth": "infinity"})
        if response.status_code not in (207, 200):
            logger.error(f"PROPFIND failed: {response.status_code}")
            return {}

        files = {}
        root = ET.fromstring(response.content)
        ns = {"d": "DAV:"}

        for response_elem in root.findall(".//d:response", ns):
            href = response_elem.find("d:href", ns)
            propstat = response_elem.find("d:propstat", ns)

            if href is None or propstat is None:
                continue

            prop = propstat.find("d:prop", ns)
            if prop is None:
                continue

            getetag = prop.find("d:getetag", ns)
            getlastmodified = prop.find("d:getlastmodified", ns)
            resourcetype = prop.find("d:resourcetype", ns)

            href_text = href.text or ""
            if remote_path.strip("/") in href_text:
                path = href_text.split(remote_path.strip("/"), 1)[1].lstrip("/")
            else:
                path = href_text.replace(self.nextcloud_url_base, "").strip("/")

            is_collection = (
                resourcetype is not None
                and resourcetype.find("d:collection", ns) is not None
            )

            if not is_collection and path and not path.endswith("/"):
                etag = None
                if getetag is not None and getetag.text:
                    etag = getetag.text.strip('"')
                mtime = None
                if getlastmodified is not None:
                    lt = getlastmodified.text
                    if lt:
                        try:
                            mtime = parsedate_to_datetime(lt).timestamp()
                        except Exception:
                            pass
                files[path] = {"etag": etag, "mtime": mtime}

        return files

    def download_file(
        self, remote_base: str, remote_file_path: str, local_path: Path
    ) -> bool:
        url = f"{self.nextcloud_url_base}/{remote_base.strip('/')}/{remote_file_path.strip('/')}"

        try:
            response = self.session.get(url, timeout=60)
            if response.status_code != 200:
                logger.error(
                    f"Failed to download {remote_file_path}: {response.status_code}"
                )
                return False

            local_path.parent.mkdir(parents=True, exist_ok=True)
            if local_path.exists():
                local_path.unlink()
            with open(local_path, "wb") as f:
                f.write(response.content)

            logger.info(f"Downloaded: {remote_file_path}")
            return True
        except Exception as e:
            logger.error(f"Error downloading {remote_file_path}: {e}")
            return False

    def sync(self):
        for remote_path in self.urls_to_check:
            logger.info(
                f"Syncing from {self.nextcloud_url_base}/{remote_path} to {self.local_base}"
            )

            remote_files = self.list_remote_files(remote_path)
            logger.info(f"Found {len(remote_files)} remote files")

            to_download = []

            for remote_file_path, info in remote_files.items():
                local_file_path = self.local_base / remote_file_path
                remote_mtime = info.get("mtime")

                if not local_file_path.exists():
                    to_download.append((remote_file_path, local_file_path))
                    continue

                if remote_mtime is not None:
                    local_mtime = local_file_path.stat().st_mtime
                    if remote_mtime > local_mtime:
                        to_download.append((remote_file_path, local_file_path))
                else:
                    remote_etag = info.get("etag")
                    if remote_etag:
                        etag_file = self.local_base / ".sync_etags.json"
                        local_etags = {}
                        if etag_file.exists():
                            local_etags = json.loads(etag_file.read_text())
                        local_etag = local_etags.get(remote_file_path)
                        if local_etag != remote_etag:
                            to_download.append((remote_file_path, local_file_path))

            logger.info(f"Need to download {len(to_download)} files")

            if not to_download:
                logger.info("All files are up to date")
                continue

            downloaded = 0
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {
                    executor.submit(
                        self.download_file, remote_path, remote, local
                    ): remote
                    for remote, local in to_download
                }

                for future in as_completed(futures):
                    if future.result():
                        downloaded += 1

            etag_file = self.local_base / ".sync_etags.json"
            local_etags = {}
            if etag_file.exists():
                local_etags = json.loads(etag_file.read_text())

            new_etags = {
                remote: remote_files[remote]["etag"]
                for remote, _ in to_download
                if remote_files[remote].get("etag")
            }
            if new_etags:
                local_etags.update(new_etags)
                etag_file.write_text(json.dumps(local_etags))

            logger.info(f"Synced {downloaded}/{len(to_download)} files")


if __name__ == "__main__":
    sync = NextcloudSync()
    sync.sync()
