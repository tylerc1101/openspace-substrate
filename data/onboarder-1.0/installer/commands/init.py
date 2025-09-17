import sys
from argparse import Namespace

from installer.utils.os_helpers import (
    ensure_usr_home_dir,
    get_env_dir,
    copy_sample_environment_to,
    open_in_editor,
    get_version_root,
    ensure_secrets_on_upgrade,
)
from installer.utils.config_helpers import (
    get_template_config,
    get_existing_config,
    deep_merge_from_old_into_new,
    find_missing_keys,
    env_config_path,
    write_toml_simple,
)
from installer.utils.container_helpers import (
    detect_engine,
    load_image,
    find_version_image_tar,
)
from installer.utils.build_plan_helpers import (
    merge_build_plan, 
    write_build_plan
)

from installer.utils.config_helpers import (
    get_template_config, 
    get_existing_config, 
    deep_merge_from_old_into_new, 
    find_missing_keys, 
    env_config_path, 
    write_toml_simple
)

def _load_version_container(version_root) -> None:
    tar = find_version_image_tar(version_root)
    if not tar:
        print("ℹ️ No version-specific image tarball found under images/. Skipping load.")
        return
    print(f"🔧 Found version image: {tar}")
    try:
        engine = detect_engine()
    except Exception as e:
        print(f"❌ ERROR: {e}", file=sys.stderr)
        return
    print(f"🔧 Loading image with: {engine}")
    try:
        load_image(engine, tar)
    except Exception as e:
        print(f"❌ ERROR: failed to load image: {e}", file=sys.stderr)
        return
    print("✔️ Version image loaded successfully.")

def handle(args: Namespace) -> int:
    """Initialize or upgrade an environment directory + config, then handle secrets and load image."""
    env_name = args.env.strip()
    if not env_name:
        print("❌ ERROR: Environment name cannot be empty.", file=sys.stderr)
        return 1

    try:
        ensure_usr_home_dir()
    except Exception as e:
        print(f"❌ ERROR: failed to ensure usr_home: {e}", file=sys.stderr)
        return 1

    env_dir = get_env_dir(env_name)
    version_root = get_version_root()

    if not env_dir.exists():
        # Fresh init
        try:
            copy_sample_environment_to(env_dir)
        except Exception as e:
            print(f"❌ ERROR: {e}", file=sys.stderr)
            return 1
        print(f"✔️ Environment '{env_name}' created at {env_dir}")

        # Load version-specific container (best-effort)
        _load_version_container(version_root)

        # Open config then secrets (fresh env already has secrets.yaml from template)
        cfg_path = env_config_path(env_dir)
        print(f"👉 Opening config for editing: {cfg_path}")
        open_in_editor(cfg_path)

        secrets_path = env_dir / "secrets.yaml"
        if secrets_path.exists():
            print(f"👉 Opening secrets for editing: {secrets_path}")
            open_in_editor(secrets_path)
        else:
            print("ℹ️ No secrets.yaml template found in sample_environment; skipping.")
        return 0

    # Upgrade-like init: merge config, manage secrets, load image
    try:
        new_template = get_template_config(version_root)
    except Exception as e:
        print(f"❌ ERROR: failed to read new template config: {e}", file=sys.stderr)
        return 1

    try:
        old_config = get_existing_config(env_dir)
    except Exception as e:
        print(f"❌ ERROR: failed to read existing config: {e}", file=sys.stderr)
        return 1

    merged = deep_merge_from_old_into_new(new_template, old_config)
    missing = find_missing_keys(new_template, merged)

    # Write merged config (with backup)
    cfg_path = env_config_path(env_dir)
    backup = cfg_path.with_suffix(".toml.bak")
    try:
        if cfg_path.exists():
            cfg_path.replace(backup)
        write_toml_simple(merged, cfg_path)
    except Exception as e:
        print(f"❌ ERROR: failed to write merged config: {e}", file=sys.stderr)
        try:
            if backup.exists():
                backup.replace(cfg_path)
        except Exception:
            pass
        return 1

    print(f"✔️ Updated config merged at: {cfg_path}")
    if backup.exists():
        print(f"💾 Backup of previous config: {backup}")

    # Build plan generation (always regenerate on init)
    try:
        # merged (fresh) config or freshly-written config is now on disk; read to get profile
        import copy
        # Prefer to read from merged data if we have it already:
        cfg_for_profile = merged if 'merged' in locals() else get_existing_config(env_dir)
        core = cfg_for_profile.get("core") or {}
        profile = (core.get("profile") or "").strip()
        if not profile:
            print("❌ ERROR: [core].profile is missing in config.toml; cannot build plan.", file=sys.stderr)
        else:
            plan = merge_build_plan(version_root, env_dir, profile)
            plan_path = write_build_plan(plan, env_dir)
            print(f"🧭 Build plan generated ({len(plan)} tasks): {plan_path}")
            # Nice touch: show the first few steps
            preview = [f"  - [{t['id']}] {t['label']} ({t['kind']})" for t in plan[:5]]
            if preview:
                print("   Preview:")
                print("\n".join(preview))
                if len(plan) > 5:
                    print(f"   ... and {len(plan)-5} more")
    except Exception as e:
        print(f"❌ ERROR: failed to generate build plan: {e}", file=sys.stderr)

    # Load version-specific container (best-effort)
    _load_version_container(version_root)

    # Secrets handling for upgrade
    secrets_path = ensure_secrets_on_upgrade(env_dir)

    # Open files only if there's work to do
    if missing:
        print("📝 New or unchanged-from-template keys that likely need attention:")
        for k in missing:
            print(f"  - {k}")
        print("👉 Opening editor so you can fill in the new values…")
        open_in_editor(cfg_path)
    else:
        print("✅ No new config keys require input.")

    # Always offer secrets editing after config phase (per your requirement)
    if secrets_path.exists():
        print(f"👉 Opening secrets for editing: {secrets_path}")
        open_in_editor(secrets_path)
    else:
        print("ℹ️ No secrets file present; skipping secrets editor.")

    return 0
