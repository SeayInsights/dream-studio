"""ExtensionLoader — Phase 19.7 Provisioner Integration.

Loads active extensions from ds_user_extensions and provides them to the
skill dispatcher as a session-scoped cache. Two integration mechanisms:

1. Invocation-time (personalization): applied at dispatch start as a post-scan
   filter. Extensions with status='active' suppress or reweight findings.
2. Install-time (capability + onboarding): provided to compile_pack() for
   baking into the compiled Claude Code integration output.

Cache design:
  Class-level dict, loaded once per Python process, reset on explicit invalidation.
  Invalidation must be called from every ds learn operation that changes extension state.
  Direct SQL updates (bypassing CLI) do NOT invalidate the cache by design — CLI is
  the source of truth for extension state changes.

Session snapshot:
  audit() takes a snapshot (dict copy) at dispatch start. Mid-audit state changes
  don't affect the running audit. The cache is the shared source; the snapshot is
  per-dispatch isolation.

Conflict resolution (applied in get_overrides_for_skill):
  suppress > threshold_override > newest-wins for same rule_id
  personalization overrides are applied at invocation time;
  capability additions are baked at install time — no runtime conflict possible.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


@dataclass
class ExtensionOverride:
    """A resolved, conflict-resolved personalization override for one skill."""

    rule_id: str | None
    action: str  # "suppress" | "threshold" | "none"
    threshold_severity: str | None = None  # for action="threshold"
    extension_id: str = ""
    confirmed_at: str = ""


class ExtensionLoader:
    """Session-scoped cache for active ds_user_extensions.

    All methods are safe to call when ds_user_extensions does not exist (table
    not yet migrated) — they return empty results gracefully.
    """

    _cache: dict[str, list[dict[str, Any]]] = {}
    _version: int = 0

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    @classmethod
    def invalidate_cache(cls) -> None:
        """Clear the session cache. Must be called after any extension state change."""
        cls._cache.clear()
        cls._version += 1
        logger.debug("ExtensionLoader cache invalidated (version=%d)", cls._version)

    def get_active_for_skill(
        self,
        skill_id: str,
        include_experimental: bool = False,
    ) -> list[dict[str, Any]]:
        """Return active extensions for a skill. Uses session cache."""
        statuses = ("active", "experimental") if include_experimental else ("active",)
        cache_key = f"{skill_id}:{':'.join(statuses)}"

        if cache_key not in self._cache:
            self._cache[cache_key] = self._query(skill_id, statuses)

        return self._cache[cache_key]

    def get_overrides_for_skill(
        self,
        skill_id: str,
        include_experimental: bool = False,
    ) -> list[ExtensionOverride]:
        """Return conflict-resolved personalization overrides for a skill.

        Conflict resolution:
          - suppress beats threshold for the same rule_id
          - newest user_confirmed_at wins within the same action type
        """
        extensions = self.get_active_for_skill(skill_id, include_experimental)
        personalization = [
            e
            for e in extensions
            if e.get("extension_type") in ("threshold_override", "option_override")
        ]

        # Group by rule_id, apply conflict resolution
        by_rule: dict[str | None, list[dict[str, Any]]] = {}
        for ext in personalization:
            content = json.loads(ext.get("content") or "{}")
            rule_id = content.get("rule_id")
            if rule_id not in by_rule:
                by_rule[rule_id] = []
            by_rule[rule_id].append(ext)

        resolved: list[ExtensionOverride] = []
        for rule_id, exts in by_rule.items():
            suppress_exts = [
                e for e in exts if json.loads(e.get("content") or "{}").get("action") == "suppress"
            ]
            if suppress_exts:
                # Suppress beats all
                ext = suppress_exts[0]
                resolved.append(
                    ExtensionOverride(
                        rule_id=rule_id,
                        action="suppress",
                        extension_id=ext.get("extension_id", ""),
                        confirmed_at=ext.get("user_confirmed_at") or "",
                    )
                )
            else:
                # Newest wins for threshold overrides
                sorted_exts = sorted(
                    exts,
                    key=lambda e: e.get("user_confirmed_at") or "",
                    reverse=True,
                )
                if sorted_exts:
                    ext = sorted_exts[0]
                    content = json.loads(ext.get("content") or "{}")
                    threshold = (
                        content.get("value")
                        if content.get("option") == "severity_threshold"
                        else None
                    )
                    resolved.append(
                        ExtensionOverride(
                            rule_id=rule_id,
                            action="threshold" if threshold else "none",
                            threshold_severity=threshold,
                            extension_id=ext.get("extension_id", ""),
                            confirmed_at=ext.get("user_confirmed_at") or "",
                        )
                    )

        return resolved

    def snapshot(
        self, skill_ids: list[str], include_experimental: bool = False
    ) -> dict[str, list[ExtensionOverride]]:
        """Take a snapshot of overrides for multiple skills at dispatch start.

        Returns a dict {skill_id: [ExtensionOverride, ...]}.
        Used by SkillDispatcher.audit() for session isolation.
        """
        result: dict[str, list[ExtensionOverride]] = {}
        for skill_id in skill_ids:
            result[skill_id] = self.get_overrides_for_skill(skill_id, include_experimental)
        return result

    def get_capability_extensions(self) -> list[dict[str, Any]]:
        """Return active capability extensions (gap_filler, mode_addition) for compile_pack()."""
        return self._query_type(("gap_filler", "mode_addition"))

    def get_onboarding_extensions(self) -> list[dict[str, Any]]:
        """Return active onboarding extensions for compile_pack()."""
        return self._query_type(("example",), content_subtype="onboarding_doc")

    def _query(self, skill_id: str, statuses: tuple[str, ...]) -> list[dict[str, Any]]:
        """Query ds_user_extensions for a specific skill and status set."""
        placeholders = ",".join("?" for _ in statuses)
        try:
            conn = self._connect()
            try:
                rows = conn.execute(
                    f"SELECT * FROM ds_user_extensions "
                    f"WHERE skill_id = ? AND status IN ({placeholders}) "
                    f"ORDER BY user_confirmed_at DESC",
                    (skill_id, *statuses),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except (sqlite3.OperationalError, FileNotFoundError):
            return []

    def _query_type(
        self,
        ext_types: tuple[str, ...],
        content_subtype: str | None = None,
    ) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in ext_types)
        try:
            conn = self._connect()
            try:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    f"SELECT * FROM ds_user_extensions "
                    f"WHERE status = 'active' AND extension_type IN ({placeholders}) "
                    f"ORDER BY user_confirmed_at DESC",
                    ext_types,
                ).fetchall()
            finally:
                conn.close()
        except (sqlite3.OperationalError, FileNotFoundError):
            return []

        results = []
        for r in rows:
            row = dict(r)
            if content_subtype:
                try:
                    content = json.loads(row.get("content") or "{}")
                    if content.get("extension_type") != content_subtype:
                        continue
                except (json.JSONDecodeError, TypeError):
                    continue
            results.append(row)
        return results

    def _connect(self) -> sqlite3.Connection:
        if self._db_path:
            conn = sqlite3.connect(str(self._db_path))
        else:
            from core.config.database import _default_db_path

            conn = sqlite3.connect(str(_default_db_path()))
        conn.row_factory = sqlite3.Row
        return conn


# ── Personalization filter ────────────────────────────────────────────────


def apply_personalization_overrides(
    findings: list[dict[str, Any]],
    overrides: list[ExtensionOverride],
) -> list[dict[str, Any]]:
    """Apply conflict-resolved personalization overrides to a findings list.

    Called at invocation time (after RulesScanner.scan() returns).
    Canonical findings are not modified — a new filtered list is returned.
    """
    if not overrides:
        return findings

    filtered = list(findings)
    for override in overrides:
        if override.action == "suppress":
            if override.rule_id:
                filtered = [f for f in filtered if f.get("rule_id") != override.rule_id]
            # rule_id=None suppresses entire skill (all findings)
            else:
                filtered = []
        elif override.action == "threshold" and override.threshold_severity:
            min_rank = SEVERITY_RANK.get(override.threshold_severity, 0)
            if override.rule_id:
                filtered = [
                    f
                    for f in filtered
                    if f.get("rule_id") != override.rule_id
                    or SEVERITY_RANK.get(f.get("severity", "info"), 0) >= min_rank
                ]
            else:
                filtered = [
                    f
                    for f in filtered
                    if SEVERITY_RANK.get(f.get("severity", "info"), 0) >= min_rank
                ]

    return filtered


# ── Mode collision detection ──────────────────────────────────────────────


class ModeCollisionError(Exception):
    """Two mode_addition extensions specify the same mode name."""


def check_mode_collisions(extensions: list[dict[str, Any]]) -> None:
    """Raise ModeCollisionError if two mode_addition extensions share a mode_name.

    19.6 (Description Disambiguation) handles the resolution flow;
    this function is the detection gate.
    """
    mode_additions = [e for e in extensions if e.get("extension_type") == "mode_addition"]
    seen: dict[str, str] = {}  # mode_name → extension_id
    for ext in mode_additions:
        content = json.loads(ext.get("content") or "{}")
        mode_name = content.get("mode_name", "")
        if not mode_name:
            continue
        if mode_name in seen:
            raise ModeCollisionError(
                f"Mode name collision detected: {mode_name!r} defined by both "
                f"{seen[mode_name]!r} and {ext.get('extension_id', '?')!r}. "
                f"Run 19.6 Description Disambiguation to resolve."
            )
        seen[mode_name] = ext.get("extension_id", "?")
