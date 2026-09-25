"""Pack-awareness helper for hook dispatch.

Provides is_pack_active() so hooks can check whether their domain pack
is enabled before doing any work. When the user has not configured
active_packs (the default), ALL packs are considered active.

Only returns False when active_packs is explicitly set AND the requested
pack is absent from that list — an explicit opt-out.
"""

from __future__ import annotations

from core.config import state

# A pack split renames the pack a hook checks against (game-dev's
# on-game-validate moved from "domains" to "apps" in the apps pack split,
# PR #817) but active_packs is a user-hand-edited opt-in allowlist that
# nothing migrates. Without this, anyone who had narrowed active_packs to
# include the pack's OLD name would have game validation silently stop
# firing on update. Maps new name -> old name(s) it split out of.
_PACK_ALIASES: dict[str, tuple[str, ...]] = {
    "apps": ("domains",),
}


def is_pack_active(pack_name: str) -> bool:
    """Return True if pack_name is active in the user's config.

    Rules:
    - active_packs absent or empty list  → all packs active (return True)
    - active_packs non-empty list        → only listed packs, or a pack
      it was split out of, are active
    """
    try:
        cfg = state.read_config()
    except Exception:
        return True  # Fail open — never suppress hooks on config read error

    active = cfg.get("active_packs")
    if not active:
        return True

    if pack_name in active:
        return True

    return any(alias in active for alias in _PACK_ALIASES.get(pack_name, ()))
