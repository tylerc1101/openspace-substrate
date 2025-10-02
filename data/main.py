#!/usr/bin/env python3
"""
Versioned onboarder entrypoint.
Only minimal CLI here; all logic lives in ./installer.
"""

import argparse
import sys
from pathlib import Path

# Ensure this version's installer package is on sys.path first
THIS_DIR = Path(__file__).resolve().parent
INSTALLER_PATH = THIS_DIR / "installer"
if str(INSTALLER_PATH) not in sys.path:
    sys.path.insert(0, str(INSTALLER_PATH))

from installer.commands.init import handle as handle_init  # noqa: E402

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Versioned onboarder")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a new environment")
    init_parser.add_argument("--env", "-e", required=True, help="Environment name (e.g., dev, staging, prod)")
    init_parser.set_defaults(func=handle_init)

    # Add more subcommands per version here later (configure, run, preflight, etc.)
    return parser

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)

if __name__ == "__main__":
    sys.exit(main())
