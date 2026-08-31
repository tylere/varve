from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .base import Detector
from .url import _collection_fingerprint


class STACDetector(Detector):
    def __init__(self, source_url: str, source_urls: list[str], detector_config: dict) -> None:
        self.stac_url = source_url
        self.asset_keys: list[str] | None = detector_config.get("asset_keys")

    def _get_item(self) -> dict:
        r = httpx.get(self.stac_url, follow_redirects=True, timeout=30)
        r.raise_for_status()
        return r.json()

    def _selected_assets(self, item: dict) -> dict[str, dict]:
        assets: dict = item.get("assets", {})
        if self.asset_keys is not None:
            return {k: v for k, v in assets.items() if k in self.asset_keys}
        return assets

    def fetch_metadata(self) -> dict:
        return self._get_item()

    def compute_fingerprint(self) -> str:
        item = self._get_item()
        assets = self._selected_assets(item)
        entries = []
        for key, asset in assets.items():
            href = asset["href"]
            r = httpx.head(href, follow_redirects=True, timeout=30)
            r.raise_for_status()
            val = r.headers.get("etag") or r.headers.get("content-length", "0")
            name = urlparse(href).path.split("/")[-1] or key
            entries.append((name, val))
        updated = item.get("properties", {}).get("updated", "")
        if updated:
            entries.append(("__updated__", updated))
        return _collection_fingerprint(entries)

    def download(self, dest_dir: Path) -> list[Path]:
        item = self._get_item()
        assets = self._selected_assets(item)
        paths = []
        for key, asset in assets.items():
            href = asset["href"]
            raw_name = urlparse(href).path.split("/")[-1] or key
            name = Path(raw_name).name.lstrip(".") or "file"
            dest = dest_dir / name
            if not dest.resolve().is_relative_to(dest_dir.resolve()):
                dest = dest_dir / hashlib.sha256(href.encode()).hexdigest()[:16]
            with httpx.stream("GET", href, follow_redirects=True, timeout=120) as r:
                r.raise_for_status()
                with dest.open("wb") as fh:
                    for chunk in r.iter_bytes(chunk_size=65536):
                        fh.write(chunk)
            paths.append(dest)
        return paths
