from pathlib import Path
from installer.common import paths
from installer.common.config_io import ensure_dir


def ensure_usr_home() -> Path:
    return ensure_dir(paths.usr_home())


def env_dir_for(env_name: str) -> Path:
    return paths.env_dir(env_name)


def is_fresh_env(env_dir: Path) -> bool:
    return not env_dir.exists()


def copy_sample_env(env_dir: Path) -> None:
    """
    Copy <version_root>/sample_environment -> <repo_root>/usr_home/<env_name>
    """
    src = paths.version_root() / "sample_environment"
    if not src.exists():
        raise FileNotFoundError(f"sample_environment not found: {src}")
    if env_dir.exists():
        raise FileExistsError(f"Destination already exists: {env_dir}")
    env_dir.parent.mkdir(parents=True, exist_ok=True)
    from shutil import copytree
    copytree(src, env_dir)
