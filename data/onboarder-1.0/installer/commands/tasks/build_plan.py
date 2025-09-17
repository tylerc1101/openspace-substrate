from pathlib import Path
from typing import Dict, Any, List, Tuple

from installer.common import paths
from installer.common.yaml_min import load_yaml_file, dump_yaml_file

ALLOWED_KINDS = {"bash", "ansible", "helmfile"}  # extend as needed


def _ensure_list(obj) -> List[Dict[str, Any]]:
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        return [obj]
    raise TypeError("Build plan must be a list of tasks or a single task mapping.")


def _load_profile_plan(profile: str) -> List[Dict[str, Any]]:
    plan_path = paths.version_root() / "installer" / "profiles" / f"{profile}.yml"
    if not plan_path.exists():
        raise FileNotFoundError(f"Profile plan not found: {plan_path}")
    return _ensure_list(load_yaml_file(plan_path))


def _load_custom_plan(env_dir: Path, name: str) -> List[Dict[str, Any]]:
    yml = env_dir / "custom" / f"{name}.yml"
    if not yml.exists():
        return []
    return _ensure_list(load_yaml_file(yml))


def _normalize_paths(tasks: List[Dict[str, Any]]) -> None:
    vr = paths.version_root()
    for t in tasks:
        f = t.get("file")
        if isinstance(f, str) and f.startswith("/installer/"):
            t["file"] = str(vr / f.lstrip("/"))


def _validate(tasks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    errs: List[str] = []
    out: List[Dict[str, Any]] = []
    for i, t in enumerate(tasks, start=1):
        missing = [k for k in ("id", "label", "kind", "file") if k not in t]
        if missing:
            errs.append(f"Task #{i} missing keys: {', '.join(missing)}")
            continue
        kind = t["kind"]
        if not isinstance(kind, str):
            errs.append(f"Task #{i} 'kind' must be a string")
            continue
        if ALLOWED_KINDS and kind not in ALLOWED_KINDS:
            errs.append(f"Task #{i} has unsupported kind: {kind} (allowed: {', '.join(sorted(ALLOWED_KINDS))})")
            continue
        out.append(t)
    return out, errs


def regenerate_build_plan(env_dir: Path, cfg: Dict[str, Any]) -> tuple[Path, int, list[str]]:
    core = cfg.get("core") or {}
    profile = (core.get("profile") or "").strip()
    if not profile:
        raise ValueError("[core].profile is missing in config.toml; cannot build plan.")

    pre = _load_custom_plan(env_dir, "pre")
    prof = _load_profile_plan(profile)
    post = _load_custom_plan(env_dir, "post")

    _normalize_paths(pre)
    _normalize_paths(prof)
    _normalize_paths(post)

    merged = pre + prof + post
    valid, errs = _validate(merged)
    if errs:
        raise ValueError("Invalid build plan:\n" + "\n".join(f"  - {e}" for e in errs))

    out_path = env_dir / "build_plan.yml"
    dump_yaml_file(valid, out_path)

    preview = [f"- [{t['id']}] {t['label']} ({t['kind']})" for t in valid[:5]]
    return out_path, len(valid), preview
