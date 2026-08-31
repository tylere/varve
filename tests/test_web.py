import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from varve.web.app import create_app
from varve.state.repo import LocalGitRepo
from varve.state.models import DatasetRecord


@pytest.fixture
def client(state_repo: Path) -> TestClient:
    app = create_app(state_repo)
    return TestClient(app)


@pytest.fixture
def client_with_dataset(state_repo: Path) -> TestClient:
    repo = LocalGitRepo(state_repo)
    repo.write_dataset(DatasetRecord(
        slug="noaa-sst", name="NOAA SST",
        source_url="https://example.org/sst",
        source_urls=[], detector_type="url", detector_config={},
        enabled=True, notes="Test notes",
        created_at="2026-08-29T00:00:00Z",
        last_fingerprint=None, last_checked_at=None,
    ))
    app = create_app(state_repo)
    return TestClient(app)


def test_dashboard_renders(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert "Varve" in r.text


def test_dataset_list_renders(client: TestClient):
    r = client.get("/datasets")
    assert r.status_code == 200


def test_dataset_detail_renders(client_with_dataset: TestClient):
    r = client_with_dataset.get("/datasets/noaa-sst")
    assert r.status_code == 200
    assert "NOAA SST" in r.text


def test_dataset_detail_404(client: TestClient):
    r = client.get("/datasets/nonexistent")
    assert r.status_code == 404


def test_destinations_requires_manager(client: TestClient):
    r = client.get("/destinations")
    assert r.status_code == 403


def test_destinations_with_token(state_repo: Path):
    app = create_app(state_repo, manager_token="secret")
    c = TestClient(app)
    r = c.get("/destinations", headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200
