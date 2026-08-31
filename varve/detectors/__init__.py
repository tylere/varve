from pathlib import Path

from varve.state.models import DatasetRecord
from .base import Detector
from .url import URLDetector


class _NotImplementedDetector(Detector):
    def __init__(self, dtype: str) -> None:
        self._type = dtype
    def fetch_metadata(self) -> dict:
        raise NotImplementedError(f"Detector '{self._type}' is not yet implemented")
    def compute_fingerprint(self) -> str:
        raise NotImplementedError(f"Detector '{self._type}' is not yet implemented")
    def download(self, dest_dir: Path) -> list[Path]:
        raise NotImplementedError(f"Detector '{self._type}' is not yet implemented")


def get_detector(dataset: DatasetRecord) -> Detector:
    if dataset.detector_type == "url":
        return URLDetector(dataset.source_url, dataset.source_urls, dataset.detector_config)
    # stac added in next task
    return _NotImplementedDetector(dataset.detector_type)
