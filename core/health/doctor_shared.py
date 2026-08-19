"""Doctor shared constants — regex patterns and hook-path inventories.

Split out of doctor.py (WO-GF-CORE-HEALTH-SKILLS): data leaf consumed by
doctor_skill_sync.py and doctor_checks.py.
"""

from __future__ import annotations

import re
from pathlib import Path

_CLI_REFERENCE_PATTERN = re.compile(r"py\s+-m\s+interfaces\.cli\.ds")
_ROUTING_BEGIN = "<!-- BEGIN AUTO-ROUTING -->"
_ROUTING_END = "<!-- END AUTO-ROUTING -->"

# Entry hooks wired directly in hooks.json (bypassing the dispatcher) and copied
# verbatim into the installed tree. Because `ds update` is version-gated, a canonical
# edit does not auto-propagate — the deployed copy can silently go stale.
_ENTRY_HOOK_RELPATHS = (
    "runtime/hooks/meta/on-edit-enforce.py",
    "runtime/hooks/meta/on-stop-enforce.py",
)

# Hook subdirs the projection sync copies (setup_hooks.step_sync_hook_projection).
_PROJECTED_HOOK_SUBDIRS = ("quality", "domains", "core", "meta")


def projected_hook_relpaths(source_root: Path) -> list[str]:
    """Every file the hook projection sync copies — the freshness manifest.

    WO-HOOK-DRIFT-STOP: the freshness check previously covered 2 of ~38 copied
    files; runtime/lib/enforcement.py (imported by BOTH enforce hooks) was
    excluded, so a stale deployed copy ran outdated enforcement undetected.
    This enumerates the SAME set step_sync_hook_projection copies (the four
    hook subdirs, runtime/lib/, session_config.py, runtime/__init__.py) so the
    check and the sync cannot drift apart independently. Sorted, repo-relative,
    POSIX separators.
    """
    rels: list[str] = []
    for sub in _PROJECTED_HOOK_SUBDIRS:
        base = source_root / "runtime" / "hooks" / sub
        if not base.is_dir():
            continue
        for f in base.rglob("*.py"):
            if "__pycache__" in f.parts:
                continue
            rels.append(f.relative_to(source_root).as_posix())
    lib = source_root / "runtime" / "lib"
    if lib.is_dir():
        for f in lib.rglob("*.py"):
            if "__pycache__" in f.parts:
                continue
            rels.append(f.relative_to(source_root).as_posix())
    for extra in ("runtime/session_config.py", "runtime/__init__.py"):
        if (source_root / extra).is_file():
            rels.append(extra)
    return sorted(set(rels))
