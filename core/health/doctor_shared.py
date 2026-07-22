"""Doctor shared constants — regex patterns and hook-path inventories.

Split out of doctor.py (WO-GF-CORE-HEALTH-SKILLS): data leaf consumed by
doctor_skill_sync.py and doctor_checks.py.
"""

from __future__ import annotations

import re

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
