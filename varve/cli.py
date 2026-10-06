import os
import re
import sys
from datetime import datetime, timezone
import click
from pathlib import Path

from varve.state.repo import LocalGitRepo
from varve.state.models import DatasetRecord, DestinationRecord, AssignmentRecord
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
def destination() -> None:
    """Manage archive destinations."""


@destination.command("add")
@click.option("--name", required=True, help="Human-readable destination name.")
@click.option("--type", "dest_type", required=True,
              type=click.Choice(["source_coop", "dryad"]), help="Destination type.")
@click.option("--credentials-env", required=True,
              help="Name of the environment variable holding credentials JSON.")
def destination_add(name: str, dest_type: str, credentials_env: str) -> None:
    """Add a new archive destination to the state repo."""
    state_repo_path = Path(os.environ.get("VARVE_STATE_REPO_PATH", "./state-repo"))
    repo = LocalGitRepo(state_repo_path)
    slug = _slugify(name)
    if repo.get_destination(slug) is not None:
        raise click.ClickException(f"destination '{slug}' already exists")
    record = DestinationRecord(
        slug=slug,
        name=name,
        type=dest_type,
        credentials_env=credentials_env,
        enabled=True,
    )
    repo.write_destination(record)
    repo.commit_and_push(f"varve: add destination {slug}")
    click.echo(f"Added destination '{slug}' [{dest_type}] using env var {credentials_env}")


@cli.group()
def assignment() -> None:
    """Manage dataset-to-destination assignments."""


@assignment.command("add")
@click.option("--dataset", "dataset_slug", required=True, help="Dataset slug.")
@click.option("--destination", "destination_slug", required=True, help="Destination slug.")
@click.option("--interval", "check_interval_hours", default=24, show_default=True,
              type=int, help="Check interval in hours.")
def assignment_add(dataset_slug: str, destination_slug: str, check_interval_hours: int) -> None:
    """Assign a dataset to a destination."""
    state_repo_path = Path(os.environ.get("VARVE_STATE_REPO_PATH", "./state-repo"))
    repo = LocalGitRepo(state_repo_path)
    if repo.get_dataset(dataset_slug) is None:
        raise click.ClickException(f"dataset '{dataset_slug}' not found")
    if repo.get_destination(destination_slug) is None:
        raise click.ClickException(f"destination '{destination_slug}' not found")
    slug = _slugify(f"{dataset_slug}-{destination_slug}")
    if repo.get_assignment(slug) is not None:
        raise click.ClickException(f"assignment '{slug}' already exists")
    record = AssignmentRecord(
        slug=slug,
        dataset_slug=dataset_slug,
        destination_slug=destination_slug,
        check_interval_hours=check_interval_hours,
        enabled=True,
    )
    repo.write_assignment(record)
    repo.commit_and_push(f"varve: assign {dataset_slug} → {destination_slug}")
    click.echo(f"Assigned '{dataset_slug}' → '{destination_slug}' (every {check_interval_hours}h)")


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

    _error_outcomes = {"mirror_error", "detector_error", "partial_error"}
    had_error = False

    if slug:
        dataset = repo.get_dataset(slug)
        if dataset is None:
            raise click.ClickException(f"dataset '{slug}' not found in state repo")
        run = run_dataset(slug, repo, force=force)
        if run is None:
            click.echo(f"Skipped {slug} — not due for a run (use --force to override)")
        else:
            click.echo(f"Done: {slug} — {run.outcome}")
            if run.outcome in _error_outcomes:
                had_error = True
    else:
        results = run_all(repo, force=force)
        if not results:
            click.echo("No datasets were due for a run.")
        else:
            for run in results:
                click.echo(f"  {run.dataset_slug}: {run.outcome}")
                if run.outcome in _error_outcomes:
                    had_error = True

    if had_error:
        sys.exit(1)
