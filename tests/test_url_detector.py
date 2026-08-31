import pytest
from pathlib import Path
from pytest_httpx import HTTPXMock
from varve.detectors.url import URLDetector


def test_fingerprint_uses_etag(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="HEAD", url="https://example.org/data.csv",
        headers={"ETag": '"abc123"', "Content-Length": "1024"},
    )
    det = URLDetector("https://example.org/data.csv", [], {})
    assert det.compute_fingerprint() == '"abc123"'


def test_fingerprint_collection_stable(httpx_mock: HTTPXMock):
    for url, etag in [
        ("https://example.org/a.csv", '"aaa"'),
        ("https://example.org/b.csv", '"bbb"'),
    ]:
        httpx_mock.add_response(method="HEAD", url=url, headers={"ETag": etag})
    det = URLDetector(
        "https://example.org/",
        ["https://example.org/a.csv", "https://example.org/b.csv"],
        {},
    )
    fp1 = det.compute_fingerprint()
    # reset mock and re-add in same order — fingerprint must be identical
    for url, etag in [
        ("https://example.org/a.csv", '"aaa"'),
        ("https://example.org/b.csv", '"bbb"'),
    ]:
        httpx_mock.add_response(method="HEAD", url=url, headers={"ETag": etag})
    assert det.compute_fingerprint() == fp1


def test_fingerprint_collection_order_independent(httpx_mock: HTTPXMock):
    # [a, b] and [b, a] must produce the same fingerprint
    for url, etag in [
        ("https://example.org/a.csv", '"aaa"'),
        ("https://example.org/b.csv", '"bbb"'),
    ]:
        httpx_mock.add_response(method="HEAD", url=url, headers={"ETag": etag})
    det_ab = URLDetector(
        "https://example.org/",
        ["https://example.org/a.csv", "https://example.org/b.csv"],
        {},
    )
    fp_ab = det_ab.compute_fingerprint()

    for url, etag in [
        ("https://example.org/b.csv", '"bbb"'),
        ("https://example.org/a.csv", '"aaa"'),
    ]:
        httpx_mock.add_response(method="HEAD", url=url, headers={"ETag": etag})
    det_ba = URLDetector(
        "https://example.org/",
        ["https://example.org/b.csv", "https://example.org/a.csv"],
        {},
    )
    assert det_ba.compute_fingerprint() == fp_ab


def test_download_single_file(httpx_mock: HTTPXMock, tmp_path: Path):
    httpx_mock.add_response(
        url="https://example.org/data.csv",
        content=b"a,b,c\n1,2,3\n",
        headers={"Content-Disposition": 'attachment; filename="data.csv"'},
    )
    det = URLDetector("https://example.org/data.csv", [], {})
    files = det.download(tmp_path)
    assert len(files) == 1
    assert files[0].name == "data.csv"
    assert files[0].read_bytes() == b"a,b,c\n1,2,3\n"


def test_download_collection(httpx_mock: HTTPXMock, tmp_path: Path):
    httpx_mock.add_response(url="https://example.org/f1.nc", content=b"data1")
    httpx_mock.add_response(url="https://example.org/f2.nc", content=b"data2")
    det = URLDetector(
        "https://example.org/",
        ["https://example.org/f1.nc", "https://example.org/f2.nc"],
        {},
    )
    files = det.download(tmp_path)
    assert {f.name for f in files} == {"f1.nc", "f2.nc"}
