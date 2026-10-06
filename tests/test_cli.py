import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from varve.state.repo import LocalGitRepo
from varve.cli import cli


def _invoke(state_repo: Path, *args: str):
    return CliRunner().invoke(cli, list(args), env={"VARVE_STATE_REPO_PATH": str(state_repo)})


def _last_pushed_subject(state_repo: Path) -> str:
    return subprocess.run(
        ["git", "log", "-1", "--format=%s", "origin/main"],
        cwd=state_repo, capture_output=True, text=True, check=True,
    ).stdout.strip()


def _add_dataset(state_repo: Path, name: str = "NOAA SST"):
    return _invoke(state_repo, "dataset", "add", "--name", name,
                   "--source-url", "https://example.org/sst.nc")


def _add_destination(state_repo: Path, name: str = "Dryad Sandbox"):
    return _invoke(state_repo, "destination", "add", "--name", name,
                   "--type", "dryad", "--credentials-env", "VARVE_DRYAD_CREDS")


# ── dataset add ───────────────────────────────────────────────────────────────

def test_dataset_add_writes_draft_and_pushes(state_repo: Path):
    result = _add_dataset(state_repo)
    assert result.exit_code == 0, result.output
    ds = LocalGitRepo(state_repo).get_dataset("noaa-sst")
    assert ds is not None
    assert ds.source_url == "https://example.org/sst.nc"
    assert ds.detector_type == "url"
    assert ds.enabled is False
    assert _last_pushed_subject(state_repo) == "varve: add dataset noaa-sst"


def test_dataset_add_enable(state_repo: Path):
    result = _invoke(state_repo, "dataset", "add", "--name", "NOAA SST",
                     "--source-url", "https://example.org/sst.nc", "--enable")
    assert result.exit_code == 0, result.output
    assert LocalGitRepo(state_repo).get_dataset("noaa-sst").enabled is True


def test_dataset_add_duplicate_fails(state_repo: Path):
    _add_dataset(state_repo)
    result = _add_dataset(state_repo)
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_dataset_add_slugifies_punctuation(state_repo: Path):
    result = _add_dataset(state_repo, name="NOAA: Sea Surface Temp (v2)!")
    assert result.exit_code == 0, result.output
    assert LocalGitRepo(state_repo).get_dataset("noaa-sea-surface-temp-v2") is not None


def test_dataset_add_long_name_slug_has_no_trailing_dash(state_repo: Path):
    # 63 chars + separator + more: naive truncation to 64 ends on "-"
    result = _add_dataset(state_repo, name="a" * 63 + " b")
    assert result.exit_code == 0, result.output
    slug = LocalGitRepo(state_repo).list_datasets()[0].slug
    assert len(slug) <= 64
    assert not slug.endswith("-")


def test_dataset_add_name_without_alphanumerics_fails(state_repo: Path):
    result = _add_dataset(state_repo, name="!!!")
    assert result.exit_code != 0
    assert not (state_repo / "datasets" / "config.yaml").exists()


# ── destination add ───────────────────────────────────────────────────────────

def test_destination_add_writes_and_pushes(state_repo: Path):
    result = _add_destination(state_repo)
    assert result.exit_code == 0, result.output
    dest = LocalGitRepo(state_repo).get_destination("dryad-sandbox")
    assert dest is not None
    assert dest.type == "dryad"
    assert dest.credentials_env == "VARVE_DRYAD_CREDS"
    assert dest.enabled is True
    assert _last_pushed_subject(state_repo) == "varve: add destination dryad-sandbox"


def test_destination_add_duplicate_fails(state_repo: Path):
    _add_destination(state_repo)
    result = _add_destination(state_repo)
    assert result.exit_code != 0
    assert "already exists" in result.output


# ── assignment add ────────────────────────────────────────────────────────────

def test_assignment_add_writes_and_pushes(state_repo: Path):
    _add_dataset(state_repo)
    _add_destination(state_repo)
    result = _invoke(state_repo, "assignment", "add", "--dataset", "noaa-sst",
                     "--destination", "dryad-sandbox", "--interval", "48")
    assert result.exit_code == 0, result.output
    a = LocalGitRepo(state_repo).get_assignment("noaa-sst-dryad-sandbox")
    assert a is not None
    assert a.dataset_slug == "noaa-sst"
    assert a.destination_slug == "dryad-sandbox"
    assert a.check_interval_hours == 48
    assert a.enabled is True
    assert _last_pushed_subject(state_repo) == "varve: assign noaa-sst → dryad-sandbox"


def test_assignment_add_duplicate_fails(state_repo: Path):
    _add_dataset(state_repo)
    _add_destination(state_repo)
    args = ("assignment", "add", "--dataset", "noaa-sst", "--destination", "dryad-sandbox")
    _invoke(state_repo, *args)
    result = _invoke(state_repo, *args)
    assert result.exit_code != 0
    assert "already exists" in result.output


@pytest.mark.parametrize("missing", ["dataset", "destination"])
def test_assignment_add_missing_reference_fails(state_repo: Path, missing: str):
    if missing != "dataset":
        _add_dataset(state_repo)
    if missing != "destination":
        _add_destination(state_repo)
    result = _invoke(state_repo, "assignment", "add", "--dataset", "noaa-sst",
                     "--destination", "dryad-sandbox")
    assert result.exit_code != 0
    assert f"{missing} " in result.output and "not found" in result.output
    assert LocalGitRepo(state_repo).list_assignments() == []
