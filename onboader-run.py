#!/usr/bin/env python3
"""
onboarder-run.py

Simple framework for onboarding environments.
CLI logic lives here; implementation lives under installer/.
"""

import argparse
import sys
from installer.commands.init import handle as handle_init  # subcommand handler


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
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

