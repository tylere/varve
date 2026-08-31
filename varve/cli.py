import os
import re
from datetime import datetime, timezone
import click
from pathlib import Path

from varve.state.repo import LocalGitRepo
from varve.state.models import DatasetRecord
from varve.monitor import run_all, run_dataset


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64]


@click.group()
def cli() -> None:
    """Varve — dataset monitoring and archiving."""


@cli.group()
def dataset() -> None:
    """Manage datasets."""


@dataset.command("add")
@click.option("--name", required=True, help="Human-readable dataset name.")
@click.option("--source-url", required=True, help="Primary source URL.")
@click.option("--detector", "detector_type", default="url", show_default=True,
              type=click.Choice(["url", "stac"]), help="Detector type.")
@click.option("--notes", default="", help="Optional notes.")
@click.option("--enable/--no-enable", default=False, show_default=True,
              help="Enable immediately (default: draft).")
def dataset_add(name: str, source_url: str, detector_type: str, notes: str, enable: bool) -> None:
    """Add a new dataset to the state repo."""
    state_repo_path = Path(os.environ.get("VARVE_STATE_REPO_PATH", "./state-repo"))
    repo = LocalGitRepo(state_repo_path)
    slug = _slugify(name)
    if repo.get_dataset(slug) is not None:
        raise click.ClickException(f"dataset '{slug}' already exists")
    record = DatasetRecord(
        slug=slug,
        name=name,
        source_url=source_url,
        source_urls=[],
        detector_type=detector_type,
        detector_config={},
        enabled=enable,
        notes=notes,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        last_fingerprint=None,
        last_checked_at=None,
    )
    repo.write_dataset(record)
    repo.commit_and_push(f"varve: add dataset {slug}")
    status = "enabled" if enable else "draft (use --enable to activate)"
    click.echo(f"Added dataset '{slug}' [{status}]")


@cli.group()
def monitor() -> None:
    """Monitor source datasets for changes."""


@monitor.command("run")
@click.option("--id", "slug", default=None, help="Monitor only this dataset slug.")
@click.option("--force", is_flag=True, default=False,
              help="Ignore check interval; run regardless of last-checked time.")
def monitor_run(slug: str | None, force: bool) -> None:
    """Check enabled datasets for changes and mirror if changed."""
    state_repo_path = Path(os.environ.get("VARVE_STATE_REPO_PATH", "./state-repo"))
    repo = LocalGitRepo(state_repo_path)

    if slug:
        dataset = repo.get_dataset(slug)
        if dataset is None:
            raise click.ClickException(f"dataset '{slug}' not found in state repo")
        run = run_dataset(slug, repo, force=force)
        if run is None:
            click.echo(f"Skipped {slug} — not due for a run (use --force to override)")
        else:
            click.echo(f"Done: {slug} — {run.outcome}")
    else:
        results = run_all(repo, force=force)
        if not results:
            click.echo("No datasets were due for a run.")
        else:
            for run in results:
                click.echo(f"  {run.dataset_slug}: {run.outcome}")
