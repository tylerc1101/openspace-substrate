import sys
from argparse import Namespace
from installer.utils.os_helpers import get_root_dir, copy_environment

def handle(args: Namespace) -> int:
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
