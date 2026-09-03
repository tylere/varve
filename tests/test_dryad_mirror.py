import pytest
from pathlib import Path
from pytest_httpx import HTTPXMock
from varve.mirrors.base import MirrorSizeError
from varve.mirrors.dryad import DryadMirror
from varve.state.models import DatasetRecord

CREDS = {
    "client_id": "test_id",
    "client_secret": "test_secret",
    "base_url": "https://sandbox.datadryad.org",
}

DATASET = DatasetRecord(
    slug="test-ds", name="Test", source_url="https://example.org/ds",
    source_urls=[], detector_type="url", detector_config={},
    enabled=True, notes="", created_at="2026-08-29T00:00:00Z",
    last_fingerprint=None, last_checked_at=None,
)


def test_size_check_raises(tmp_path: Path):
    f = tmp_path / "large.bin"
    # write 10 GB + 1 byte worth of metadata (we mock the size, not actual disk)
    f.write_bytes(b"x")
    mirror = DryadMirror(CREDS)
    # Patch stat to return a huge size
    import unittest.mock as mock
    huge_stat = mock.MagicMock()
    huge_stat.st_size = 10 * 1024**3 + 1
    with mock.patch.object(Path, "stat", return_value=huge_stat):
        with pytest.raises(MirrorSizeError, match="10 GB"):
            mirror.upload([f], DATASET, {"archived_at": "2026-08-29T14:00:00Z"})


def test_upload_full_flow(httpx_mock: HTTPXMock, tmp_path: Path):
    # token
    httpx_mock.add_response(
        method="POST",
        url="https://sandbox.datadryad.org/oauth/token",
        json={"access_token": "tok123", "token_type": "bearer"},
    )
    # create dataset
    httpx_mock.add_response(
        method="POST",
        url="https://sandbox.datadryad.org/api/v2/datasets",
        json={"identifier": "doi:10.5072/dryad.test", "id": 99},
        status_code=201,
    )
    # upload file
    httpx_mock.add_response(
        method="PUT",
        url="https://sandbox.datadryad.org/api/v2/datasets/99/files/data.csv",
        json={"status": "uploaded"},
    )
    # submit
    httpx_mock.add_response(
        method="POST",
        url="https://sandbox.datadryad.org/api/v2/datasets/99/versions",
        json={"versionNumber": 1},
        status_code=202,
    )

    f = tmp_path / "data.csv"
    f.write_text("a,b,c")
    mirror = DryadMirror(CREDS)
    remote_id = mirror.upload([f], DATASET, {"archived_at": "2026-08-29T14:00:00Z"})
    assert "dryad" in remote_id.lower() or "99" in remote_id
