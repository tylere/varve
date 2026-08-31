import os
from pathlib import Path

STATE_REPO_PATH: Path = Path(os.environ.get("VARVE_STATE_REPO_PATH", "./state-repo"))
MANAGER_TOKEN: str | None = os.environ.get("VARVE_MANAGER_TOKEN")
PULL_INTERVAL_SECONDS: int = int(os.environ.get("VARVE_PULL_INTERVAL", "300"))
