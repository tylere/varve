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


def test_create_dataset_requires_manager(client: TestClient):
    r = client.post("/datasets", data={
        "name": "Test", "source_url": "https://x.org/f",
        "detector_type": "url", "notes": "",
    })
    assert r.status_code == 403


def test_create_dataset_with_token(state_repo: Path):
    app = create_app(state_repo, manager_token="secret")
    c = TestClient(app, follow_redirects=False)
    r = c.post("/datasets",
               data={"name": "New DS", "source_url": "https://x.org/f",
                     "detector_type": "url", "notes": ""},
               headers={"Authorization": "Bearer secret"})
    assert r.status_code in (200, 302, 303)
    repo = LocalGitRepo(state_repo)
    datasets = repo.list_datasets()
    assert any(d.name == "New DS" for d in datasets)
    new_ds = next(d for d in datasets if d.name == "New DS")
    assert new_ds.enabled is False  # draft by default


def test_toggle_dataset(state_repo: Path):
    repo = LocalGitRepo(state_repo)
    from varve.state.models import DatasetRecord
    ds = DatasetRecord(
        slug="t1", name="T1", source_url="https://x.org",
        source_urls=[], detector_type="url", detector_config={},
        enabled=False, notes="", created_at="2026-08-29T00:00:00Z",
        last_fingerprint=None, last_checked_at=None,
    )
    repo.write_dataset(ds)
    app = create_app(state_repo, manager_token="secret")
    c = TestClient(app)
    r = c.patch("/datasets/t1/toggle", headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200
    assert repo.get_dataset("t1").enabled is True


def test_trigger_requires_manager(client_with_dataset: TestClient):
    r = client_with_dataset.post("/monitor/trigger/noaa-sst")
    assert r.status_code == 403


def test_trigger_unknown_dataset(state_repo: Path):
    app = create_app(state_repo, manager_token="secret")
    c = TestClient(app)
    r = c.post("/monitor/trigger/nonexistent",
               headers={"Authorization": "Bearer secret"})
    assert r.status_code == 404


def test_trigger_returns_run_id(state_repo: Path):
    app = create_app(state_repo, manager_token="secret")
    c = TestClient(app)
    from varve.state.repo import LocalGitRepo
    from varve.state.models import DatasetRecord
    repo = LocalGitRepo(state_repo)
    repo.write_dataset(DatasetRecord(
        slug="noaa-sst", name="NOAA SST", source_url="https://x.org",
        source_urls=[], detector_type="url", detector_config={},
        enabled=True, notes="", created_at="2026-08-29T00:00:00Z",
        last_fingerprint=None, last_checked_at=None,
    ))
    r = c.post("/monitor/trigger/noaa-sst",
               headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200
    body = r.json()
    assert "run_id" in body
