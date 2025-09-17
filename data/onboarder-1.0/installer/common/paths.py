from pathlib import Path

def version_root() -> Path:
    """
    Returns the version root directory:
      .../data/onboarder-<ver>
    """
    return Path(__file__).resolve().parents[2]

def repo_root() -> Path:
    """
    Returns the repository root, parent of 'data'.
    """
    return version_root().parent.parent

def usr_home() -> Path:
    return repo_root() / "usr_home"

def env_dir(env_name: str) -> Path:
    return usr_home() / env_name
