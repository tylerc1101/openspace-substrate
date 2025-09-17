import os
import subprocess
import sys
from pathlib import Path

def open_in_editor(path: Path) -> None:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        try:
            subprocess.run([editor, str(path)], check=False)
        except Exception as e:
            print(f"⚠️ Failed to launch editor '{editor}': {e}", file=sys.stderr)
        return

    try:
        if sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif os.name == "nt":
            os.startfile(str(path))  # type: ignore
        else:
            print(f"⚠️ No editor configured; please edit manually: {path}")
    except Exception as e:
        print(f"⚠️ Could not open file automatically; please edit: {path} ({e})", file=sys.stderr)
