# varve
Dataset archiving service

> A varve is an annual pair of alternating coarse and fine sediment layers deposited in a body of still water, usually a glacial lake.

Varve monitors source datasets for changes and archives copies to long-term storage destinations (Dryad, source.coop), minting a mock DOI for each archived version. State is stored as YAML/JSON files in a git repository — no database required.

## How it works

1. You create a **state repo** — a plain git repository that holds dataset configs, run history, and mirror records as YAML/JSON files.
2. Varve runs on a schedule (or manually), checks each configured dataset for changes via ETag or STAC asset fingerprinting, downloads changed datasets, uploads them to configured destinations, and commits the updated state back to the repo.
3. An optional web UI lets you browse datasets, destinations, run history, and trigger runs live with streaming log output.

## Setting up a state repo on GitHub

> The same steps apply on GitLab or Gitea — use `.gitlab-ci.yml` or `.gitea/workflows/monitor.yml` from `state-repo-template/` instead of the GitHub Actions file.

### 1. Create the repository

Create a new repository on GitHub (e.g. `my-org/varve-state`). It can be public or private. Clone it locally:

```bash
git clone https://github.com/my-org/varve-state.git
cd varve-state
```

### 2. Add the scheduler workflow

Copy the GitHub Actions workflow from this repo's `state-repo-template/`:

```bash
mkdir -p .github/workflows
cp /path/to/varve/state-repo-template/.github/workflows/monitor.yml .github/workflows/
git add .github/workflows/monitor.yml
git commit -m "Add varve monitor workflow"
git push
```

The workflow runs every 6 hours and can also be triggered manually from the Actions tab.

### 3. Configure archive destinations

Varve supports two archive destinations. You can configure one or both.

#### source.coop

source.coop provides S3-compatible storage. You'll need an account and a product (repository) created at [source.coop](https://source.coop).

Create the credentials JSON — Varve needs your access key, the S3 bucket name, your username (`owner`), and the product slug:

```json
{
  "access_key": "your-access-key-id",
  "secret_key": "your-secret-access-key",
  "bucket": "your-bucket-name",
  "owner": "your-username",
  "product": "your-product-slug",
  "endpoint_url": "https://data.source.coop"
}
```

The `owner` and `product` fields control the public URL path: archived files appear at `https://data.source.coop/{owner}/{product}/{timestamp}/`.

Add this JSON as a GitHub Actions secret named `VARVE_SC_CREDENTIALS` under **Settings → Secrets and variables → Actions**.

Then register the destination in the state repo. Create `destinations/source-coop/config.yaml`:

```yaml
slug: source-coop
name: source.coop
type: source_coop
credentials_env: VARVE_SC_CREDENTIALS
enabled: true
```

#### Dryad

Dryad requires OAuth2 client credentials. Register an application in your [Dryad account settings](https://datadryad.org/stash/user_account) to get a client ID and secret. For testing, use the Dryad sandbox at `https://sandbox.datadryad.org`.

```json
{
  "base_url": "https://datadryad.org",
  "client_id": "your-client-id",
  "client_secret": "your-client-secret"
}
```

Use `"base_url": "https://sandbox.datadryad.org"` for testing. Dryad has a 10 GB per-dataset limit — datasets exceeding this are skipped for Dryad but still mirrored to other destinations.

Add this JSON as a GitHub Actions secret named `VARVE_DRYAD_CREDENTIALS`.

Then create `destinations/dryad/config.yaml`:

```yaml
slug: dryad
name: Dryad
type: dryad
credentials_env: VARVE_DRYAD_CREDENTIALS
enabled: true
```

#### Assigning destinations to datasets

Create `assignments/{dataset-slug}-{destination-slug}/config.yaml` to connect a dataset to a destination:

```yaml
slug: my-dataset-source-coop
dataset_slug: my-dataset
destination_slug: source-coop
check_interval_hours: 24
enabled: true
```

Commit the destination and assignment configs and push. Varve will archive to the configured destinations the next time it detects a change.

### 4. Install varve and configure datasets

```bash
pip install uv
uv tool install varve
```

Add your first dataset:

```bash
# Creates datasets/my-dataset/config.yaml in the state repo
varve dataset add \
  --name "My Dataset" \
  --source-url "https://example.org/data.zip" \
  --detector url
```

Or create `datasets/my-dataset/config.yaml` directly:

```yaml
slug: my-dataset
name: My Dataset
source_url: https://example.org/data.zip
detector_type: url
detector_config: {}
enabled: true
notes: ""
created_at: "2026-01-01T00:00:00Z"
last_fingerprint: null
last_checked_at: null
```

Commit and push the config to trigger the next scheduled run.

### 5. Run manually

```bash
# Check all enabled datasets now (respects check intervals)
VARVE_STATE_REPO_PATH=. varve monitor run

# Force-run a specific dataset regardless of interval
VARVE_STATE_REPO_PATH=. varve monitor run --id my-dataset --force
```

You can also trigger a run from the Actions tab using **workflow_dispatch**.

## Web UI (optional)

The web UI requires a running server with a local clone of the state repo. Serve it with uvicorn:

```bash
VARVE_STATE_REPO_PATH=/path/to/varve-state \
VARVE_MANAGER_TOKEN=your-secret-token \
uvicorn varve.web.app:create_app --factory --reload
```

Open `http://localhost:8000`. Manager write actions (adding datasets, triggering runs) require `?token=your-secret-token` appended to the URL. Omit `VARVE_MANAGER_TOKEN` to make the UI read-only.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `VARVE_STATE_REPO_PATH` | `./state-repo` | Path to the local state repo clone |
| `VARVE_MANAGER_TOKEN` | _(none)_ | Token required for write actions in the web UI; omit for read-only |
| `VARVE_PULL_INTERVAL` | `300` | Seconds between automatic git pulls in the web UI |
