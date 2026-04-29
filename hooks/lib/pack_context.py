"""Pack-awareness helper for hook dispatch.

Provides is_pack_active() so hooks can check whether their domain pack
is enabled before doing any work. When the user has not configured
active_packs (the default), ALL packs are considered active.

Only returns False when active_packs is explicitly set AND the requested
pack is absent from that list — an explicit opt-out.
"""

from __future__ import annotations

from . import state


def is_pack_active(pack_name: str) -> bool:
    """Return True if pack_name is active in the user's config.

    Rules:
    - active_packs absent or empty list  → all packs active (return True)
    - active_packs non-empty list        → only listed packs active
    """
    try:
        cfg = state.read_config()
    except Exception:
        return True  # Fail open — never suppress hooks on config read error

    active = cfg.get("active_packs")
    if not active:
        return True

    return pack_name in active
