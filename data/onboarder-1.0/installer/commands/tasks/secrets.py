from pathlib import Path
from shutil import copy2

from installer.common import paths, editor


def _template_secrets_path() -> Path:
    return paths.version_root() / "sample_environment" / "secrets.yaml"


def _env_secrets_path(env_dir: Path) -> Path:
    return env_dir / "secrets.yaml"


def handle_secrets_after_config(env_dir: Path) -> None:
    """
    - Fresh: secrets.yaml was copied with the sample env (if template exists) -> open it if present
    - Upgrade: if env secrets.yaml exists, keep it and drop template as secrets.yaml.new; else copy template
    - Always open the *primary* secrets file for editing if present
    """
    tmpl = _template_secrets_path()
    target = _env_secrets_path(env_dir)

    if tmpl.exists():
        if target.exists():
            # Upgrade: keep current secrets, place new template next to it
            new_path = target.with_suffix(target.suffix + ".new")
            copy2(tmpl, new_path)
            print(f"ℹ️ New secrets template from this version placed at: {new_path}")
        else:
            # Fresh or upgrade w/o secrets: copy template in
            target.parent.mkdir(parents=True, exist_ok=True)
            copy2(tmpl, target)
            print(f"✔️ Secrets template copied to: {target}")
    else:
        # No template provided in this version
        pass

    if target.exists():
        print(f"👉 Opening secrets for editing: {target}")
        editor.open_in_editor(target)
    else:
        print("ℹ️ No secrets file present; skipping secrets editor.")
