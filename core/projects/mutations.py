"""Project lifecycle mutations — facade over the split modules.

Skills, workflows, and hooks should import these directly instead of
shelling out to `ds project set-active` / `ds project deactivate`. Each
function returns a dict; the CLI wrapper in `interfaces/cli/ds.py` is
responsible for serialization.

WO-GF-CORE-DATA-split: implementation moved to mutations_{shared,
activation,delete,register,metadata}.py; this module re-exports the public
API so existing `from core.projects.mutations import X` callers are
unchanged.
"""

from __future__ import annotations

from .mutations_shared import _require_db
from .mutations_activation import (
    deactivate_project,
    set_active_project,
)
from .mutations_delete import delete_project
from .mutations_register import (
    _write_project_marker,
    register_project,
)
from .mutations_metadata import (
    set_project_vision,
    update_project_path,
)

__all__ = [
    "_require_db",
    "_write_project_marker",
    "deactivate_project",
    "delete_project",
    "register_project",
    "set_active_project",
    "set_project_vision",
    "update_project_path",
]
