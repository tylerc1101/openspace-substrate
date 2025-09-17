from pathlib import Path
import os
import shutil
import subprocess
import sys
from typing import Optional, Tuple

def get_version_root() -> Path:
    return Path(__file__).resolve().parents[2]

def get_repo_root() -> Path:
    return get_version_root().parent.parent

def get_usr_home() -> Path:
    return get_repo_root() / "usr_home"

def ensure_usr_home_dir() -> Path:
    p = get_usr_home()
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_env_dir(env_name: str) -> Path:
    return get_usr_home() / env_name

def get_sample_environment_dir() -> Path:
    return get_version_root() / "sample_environment"

def copy_sample_environment_to(env_dir: Path) -> None:
    src = get_sample_environment_dir()
    if not src.exists():
        raise FileNotFoundError(f"sample_environment not found: {src}")
    if env_dir.exists():
        raise FileExistsError(f"Destination already exists: {env_dir}")
    env_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, env_dir)

def open_in_editor(path: Path) -> None:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        try:
            subprocess.run([editor, str(path)], check=False)
        except Exception as e:
            print(f"⚠️  Failed to launch editor '{editor}': {e}", file=sys.stderr)
        return
    try:
        if sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            print(f"⚠️  No editor configured; please edit: {path}")
    except Exception as e:
        print(f"⚠️  Could not open file automatically; please edit: {path}  ({e})", file=sys.stderr)

# -----------------
# Secrets helpers
# -----------------

def get_secrets_paths() -> Tuple[Path, Path]:
    """
    Return (template_path, filename) for secrets.
    Template: <version_root>/sample_environment/secrets.yaml (recommended)
    Target file name inside env: secrets.yaml
    """
    version_root = get_version_root()
    template = version_root / "sample_environment" / "secrets.yaml"
    return template, Path("secrets.yaml")

def ensure_secrets_on_upgrade(env_dir: Path) -> Path:
    """
    Ensure env has a secrets file in upgrade scenario.
    Behavior:
      - If env secrets.yaml DOES NOT exist and a template exists -> copy it in.
      - If env secrets.yaml DOES exist and a template exists -> write template as secrets.yaml.new next to it.
      - If no template exists -> do nothing.
    Returns the path to the *primary* secrets file the user should edit (env_dir/secrets.yaml).
    """
    template, relname = get_secrets_paths()
    target = env_dir / relname
    if not template.exists():
        return target

    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template, target)
        print(f"✔️ Secrets template copied to: {target}")
    else:
        # keep user's existing secrets; offer the new template for review
        new_path = target.with_suffix(target.suffix + ".new")
        shutil.copy2(template, new_path)
        print(f"ℹ️ New secrets template from this version placed at: {new_path}")

    return target


