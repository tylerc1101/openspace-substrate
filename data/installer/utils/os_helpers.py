from pathlib import Path
import shutil

def get_root_dir() -> Path:
    """
    Return the project root (the directory that contains onboarder-run.py).

    Assumes this file lives at: <root>/installer/utils/os_helpers.py
    So root is two levels up from here.
    """
    return Path(__file__).resolve().parents[2]


def copy_environment(root_dir: Path, env_name: str) -> Path:
    """
    Copy usr_home/sample_environment to usr_home/<env_name>.
    Returns path to new environment.
    """
    src = root_dir / "usr_home" / "sample_environment"
    dst = root_dir / "usr_home" / env_name

    if not src.exists():
        raise FileNotFoundError(f"Source not found: {src}")
    if dst.exists():
        raise FileExistsError(f"Destination already exists: {dst}")

    shutil.copytree(src, dst)
    return dst
