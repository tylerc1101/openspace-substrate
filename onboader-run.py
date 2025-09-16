#!/usr/bin/env python3
"""
onboarder-run.py

Simple framework for onboarding environments.
Supports subcommands for easy expansion.
"""

import argparse
import shutil
import sys
from pathlib import Path


# ---------------------------
# Helpers
# ---------------------------

def get_root_dir() -> Path:
    """Return the directory where this script lives."""
    return Path(__file__).resolve().parent


def copy_environment(root_dir: Path, env_name: str) -> Path:
    """
    Copy sample_environment to usr_home/<env_name>.
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


# ---------------------------
# Subcommand Handlers
# ---------------------------

def handle_init(args: argparse.Namespace) -> int:
    """Handle the 'init' subcommand."""
    root_dir = get_root_dir()
    env_name = args.env.strip()

    if not env_name:
        print("❌ ERROR: Environment name cannot be empty.", file=sys.stderr)
        return 1

    try:
        new_env_path = copy_environment(root_dir, env_name)
    except Exception as e:
        print(f"❌ ERROR: {e}", file=sys.stderr)
        return 1

    print(f"✔️ Environment '{env_name}' created at {new_env_path}")
    return 0


# ---------------------------
# Main CLI
# ---------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser with subcommands."""
    parser = argparse.ArgumentParser(description="Environment onboarding tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init subcommand
    init_parser = subparsers.add_parser("init", help="Initialize a new environment")
    init_parser.add_argument(
        "--env", "-e",
        required=True,
        help="Name of environment to create (e.g., dev, staging, prod)"
    )
    init_parser.set_defaults(func=handle_init)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Call the right handler
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
