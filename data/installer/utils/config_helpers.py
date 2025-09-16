import sys
from pathlib import Path

# Python 3.11+ stdlib TOML parser
try:
    import tomllib  # type: ignore[attr-defined]
except Exception:
    print("ERROR: Python 3.11+ is required (needs stdlib 'tomllib').", file=sys.stderr)
    raise

def env_config_path(env_dir: Path) -> Path:
    """Return <env_dir>/config.toml."""
    return env_dir / "config.toml"


def read_env_config(env_dir: Path) -> dict:
    """
    Read and parse TOML config at <env_dir>/config.toml.
    Returns a Python dict.
    """
    cfg_path = env_config_path(env_dir)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config TOML not found: {cfg_path}")
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Config path is not a file: {cfg_path}")

    with cfg_path.open("rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"Invalid TOML in {cfg_path}: {e}") from e
    return data


def get_core(cfg: dict) -> dict:
    """Return the [core] section or an empty dict."""
    core = cfg.get("core")
    return core if isinstance(core, dict) else {}


def require_core_value(core: dict, key: str) -> str:
    """
    Fetch and validate a required string in [core] (e.g., 'onboarder', 'profile').
    Returns the stripped string or raises ValueError.
    """
    val = core.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"[core].{key} is missing or invalid in config.toml")
    return val.strip()
