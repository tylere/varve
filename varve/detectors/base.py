from abc import ABC, abstractmethod
from pathlib import Path


class Detector(ABC):
    @abstractmethod
    def fetch_metadata(self) -> dict:
        """Lightweight metadata check — no full download."""

    @abstractmethod
    def compute_fingerprint(self) -> str:
        """Returns a stable string fingerprint of the current dataset state."""

    @abstractmethod
    def download(self, dest_dir: Path) -> list[Path]:
        """Download all files into dest_dir; return list of downloaded paths."""
