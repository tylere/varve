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


DATA_PROXY_URL = "https://data.source.coop"


def parse_source_coop_url(url: str) -> dict:
    """Extract owner and product from a source.coop URL or S3 URI.

    Supported formats:
      s3://{owner}/{product}/...
      https://source.coop/{owner}/{product}/...
      https://data.source.coop/{owner}/{product}/...

    Returns a dict with keys 'owner' and 'product'.
    Raises ValueError if the URL cannot be parsed.
    """
    parsed = urlparse(url)
    if parsed.scheme == "s3":
        product = parsed.path.lstrip("/").split("/")[0]
        if not parsed.netloc or not product:
            raise ValueError(f"S3 URI must have owner and product: {url}")
        return {"owner": parsed.netloc, "product": product}
    elif parsed.scheme in ("http", "https"):
        parts = parsed.path.lstrip("/").split("/")
        if len(parts) < 2:
            raise ValueError(f"source.coop URL must include owner and product: {url}")
        return {"owner": parts[0], "product": parts[1]}
    else:
        raise ValueError(f"Unrecognised URL scheme '{parsed.scheme}': {url}")


class SourceCoopMirror(Mirror):
    """Uploads through the source.coop data proxy, where the bucket is the owner account.

    Holds no keys: boto3's default credential chain picks up a service account sign-in
    (GitHub Actions OIDC, or an API key via AWS_ROLE_ARN + AWS_WEB_IDENTITY_TOKEN_FILE).
    """

    def __init__(self, credentials: dict) -> None:
        if "repository_url" in credentials:
            parsed = parse_source_coop_url(credentials["repository_url"])
            self.owner = parsed["owner"]
            self.product = parsed["product"]
        else:
            self.owner = credentials["owner"]
            self.product = credentials["product"]
        self.s3 = boto3.client(
            "s3",
            endpoint_url=credentials.get("endpoint_url") or DATA_PROXY_URL,
            # The proxy accepts any region, but boto3 won't sign without one
            region_name=credentials.get("region_name") or "us-west-2",
        )

    def upload(self, files: list[Path], dataset: DatasetRecord, run_metadata: dict) -> str:
        ts = _ts_to_prefix(run_metadata["archived_at"])
        prefix = f"{self.product}/{ts}"
        base_url = f"{DATA_PROXY_URL}/{self.owner}/{prefix}"

        asset_hrefs: dict[str, str] = {}
        for f in files:
            key = f"{prefix}/{f.name}"
            self.s3.upload_file(str(f), self.owner, key)
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
            Bucket=self.owner,
            Key=stac_key,
            Body=json.dumps(stac_item, indent=2).encode(),
            ContentType="application/json",
        )

        return f"{base_url}/"
