from dataclasses import dataclass


@dataclass
class DatasetRecord:
    slug: str
    name: str
    source_url: str
    source_urls: list[str]
    detector_type: str
    detector_config: dict
    enabled: bool
    notes: str
    created_at: str
    last_fingerprint: str | None
    last_checked_at: str | None


@dataclass
class DestinationRecord:
    slug: str
    name: str
    type: str
    credentials_env: str
    enabled: bool


@dataclass
class AssignmentRecord:
    slug: str
    dataset_slug: str
    destination_slug: str
    check_interval_hours: int
    enabled: bool


@dataclass
class RunRecord:
    dataset_slug: str
    timestamp: str          # filename-safe ISO slug, e.g. "20260829T140000Z"
    started_at: str         # full ISO-8601
    finished_at: str | None
    outcome: str            # unchanged|mirrored|disappeared|mirror_error|detector_error
    fingerprint_before: str | None
    fingerprint_after: str | None
    log: str


@dataclass
class MirrorRecord:
    dataset_slug: str
    timestamp: str
    destination_slug: str
    archived_at: str
    remote_identifier: str
    mock_doi: str
    source_metadata: dict
