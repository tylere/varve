from abc import ABC, abstractmethod
from pathlib import Path

from varve.state.models import DatasetRecord


class MirrorSizeError(Exception):
    """Raised when a dataset is too large for the target mirror."""


class Mirror(ABC):
    @abstractmethod
    def upload(self, files: list[Path], dataset: DatasetRecord, run_metadata: dict) -> str:
        """Upload files; return a human-readable remote identifier."""
