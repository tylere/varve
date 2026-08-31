from __future__ import annotations

from pathlib import Path

import httpx

from varve.state.models import DatasetRecord
from .base import Mirror, MirrorSizeError

DRYAD_MAX_BYTES = 10 * 1024**3  # 10 GB


class DryadMirror(Mirror):
    def __init__(self, credentials: dict) -> None:
        self.base_url = credentials["base_url"].rstrip("/")
        self.client_id = credentials["client_id"]
        self.client_secret = credentials["client_secret"]

    def _get_token(self) -> str:
        r = httpx.post(
            f"{self.base_url}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["access_token"]

    def upload(self, files: list[Path], dataset: DatasetRecord, run_metadata: dict) -> str:
        total = sum(f.stat().st_size for f in files)
        if total > DRYAD_MAX_BYTES:
            gb = total / 1024**3
            raise MirrorSizeError(
                f"Total size {gb:.1f} GB exceeds Dryad 10 GB limit — skipping Dryad"
            )

        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        # Create dataset record
        r = httpx.post(
            f"{self.base_url}/api/v2/datasets",
            json={
                "title": dataset.name,
                "authors": [{"firstName": "Varve", "lastName": "Archive"}],
                "relatedWorks": [
                    {"relationship": "IsDerivedFrom", "identifier": dataset.source_url}
                ],
            },
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        dataset_id = body["id"]
        assigned_doi: str | None = body.get("identifier")

        # Upload each file
        for f in files:
            with f.open("rb") as fh:
                r = httpx.put(
                    f"{self.base_url}/api/v2/datasets/{dataset_id}/files/{f.name}",
                    content=fh.read(),
                    headers={**headers, "Content-Type": "application/octet-stream"},
                    timeout=300,
                )
                r.raise_for_status()

        # Submit for curation
        r = httpx.post(
            f"{self.base_url}/api/v2/datasets/{dataset_id}/versions",
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()

        return assigned_doi or f"{self.base_url}/datasets/{dataset_id}"
