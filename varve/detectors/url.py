from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import unquote, urlparse


import httpx

from .base import Detector


def _filename_from_url(url: str, response: httpx.Response) -> str:
    cd = response.headers.get("content-disposition", "")
    if "filename=" in cd:
        name = cd.split("filename=")[-1].strip().strip('"')
    else:
        name = unquote(urlparse(url).path.rstrip("/").split("/")[-1]) or "download"
    name = Path(name).name  # strip any path components
    name = name.lstrip(".") or "file"  # strip leading dots, fallback
    return name


def _collection_fingerprint(entries: list[tuple[str, str]]) -> str:
    """SHA-256 of sorted [(filename, etag_or_size)] pairs."""
    payload = "|".join(f"{n}:{v}" for n, v in sorted(entries))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


class URLDetector(Detector):
    def __init__(self, source_url: str, source_urls: list[str], detector_config: dict) -> None:
        self.urls = source_urls if source_urls else [source_url]
        self.config = detector_config

    def _head(self, url: str) -> httpx.Response:
        return httpx.head(url, follow_redirects=True, timeout=30)

    def fetch_metadata(self) -> dict:
        meta = []
        for url in self.urls:
            r = self._head(url)
            r.raise_for_status()
            meta.append({
                "url": url,
                "etag": r.headers.get("etag"),
                "last_modified": r.headers.get("last-modified"),
                "content_length": r.headers.get("content-length"),
                "status": r.status_code,
            })
        return {"urls": meta}

    def compute_fingerprint(self) -> str:
        if len(self.urls) == 1:
            r = self._head(self.urls[0])
            r.raise_for_status()
            if etag := r.headers.get("etag"):
                return etag
            # fall back: partial SHA-256 (first 1 MB)
            with httpx.stream("GET", self.urls[0], headers={"Range": "bytes=0-1048575"},
                              follow_redirects=True, timeout=60) as resp:
                h = hashlib.sha256()
                for chunk in resp.iter_bytes(chunk_size=65536):
                    h.update(chunk)
                return "sha256-partial:" + h.hexdigest()
        else:
            entries = []
            for url in self.urls:
                r = self._head(url)
                r.raise_for_status()
                name = unquote(urlparse(url).path.split("/")[-1])
                val = r.headers.get("etag") or r.headers.get("content-length", "0")
                entries.append((name, val))
            return _collection_fingerprint(entries)

    def download(self, dest_dir: Path) -> list[Path]:
        paths = []
        for url in self.urls:
            with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
                r.raise_for_status()
                name = _filename_from_url(url, r)
                dest = dest_dir / name
                if not dest.resolve().is_relative_to(dest_dir.resolve()):
                    dest = dest_dir / hashlib.sha256(url.encode()).hexdigest()[:16]
                with dest.open("wb") as fh:
                    for chunk in r.iter_bytes(chunk_size=65536):
                        fh.write(chunk)
                paths.append(dest)
        return paths
