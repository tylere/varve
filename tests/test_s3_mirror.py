import json
import pytest
import boto3
from moto import mock_aws
from pathlib import Path
from varve.mirrors.s3 import S3Mirror
from varve.state.models import DatasetRecord

CREDS = {
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test",
    "bucket": "my-test-bucket",
    "region_name": "us-east-1",
}

DATASET = DatasetRecord(
    slug="my-dataset",
    name="My Dataset",
    source_url="https://example.org/data.zip",
    source_urls=[],
    detector_type="url",
    detector_config={},
    enabled=True,
    notes="",
    created_at="2026-01-01T00:00:00Z",
    last_fingerprint=None,
    last_checked_at=None,
)


@mock_aws
def test_upload_stores_files_and_stac(tmp_path):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="my-test-bucket")
    f = tmp_path / "data.zip"
    f.write_bytes(b"hello")
    mirror = S3Mirror(CREDS)
    remote_id = mirror.upload([f], DATASET, {"archived_at": "2026-01-01T00:00:00Z"})

    assert remote_id.startswith("s3://my-test-bucket/my-dataset/")

    s3 = boto3.client("s3", region_name="us-east-1")
    objects = s3.list_objects_v2(Bucket="my-test-bucket")["Contents"]
    keys = [o["Key"] for o in objects]
    assert any("data.zip" in k for k in keys)
    assert any("stac-item.json" in k for k in keys)


@mock_aws
def test_upload_with_prefix(tmp_path):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="my-test-bucket")
    f = tmp_path / "data.zip"
    f.write_bytes(b"hello")
    creds = {**CREDS, "prefix": "varve/"}
    mirror = S3Mirror(creds)
    remote_id = mirror.upload([f], DATASET, {"archived_at": "2026-01-01T00:00:00Z"})

    assert remote_id.startswith("s3://my-test-bucket/varve/my-dataset/")

    s3 = boto3.client("s3", region_name="us-east-1")
    objects = s3.list_objects_v2(Bucket="my-test-bucket")["Contents"]
    keys = [o["Key"] for o in objects]
    assert all(k.startswith("varve/") for k in keys)


@mock_aws
def test_stac_item_has_derived_from(tmp_path):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="my-test-bucket")
    f = tmp_path / "data.zip"
    f.write_bytes(b"hello")
    mirror = S3Mirror(CREDS)
    mirror.upload([f], DATASET, {"archived_at": "2026-01-01T00:00:00Z"})

    s3 = boto3.client("s3", region_name="us-east-1")
    objects = s3.list_objects_v2(Bucket="my-test-bucket")["Contents"]
    stac_key = next(o["Key"] for o in objects if o["Key"].endswith("stac-item.json"))
    body = s3.get_object(Bucket="my-test-bucket", Key=stac_key)["Body"].read()
    item = json.loads(body)
    assert item["links"][0]["href"] == "https://example.org/data.zip"
    assert item["links"][0]["rel"] == "derived_from"
