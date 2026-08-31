import pytest
from pathlib import Path
from pytest_httpx import HTTPXMock
from varve.detectors.stac import STACDetector

STAC_ITEM = {
    "type": "Feature",
    "stac_version": "1.0.0",
    "id": "test-item",
    "properties": {"datetime": "2026-08-29T00:00:00Z"},
    "assets": {
        "data": {"href": "https://example.org/data.tif", "type": "image/tiff"},
        "metadata": {"href": "https://example.org/meta.xml", "type": "application/xml"},
    },
    "links": [],
    "geometry": None,
    "bbox": [],
}


def test_fetch_metadata(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url="https://example.org/item.json", json=STAC_ITEM)
    det = STACDetector("https://example.org/item.json", [], {})
    meta = det.fetch_metadata()
    assert meta["id"] == "test-item"
    assert "assets" in meta


def test_fingerprint_stable(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url="https://example.org/item.json", json=STAC_ITEM)
    httpx_mock.add_response(method="HEAD", url="https://example.org/data.tif",
                             headers={"ETag": '"etag1"'})
    httpx_mock.add_response(method="HEAD", url="https://example.org/meta.xml",
                             headers={"ETag": '"etag2"'})
    det = STACDetector("https://example.org/item.json", [], {})
    fp = det.compute_fingerprint()
    assert fp.startswith("sha256:")


def test_fingerprint_changes_when_asset_etag_changes(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url="https://example.org/item.json", json=STAC_ITEM)
    httpx_mock.add_response(method="HEAD", url="https://example.org/data.tif",
                             headers={"ETag": '"etag1"'})
    httpx_mock.add_response(method="HEAD", url="https://example.org/meta.xml",
                             headers={"ETag": '"etag2"'})
    det = STACDetector("https://example.org/item.json", [], {})
    fp1 = det.compute_fingerprint()

    httpx_mock.add_response(url="https://example.org/item.json", json=STAC_ITEM)
    httpx_mock.add_response(method="HEAD", url="https://example.org/data.tif",
                             headers={"ETag": '"etag-CHANGED"'})
    httpx_mock.add_response(method="HEAD", url="https://example.org/meta.xml",
                             headers={"ETag": '"etag2"'})
    fp2 = det.compute_fingerprint()
    assert fp1 != fp2


def test_download_all_assets(httpx_mock: HTTPXMock, tmp_path: Path):
    httpx_mock.add_response(url="https://example.org/item.json", json=STAC_ITEM)
    httpx_mock.add_response(url="https://example.org/data.tif", content=b"TIFF")
    httpx_mock.add_response(url="https://example.org/meta.xml", content=b"<xml/>")
    det = STACDetector("https://example.org/item.json", [], {})
    files = det.download(tmp_path)
    assert {f.name for f in files} == {"data.tif", "meta.xml"}


def test_download_filtered_asset_keys(httpx_mock: HTTPXMock, tmp_path: Path):
    httpx_mock.add_response(url="https://example.org/item.json", json=STAC_ITEM)
    httpx_mock.add_response(url="https://example.org/data.tif", content=b"TIFF")
    det = STACDetector("https://example.org/item.json", [], {"asset_keys": ["data"]})
    files = det.download(tmp_path)
    assert len(files) == 1
    assert files[0].name == "data.tif"
