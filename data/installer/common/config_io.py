import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    import tomllib  # Python 3.11+
except ImportError:
    print("❌ Python 3.11+ required (needs 'tomllib' for TOML parsing).", file=sys.stderr)
    raise


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def read_toml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("rb") as f:
        return tomllib.load(f)

def write_toml_simple(doc: Dict[str, Any], dest: Path) -> None:
    """
    Minimal TOML writer (scalars, bools, dicts).
    No comments preserved.
    """
    lines: List[str] = []

    def emit_table(prefix: List[str], obj: Dict[str, Any]) -> None:
        scalars: Dict[str, Any] = {}
        tables: Dict[str, Dict[str, Any]] = {}
        for k, v in obj.items():
            if isinstance(v, dict):
                tables[k] = v
            else:
                scalars[k] = v
        if prefix:
            lines.append(f"[{'.'.join(prefix)}]")
        for k, v in scalars.items():
            if isinstance(v, str):
                sval = v.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{k} = "{sval}"')
            elif isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k} = {v}")
            elif v is None:
                lines.append(f"{k} = null")
            else:
                lines.append(f"{k} = {repr(v)}")
        if scalars and tables:
            lines.append("")
        for k, sub in tables.items():
            lines.append("")
            emit_table(prefix + [k], sub)

    emit_table([], doc)
    content = "\n".join(lines).rstrip() + "\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")

# ----------------
# Config helpers
# ----------------

def read_template_config(version_root: Path) -> Dict[str, Any]:
    return read_toml(version_root / "sample_environment" / "config.toml")

def read_env_config(env_dir: Path) -> Dict[str, Any]:
    return read_toml(env_dir / "config.toml")

def deep_merge_from_old_into_new(new_cfg: Dict[str, Any], old_cfg: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v_new in new_cfg.items():
        if isinstance(v_new, dict):
            v_old = old_cfg.get(k, {})
            if isinstance(v_old, dict):
                out[k] = deep_merge_from_old_into_new(v_new, v_old)
            else:
                out[k] = deep_merge_from_old_into_new(v_new, {})
        else:
            if k in old_cfg and not isinstance(old_cfg.get(k), dict):
                out[k] = old_cfg[k]
            else:
                out[k] = v_new
    return out

def find_missing_keys(new_cfg: Dict[str, Any], merged_cfg: Dict[str, Any]) -> List[str]:
    missing: List[str] = []

    def walk(n: Dict[str, Any], m: Dict[str, Any], prefix: List[str]) -> None:
        for k, nv in n.items():
            path = prefix + [k]
            if isinstance(nv, dict):
                mv = m.get(k, {})
                if isinstance(mv, dict):
                    walk(nv, mv, path)
                else:
                    missing.append(".".join(path))
            else:
                if k not in m:
                    missing.append(".".join(path))
                elif m[k] == nv:
                    missing.append(".".join(path))

    walk(new_cfg, merged_cfg, [])
    return sorted(set(missing))
