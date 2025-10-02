#!/usr/bin/env python3
"""
Minimal launcher:
- Find latest data/onboarder-<version> directory
- Load its container image tar (docker|podman)
- Run the container with /data and /usr_home mounted
- Inside the container, execute: python3 /data/<onboarder-dir>/main.py <args>
"""

from __future__ import annotations

import os
import re
import runpy
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple, List

ONBOARDER_PREFIX = "onboarder-"


# ---------------------------
# Path helpers
# ---------------------------

def repo_root() -> Path:
    return Path(__file__).resolve().parent

def data_dir() -> Path:
    return repo_root() / "data"

def usr_home_dir() -> Path:
    d = repo_root() / "usr_home"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------
# Onboarder version discovery
# ---------------------------

_version_re = re.compile(rf"^{re.escape(ONBOARDER_PREFIX)}(\d+(?:\.\d+)*)$")

def parse_version_from_name(name: str) -> Optional[Tuple[int, ...]]:
    m = _version_re.match(name)
    if not m:
        return None
    try:
        return tuple(int(x) for x in m.group(1).split("."))
    except ValueError:
        return None

def find_latest_onboarder_dir(droot: Path) -> Optional[Path]:
    candidates = [p for p in droot.iterdir() if p.is_dir() and p.name.startswith(ONBOARDER_PREFIX)]
    if not candidates:
        return None
    with_versions = []
    without_versions = []
    for d in candidates:
        v = parse_version_from_name(d.name)
        (with_versions if v is not None else without_versions).append((v, d) if v else d)
    if with_versions:
        with_versions.sort(key=lambda t: t[0], reverse=True)
        return with_versions[0][1]
    # fallback by mtime
    without_versions.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return without_versions[0] if without_versions else None


# ---------------------------
# Container engine + image
# ---------------------------

def detect_engine() -> str:
    from shutil import which
    if which("podman"):
        return "podman"
    if which("docker"):
        return "docker"
    raise FileNotFoundError("No container engine found in PATH (podman or docker)")

def find_image_tar(version_dir: Path) -> Optional[Path]:
    images = version_dir / "images"
    if not images.is_dir():
        return None
    candidates: List[Path] = []
    for pat in ("*.tar", "*.tar.gz", "*.tgz", "*.oci.tar", "*.oci.tar.gz"):
        candidates.extend(images.glob(pat))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]

_image_loaded_re = re.compile(r"Loaded image(?:\(s\))?:\s*(\S+)", re.IGNORECASE)
_image_id_re     = re.compile(r"sha256:[a-f0-9]{64}", re.IGNORECASE)

def load_image(engine: str, tar: Path) -> str:
    """
    Load the tarball with <engine> load -i <tar>
    Return the best-guess image reference (repo:tag or image ID) for `engine run`.
    """
    cmd = [engine, "load", "-i", str(tar)]
    proc = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(f"Failed to load image ({engine}): {msg}")

    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    # Try to extract a repo:tag
    m = None
    for line in out.splitlines():
        m = _image_loaded_re.search(line)
        if m:
            break
    if m:
        return m.group(1)

    # Fallback: image ID
    mid = _image_id_re.search(out)
    if mid:
        return mid.group(0)

    # Last resort: allow manual override via file
    # If data/onboarder-*/image.txt exists with the reference, use it.
    return ""  # caller can decide to error or fallback


# ---------------------------
# Running the container
# ---------------------------

def tty_args(engine: str) -> list[str]:
    # Add -it if attached to a TTY for nicer UX
    # (safe for both docker and podman)
    if sys.stdin.isatty() and sys.stdout.isatty():
        return ["-it"]
    return []

def run_in_container(engine: str, image_ref: str, host_data: Path, host_usr_home: Path, version_dir: Path, args: list[str]) -> int:
    """
    Run inside the image with mounts:
      host <repo>/data     -> /data
      host <repo>/usr_home -> /usr_home
    Execute: python3 /data/<onboarder-dir>/main.py <args...>
    """
    container_data = "/data"
    container_usr_home = "/usr_home"
    onboarder_inside = f"{container_data}/{version_dir.name}"
    entry = f"{onboarder_inside}/main.py"

    cmd = [
        engine, "run", "--rm",
        *tty_args(engine),
        "-v", f"{str(host_data)}:{container_data}:Z",
        "-v", f"{str(host_usr_home)}:{container_usr_home}:Z",
        "-w", onboarder_inside,
        image_ref,
        "python3", entry, *args
    ]

    # Inherit user's environment minimally; adjust if needed later
    proc = subprocess.run(cmd)
    return proc.returncode


# ---------------------------
# Main flow
# ---------------------------

def main(argv: list[str]) -> int:
    root = repo_root()
    ddir = data_dir()
    udir = usr_home_dir()

    # 1) Find latest onboarder dir
    version_dir = find_latest_onboarder_dir(ddir)
    if not version_dir:
        print(f"ERROR: No '{ONBOARDER_PREFIX}*' directories found under: {ddir}", file=sys.stderr)
        return 1

    # 2) Detect engine
    try:
        engine = detect_engine()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # 3) Load image tar (if present)
    image_ref = ""
    tar = find_image_tar(version_dir)
    if tar:
        try:
            print(f"🔧 Loading image from: {tar}")
            image_ref = load_image(engine, tar)
        except Exception as e:
            print(f"ERROR: Failed to load image: {e}", file=sys.stderr)
            return 1
    else:
        # Optional: allow an image reference file if tar isn't bundled
        ref_file = version_dir / "image.txt"
        if ref_file.exists():
            image_ref = ref_file.read_text(encoding="utf-8").strip()

    if not image_ref:
        print(
            "ERROR: Could not determine image reference to run.\n"
            f"- Ensure an image tar exists under: {version_dir}/images\n"
            f"  OR provide {version_dir}/image.txt with a repo:tag",
            file=sys.stderr
        )
        return 1

    # 4) Run the container, executing that version's main.py with forwarded args
    print(f"▶️  Running {engine} with image: {image_ref}")
    rc = run_in_container(engine, image_ref, ddir, udir, version_dir, argv)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
