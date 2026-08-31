import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

import httpx
from click.testing import CliRunner

from varve.state.repo import LocalGitRepo
from varve.state.models import (
    DatasetRecord, DestinationRecord, AssignmentRecord,
)
from varve.monitor import is_due, run_dataset
from varve.cli import cli


def _make_dataset(**kwargs) -> DatasetRecord:
    defaults = dict(
        slug="ds1", name="DS1", source_url="https://x.org/f",
        source_urls=[], detector_type="url", detector_config={},
        enabled=True, notes="", created_at="2026-08-29T00:00:00Z",
        last_fingerprint=None, last_checked_at=None,
    )
    return DatasetRecord(**{**defaults, **kwargs})


def _make_assignment(**kwargs) -> AssignmentRecord:
    defaults = dict(
        slug="a1", dataset_slug="ds1", destination_slug="dest1",
        check_interval_hours=48, enabled=True,
    )
    return AssignmentRecord(**{**defaults, **kwargs})


def test_is_due_first_run():
    ds = _make_dataset(last_checked_at=None)
    assert is_due(ds, [_make_assignment()]) is True


def test_is_due_disabled_dataset():
    ds = _make_dataset(enabled=False, last_checked_at=None)
    assert is_due(ds, [_make_assignment()]) is False


def test_is_due_no_assignments():
    ds = _make_dataset(last_checked_at=None)
    assert is_due(ds, []) is False


def test_is_due_not_yet():
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(hours=1)).isoformat()
    ds = _make_dataset(last_checked_at=recent)
    assert is_due(ds, [_make_assignment(check_interval_hours=48)]) is False


def test_is_due_overdue():
    now = datetime.now(timezone.utc)
    old = (now - timedelta(hours=49)).isoformat()
    ds = _make_dataset(last_checked_at=old)
    assert is_due(ds, [_make_assignment(check_interval_hours=48)]) is True


def test_run_dataset_unchanged(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    ds = _make_dataset(last_fingerprint="fp1")
    repo.write_dataset(ds)

    dest = DestinationRecord(
        slug="dest1", name="D", type="dryad",
        credentials_env="VARVE_DRYAD_CREDS", enabled=True,
    )
    repo.write_destination(dest)
    repo.write_assignment(_make_assignment())

    mock_detector = MagicMock()
    mock_detector.compute_fingerprint.return_value = "fp1"  # same as before

    with patch("varve.monitor.get_detector", return_value=mock_detector):
        result = run_dataset("ds1", repo, force=True)

    assert result is not None
    assert result.outcome == "unchanged"
    runs = repo.list_runs("ds1")
    assert len(runs) == 1
    assert runs[0].outcome == "unchanged"


def test_run_dataset_mirrored(state_repo: Path, tmp_path: Path):
    repo = LocalGitRepo(state_repo)
    ds = _make_dataset(last_fingerprint="fp-old")
    repo.write_dataset(ds)

    dest = DestinationRecord(
        slug="dest1", name="D", type="source_coop",
        credentials_env="VARVE_SC_CREDS", enabled=True,
    )
    repo.write_destination(dest)
    repo.write_assignment(_make_assignment())

    data_file = tmp_path / "data.csv"
    data_file.write_text("x,y")

    mock_detector = MagicMock()
    mock_detector.compute_fingerprint.return_value = "fp-new"
    mock_detector.fetch_metadata.return_value = {}
    mock_detector.download.return_value = [data_file]

    mock_mirror = MagicMock()
    mock_mirror.upload.return_value = "https://data.source.coop/org/prod/ts/"

    creds_json = '{"access_key":"k","secret_key":"s","bucket":"b","endpoint_url":null,"owner":"org","product":"prod"}'

    with patch("varve.monitor.get_detector", return_value=mock_detector), \
         patch("varve.monitor.get_mirror", return_value=mock_mirror), \
         patch.dict(os.environ, {"VARVE_SC_CREDS": creds_json}):
        result = run_dataset("ds1", repo, force=True)

    assert result is not None
    assert result.outcome == "mirrored"
    updated = repo.get_dataset("ds1")
    assert updated.last_fingerprint == "fp-new"
    mirrors = repo.list_mirrors("ds1")
    assert len(mirrors) == 1
    assert mirrors[0].remote_identifier == "https://data.source.coop/org/prod/ts/"


def test_run_dataset_disappeared(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    ds = _make_dataset(last_fingerprint="fp1")
    repo.write_dataset(ds)

    dest = DestinationRecord(
        slug="dest1", name="D", type="dryad",
        credentials_env="VARVE_DRYAD_CREDS", enabled=True,
    )
    repo.write_destination(dest)
    repo.write_assignment(_make_assignment())

    mock_response = MagicMock()
    mock_response.status_code = 404

    mock_detector = MagicMock()
    mock_detector.compute_fingerprint.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=mock_response
    )

    with patch("varve.monitor.get_detector", return_value=mock_detector):
        result = run_dataset("ds1", repo, force=True)

    assert result is not None
    assert result.outcome == "disappeared"
    # state.yaml fingerprint/checked_at must NOT be updated
    updated = repo.get_dataset("ds1")
    assert updated.last_fingerprint == "fp1"
    assert updated.last_checked_at is None


def test_cli_monitor_run_unknown_dataset(state_repo: Path):
    runner = CliRunner()
    result = runner.invoke(cli, ["monitor", "run", "--id", "nonexistent"],
                           env={"VARVE_STATE_REPO_PATH": str(state_repo)})
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_cli_monitor_run_skips_disabled(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    ds = _make_dataset(enabled=False, last_checked_at=None)
    repo.write_dataset(ds)
    runner = CliRunner()
    result = runner.invoke(cli, ["monitor", "run"],
                           env={"VARVE_STATE_REPO_PATH": str(state_repo)})
    assert result.exit_code == 0
    assert repo.list_runs("ds1") == []
