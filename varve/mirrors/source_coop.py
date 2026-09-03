from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import boto3

from varve.state.models import DatasetRecord
from .base import Mirror


def _ts_to_prefix(archived_at: str) -> str:
    cleaned = archived_at.replace("-", "").replace(":", "").replace(".", "").rstrip("Z")
    return cleaned[:15] + "Z"


def parse_source_coop_url(url: str) -> dict:
    """Extract owner, product, and (if available) bucket from a source.coop URL or S3 URI.

    Supported formats:
      s3://{bucket}/{owner}/{product}/...
      https://source.coop/{owner}/{product}/...
      https://data.source.coop/{owner}/{product}/...

    Returns a dict with keys 'owner', 'product', and optionally 'bucket'.
    Raises ValueError if the URL cannot be parsed.
    """
    parsed = urlparse(url)
    if parsed.scheme == "s3":
        bucket = parsed.netloc
        parts = parsed.path.lstrip("/").split("/")
        if len(parts) < 2:
            raise ValueError(f"S3 URI must have at least owner and product: {url}")
        return {"bucket": bucket, "owner": parts[0], "product": parts[1]}
    elif parsed.scheme in ("http", "https"):
        parts = parsed.path.lstrip("/").split("/")
        if len(parts) < 2:
            raise ValueError(f"source.coop URL must include owner and product: {url}")
        return {"owner": parts[0], "product": parts[1]}
    else:
        raise ValueError(f"Unrecognised URL scheme '{parsed.scheme}': {url}")


class SourceCoopMirror(Mirror):
    def __init__(self, credentials: dict) -> None:
        if "repository_url" in credentials:
            parsed = parse_source_coop_url(credentials["repository_url"])
            self.owner = parsed["owner"]
            self.product = parsed["product"]
            self.bucket = parsed.get("bucket") or credentials["bucket"]
        else:
            self.owner = credentials["owner"]
            self.product = credentials["product"]
            self.bucket = credentials["bucket"]
        kwargs: dict = {
            "aws_access_key_id": credentials["aws_access_key_id"],
            "aws_secret_access_key": credentials["aws_secret_access_key"],
        }
        if credentials.get("aws_session_token"):
            kwargs["aws_session_token"] = credentials["aws_session_token"]
        if credentials.get("region_name"):
            kwargs["region_name"] = credentials["region_name"]
        if credentials.get("endpoint_url"):
            kwargs["endpoint_url"] = credentials["endpoint_url"]
        self.s3 = boto3.client("s3", **kwargs)

    def upload(self, files: list[Path], dataset: DatasetRecord, run_metadata: dict) -> str:
        ts = _ts_to_prefix(run_metadata["archived_at"])
        prefix = f"{self.owner}/{self.product}/{ts}"
        base_url = f"https://data.source.coop/{prefix}"

        asset_hrefs: dict[str, str] = {}
        for f in files:
            key = f"{prefix}/{f.name}"
            self.s3.upload_file(str(f), self.bucket, key)
            asset_hrefs[f.name] = f"{base_url}/{f.name}"

        # Write STAC Item
        stac_item = {
            "type": "Feature",
            "stac_version": "1.0.0",
            "id": f"{dataset.slug}-{ts}",
            "properties": {"datetime": run_metadata["archived_at"]},
            "geometry": None,
            "bbox": None,
            "links": [
                {"rel": "derived_from", "href": dataset.source_url}
            ],
            "assets": {
                name: {"href": href, "type": "application/octet-stream"}
                for name, href in asset_hrefs.items()
            },
        }
        stac_key = f"{prefix}/stac-item.json"
        self.s3.put_object(
            Bucket=self.bucket,
            Key=stac_key,
            Body=json.dumps(stac_item, indent=2).encode(),
            ContentType="application/json",
        )

        return f"{base_url}/"
