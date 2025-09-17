from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .yaml_helpers import load_yaml_file, dump_yaml_file

# Optional: constrain to kinds you support right now
ALLOWED_KINDS = {"bash", "ansible", "helmfile"}

def _ensure_list(obj: Any) -> List[Dict[str, Any]]:
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    # allow single-item YAML mapping
    if isinstance(obj, dict):
        return [obj]
    raise TypeError("Build plan YAML must be a list of task objects or a single task mapping.")

def _normalize_task_paths(tasks: List[Dict[str, Any]], version_root: Path) -> None:
    """
    Convert 'file' entries like '/installer/profile/tasks/foo.sh' to absolute
    paths under this version's installer dir.
    """
    for t in tasks:
        f = t.get("file")
        if isinstance(f, str) and f.startswith("/installer/"):
            t["file"] = str(version_root / f.lstrip("/"))

def _validate_tasks(tasks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    out: List[Dict[str, Any]] = []
    for idx, t in enumerate(tasks, start=1):
        missing = [k for k in ("id", "kind", "label", "file") if k not in t]
        if missing:
            errors.append(f"Task #{idx} missing keys: {', '.join(missing)}")
            continue
        kind = t["kind"]
        if not isinstance(kind, str):
            errors.append(f"Task #{idx} 'kind' must be a string")
            continue
        if ALLOWED_KINDS and kind not in ALLOWED_KINDS:
            errors.append(f"Task #{idx} has unsupported kind: {kind} (allowed: {', '.join(sorted(ALLOWED_KINDS))})")
            continue
        out.append(t)
    return out, errors

def load_profile_plan(version_root: Path, profile: str) -> List[Dict[str, Any]]:
    plan_path = version_root / "installer" / "profiles" / f"{profile}.yml"
    if not plan_path.exists():
        raise FileNotFoundError(f"Profile plan not found: {plan_path}")
    data = load_yaml_file(plan_path)
    return _ensure_list(data)

def load_custom_plan(env_dir: Path, name: str) -> List[Dict[str, Any]]:
    """
    name is 'pre' or 'post'
    """
    yml = env_dir / "custom" / f"{name}.yml"
    if not yml.exists():
        return []
    data = load_yaml_file(yml)
    return _ensure_list(data)

def merge_build_plan(version_root: Path, env_dir: Path, profile: str) -> List[Dict[str, Any]]:
    pre = load_custom_plan(env_dir, "pre")
    prof = load_profile_plan(version_root, profile)
    post = load_custom_plan(env_dir, "post")

    # Normalize paths for this version
    _normalize_task_paths(pre, version_root)
    _normalize_task_paths(prof, version_root)
    _normalize_task_paths(post, version_root)

    merged = pre + prof + post

    # Validate
    valid, errs = _validate_tasks(merged)
    if errs:
        # Keep only valid tasks but report problems
        msg = "\n".join(f"  - {e}" for e in errs)
        raise ValueError(f"Invalid build plan tasks:\n{msg}")

    return valid

def write_build_plan(plan: List[Dict[str, Any]], env_dir: Path) -> Path:
    out = env_dir / "build_plan.yml"
    dump_yaml_file(plan, out)
    return out
