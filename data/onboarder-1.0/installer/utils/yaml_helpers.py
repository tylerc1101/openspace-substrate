from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

# ---- Tiny YAML subset parser/dumper ----
# Supported:
#   - Top-level: list of mappings (each mapping = a task)
#   - Mapping entries are simple scalars: key: value
#   - Values may be unquoted or double-quoted strings
#   - Comments start with '#' (only if not within quotes)
#   - Blank lines allowed
#
# Not supported (by design to stay dependency-free):
#   - Nested mappings/arrays
#   - Multiline scalars
#   - Single quotes, block scalars, anchors, etc.

def _strip_comment(line: str) -> str:
    """Strip comments that start with '#' and are not inside double quotes."""
    out = []
    in_quotes = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"':
            in_quotes = not in_quotes
            out.append(ch)
        elif ch == '#' and not in_quotes:
            break  # start of comment
        else:
            out.append(ch)
        i += 1
    return "".join(out).rstrip()

def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        inner = s[1:-1]
        # minimal unescape
        inner = inner.replace('\\"', '"').replace('\\\\', '\\')
        return inner
    return s

def _parse_key_value(s: str) -> Tuple[str, str]:
    if ":" not in s:
        raise ValueError(f"Expected 'key: value' in: {s!r}")
    key, val = s.split(":", 1)
    key = key.strip()
    val = _unquote(val.strip())
    if not key:
        raise ValueError(f"Empty key in mapping: {s!r}")
    return key, val

def _leading_dash(line: str) -> bool:
    # treat lines beginning (after indentation) with '- ' as new list item
    stripped = line.lstrip()
    return stripped.startswith("- ")

def _strip_list_dash(line: str) -> str:
    stripped = line.lstrip()
    # remove '- ' prefix once
    return stripped[2:] if stripped.startswith("- ") else stripped

def parse_plan_yaml(text: str) -> List[Dict[str, Any]]:
    """
    Parse a YAML subset representing a list of flat mappings.
    Returns: list of dicts.
    """
    tasks: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for raw in text.splitlines():
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            # blank or comment-only
            continue

        if _leading_dash(line):
            # start a new task
            payload = _strip_list_dash(line).strip()
            # payload can be empty (then following lines provide k/v), or 'key: value'
            if current is not None:
                tasks.append(current)
            current = {}

            if payload:
                k, v = _parse_key_value(payload)
                current[k] = v
        else:
            # continuation lines for current mapping: 'key: value'
            if current is None:
                raise ValueError(f"Unexpected line outside of list item: {raw!r}")
            k, v = _parse_key_value(line)
            current[k] = v

    if current is not None:
        tasks.append(current)

    return tasks

def dump_plan_yaml(tasks: List[Dict[str, Any]]) -> str:
    """
    Emit a minimal YAML list of mappings. Keys are emitted in a stable order:
    id, label, kind, file, then any other keys sorted alphabetically.
    """
    lines: List[str] = []
    for t in tasks:
        # order keys deterministically
        base_order = ["id", "label", "kind", "file"]  # 👈 new order
        keys = [k for k in base_order if k in t] + sorted(k for k in t.keys() if k not in base_order)

        # header line: '- id: VALUE' if 'id' exists
        if "id" in t:
            val = str(t["id"])
            val = val if (val and all(c not in val for c in '":#\n')) else f'"{val.replace("\\", "\\\\").replace(\'"\', r"\"")}"'
            lines.append(f"- id: {val}")
            indent = "  "
            for k in keys:
                if k == "id":
                    continue
                v = str(t[k])
                if any(c in v for c in '":#\n ') or v == "":
                    v = '"' + v.replace("\\", "\\\\").replace('"', r'\"') + '"'
                lines.append(f"{indent}{k}: {v}")
        else:
            lines.append("-")
            indent = "  "
            for k in keys:
                v = str(t[k])
                if any(c in v for c in '":#\n ') or v == "":
                    v = '"' + v.replace("\\", "\\\\").replace('"', r'\"') + '"'
                lines.append(f"{indent}{k}: {v}")
        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + ("\n" if lines else "")


# Public API (compatible with earlier helper names)
def load_yaml_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    return parse_plan_yaml(text)

def dump_yaml_file(data: Any, path: Path) -> None:
    if not isinstance(data, list):
        raise TypeError("Expected a list of tasks to dump as YAML.")
    content = dump_plan_yaml(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
