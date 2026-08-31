from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from .models import (
    AssignmentRecord,
    DatasetRecord,
    DestinationRecord,
    MirrorRecord,
    RunRecord,
)



class LocalGitRepo:
    def __init__(self, repo_path: Path) -> None:
        self.root = Path(repo_path)

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    # ── git ──────────────────────────────────────────────────────────────────

    def pull(self) -> None:
        try:
            self._git("pull", "--rebase")
        except subprocess.CalledProcessError:
            pass  # no remote, or nothing to pull

    def commit_and_push(self, message: str, max_retries: int = 3) -> None:
        self._git("add", "-A")
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=self.root, capture_output=True
        )
        if staged.returncode == 0:
            return  # nothing to commit
        self._git("commit", "-m", message)
        if not self._git("remote"):
            return  # no remote configured
        for attempt in range(max_retries):
            try:
                self._git("push")
                return
            except subprocess.CalledProcessError:
                if attempt == max_retries - 1:
                    raise
                self._git("pull", "--rebase")

    # ── dataset reads ─────────────────────────────────────────────────────────

    def get_dataset(self, slug: str) -> DatasetRecord | None:
        config_path = self.root / "datasets" / slug / "config.yaml"
        if not config_path.exists():
            return None
        config = yaml.safe_load(config_path.read_text())
        state_path = self.root / "datasets" / slug / "state.yaml"
        state: dict = yaml.safe_load(state_path.read_text()) if state_path.exists() else {}
        state = state or {}
        return DatasetRecord(
            slug=slug,
            name=config["name"],
            source_url=config["source_url"],
            source_urls=config.get("source_urls", []),
            detector_type=config["detector_type"],
            detector_config=config.get("detector_config", {}),
            enabled=config.get("enabled", False),
            notes=config.get("notes", ""),
            created_at=config["created_at"],
            last_fingerprint=state.get("last_fingerprint"),
            last_checked_at=state.get("last_checked_at"),
        )

    def list_datasets(self) -> list[DatasetRecord]:
        d = self.root / "datasets"
        if not d.exists():
            return []
        results = []
        for slug_dir in sorted(d.iterdir()):
            if slug_dir.is_dir():
                r = self.get_dataset(slug_dir.name)
                if r:
                    results.append(r)
        return results

    # ── destination reads ─────────────────────────────────────────────────────

    def get_destination(self, slug: str) -> DestinationRecord | None:
        p = self.root / "destinations" / slug / "config.yaml"
        if not p.exists():
            return None
        c = yaml.safe_load(p.read_text())
        return DestinationRecord(
            slug=slug,
            name=c["name"],
            type=c["type"],
            credentials_env=c["credentials_env"],
            enabled=c.get("enabled", True),
        )

    def list_destinations(self) -> list[DestinationRecord]:
        d = self.root / "destinations"
        if not d.exists():
            return []
        return [r for sd in sorted(d.iterdir()) if sd.is_dir() for r in [self.get_destination(sd.name)] if r]

    # ── assignment reads ──────────────────────────────────────────────────────

    def get_assignment(self, slug: str) -> AssignmentRecord | None:
        p = self.root / "assignments" / slug / "config.yaml"
        if not p.exists():
            return None
        c = yaml.safe_load(p.read_text())
        return AssignmentRecord(
            slug=slug,
            dataset_slug=c["dataset_slug"],
            destination_slug=c["destination_slug"],
            check_interval_hours=c["check_interval_hours"],
            enabled=c.get("enabled", True),
        )

    def list_assignments(self) -> list[AssignmentRecord]:
        d = self.root / "assignments"
        if not d.exists():
            return []
        return [r for sd in sorted(d.iterdir()) if sd.is_dir() for r in [self.get_assignment(sd.name)] if r]

    def get_assignments_for_dataset(self, dataset_slug: str) -> list[AssignmentRecord]:
        return [a for a in self.list_assignments() if a.dataset_slug == dataset_slug]

    # ── run reads ─────────────────────────────────────────────────────────────

    def list_runs(self, dataset_slug: str) -> list[RunRecord]:
        d = self.root / "runs" / dataset_slug
        if not d.exists():
            return []
        records = []
        for f in sorted(d.glob("*.json"), reverse=True):
            data = json.loads(f.read_text())
            records.append(RunRecord(
                dataset_slug=dataset_slug,
                timestamp=f.stem,
                started_at=data["started_at"],
                finished_at=data.get("finished_at"),
                outcome=data["outcome"],
                fingerprint_before=data.get("fingerprint_before"),
                fingerprint_after=data.get("fingerprint_after"),
                log=data.get("log", ""),
            ))
        return records

    # ── mirror reads ──────────────────────────────────────────────────────────

    def list_mirrors(self, dataset_slug: str) -> list[MirrorRecord]:
        d = self.root / "mirrors" / dataset_slug
        if not d.exists():
            return []
        records = []
        for f in sorted(d.glob("*.json"), reverse=True):
            data = json.loads(f.read_text())
            # stem is either "{ts}-{dest_slug}" (new) or "{ts}" (legacy)
            stem_ts = f.stem.split("-")[0] if "-" in f.stem else f.stem
            records.append(MirrorRecord(
                dataset_slug=dataset_slug,
                timestamp=stem_ts,
                destination_slug=data["destination_slug"],
                archived_at=data["archived_at"],
                remote_identifier=data["remote_identifier"],
                mock_doi=data["mock_doi"],
                source_metadata=data.get("source_metadata", {}),
            ))
        return records

    # ── writes ────────────────────────────────────────────────────────────────

    def write_dataset(self, record: DatasetRecord) -> None:
        d = self.root / "datasets" / record.slug
        d.mkdir(parents=True, exist_ok=True)
        config: dict = {
            "name": record.name,
            "source_url": record.source_url,
            "detector_type": record.detector_type,
            "detector_config": record.detector_config,
            "enabled": record.enabled,
            "notes": record.notes,
            "created_at": record.created_at,
        }
        if record.source_urls:
            config["source_urls"] = record.source_urls
        (d / "config.yaml").write_text(yaml.dump(config, sort_keys=False))
        self.update_dataset_state(
            record.slug,
            fingerprint=record.last_fingerprint,
            checked_at=record.last_checked_at,
        )

    def update_dataset_state(
        self, slug: str, *, fingerprint: str | None = None, checked_at: str | None = None
    ) -> None:
        state_path = self.root / "datasets" / slug / "state.yaml"
        state: dict = yaml.safe_load(state_path.read_text()) if state_path.exists() else {}
        state = state or {}
        if fingerprint is not None:
            state["last_fingerprint"] = fingerprint
        if checked_at is not None:
            state["last_checked_at"] = checked_at
        state_path.write_text(yaml.dump(state, sort_keys=False) if state else "")

    def write_destination(self, record: DestinationRecord) -> None:
        d = self.root / "destinations" / record.slug
        d.mkdir(parents=True, exist_ok=True)
        config = {
            "name": record.name,
            "type": record.type,
            "credentials_env": record.credentials_env,
            "enabled": record.enabled,
        }
        (d / "config.yaml").write_text(yaml.dump(config, sort_keys=False))

    def write_assignment(self, record: AssignmentRecord) -> None:
        d = self.root / "assignments" / record.slug
        d.mkdir(parents=True, exist_ok=True)
        config = {
            "dataset_slug": record.dataset_slug,
            "destination_slug": record.destination_slug,
            "check_interval_hours": record.check_interval_hours,
            "enabled": record.enabled,
        }
        (d / "config.yaml").write_text(yaml.dump(config, sort_keys=False))

    def write_run(self, record: RunRecord) -> None:
        d = self.root / "runs" / record.dataset_slug
        d.mkdir(parents=True, exist_ok=True)
        data = {
            "started_at": record.started_at,
            "finished_at": record.finished_at,
            "outcome": record.outcome,
            "fingerprint_before": record.fingerprint_before,
            "fingerprint_after": record.fingerprint_after,
            "log": record.log,
        }
        (d / f"{record.timestamp}.json").write_text(json.dumps(data, indent=2))

    def write_mirror(self, record: MirrorRecord) -> None:
        d = self.root / "mirrors" / record.dataset_slug
        d.mkdir(parents=True, exist_ok=True)
        data = {
            "destination_slug": record.destination_slug,
            "archived_at": record.archived_at,
            "remote_identifier": record.remote_identifier,
            "mock_doi": record.mock_doi,
            "source_metadata": record.source_metadata,
        }
        (d / f"{record.timestamp}-{record.destination_slug}.json").write_text(json.dumps(data, indent=2))
