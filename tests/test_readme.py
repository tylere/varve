from pathlib import Path

from varve.state.repo import LocalGitRepo
from varve.state.models import DatasetRecord, MirrorRecord, RunRecord
from varve.readme import generate_readme


def _make_dataset(**kwargs) -> DatasetRecord:
    defaults = dict(
        slug="test-ds", name="Test Dataset", source_url="https://example.org/data",
        source_urls=[], detector_type="url", detector_config={},
        enabled=True, notes="", created_at="2026-09-01T00:00:00Z",
        last_fingerprint=None, last_checked_at=None,
    )
    return DatasetRecord(**{**defaults, **kwargs})


def test_generate_readme_no_datasets(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    readme = generate_readme(repo)
    assert "# Varve Dataset Status" in readme
    assert "No datasets configured" in readme


def test_generate_readme_with_dataset(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    ds = _make_dataset(last_checked_at="2026-10-01T08:00:00Z")
    repo.write_dataset(ds)

    readme = generate_readme(repo)
    assert "Test Dataset" in readme
    assert "test-ds" in readme
    assert "https://example.org/data" in readme
    assert "2026-10-01 08:00 UTC" in readme
    assert "No runs yet" in readme


def test_generate_readme_with_runs_and_mirrors(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    ds = _make_dataset(last_checked_at="2026-10-10T12:00:00Z")
    repo.write_dataset(ds)
    repo.update_dataset_state("test-ds", archived_hashes=["sha256:abc"])

    run = RunRecord(
        dataset_slug="test-ds", timestamp="20261010T120000Z",
        started_at="2026-10-10T12:00:00Z", finished_at="2026-10-10T12:00:05Z",
        outcome="mirrored", fingerprint_before=None, fingerprint_after="etag-1", log="",
        mirror_outcomes={"dest-a": "mirrored"},
    )
    repo.write_run(run)

    mirror = MirrorRecord(
        dataset_slug="test-ds", timestamp="20261010T120000Z",
        destination_slug="dest-a", archived_at="2026-10-10T12:00:03Z",
        remote_identifier="https://data.example.org/archive/20261010/",
        mock_doi="10.5072/varve.test-ds.1",
        source_metadata={},
    )
    repo.write_mirror(mirror)

    readme = generate_readme(repo)
    assert "mirrored ✓" in readme
    assert "dest-a" in readme
    assert "https://data.example.org/archive/20261010/" in readme
    assert "| 1 |" in readme  # archived versions count in summary table


def test_readme_written_on_commit(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    ds = _make_dataset()
    repo.write_dataset(ds)
    repo.commit_and_push("add dataset")
    assert (state_repo / "README.md").exists()
    readme = (state_repo / "README.md").read_text()
    assert "Test Dataset" in readme


def test_readme_not_committed_when_nothing_to_commit(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    # no changes — commit_and_push should be a no-op and not create README
    repo.commit_and_push("should not commit")
    assert not (state_repo / "README.md").exists()


def test_run_all_bootstraps_readme_when_nothing_due(state_repo: Path):
    """run_all must create README even when no datasets are due for a run."""
    from varve.monitor import run_all

    repo = LocalGitRepo(state_repo)
    # Dataset checked very recently so is_due returns False
    ds = _make_dataset(
        enabled=True,
        last_checked_at="2099-01-01T00:00:00Z",  # far future → never due
    )
    repo.write_dataset(ds)
    repo.commit_and_push("add dataset")

    results = run_all(repo)
    assert results == []
    assert (state_repo / "README.md").exists()
    readme = (state_repo / "README.md").read_text()
    assert "Test Dataset" in readme


def test_run_all_readme_no_spurious_commit(state_repo: Path):
    """Second run_all with no state change does not create an extra commit."""
    import subprocess
    from varve.monitor import run_all

    repo = LocalGitRepo(state_repo)
    ds = _make_dataset(enabled=True, last_checked_at="2099-01-01T00:00:00Z")
    repo.write_dataset(ds)
    repo.commit_and_push("add dataset")

    run_all(repo)  # creates README
    log1 = subprocess.run(
        ["git", "log", "--oneline"], cwd=state_repo, capture_output=True, text=True
    ).stdout.strip()

    run_all(repo)  # nothing changed → no new commit
    log2 = subprocess.run(
        ["git", "log", "--oneline"], cwd=state_repo, capture_output=True, text=True
    ).stdout.strip()

    assert log1 == log2
