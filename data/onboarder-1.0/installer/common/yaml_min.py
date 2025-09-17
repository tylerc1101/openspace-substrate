from pathlib import Path
from typing import Any, Dict, List, Tuple

# --- minimal YAML subset ---
# - top-level: list of tasks (dicts)
# - keys: id, label, kind, file (+ optional extras)
# - values: scalars (strings, quoted or unquoted)
# - supports comments (#) and blank lines

def _strip_comment(line: str) -> str:
    out = []
    in_quotes = False
    for ch in line:
        if ch == '"':
            in_quotes = not in_quotes
            out.append(ch)
        elif ch == '#' and not in_quotes:
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()

def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].replace('\\"', '"').replace('\\\\', '\\')
    return s

def _parse_kv(s: str) -> Tuple[str, str]:
    if ":" not in s:
        raise ValueError(f"Expected 'key: value' in: {s!r}")
    k, v = s.split(":", 1)
    return k.strip(), _unquote(v.strip())

def load_yaml_file(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    tasks: List[Dict[str, Any]] = []
    cur: Dict[str, Any] | None = None

    for raw in text.splitlines():
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("- "):
            if cur is not None:
                tasks.append(cur)
            cur = {}
            payload = line.lstrip()[2:].strip()
            if payload:
                k, v = _parse_kv(payload)
                cur[k] = v
        else:
            if cur is None:
                raise ValueError(f"Unexpected line: {raw!r}")
            k, v = _parse_kv(line)
            cur[k] = v
    if cur is not None:
        tasks.append(cur)
    return tasks

def dump_yaml_file(tasks: List[Dict[str, Any]], path: Path) -> None:
    lines: List[str] = []
    order = ["id", "label", "kind", "file"]
    for t in tasks:
        if "id" in t:
            lines.append(f"- id: {t['id']}")
            for k in order[1:]:
                if k in t:
                    lines.append(f"  {k}: {t[k]}")
        else:
            lines.append("-")
            for k, v in t.items():
                lines.append(f"  {k}: {v}")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    content = "\n".join(lines) + "\n"
    path.write_text(content, encoding="utf-8")
