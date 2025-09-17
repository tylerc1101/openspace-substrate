from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, List, Dict

from installer.common import paths, editor
from installer.common.config_io import (
    read_template_config,
    read_env_config,
    write_toml_simple,
    deep_merge_from_old_into_new,
    find_missing_keys,
)


@dataclass
class MergeResult:
    fresh: bool
    config_path: Path
    backup_path: Optional[Path]
    missing_keys: List[str]
    config_dict: Dict[str, Any]
    open_config_editor: Callable[[], None]


def merge_config(env_dir: Path, fresh: bool) -> MergeResult:
    cfg_path = env_dir / "config.toml"
    backup: Optional[Path] = None

    if fresh:
        # Template already copied by env.copy_sample_env(); nothing to merge yet.
        merged = read_env_config(env_dir)
        missing: List[str] = []  # fresh path: we won't force missing; editor opens later if you want
    else:
        new_template = read_template_config(paths.version_root())
        old_config = read_env_config(env_dir)
        merged = deep_merge_from_old_into_new(new_template, old_config)
        missing = find_missing_keys(new_template, merged)

        backup = cfg_path.with_suffix(".toml.bak")
        if cfg_path.exists():
            cfg_path.replace(backup)
        write_toml_simple(merged, cfg_path)

    def _open_editor() -> None:
        editor.open_in_editor(cfg_path)

    return MergeResult(
        fresh=fresh,
        config_path=cfg_path,
        backup_path=backup,
        missing_keys=missing,
        config_dict=merged,
        open_config_editor=_open_editor,
    )
