import sys
from pathlib import Path
from typing import Any, Dict, Tuple, List

# Python 3.11+ stdlib TOML parser
try:
    import tomllib  # type: ignore[attr-defined]
except Exception:
    print("ERROR: Python 3.11+ is required (needs stdlib 'tomllib').", file=sys.stderr)
    raise

# -------- I/O --------

def env_config_path(env_dir: Path) -> Path:
    return env_dir / "config.toml"

def read_toml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"TOML not found: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"TOML path is not a file: {path}")
    with path.open("rb") as f:
        try:
            return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"Invalid TOML in {path}: {e}") from e

def write_toml_simple(doc: Dict[str, Any], dest: Path) -> None:
    """
    Minimal TOML writer that supports nested tables of scalars/bools/ints/strs.
    This keeps us dependency-free. Comments from templates are not preserved.
    """
    lines: List[str] = []
    def emit_table(prefix: List[str], obj: Dict[str, Any]) -> None:
        # gather scalars and subtables
        scalars: Dict[str, Any] = {}
        tables: Dict[str, Dict[str, Any]] = {}
        for k, v in obj.items():
            if isinstance(v, dict):
                tables[k] = v
            else:
                scalars[k] = v
        if prefix:  # root table has no header
            lines.append(f"[{'.'.join(prefix)}]")
        for k, v in scalars.items():
            if isinstance(v, str):
                # naïve escaping for quotes and backslashes
                sval = v.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{k} = "{sval}"')
            elif isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k} = {v}")
            elif v is None:
                lines.append(f"{k} = null")
            else:
                # Simple repr for lists/other types if encountered
                lines.append(f"{k} = {repr(v)}")
        if scalars and (tables):
            lines.append("")  # spacing between groups
        for k, sub in tables.items():
            if lines and not lines[-1].strip():
                pass
            else:
                lines.append("")
            emit_table(prefix + [k], sub)

    emit_table([], doc)
    # ensure trailing newline
    content = "\n".join(lines).rstrip() + "\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")

# -------- Helpers for init/upgrade --------

def get_template_config(version_root: Path) -> Dict[str, Any]:
    return read_toml(version_root / "sample_environment" / "config.toml")

def get_existing_config(env_dir: Path) -> Dict[str, Any]:
    return read_toml(env_config_path(env_dir))

def deep_merge_from_old_into_new(new_cfg: Dict[str, Any], old_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a merged config:
      - where keys match (and are not tables), carry the old value into the new
      - recurse into tables (dicts)
      - keys only in new stay as-is (user attention)
      - keys only in old are dropped (assumed removed/deprecated)
    """
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
    """
    Return dotted-key paths that are present in new_cfg but have default values
    because they were not present in the old config (i.e., likely need attention).
    """
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
                # If value unchanged from template after merge, mark as missing/attention
                if k not in m:
                    missing.append(".".join(path))
                else:
                    # If the merged value equals the template value, it might still need editing.
                    if m[k] == nv:
                        missing.append(".".join(path))
    walk(new_cfg, merged_cfg, [])
    return sorted(set(missing))
