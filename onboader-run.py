#!/usr/bin/env python3
"""
Minimal launcher that locates the newest onboarder in ./data and delegates to it.

Rules:
- Look under <root>/data for directories named 'onboarder-*'
- Choose the highest semantic version (e.g., onboarder-1.2.3 > onboarder-1.0)
- Execute its 'main.py' as __main__
"""

from __future__ import annotations
import sys
import re
import runpy
from pathlib import Path
from typing import Optional, Tuple


ONBOARDER_PREFIX = "onboarder-"
ENTRY_FILE = "main.py"


def get_root_dir() -> Path:
    """Directory where this launcher lives."""
    return Path(__file__).resolve().parent


def find_onboarder_dirs(data_dir: Path) -> list[Path]:
    """Return onboarder-* directories under data/."""
    if not data_dir.exists():
        return []
    return [
        p for p in data_dir.iterdir()
        if p.is_dir() and p.name.startswith(ONBOARDER_PREFIX)
    ]


_version_re = re.compile(rf"^{re.escape(ONBOARDER_PREFIX)}(\d+(?:\.\d+)*)$")


def parse_version_from_name(name: str) -> Optional[Tuple[int, ...]]:
    """
    Extract numeric version tuple from 'onboarder-X[.Y[.Z...]]'.
    Returns None if no match or non-numeric pieces.
    """
    m = _version_re.match(name)
    if not m:
        return None
    parts = m.group(1).split(".")
    try:
        return tuple(int(x) for x in parts)
    except ValueError:
        return None


def choose_best_onboarder(dirs: list[Path]) -> Optional[Path]:
    """
    Choose the best onboarder dir:
      1) Highest parsed semantic version
      2) If none parseable, latest mtime
    """
    if not dirs:
        return None

    with_versions = []
    without_versions = []

    for d in dirs:
        v = parse_version_from_name(d.name)
        if v is not None:
            with_versions.append((v, d))
        else:
            without_versions.append(d)

    if with_versions:
        with_versions.sort(key=lambda t: t[0], reverse=True)
        return with_versions[0][1]

    without_versions.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return without_versions[0] if without_versions else None


def main(argv: list[str]) -> int:
    root = get_root_dir()
    data_dir = root / "data"

    candidates = find_onboarder_dirs(data_dir)
    if not candidates:
        print(f"ERROR: No '{ONBOARDER_PREFIX}*' directories found under: {data_dir}", file=sys.stderr)
        return 1

    chosen = choose_best_onboarder(candidates)
    if not chosen:
        print(f"ERROR: Failed to select an onboarder under: {data_dir}", file=sys.stderr)
        return 1

    entry = chosen / ENTRY_FILE
    if not entry.is_file():
        print(f"ERROR: Expected entry script not found: {entry}", file=sys.stderr)
        return 1

    # Delegate execution
    sys.argv = [str(entry), *argv]  # forward args to the real entry
    try:
        runpy.run_path(str(entry), run_name="__main__")
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception as e:
        print(f"ERROR: Unhandled exception while running {entry}: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

