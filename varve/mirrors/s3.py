from __future__ import annotations

import json
from pathlib import Path

import boto3

from varve.state.models import DatasetRecord
from .base import Mirror


def _ts_to_prefix(archived_at: str) -> str:
    cleaned = archived_at.replace("-", "").replace(":", "").replace(".", "").rstrip("Z")
    return cleaned[:15] + "Z"


class S3Mirror(Mirror):
    """Generic S3 mirror using long-lived IAM credentials (key + secret).

    Credentials format:
      {
        "aws_access_key_id": "AKIA...",
        "aws_secret_access_key": "...",
        "bucket": "my-bucket",
        "prefix": "varve/",          // optional, default ""
        "region_name": "us-east-1",  // optional
        "endpoint_url": "..."        // optional, for S3-compatible services
      }

    Files are stored at: {prefix}{dataset_slug}/{timestamp}/{filename}
    """

    def __init__(self, credentials: dict) -> None:
        self.bucket = credentials["bucket"]
        self.prefix = credentials.get("prefix", "")
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
        key_prefix = f"{self.prefix}{dataset.slug}/{ts}"

        asset_hrefs: dict[str, str] = {}
        for f in files:
            key = f"{key_prefix}/{f.name}"
            self.s3.upload_file(str(f), self.bucket, key)
            asset_hrefs[f.name] = f"s3://{self.bucket}/{key}"

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
        stac_key = f"{key_prefix}/stac-item.json"
        self.s3.put_object(
            Bucket=self.bucket,
            Key=stac_key,
            Body=json.dumps(stac_item, indent=2).encode(),
            ContentType="application/json",
        )

        return f"s3://{self.bucket}/{key_prefix}/"
