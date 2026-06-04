"""Extension Description Disambiguation — Phase 19.6.

Activation-time gate for mode_addition and gap_filler extensions.
Prevents routing degradation caused by new extension descriptions that
shadow existing canonical skill descriptions.

Thresholds (from 18.9.9 decision log):
  < 0.70  → clean   — activation proceeds normally
  0.70-0.85 → warning  — activation blocked until operator accepts via --accept-warning
  ≥ 0.85  → critical  — activation blocked until operator provides --force "<reason>"

Classification gating:
  mode_addition → check against all canonical skill descriptions (32 in 18.9.9)
  gap_filler    → check within same skill's existing rules only
  others        → no check, always clean

Zero LLM. Pure Python Jaccard on word tokens. Zero tokens.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

WARNING_THRESHOLD = 0.70
CRITICAL_THRESHOLD = 0.85

_CANONICAL_SKILLS_ROOT = Path(__file__).parents[2] / "canonical" / "skills"


@dataclass
class CollisionPair:
    compared_id: str  # skill_id or rule_id of the colliding item
    compared_description: str
    similarity_score: float


@dataclass
class CollisionResult:
    status: str  # "clean" | "warning" | "critical"
    extension_id: str
    candidate_description: str
    collisions: list[CollisionPair] = field(default_factory=list)
    verdict_reason: str = ""
    accepted: bool = False  # set when operator accepts via CLI
    force_reason: str = ""  # set when operator uses --force


# ── Core calculation ──────────────────────────────────────────────────────


def jaccard_similarity(text_a: str, text_b: str) -> float:
    """Word-level Jaccard similarity between two description strings.

    Returns 0.0–1.0. Empty strings return 0.0 to avoid false positives.
    """
    if not text_a or not text_b:
        return 0.0
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


# ── Description extraction ────────────────────────────────────────────────


def extract_description(extension: dict[str, Any]) -> str | None:
    """Extract the description from an extension's content JSON."""
    content_raw = extension.get("content")
    if not content_raw:
        return None
    try:
        content = json.loads(content_raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return content.get("description") or content.get("doc_title") or None


# ── Comparison sets ───────────────────────────────────────────────────────


def load_canonical_descriptions(skill_id: str | None = None) -> list[tuple[str, str]]:
    """Load (identifier, description) tuples from canonical skill metadata.yml files.

    If skill_id given, returns only that skill's rules from its rules.yml.
    Otherwise returns all canonical skill descriptions from metadata.yml.
    """
    results: list[tuple[str, str]] = []

    if skill_id:
        # For gap_filler: load same-skill rules from rules.yml
        parts = skill_id.replace("ds-", "").split(":")
        if len(parts) >= 2:
            pack, mode = parts[0], parts[1]
            rules_path = _CANONICAL_SKILLS_ROOT / pack / "modes" / mode / "rules.yml"
            if rules_path.exists():
                try:
                    import yaml

                    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or []
                    for rule in rules:
                        rule_id = rule.get("id", "")
                        desc = rule.get("description", "")
                        if rule_id and desc:
                            results.append((f"{skill_id}:{rule_id}", desc))
                except Exception:
                    pass
        return results

    # For mode_addition: load all canonical skill descriptions
    for meta_path in sorted(_CANONICAL_SKILLS_ROOT.rglob("metadata.yml")):
        try:
            import yaml

            data = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            desc = data.get("description", "")
            if not desc:
                continue
            # Use the skill's path as the identifier
            rel = meta_path.parent.relative_to(_CANONICAL_SKILLS_ROOT).as_posix()
            results.append((rel, desc))
        except Exception:
            pass

    return results


def load_active_mode_descriptions(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Load descriptions of all active mode_addition extensions for comparison."""
    results: list[tuple[str, str]] = []
    try:
        rows = conn.execute(
            "SELECT extension_id, content FROM ds_user_extensions "
            "WHERE status = 'active' AND extension_type = 'mode_addition'"
        ).fetchall()
        for r in rows:
            try:
                content = json.loads(r[1] or "{}")
                desc = content.get("description", "")
                if desc:
                    results.append((r[0], desc))
            except Exception:
                pass
    except sqlite3.OperationalError:
        pass
    return results


# ── Main check ────────────────────────────────────────────────────────────


def check_extension_description(
    extension: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> CollisionResult:
    """Check extension description for collision with canonical skills or existing rules.

    Classification gating:
      mode_addition → checks against all canonical skill descriptions + active mode extensions
      gap_filler    → checks within-skill only (same skill's rules.yml)
      all others    → clean (no check needed)
    """
    extension_id = extension.get("extension_id", "")
    ext_type = extension.get("extension_type", "")
    skill_id = extension.get("skill_id", "")

    # Classification gate — only check mode_addition and gap_filler
    if ext_type not in ("mode_addition", "gap_filler"):
        return CollisionResult(
            status="clean",
            extension_id=extension_id,
            candidate_description="",
            verdict_reason=f"no check for {ext_type!r}",
        )

    candidate_desc = extract_description(extension)
    if not candidate_desc:
        return CollisionResult(
            status="clean",
            extension_id=extension_id,
            candidate_description="",
            verdict_reason="no description to check",
        )

    # Load comparison set
    if ext_type == "mode_addition":
        comparisons = load_canonical_descriptions()
        if conn:
            comparisons += load_active_mode_descriptions(conn)
    else:
        # gap_filler: within-skill only
        comparisons = load_canonical_descriptions(skill_id)

    # Compute pairwise scores
    worst_score = 0.0
    collisions: list[CollisionPair] = []

    for comp_id, comp_desc in comparisons:
        score = jaccard_similarity(candidate_desc, comp_desc)
        if score >= WARNING_THRESHOLD:
            collisions.append(
                CollisionPair(
                    compared_id=comp_id,
                    compared_description=comp_desc,
                    similarity_score=score,
                )
            )
        worst_score = max(worst_score, score)

    # Sort collisions by score descending
    collisions.sort(key=lambda c: c.similarity_score, reverse=True)

    if worst_score >= CRITICAL_THRESHOLD:
        status = "critical"
        reason = (
            f"critical collision: similarity={worst_score:.2f} ≥ {CRITICAL_THRESHOLD} "
            f"with {collisions[0].compared_id!r}"
        )
    elif worst_score >= WARNING_THRESHOLD:
        status = "warning"
        reason = (
            f"description collision: similarity={worst_score:.2f} ≥ {WARNING_THRESHOLD} "
            f"with {collisions[0].compared_id!r}"
        )
    else:
        status = "clean"
        reason = f"no collision (worst_score={worst_score:.2f})"

    return CollisionResult(
        status=status,
        extension_id=extension_id,
        candidate_description=candidate_desc,
        collisions=collisions,
        verdict_reason=reason,
    )
