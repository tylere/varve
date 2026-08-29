# Varve — Dataset Monitoring & Archiving Service Design

**Date:** 2026-08-28  
**Status:** Approved for implementation  
**Scope:** Prototype — full monitoring loop with real mirror integrations; DOI minting mocked

---

## Overview

Varve monitors source datasets for changes and archives copies to one or more mirror destinations. When a change is detected, the dataset is downloaded and uploaded to each assigned mirror, a mock DOI is recorded, and the event is logged. A web UI lets users browse datasets and monitoring history; managers configure datasets, destinations, and assignments.

---

## Architecture

```
Browser (HTMX)
      │
FastAPI (Jinja2 templates + REST endpoints)
      │
PlatformReader (abstraction — GitHub API or local clone)
      │
State repo (git — local clone on disk)
      │
varve monitor (CLI script, run manually or via CI/CD cron)
    ├── Detector plugins (URL, STAC; DOI/data-portal stubbed)
    └── Mirror adapters (Dryad, source.coop)
```

Three components share state through a git repository:

- **State repo:** a git repository whose files are the canonical record of datasets, destinations, assignments, run history, and mirror copies. It can be hosted on GitHub, GitLab, Gitea, Forgejo, or any git host — or run entirely locally.
- **`varve monitor` CLI:** pulls the state repo, reads config files, runs detectors and mirrors, writes result files, and pushes. All state writes are plain git operations — the CLI never calls a platform REST API.
- **Web UI:** reads state from a local clone (via `LocalGitReader`) or optionally from the platform REST API (via `GitHubReader` / `GitLabReader`) as a faster alternative. Never writes via the API.

The web UI can trigger a monitoring run via a "Run now" button (spawns the CLI as a subprocess, streams output via SSE).

---

## State Repository Layout

All state is stored as YAML/JSON files in a git repository. Git history is the audit trail — no separate database. Credentials are never stored in the repo; they are referenced by environment variable name.

```
state-repo/
├── datasets/
│   └── {slug}/
│       ├── config.yaml     # static config (source_url, detector_type, notes, …)
│       └── state.yaml      # mutable state (last_fingerprint, last_checked_at)
├── destinations/
│   └── {slug}/
│       └── config.yaml     # type, credentials_env, enabled
├── assignments/
│   └── {slug}/
│       └── config.yaml     # dataset_slug, destination_slug, check_interval_hours, enabled
├── runs/
│   └── {dataset-slug}/
│       └── {iso-timestamp}.json   # one file per monitoring run
└── mirrors/
    └── {dataset-slug}/
        └── {iso-timestamp}.json   # one file per successful archive
```

### `datasets/{slug}/config.yaml`
```yaml
name: "NOAA Sea Surface Temperature"
source_url: "https://example.org/dataset/sst"
detector_type: url          # url | stac | doi | data_portal
detector_config: {}         # detector-specific options
notes: ""
created_at: "2026-08-29T00:00:00Z"
```

### `datasets/{slug}/state.yaml`
```yaml
last_fingerprint: "sha256:abc123..."
last_checked_at: "2026-08-29T14:00:00Z"
```

### `destinations/{slug}/config.yaml`
```yaml
name: "Dryad Sandbox"
type: dryad                 # dryad | source_coop
credentials_env: VARVE_DRYAD_CREDENTIALS   # env var holding JSON credentials
enabled: true
```

Credentials are loaded at runtime from the named env var — never written to the repo.

### `assignments/{slug}/config.yaml`
```yaml
dataset_slug: noaa-sst
destination_slug: dryad-sandbox
check_interval_hours: 48
enabled: true
```

### `runs/{dataset-slug}/{iso-timestamp}.json`
```json
{
  "started_at": "2026-08-29T14:00:00Z",
  "finished_at": "2026-08-29T14:00:12Z",
  "outcome": "mirrored",
  "fingerprint_before": "sha256:aaa...",
  "fingerprint_after":  "sha256:bbb...",
  "log": "..."
}
```
Outcomes: `unchanged` | `mirrored` | `disappeared` | `mirror_error` | `detector_error`

### `mirrors/{dataset-slug}/{iso-timestamp}.json`
```json
{
  "destination_slug": "source-coop-varve",
  "archived_at": "2026-08-29T14:00:30Z",
  "remote_identifier": "https://data.source.coop/owner/product/2026-08-29T140030Z/",
  "mock_doi": "10.5072/varve.noaa-sst.1724937630",
  "source_metadata": { "…": "…" }
}
```

---

## State Layer

### Hard constraint: writes via plain git only

The monitor CLI and web UI **never** call a platform REST API to write state. All writes follow this sequence:

```
git pull --rebase
# … modify YAML/JSON files …
git add -A
git commit -m "varve: monitor run {dataset-slug} @ {timestamp} — {outcome}"
git push
```

If `git push` fails (another run pushed concurrently): `git pull --rebase && git push`, up to 3 retries. This is the only concurrency mechanism — no locks, no transactions.

### Platform abstraction for reads

The `PlatformReader` interface provides read-only access to state. The web UI instantiates one at startup based on config:

```python
class PlatformReader:
    def list_datasets(self) -> list[DatasetRecord]
    def get_dataset(self, slug: str) -> DatasetRecord
    def list_runs(self, dataset_slug: str) -> list[RunRecord]
    def list_mirrors(self, dataset_slug: str) -> list[MirrorRecord]
    def list_assignments(self) -> list[AssignmentRecord]
    def list_destinations(self) -> list[DestinationRecord]
```

Implementations:

| Class | Reads from | Use case |
|---|---|---|
| `LocalGitReader` | Local clone on disk | Default; works offline and on any git host |
| `GitHubReader` | GitHub REST API | Faster page loads when hosted on GitHub; no local clone needed |
| `GitLabReader` | GitLab REST API | When hosted on GitLab or self-hosted GitLab |

`LocalGitReader` is the default and the fallback. A background thread periodically runs `git pull` to keep the local clone fresh (configurable interval, default 5 minutes). The monitor CLI always uses the local clone directly.

### Migration path between git hosts

1. `git remote set-url origin <new-host>/<repo>` — core function restored immediately
2. Switch `PlatformReader` implementation in config (or keep `LocalGitReader` — it works everywhere)
3. Update CI/CD scheduler config (GitHub Actions → GitLab CI → Gitea/Forgejo Actions — cron syntax is nearly identical across all three)

The state files themselves require no transformation.

---

## Scheduler

The monitoring loop runs as a CI/CD cron job. The state repo ships a workflow file for each supported platform:

| File | Platform |
|---|---|
| `.github/workflows/monitor.yml` | GitHub Actions |
| `.gitlab-ci.yml` | GitLab CI / self-hosted GitLab |
| `.gitea/workflows/monitor.yml` | Gitea Actions / Forgejo Actions |

Each workflow: checkout state repo → install varve → `varve monitor run` → the CLI handles committing and pushing results.

For operators not using any of these platforms, `varve monitor run` can be invoked directly via system cron or any scheduler that can run a shell command.

---

## Detector Plugin System

### Interface

```python
class Detector:
    def fetch_metadata(self) -> dict           # lightweight: version, last-modified, size
    def compute_fingerprint(self) -> str       # ETag, checksum, or version hash
    def download(self, dest_dir: Path) -> list[Path]  # stream files into dest_dir, return list
```

`download()` always writes into a directory and returns the list of files placed there. Single-file datasets return a one-element list. Mirror adapters iterate over the list and upload each file individually — no zipping.

**Fingerprinting collections:** SHA-256 of the sorted `[(filename, etag_or_size), ...]` pairs. Stable across runs when the collection is unchanged; changes when any file is added, removed, or modified.

### `URLDetector`
- `fetch_metadata()`: HEAD request; captures `ETag`, `Last-Modified`, `Content-Length`
- `compute_fingerprint()`: returns `ETag` if present; else SHA-256 of the first 1 MB via range request as a cheap probe; falls back to full-download SHA-256 only if neither is available
- `download()`: streaming GET into `dest_dir/{filename}` (filename inferred from URL or `Content-Disposition`); returns `[dest_dir/filename]`

### `STACDetector`
- `fetch_metadata()`: GET the STAC Item JSON; captures `datetime`, `updated`, asset `href`s and their sizes
- `compute_fingerprint()`: collection fingerprint over all asset `(href-basename, etag-or-size)` pairs + item `updated` field
- `download()`: HEAD each asset href first (cheap); streaming GET each asset into `dest_dir/`; returns list of downloaded paths. Only downloads assets listed in `detector_config.asset_keys` if specified, otherwise all assets.

### `DOIDetector`, `DataPortalDetector`
Registered but raise `NotImplementedError`. Architecture is in place for future implementation.

### Detector selection
`dataset.detector_type` maps to a detector class via a registry dict. Instantiated with `dataset.source_url` and `dataset.detector_config`.

---

## Monitor CLI

### Entry point

```
varve monitor run              # check all enabled datasets due for a run
varve monitor run --id 42      # check one specific dataset
varve monitor run --force      # ignore interval, check all enabled datasets now
```

"Due for a run" means: `last_checked_at IS NULL` OR `last_checked_at + check_interval_hours ≤ now()`.

### Per-dataset flow

1. `git pull --rebase` on the local state repo clone
2. Read `datasets/{slug}/config.yaml` and `state.yaml`; load active assignments
3. Instantiate detector; call `fetch_metadata()` + `compute_fingerprint()`
4. Compare fingerprint to `state.yaml.last_fingerprint`
5. **Unchanged:** write `runs/{slug}/{timestamp}.json` (outcome `unchanged`); update `state.yaml.last_checked_at`; commit + push; stop
6. **Changed or first run:**
   a. Call `detector.download()` into a temp directory; receives list of local paths
   b. For each active assignment: call the appropriate mirror adapter's `upload()`, passing the file list
   c. Write `mirrors/{slug}/{timestamp}.json` per destination
   d. Mint mock DOI: `10.5072/varve.{slug}.{unix_timestamp}`; store in mirror JSON; log `IsDerivedFrom: {source_url}`
   e. Update `state.yaml` (`last_fingerprint`, `last_checked_at`)
   f. Write `runs/{slug}/{timestamp}.json` (outcome `mirrored`)
   g. `git add -A && git commit -m "varve: {slug} @ {timestamp} — mirrored" && git push` (with rebase-retry on conflict)
7. **Source 404/410:** write run JSON (outcome `disappeared`); do NOT update `state.yaml`; commit + push; log warning
8. **Any exception:** write run JSON (outcome `detector_error` or `mirror_error`); do NOT update `state.yaml`; commit + push; log traceback

The CLI prints structured log lines (timestamp + level + message) that can be consumed by the SSE endpoint.

---

## Web UI

**Stack:** FastAPI + Jinja2 + HTMX. No JS build step.

**State access:** The web server holds a `PlatformReader` instance (default: `LocalGitReader` pointed at a local clone of the state repo). A background thread pulls the clone every 5 minutes. Manager write actions (add dataset, add destination, add assignment, toggle assignment) commit and push directly via the local clone — plain git, no platform API.

**Manager authentication:** `VARVE_MANAGER_TOKEN` env var. Manager routes check for matching `Authorization: Bearer <token>` header or `?token=<token>` query param. No token = read-only user.

### Routes

| Method | Path | Access | Description |
|---|---|---|---|
| GET | `/` | All | Dashboard: recent runs, dataset count, last-checked summary |
| GET | `/datasets` | All | Dataset list with status badges |
| GET | `/datasets/{id}` | All | Dataset detail: monitoring history, mirror copies |
| GET | `/datasets/new` | Manager | Add dataset form |
| POST | `/datasets` | Manager | Create dataset |
| GET | `/datasets/{id}/edit` | Manager | Edit dataset |
| POST | `/datasets/{id}` | Manager | Update dataset |
| GET | `/destinations` | Manager | List destinations |
| GET | `/destinations/new` | Manager | Add destination form |
| POST | `/destinations` | Manager | Create destination |
| GET | `/assignments` | Manager | Dataset→destination assignment table |
| GET | `/assignments/new` | Manager | Create assignment form |
| POST | `/assignments` | Manager | Create assignment |
| POST | `/monitor/trigger/{dataset_id}` | Manager | Spawn monitor run, return `run_id` |
| GET | `/monitor/stream/{run_id}` | Manager | SSE stream of log lines for a run |
| GET | `/monitor/status/{run_id}` | All | JSON: run outcome + finished flag (for HTMX polling) |
| PATCH | `/assignments/{id}/toggle` | Manager | Enable/disable an assignment inline |

### HTMX interactions
- "Run now" button: POST to `/monitor/trigger/{id}`, gets `run_id`, opens SSE stream into a log panel via `hx-ext="sse"`
- Dataset list status badges: `hx-trigger="every 30s"` partial refresh
- Assignment table: inline enable/disable toggle via PATCH

---

## Mirror Adapters

### Interface

```python
class Mirror:
    def upload(self, files: list[Path], dataset: Dataset, run_metadata: dict) -> str
    # returns remote_identifier (Dryad dataset ID or source.coop URL prefix)
```

Accepts a list of local file paths (one for single-file datasets, many for collections). Returns a human-readable remote identifier stored in `mirror_copy.remote_identifier`.

### `DryadMirror`
- Auth: OAuth2 client-credentials flow against `https://sandbox.datadryad.org` (sandbox for prototype)
- **Size check:** if total file size exceeds 10 GB, raise `MirrorSizeError` immediately — Dryad cannot accept TB-scale datasets. The monitor logs `mirror_error` for this assignment and continues to other destinations.
- Flow: `POST /api/v2/datasets` → for each file: `PUT /api/v2/datasets/{id}/files/{filename}` → `POST /api/v2/datasets/{id}/versions`
- Captures Dryad-assigned DOI if returned; otherwise falls back to mock DOI
- Credentials in `destination.credentials`: `{"client_id": "...", "client_secret": "...", "base_url": "https://sandbox.datadryad.org"}`

### `SourceCoopMirror`
source.coop datasets are addressed as `https://data.source.coop/{owner}/{product}/{filepath}`. The mirror adapter uploads files to S3 with keys structured to match this URL pattern.

- S3-compatible upload via `boto3`
- Credentials include `owner` and `product` fields that set the key prefix: `{owner}/{product}/{archived_at_iso}/{filename}`
- **Streaming upload:** for each file, uses `boto3` multipart upload streaming directly from the source HTTP response where possible — avoiding writing large files to local disk. The `download()` step is bypassed for source.coop destinations when the detector supports streaming; otherwise falls back to uploading from the temp file list.
- After all files are uploaded, writes a minimal STAC Item JSON to `{owner}/{product}/{archived_at_iso}/stac-item.json` referencing each asset at its full `https://data.source.coop/...` URL
- Credentials in `destination.credentials`: `{"access_key": "...", "secret_key": "...", "bucket": "...", "endpoint_url": "...", "owner": "...", "product": "..."}`
- `remote_identifier` returned: `https://data.source.coop/{owner}/{product}/{archived_at_iso}/`

### Failure handling
If `upload()` raises, the `monitor_run` outcome is set to `mirror_error` and the exception traceback is appended to `monitor_run.log`. `dataset.last_fingerprint` is NOT updated, so the next scheduled run retries. A `MirrorSizeError` is logged clearly without a traceback.

---

## Project Structure

```
varve/                          # Python package (pip-installable)
├── varve/
│   ├── __init__.py
│   ├── state/
│   │   ├── reader.py           # PlatformReader base + LocalGitReader
│   │   ├── github_reader.py    # GitHubReader (optional, read-only)
│   │   ├── gitlab_reader.py    # GitLabReader (optional, read-only)
│   │   └── models.py           # dataclasses: DatasetRecord, RunRecord, etc.
│   ├── cli.py                  # varve monitor CLI (Click)
│   ├── detectors/
│   │   ├── base.py
│   │   ├── url.py
│   │   └── stac.py
│   ├── mirrors/
│   │   ├── base.py
│   │   ├── dryad.py
│   │   └── source_coop.py
│   ├── web/
│   │   ├── app.py              # FastAPI app factory
│   │   ├── routes/
│   │   │   ├── datasets.py
│   │   │   ├── destinations.py
│   │   │   ├── assignments.py
│   │   │   └── monitor.py
│   │   └── templates/
│   │       ├── base.html
│   │       ├── dashboard.html
│   │       ├── datasets/
│   │       └── ...
│   └── config.py               # env var loading
├── tests/
│   ├── test_detectors.py
│   ├── test_mirrors.py
│   ├── test_monitor.py
│   └── test_state_reader.py
├── pyproject.toml
└── README.md

state-repo/                     # separate git repository (the state store)
├── datasets/
├── destinations/
├── assignments/
├── runs/
├── mirrors/
├── .github/workflows/monitor.yml
├── .gitlab-ci.yml
└── .gitea/workflows/monitor.yml
```

---

## Testing Approach

- **Detectors:** unit tests with `pytest-httpx` to mock HTTP; test fingerprint stability and change detection logic
- **Mirrors:** unit tests with `moto` (S3 mock for source.coop) and `pytest-httpx` mocks for Dryad API
- **State layer:** unit tests for `LocalGitReader` against a fixture repo (a real git repo created in `tmp_path`); assert YAML files are read and written correctly; assert push-retry logic on conflict
- **Monitor CLI:** integration tests using a fixture state repo; run the CLI against mocked detectors and mirrors; assert the correct YAML/JSON files are written and committed
- **Web routes:** FastAPI `TestClient` with a `LocalGitReader` pointed at a fixture repo; assert page renders and manager-only routes reject unauthenticated requests

---

## Out of Scope (Prototype)

- Dataset proposal workflow (GitHub Issues integration)
- Real DOI minting via DataCite API
- User accounts / full auth system
- `GitHubReader` / `GitLabReader` implementations (prototype uses `LocalGitReader` only)
- DOI/data-portal detector implementations
- Streaming bypass of local temp for non-S3 sources (first cut downloads to temp dir regardless)
