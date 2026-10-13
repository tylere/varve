from __future__ import annotations

from datetime import datetime, timezone


def _fmt_dt(iso: str | None) -> str:
    if iso is None:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return iso


_OUTCOME_LABEL: dict[str, str] = {
    "unchanged": "unchanged",
    "mirrored": "mirrored ✓",
    "partial_error": "partial error ⚠️",
    "mirror_error": "mirror error ✗",
    "detector_error": "detector error ✗",
    "disappeared": "disappeared 🔴",
}


def generate_readme(repo) -> str:  # repo: LocalGitRepo (duck-typed to avoid circular import)
    datasets = repo.list_datasets()

    # Use the most recent run timestamp so content is deterministic;
    # a run with no new records won't produce a spurious commit.
    last_run_at: str | None = None
    for ds in datasets:
        runs = repo.list_runs(ds.slug)
        if runs and (last_run_at is None or runs[0].started_at > last_run_at):
            last_run_at = runs[0].started_at

    lines: list[str] = [
        "# Varve Dataset Status",
        "",
        f"*Last updated: {_fmt_dt(last_run_at)}*",
        "",
    ]

    if not datasets:
        lines += ["*No datasets configured.*", ""]
        return "\n".join(lines)

    lines += [
        "## Summary",
        "",
        "| Dataset | Enabled | Last Scanned | Last Archived | Versions |",
        "|---------|---------|--------------|---------------|----------|",
    ]

    for ds in datasets:
        mirrors = repo.list_mirrors(ds.slug)
        last_archived = mirrors[0].archived_at if mirrors else None
        anchor = ds.slug
        name_link = f"[{ds.name}](#{anchor})"
        enabled = "✓" if ds.enabled else "—"
        lines.append(
            f"| {name_link} | {enabled} | {_fmt_dt(ds.last_checked_at)}"
            f" | {_fmt_dt(last_archived)} | {len(ds.archived_hashes)} |"
        )

    lines += ["", "---", ""]

    for ds in datasets:
        runs = repo.list_runs(ds.slug)
        mirrors = repo.list_mirrors(ds.slug)

        lines += [
            f"## {ds.name}",
            "",
            f"- **Slug:** `{ds.slug}`",
            f"- **Source:** {ds.source_url}",
            f"- **Detector:** {ds.detector_type}",
            f"- **Enabled:** {'Yes' if ds.enabled else 'No'}",
            f"- **Created:** {_fmt_dt(ds.created_at)}",
        ]
        if ds.notes:
            lines.append(f"- **Notes:** {ds.notes}")
        lines.append("")

        lines += [
            "**State**",
            "",
            f"- Last scanned: {_fmt_dt(ds.last_checked_at)}",
            f"- Archived versions: {len(ds.archived_hashes)}",
            "",
        ]

        if runs:
            lines += [
                "**Recent Runs** (last 10)",
                "",
                "| Started | Outcome |",
                "|---------|---------|",
            ]
            for run in runs[:10]:
                label = _OUTCOME_LABEL.get(run.outcome, run.outcome)
                lines.append(f"| {_fmt_dt(run.started_at)} | {label} |")
            lines.append("")
        else:
            lines += ["*No runs yet.*", ""]

        if mirrors:
            lines += [
                "**Archived Copies**",
                "",
                "| Archived At | Destination | Location |",
                "|-------------|-------------|----------|",
            ]
            for m in mirrors:
                loc = f"[link]({m.remote_identifier})" if m.remote_identifier else "—"
                lines.append(f"| {_fmt_dt(m.archived_at)} | {m.destination_slug} | {loc} |")
            lines.append("")

        lines += ["---", ""]

    return "\n".join(lines)
