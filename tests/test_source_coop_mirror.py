import json
import pytest
import boto3
from moto import mock_aws
from pathlib import Path
from varve.mirrors.source_coop import SourceCoopMirror, parse_source_coop_url
from varve.state.models import DatasetRecord


def test_parse_s3_uri():
    # Data proxy layout: the bucket is the account, the key starts with the product
    result = parse_source_coop_url("s3://tyler/test-tiff-not-cloud-optimized/Victoria.tif")
    assert result == {"owner": "tyler", "product": "test-tiff-not-cloud-optimized"}


def test_parse_s3_uri_without_product():
    with pytest.raises(ValueError):
        parse_source_coop_url("s3://tyler/")


def test_parse_source_coop_https():
    result = parse_source_coop_url("https://source.coop/tyler/varve-data-mirror-test")
    assert result == {"owner": "tyler", "product": "varve-data-mirror-test"}
    assert "bucket" not in result


def test_parse_source_coop_https_with_path():
    result = parse_source_coop_url(
        "https://source.coop/tyler/test-tiff-not-cloud-optimized/Victoria.tif"
    )
    assert result["owner"] == "tyler"
    assert result["product"] == "test-tiff-not-cloud-optimized"


def test_parse_data_source_coop_https():
    result = parse_source_coop_url("https://data.source.coop/tyler/varve-data-mirror-test")
    assert result == {"owner": "tyler", "product": "varve-data-mirror-test"}


def test_parse_invalid_url():
    with pytest.raises(ValueError):
        parse_source_coop_url("https://source.coop/tyler")


def test_parse_unknown_scheme():
    with pytest.raises(ValueError):
        parse_source_coop_url("ftp://source.coop/tyler/repo")

# No keys: AWS credentials come from the environment (a service account sign-in)
CREDS = {"owner": "my-org", "product": "noaa-sst"}
# moto intercepts AWS hostnames only, so point uploads there rather than at the real proxy
MOTO_CREDS = {**CREDS, "endpoint_url": "https://s3.us-east-1.amazonaws.com"}

DATASET = DatasetRecord(
    slug="noaa-sst", name="NOAA SST", source_url="https://example.org/sst",
    source_urls=[], detector_type="url", detector_config={},
    enabled=True, notes="", created_at="2026-08-29T00:00:00Z",
    last_fingerprint=None, last_checked_at=None,
)


def _s3():
    return boto3.client("s3", region_name="us-east-1")


@mock_aws
def test_upload_creates_s3_objects(tmp_path: Path):
    _s3().create_bucket(Bucket="my-org")

    f1 = tmp_path / "data.csv"
    f2 = tmp_path / "meta.xml"
    f1.write_text("a,b,c")
    f2.write_text("<meta/>")

    mirror = SourceCoopMirror(MOTO_CREDS)
    remote_id = mirror.upload(
        [f1, f2], DATASET, {"archived_at": "2026-08-29T14:00:00Z"}
    )

    objects = sorted(o["Key"] for o in _s3().list_objects_v2(Bucket="my-org")["Contents"])

    assert objects == [
        "noaa-sst/20260829T140000Z/data.csv",
        "noaa-sst/20260829T140000Z/meta.xml",
        "noaa-sst/20260829T140000Z/stac-item.json",
    ]
    assert remote_id == "https://data.source.coop/my-org/noaa-sst/20260829T140000Z/"


def test_client_targets_data_proxy():
    mirror = SourceCoopMirror(CREDS)
    assert mirror.s3.meta.endpoint_url == "https://data.source.coop"


def test_endpoint_url_override():
    mirror = SourceCoopMirror({**CREDS, "endpoint_url": "http://localhost:9000"})
    assert mirror.s3.meta.endpoint_url == "http://localhost:9000"


def test_repository_url_sets_owner_and_product():
    mirror = SourceCoopMirror({"repository_url": "https://source.coop/tyler/varve-data-mirror-test"})
    assert (mirror.owner, mirror.product) == ("tyler", "varve-data-mirror-test")


@mock_aws
def test_stac_item_references_correct_urls(tmp_path: Path):
    _s3().create_bucket(Bucket="my-org")

    f = tmp_path / "data.csv"
    f.write_text("a,b")

    mirror = SourceCoopMirror(MOTO_CREDS)
    mirror.upload([f], DATASET, {"archived_at": "2026-08-29T14:00:00Z"})

    item = json.loads(_s3().get_object(
        Bucket="my-org", Key="noaa-sst/20260829T140000Z/stac-item.json")["Body"].read())

    hrefs = [a["href"] for a in item["assets"].values()]
    assert all(h.startswith("https://data.source.coop/") for h in hrefs)
