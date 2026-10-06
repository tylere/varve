"""Sources behind a load balancer can report a different fingerprint (ETag) per
backend server while serving identical bytes. Only new *content* should be archived."""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from varve.monitor import run_dataset
from varve.state.models import AssignmentRecord, DatasetRecord, DestinationRecord
from varve.state.repo import LocalGitRepo


class FakeSource:
    """A detector whose fingerprint and served bytes the test controls."""

    def __init__(self) -> None:
        self.fingerprint = ""
        self.content = b""
        self.downloads = 0

    def detector(self) -> MagicMock:
        d = MagicMock()
        d.compute_fingerprint.side_effect = lambda: self.fingerprint
        d.fetch_metadata.return_value = {}
        d.download.side_effect = self._download
        return d

    def _download(self, dest_dir: Path) -> list[Path]:
        self.downloads += 1
        f = dest_dir / "data.kmz"
        f.write_bytes(self.content)
        return [f]


@pytest.fixture
def repo(state_repo: Path) -> LocalGitRepo:
    r = LocalGitRepo(state_repo)
    r.write_dataset(DatasetRecord(
        slug="ds1", name="DS1", source_url="https://x.org/f", source_urls=[],
        detector_type="url", detector_config={}, enabled=True, notes="",
        created_at="2026-08-29T00:00:00Z", last_fingerprint=None, last_checked_at=None,
    ))
    r.write_destination(DestinationRecord(
        slug="dest1", name="D", type="source_coop", credentials_env="VARVE_TEST_CREDS", enabled=True,
    ))
    r.write_assignment(AssignmentRecord(
        slug="a1", dataset_slug="ds1", destination_slug="dest1", check_interval_hours=6, enabled=True,
    ))
    return r


@pytest.fixture
def source() -> FakeSource:
    return FakeSource()


@pytest.fixture
def mirror() -> MagicMock:
    m = MagicMock()
    m.upload.return_value = "https://data.source.coop/org/prod/ts/"
    return m


@pytest.fixture
def run(repo: LocalGitRepo, source: FakeSource, mirror: MagicMock):
    def _run(fingerprint: str, content: bytes) -> str:
        source.fingerprint, source.content = fingerprint, content
        with patch("varve.monitor.get_detector", return_value=source.detector()), \
             patch("varve.monitor.get_mirror", return_value=mirror), \
             patch.dict(os.environ, {"VARVE_TEST_CREDS": "{}"}):
            return run_dataset("ds1", repo, force=True).outcome
    return _run


def test_same_content_under_new_etag_is_not_archived_again(run, mirror):
    assert run('"etag-server-a"', b"v1") == "mirrored"
    assert run('"etag-server-b"', b"v1") == "unchanged"
    assert mirror.upload.call_count == 1


def test_known_alias_skips_download(run, source, mirror):
    run('"etag-server-a"', b"v1")
    run('"etag-server-b"', b"v1")
    downloads = source.downloads
    # Alternating between both servers: no further downloads or uploads
    assert run('"etag-server-a"', b"v1") == "unchanged"
    assert run('"etag-server-b"', b"v1") == "unchanged"
    assert source.downloads == downloads
    assert mirror.upload.call_count == 1


def test_real_change_is_archived(run, mirror):
    run('"etag-server-a"', b"v1")
    assert run('"etag-v2"', b"v2") == "mirrored"
    assert mirror.upload.call_count == 2


def test_server_still_serving_old_content_is_not_rearchived(run, mirror):
    run('"etag-server-a-v1"', b"v1")
    run('"etag-server-b-v1"', b"v1")
    run('"etag-server-a-v2"', b"v2")
    # Server b hasn't picked up v2 yet
    assert run('"etag-server-b-v1"', b"v1") == "unchanged"
    assert mirror.upload.call_count == 2


def test_failed_mirror_is_retried(run, mirror):
    mirror.upload.side_effect = RuntimeError("boom")
    assert run('"etag-server-a"', b"v1") == "mirror_error"
    mirror.upload.side_effect = None
    assert run('"etag-server-b"', b"v1") == "mirrored"


def test_fingerprint_map_is_capped(run, repo):
    for i in range(25):
        run(f'"etag-{i}"', b"v1")
    hashes = repo.get_dataset("ds1").fingerprint_hashes
    assert len(hashes) == 20
    assert '"etag-24"' in hashes and '"etag-0"' not in hashes
