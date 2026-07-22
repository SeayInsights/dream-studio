"""Claude Code integration installer.

User scope:
  skills/ds-bootstrap/SKILL.md  → create
  settings.json                 → merge_json for hooks block
  settings.local.json           → always skip (private/local config)

Project scope: same files under .claude/ in working directory.

WO-GF-CONTROL-INSTALL-split: implementation moved to claude_code_{shared,
fileops,launcher,installer}.py; this module re-exports the public+private
surface so existing `from integrations.installer.claude_code import X`
callers are unchanged.
"""

from __future__ import annotations

import platform  # noqa: F401 — re-exposed so `patch("integrations.installer.claude_code.platform.system", ...)` still resolves (stdlib singleton shared with the siblings)

from .claude_code_fileops import (
    _collect_hook_file_ops,
    _collect_skill_dir_ops,
    _interpolate_hooks_dir,
    _interpolate_statusline_cmd,
)
from .claude_code_installer import (
    ClaudeCodeInstaller,
    _post_install_validate,
    _skill_id_from_dir_name,
)
from .claude_code_launcher import (
    _FIRST_RUN_GUIDE_TEXT,
    _first_run_guide,
    _get_ds_version,
    _write_global_launcher,
    _write_path_to_profile,
)
from .claude_code_shared import (
    _CHUNK_SIZE,
    _DS_ENTRY,
    _DS_PATH_MARKER,
    _INSTALLER_DIR,
    _REPO_ROOT,
    _compute_file_hash_chunked,
    _python_cmd,
)

__all__ = [
    "ClaudeCodeInstaller",
    "_CHUNK_SIZE",
    "_DS_ENTRY",
    "_DS_PATH_MARKER",
    "_FIRST_RUN_GUIDE_TEXT",
    "_INSTALLER_DIR",
    "_REPO_ROOT",
    "_collect_hook_file_ops",
    "_collect_skill_dir_ops",
    "_compute_file_hash_chunked",
    "_first_run_guide",
    "_get_ds_version",
    "_interpolate_hooks_dir",
    "_interpolate_statusline_cmd",
    "_post_install_validate",
    "_python_cmd",
    "_skill_id_from_dir_name",
    "_write_global_launcher",
    "_write_path_to_profile",
]
