import yaml, json
from pathlib import Path
from varve.state.repo import LocalGitRepo
from varve.state.models import DatasetRecord, DestinationRecord, AssignmentRecord, RunRecord, MirrorRecord


def test_list_datasets_empty(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    assert repo.list_datasets() == []


def test_write_and_read_dataset(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    rec = DatasetRecord(
        slug="noaa-sst",
        name="NOAA SST",
        source_url="https://example.org/sst",
        source_urls=[],
        detector_type="url",
        detector_config={},
        enabled=False,
        notes="",
        created_at="2026-08-29T00:00:00Z",
        last_fingerprint=None,
        last_checked_at=None,
    )
    repo.write_dataset(rec)
    result = repo.get_dataset("noaa-sst")
    assert result == rec


def test_update_dataset_state(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    rec = DatasetRecord(
        slug="ds1", name="DS1", source_url="https://x.org/f",
        source_urls=[], detector_type="url", detector_config={},
        enabled=True, notes="", created_at="2026-08-29T00:00:00Z",
        last_fingerprint=None, last_checked_at=None,
    )
    repo.write_dataset(rec)
    repo.update_dataset_state("ds1", fingerprint="sha256:abc", checked_at="2026-08-29T12:00:00Z")
    result = repo.get_dataset("ds1")
    assert result.last_fingerprint == "sha256:abc"
    assert result.last_checked_at == "2026-08-29T12:00:00Z"


def test_write_and_read_run(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    rec = RunRecord(
        dataset_slug="ds1", timestamp="20260829T140000Z",
        started_at="2026-08-29T14:00:00Z", finished_at="2026-08-29T14:00:05Z",
        outcome="unchanged", fingerprint_before="sha256:aaa",
        fingerprint_after="sha256:aaa", log="",
    )
    repo.write_run(rec)
    runs = repo.list_runs("ds1")
    assert len(runs) == 1
    assert runs[0].outcome == "unchanged"


def test_commit_and_push(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    (state_repo / "datasets" / ".gitkeep").write_text("x")
    repo.commit_and_push("test commit")
    # verify commit exists
    import subprocess
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=state_repo, capture_output=True, text=True
    ).stdout
    assert "test commit" in log


def test_commit_no_op_when_nothing_changed(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    repo.commit_and_push("should not commit")
    import subprocess
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=state_repo, capture_output=True, text=True
    ).stdout
    assert "should not commit" not in log
