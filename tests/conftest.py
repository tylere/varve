import subprocess
import pytest
from pathlib import Path


@pytest.fixture
def state_repo(tmp_path: Path) -> Path:
    """A working git clone with a bare 'remote', pre-populated with empty subdirs."""
    bare = tmp_path / "remote.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(bare)], check=True)

    working = tmp_path / "repo"
    subprocess.run(["git", "clone", str(bare), str(working)], check=True)
    subprocess.run(["git", "config", "user.email", "ci@varve.test"], cwd=working, check=True)
    subprocess.run(["git", "config", "user.name", "Varve CI"], cwd=working, check=True)

    for d in ["datasets", "destinations", "assignments", "runs", "mirrors"]:
        (working / d).mkdir()
        (working / d / ".gitkeep").touch()

    subprocess.run(["git", "add", "-A"], cwd=working, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=working, check=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=working, check=True)
    return working
