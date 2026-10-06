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


# ── slug generation on create ────────────────────────────────────────────────

@pytest.fixture
def mgr_client(state_repo: Path) -> TestClient:
    app = create_app(state_repo, manager_token="secret")
    return TestClient(app, follow_redirects=False,
                      headers={"Authorization": "Bearer secret"})


def _post_dataset(c: TestClient, name: str):
    return c.post("/datasets", data={"name": name, "source_url": "https://x.org/f",
                                     "detector_type": "url", "notes": ""})


def _post_destination(c: TestClient, name: str):
    return c.post("/destinations", data={"name": name, "type": "dryad",
                                         "credentials_env": "VARVE_DRYAD_CREDS"})


def test_create_dataset_long_name_slug_has_no_trailing_dash(mgr_client: TestClient, state_repo: Path):
    r = _post_dataset(mgr_client, "a" * 63 + " b")
    assert r.status_code == 303
    slug = LocalGitRepo(state_repo).list_datasets()[0].slug
    assert len(slug) <= 64
    assert not slug.endswith("-")


def test_create_dataset_name_without_alphanumerics_rejected(mgr_client: TestClient, state_repo: Path):
    r = _post_dataset(mgr_client, "!!!")
    assert r.status_code == 400
    assert not (state_repo / "datasets" / "config.yaml").exists()


def test_create_destination_long_name_slug_has_no_trailing_dash(mgr_client: TestClient, state_repo: Path):
    r = _post_destination(mgr_client, "a" * 63 + " b")
    assert r.status_code == 303
    slug = LocalGitRepo(state_repo).list_destinations()[0].slug
    assert len(slug) <= 64
    assert not slug.endswith("-")


def test_create_destination_name_without_alphanumerics_rejected(mgr_client: TestClient, state_repo: Path):
    r = _post_destination(mgr_client, "!!!")
    assert r.status_code == 400
    assert not (state_repo / "destinations" / "config.yaml").exists()


def test_create_dataset_duplicate_rejected(mgr_client: TestClient, state_repo: Path):
    _post_dataset(mgr_client, "New DS")
    r = mgr_client.post("/datasets", data={"name": "New DS", "source_url": "https://other.org/g",
                                           "detector_type": "url", "notes": ""})
    assert r.status_code == 409
    assert LocalGitRepo(state_repo).get_dataset("new-ds").source_url == "https://x.org/f"


def test_create_destination_duplicate_rejected(mgr_client: TestClient, state_repo: Path):
    _post_destination(mgr_client, "Dryad Sandbox")
    r = mgr_client.post("/destinations", data={"name": "Dryad Sandbox", "type": "source_coop",
                                               "credentials_env": "OTHER"})
    assert r.status_code == 409
    assert LocalGitRepo(state_repo).get_destination("dryad-sandbox").type == "dryad"


def test_create_assignment_duplicate_rejected(mgr_client: TestClient, state_repo: Path):
    _post_dataset(mgr_client, "ds")
    _post_destination(mgr_client, "dest")
    data = {"dataset_slug": "ds", "destination_slug": "dest", "check_interval_hours": "48"}
    mgr_client.post("/assignments", data=data)
    r = mgr_client.post("/assignments", data={**data, "check_interval_hours": "1"})
    assert r.status_code == 409
    assert LocalGitRepo(state_repo).get_assignment("ds-dest").check_interval_hours == 48


@pytest.mark.parametrize("missing", ["dataset", "destination"])
def test_create_assignment_missing_reference_rejected(mgr_client: TestClient, state_repo: Path,
                                                      missing: str):
    if missing != "dataset":
        _post_dataset(mgr_client, "ds")
    if missing != "destination":
        _post_destination(mgr_client, "dest")
    r = mgr_client.post("/assignments", data={"dataset_slug": "ds", "destination_slug": "dest",
                                              "check_interval_hours": "48"})
    assert r.status_code == 400
    assert f"{missing} " in r.json()["detail"] and "not found" in r.json()["detail"]
    assert LocalGitRepo(state_repo).list_assignments() == []


def test_create_assignment_long_slugs_have_no_trailing_dash(mgr_client: TestClient, state_repo: Path):
    _post_dataset(mgr_client, "a" * 63)
    _post_destination(mgr_client, "b")
    r = mgr_client.post("/assignments", data={"dataset_slug": "a" * 63,
                                              "destination_slug": "b",
                                              "check_interval_hours": "48"})
    assert r.status_code == 303
    slug = LocalGitRepo(state_repo).list_assignments()[0].slug
    assert len(slug) <= 64
    assert not slug.endswith("-")
