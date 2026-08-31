import os
import click
from pathlib import Path

from varve.state.repo import LocalGitRepo
from varve.monitor import run_all, run_dataset


@click.group()
def cli() -> None:
    """Varve — dataset monitoring and archiving."""


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
