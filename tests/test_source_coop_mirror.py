import json
import boto3
from moto import mock_aws
from pathlib import Path
from varve.mirrors.source_coop import SourceCoopMirror
from varve.state.models import DatasetRecord

CREDS = {
    "access_key": "test",
    "secret_key": "test",
    "bucket": "test-bucket",
    "endpoint_url": None,
    "owner": "my-org",
    "product": "noaa-sst",
}

DATASET = DatasetRecord(
    slug="noaa-sst", name="NOAA SST", source_url="https://example.org/sst",
    source_urls=[], detector_type="url", detector_config={},
    enabled=True, notes="", created_at="2026-08-29T00:00:00Z",
    last_fingerprint=None, last_checked_at=None,
)


@mock_aws
def test_upload_creates_s3_objects(tmp_path: Path):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")

    f1 = tmp_path / "data.csv"
    f2 = tmp_path / "meta.xml"
    f1.write_text("a,b,c")
    f2.write_text("<meta/>")

    mirror = SourceCoopMirror(CREDS)
    remote_id = mirror.upload(
        [f1, f2], DATASET, {"archived_at": "2026-08-29T14:00:00Z"}
    )

    s3 = boto3.client("s3", region_name="us-east-1")
    objects = [o["Key"] for o in s3.list_objects_v2(Bucket="test-bucket")["Contents"]]

    assert any("data.csv" in k for k in objects)
    assert any("meta.xml" in k for k in objects)
    assert any("stac-item.json" in k for k in objects)
    assert remote_id.startswith("https://data.source.coop/my-org/noaa-sst/")
    # verify timestamp prefix is single-Z (no double-Z from _ts_to_prefix)
    assert "ZZ" not in remote_id


@mock_aws
def test_stac_item_references_correct_urls(tmp_path: Path):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")

    f = tmp_path / "data.csv"
    f.write_text("a,b")

    mirror = SourceCoopMirror(CREDS)
    mirror.upload([f], DATASET, {"archived_at": "2026-08-29T14:00:00Z"})

    s3 = boto3.client("s3", region_name="us-east-1")
    objects = s3.list_objects_v2(Bucket="test-bucket")["Contents"]
    stac_key = next(o["Key"] for o in objects if "stac-item.json" in o["Key"])
    item = json.loads(s3.get_object(Bucket="test-bucket", Key=stac_key)["Body"].read())

    hrefs = [a["href"] for a in item["assets"].values()]
    assert all(h.startswith("https://data.source.coop/") for h in hrefs)
