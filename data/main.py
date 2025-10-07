#!/usr/bin/env python3
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except Exception:
    print("ERROR: PyYAML is required in the onboarder image (pip install pyyaml)", file=sys.stderr)
    sys.exit(1)

# Fixed paths inside the container run context
INSTALL_ROOT = Path("/install")
DATA_DIR = INSTALL_ROOT / "data"
USR_HOME = INSTALL_ROOT / "usr_home"
LOG_DIR = INSTALL_ROOT / "logs"
STATE_FILE = LOG_DIR / "state.json"


def eprint(*a, **k):
    print(*a, file=sys.stderr, **k)


def load_yaml(p: Path):
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_state(state: dict):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def normalize_profile_filename(name: str) -> str:
    """Allow 'default' or 'default.yml' in group_vars; normalize to filename."""
    name = str(name).strip()
    return name if name.endswith(".yml") else f"{name}.yml"


def render_args(args_list, context: dict):
    """
    Very light templating for step args/strings: supports {env}, {profile}, {profile_kind}
    and {{ env }}, {{ profile }}, {{ profile_kind }} styles.
    """
    rendered = []
    for a in (args_list or []):
        s = str(a)
        for k, v in context.items():
            s = re.sub(r"\{\{\s*"+re.escape(k)+r"\s*\}\}", str(v), s)
            s = s.replace("{"+k+"}", str(v))
        rendered.append(s)
    return rendered


def run_cmd(cmd, log_file: Path, cwd=None, env=None) -> int:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=env,
    )
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with log_file.open("w", encoding="utf-8") as lf:
        for line in proc.stdout:
            sys.stdout.write(line)
            lf.write(line)
    return proc.wait()


def main():
    ap = argparse.ArgumentParser(description="Onboarder Orchestrator")
    ap.add_argument("--env", required=True, help="Environment name (matches usr_home/<env>)")
    ap.add_argument("--profile", required=True,
                    help="Profile kind (e.g., basekit | baremetal | aws).")
    ap.add_argument("--resume", action="store_true",
                    help="Skip steps that are already completed in logs/state.json")
    ap.add_argument("--debug", action="store_true", help="Print extra debug info")
    args = ap.parse_args()

    # Resolve env paths
    env_dir = USR_HOME / args.env
    if not env_dir.exists():
        eprint(f"ERROR: env dir not found: {env_dir}")
        return 2

    profile_kind = args.profile.strip()

    # Inventory is fixed: usr_home/<env>/config.yml
    inventory = env_dir / "config.yml"
    if not inventory.exists():
        eprint(f"ERROR: inventory file not found: {inventory}")
        return 2

    # group_vars/<profile_kind>.yml is required and must include 'profile'
    gv_file = env_dir / "group_vars" / f"{profile_kind}.yml"
    if not gv_file.exists():
        eprint(f"ERROR: group vars not found for profile '{profile_kind}': {gv_file}")
        return 2

    gv = load_yaml(gv_file) or {}
    profile_name = gv.get("profile", "default")
    profile_filename = normalize_profile_filename(profile_name)

    # The profile steps file lives under data/profiles/<profile_kind>/<profile_name>.yml
    profile_file = DATA_DIR / "profiles" / profile_kind / profile_filename
    if not profile_file.exists():
        eprint(f"ERROR: profile file not found: {profile_file}")
        return 2

    # Debug info if requested
    if args.debug:
        print(f"==> ENV: {args.env}")
        print(f"==> PROFILE KIND: {profile_kind}")
        print(f"==> PROFILE NAME: {profile_name}")
        print(f"==> PROFILE FILE: {profile_file}")
        print(f"==> INVENTORY: {inventory}")
        print(f"==> GROUP_VARS: {gv_file}")

    # Load steps (support either top-level list or { steps: [...] })
    profile_doc = load_yaml(profile_file)
    steps = profile_doc.get("steps") if isinstance(profile_doc, dict) else profile_doc
    if not isinstance(steps, list):
        eprint(f"ERROR: {profile_file} must define a list of steps or a 'steps:' list")
        return 2

    # State for resume
    state = load_state()
    completed = set(state.get("completed_steps", []))
    overall = {
        "env": args.env,
        "profile_kind": profile_kind,
        "profile_file": str(profile_file),
        "inventory": str(inventory),
        "group_vars": str(gv_file),
    }

    # Context for lightweight templating in args
    ctx = {
        "env": args.env,
        "profile": profile_name,
        "profile_kind": profile_kind,
    }

    # Execute steps
    for i, step in enumerate(steps, 1):
        # Expected step keys:
        # id (str|int), description (str), kind (ansible|python3|python|shell|bash|sh), file (str), args (list)
        sid = str(step.get("id", i))
        desc = step.get("description") or step.get("desc") or ""
        kind = (step.get("kind") or "").lower().strip()
        file_rel = step.get("file")
        extra_args = step.get("args") or []

        if not kind or not file_rel:
            eprint(f"[SKIP] step {sid}: missing 'kind' or 'file' in {profile_file}")
            continue

        if args.resume and sid in completed:
            print(f"[{sid}] SKIP (already completed): {desc}")
            continue

        # Resolve script/playbook path
        file_path = Path(file_rel)
        if not file_path.is_absolute():
            file_path = DATA_DIR / file_rel
        if not file_path.exists():
            eprint(f"[{sid}] ERROR: step file not found: {file_path}")
            return 3

        rendered_args = render_args(extra_args, ctx)

        # Build command by kind
        if kind == "ansible":
            cmd = ["ansible-playbook", "-i", str(inventory), str(file_path)]
            if rendered_args:
                cmd.extend(rendered_args)
        elif kind in ("python", "python3"):
            cmd = ["python3", str(file_path)] + rendered_args
        elif kind in ("shell", "bash", "sh"):
            interpreter = "/bin/bash" if kind in ("bash", "shell") else "/bin/sh"
            cmd = [interpreter, str(file_path)] + rendered_args
        else:
            eprint(f"[{sid}] ERROR: unsupported step kind '{kind}'")
            return 4

        # Run and log
        step_log = LOG_DIR / f"{sid}.log"
        print(f"[{sid}] {desc} -> {' '.join(shlex.quote(c) for c in cmd)}")
        rc = run_cmd(cmd, log_file=step_log, cwd=INSTALL_ROOT)
        if rc != 0:
            eprint(f"[{sid}] FAILED (rc={rc}). See log: {step_log}")
            state["failed_step"] = sid
            state["overall"] = overall
            save_state(state)
            return rc

        print(f"[{sid}] OK (log: {step_log})")
        completed.add(sid)
        state["completed_steps"] = sorted(list(completed))
        state["overall"] = overall
        save_state(state)

    print("All steps completed ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
