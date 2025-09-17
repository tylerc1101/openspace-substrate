import shutil
import subprocess
from pathlib import Path
from typing import Optional, Sequence

def detect_engine() -> str:
    if shutil.which("podman"):
        return "podman"
    if shutil.which("docker"):
        return "docker"
    raise FileNotFoundError("No container engine found (docker or podman)")

def load_image(engine: str, tarball: Path) -> None:
    cmd = [engine, "load", "-i", str(tarball)]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)
    if proc.stdout:
        print(proc.stdout.strip())

def _glob_many(base: Path, patterns: Sequence[str]) -> list[Path]:
    out: list[Path] = []
    for pat in patterns:
        out.extend(base.glob(pat))
    return out

def find_version_image_tar(version_root: Path) -> Optional[Path]:
    images_dir = version_root / "images"
    if not images_dir.is_dir():
        return None
    candidates = _glob_many(images_dir, ("*.tar", "*.tar.gz", "*.tgz", "*.oci.tar", "*.oci.tar.gz"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]
