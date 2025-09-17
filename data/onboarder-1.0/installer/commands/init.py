import sys
from argparse import Namespace
from pathlib import Path

from .tasks.env import ensure_usr_home, env_dir_for, is_fresh_env, copy_sample_env
from .tasks.config_merge import merge_config
from .tasks.secrets import handle_secrets_after_config
from .tasks.build_plan import regenerate_build_plan


def handle(args: Namespace) -> int:
    env_name = args.env.strip()
    if not env_name:
        print("❌ ERROR: Environment name cannot be empty.", file=sys.stderr)
        return 1

    try:
        ensure_usr_home()
    except Exception as e:
        print(f"❌ ERROR: failed to ensure usr_home: {e}", file=sys.stderr)
        return 1

    env_dir: Path = env_dir_for(env_name)
    fresh = is_fresh_env(env_dir)

    if fresh:
        try:
            copy_sample_env(env_dir)
            print(f"✔️ Environment '{env_name}' created at {env_dir}")
        except Exception as e:
            print(f"❌ ERROR: {e}", file=sys.stderr)
            return 1

    # Merge config (fresh = no merge; upgrade = merge + backup)
    try:
        merge_result = merge_config(env_dir, fresh=fresh)
    except Exception as e:
        print(f"❌ ERROR: config merge failed: {e}", file=sys.stderr)
        return 1

    if merge_result.backup_path:
        print(f"💾 Backup of previous config: {merge_result.backup_path}")
    print(f"✔️ Config is at: {merge_result.config_path}")

    # Always regenerate build plan on init
    try:
        plan_path, plan_count, plan_preview = regenerate_build_plan(env_dir, merge_result.config_dict)
        print(f"🧭 Build plan generated ({plan_count} tasks): {plan_path}")
        if plan_preview:
            print("   Preview:")
            for line in plan_preview:
                print(f"   {line}")
            if plan_count > len(plan_preview):
                print(f"   ... and {plan_count - len(plan_preview)} more")
    except Exception as e:
        print(f"❌ ERROR: failed to generate build plan: {e}", file=sys.stderr)

    # Open config editor if there are new/missing keys
    if merge_result.missing_keys:
        print("📝 New keys that likely need attention:")
        for k in merge_result.missing_keys:
            print(f"  - {k}")
        merge_result.open_config_editor()

    # Secrets handling (copy/keep/new-template + open editor)
    try:
        handle_secrets_after_config(env_dir)
    except Exception as e:
        print(f"❌ ERROR: secrets step failed: {e}", file=sys.stderr)
        return 1

    if not merge_result.missing_keys:
        print("✅ Init completed with no config edits required.")
    else:
        print("✔️ Init completed. Config/secrets editors were opened.")
    return 0
