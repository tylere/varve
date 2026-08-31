from __future__ import annotations

import json
import os
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

import httpx

from varve.detectors import get_detector
from varve.mirrors import get_mirror
from varve.mirrors.base import MirrorSizeError
from varve.state.models import AssignmentRecord, DatasetRecord, MirrorRecord, RunRecord
from varve.state.repo import LocalGitRepo


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ts_slug(ts: str) -> str:
    cleaned = ts.replace("-", "").replace(":", "").replace(".", "").rstrip("Z")
    return cleaned[:15] + "Z"


def is_due(dataset: DatasetRecord, assignments: list[AssignmentRecord]) -> bool:
    if not dataset.enabled:
        return False
    active = [a for a in assignments if a.enabled]
    if not active:
        return False
    if dataset.last_checked_at is None:
        return True
    checked = datetime.fromisoformat(dataset.last_checked_at.replace("Z", "+00:00"))
    interval_h = min(a.check_interval_hours for a in active)
    elapsed_h = (datetime.now(timezone.utc) - checked).total_seconds() / 3600
    return elapsed_h >= interval_h


def run_dataset(slug: str, repo: LocalGitRepo, *, force: bool = False) -> RunRecord | None:
    repo.pull()
    dataset = repo.get_dataset(slug)
    if dataset is None:
        raise ValueError(f"Dataset '{slug}' not found in state repo")

    assignments = repo.get_assignments_for_dataset(slug)

    if not force and not is_due(dataset, assignments):
        return None

    started_at = _now_iso()
    ts = _ts_slug(started_at)
    log_lines: list[str] = []

    def _log(msg: str) -> None:
        line = f"[{_now_iso()}] {msg}"
        log_lines.append(line)
        print(line)

    detector = get_detector(dataset)

    # ── detect ───────────────────────────────────────────────────────────────
    try:
        fingerprint_after = detector.compute_fingerprint()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (404, 410):
            _log(f"Dataset disappeared (HTTP {exc.response.status_code})")
            run = RunRecord(
                dataset_slug=slug, timestamp=ts, started_at=started_at,
                finished_at=_now_iso(), outcome="disappeared",
                fingerprint_before=dataset.last_fingerprint, fingerprint_after=None,
                log="\n".join(log_lines),
            )
            repo.write_run(run)
            repo.commit_and_push(f"varve: {slug} @ {ts} — disappeared")
            return run
        tb = traceback.format_exc()
        _log(f"ERROR detector: {tb}")
        run = RunRecord(
            dataset_slug=slug, timestamp=ts, started_at=started_at,
            finished_at=_now_iso(), outcome="detector_error",
            fingerprint_before=dataset.last_fingerprint, fingerprint_after=None,
            log="\n".join(log_lines),
        )
        repo.write_run(run)
        repo.commit_and_push(f"varve: {slug} @ {ts} — detector_error")
        return run
    except Exception:
        tb = traceback.format_exc()
        _log(f"ERROR detector: {tb}")
        run = RunRecord(
            dataset_slug=slug, timestamp=ts, started_at=started_at,
            finished_at=_now_iso(), outcome="detector_error",
            fingerprint_before=dataset.last_fingerprint, fingerprint_after=None,
            log="\n".join(log_lines),
        )
        repo.write_run(run)
        repo.commit_and_push(f"varve: {slug} @ {ts} — detector_error")
        return run

    # ── unchanged check ───────────────────────────────────────────────────────
    # force only bypasses is_due; matching fingerprints always means unchanged
    if fingerprint_after == dataset.last_fingerprint:
        _log("Fingerprint unchanged — no action needed")
        run = RunRecord(
            dataset_slug=slug, timestamp=ts, started_at=started_at,
            finished_at=_now_iso(), outcome="unchanged",
            fingerprint_before=dataset.last_fingerprint,
            fingerprint_after=fingerprint_after,
            log="\n".join(log_lines),
        )
        repo.write_run(run)
        repo.update_dataset_state(slug, checked_at=_now_iso())
        repo.commit_and_push(f"varve: {slug} @ {ts} — unchanged")
        return run

    _log(f"Change detected: {dataset.last_fingerprint!r} → {fingerprint_after!r}")

    # ── download ──────────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        dest_dir = Path(tmp) / "download"
        dest_dir.mkdir()
        try:
            files = detector.download(dest_dir)
            _log(f"Downloaded {len(files)} file(s)")
        except Exception:
            tb = traceback.format_exc()
            _log(f"ERROR download: {tb}")
            run = RunRecord(
                dataset_slug=slug, timestamp=ts, started_at=started_at,
                finished_at=_now_iso(), outcome="detector_error",
                fingerprint_before=dataset.last_fingerprint,
                fingerprint_after=fingerprint_after,
                log="\n".join(log_lines),
            )
            repo.write_run(run)
            repo.commit_and_push(f"varve: {slug} @ {ts} — detector_error")
            return run

        # ── mirror ────────────────────────────────────────────────────────────
        any_mirrored = False
        active_assignments = [a for a in assignments if a.enabled]

        for assignment in active_assignments:
            destination = repo.get_destination(assignment.destination_slug)
            if destination is None or not destination.enabled:
                continue
            try:
                creds_json = os.environ[destination.credentials_env]
                credentials = json.loads(creds_json)
            except KeyError:
                _log(f"SKIP {destination.slug}: env var {destination.credentials_env!r} not set")
                continue

            archived_at = _now_iso()
            run_meta = {"archived_at": archived_at}
            mock_doi = f"10.5072/varve.{slug}.{int(datetime.now(timezone.utc).timestamp())}"
            _log(f"IsDerivedFrom: {dataset.source_url}")
            _log(f"Mock DOI: {mock_doi}")

            try:
                mirror = get_mirror(destination, credentials)
                remote_id = mirror.upload(files, dataset, run_meta)
                _log(f"Mirrored to {destination.slug}: {remote_id}")
            except MirrorSizeError as exc:
                _log(f"SKIP {destination.slug}: {exc}")
                continue
            except Exception:
                tb = traceback.format_exc()
                _log(f"ERROR mirror {destination.slug}: {tb}")
                continue

            mirror_record = MirrorRecord(
                dataset_slug=slug,
                timestamp=_ts_slug(archived_at),
                destination_slug=destination.slug,
                archived_at=archived_at,
                remote_identifier=remote_id,
                mock_doi=mock_doi,
                source_metadata=detector.fetch_metadata(),
            )
            repo.write_mirror(mirror_record)
            any_mirrored = True

    # ── finalise ──────────────────────────────────────────────────────────────
    outcome = "mirrored" if any_mirrored else "mirror_error"
    if any_mirrored:
        repo.update_dataset_state(slug, fingerprint=fingerprint_after, checked_at=_now_iso())

    run = RunRecord(
        dataset_slug=slug, timestamp=ts, started_at=started_at,
        finished_at=_now_iso(), outcome=outcome,
        fingerprint_before=dataset.last_fingerprint,
        fingerprint_after=fingerprint_after,
        log="\n".join(log_lines),
    )
    repo.write_run(run)
    repo.commit_and_push(f"varve: {slug} @ {ts} — {outcome}")
    return run


def run_all(repo: LocalGitRepo, *, force: bool = False) -> list[RunRecord]:
    repo.pull()
    results = []
    for dataset in repo.list_datasets():
        assignments = repo.get_assignments_for_dataset(dataset.slug)
        if force or is_due(dataset, assignments):
            run = run_dataset(dataset.slug, repo, force=force)
            if run:
                results.append(run)
    return results
