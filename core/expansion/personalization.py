"""Personalization compiler — Phase 19.4a.

Pure SQL compilation of personalization extensions from observed dismissal
patterns. Zero LLM. Zero speculation.

The compiled content IS the observed preference — derived from the finding_ids
the operator actually dismissed. `compiled_from` MUST cite real source IDs.
If the compiler cannot find supporting evidence, compilation fails cleanly
with no content written and the friction signal returned to deferred state.

This is the SkillsBench defense:
  SkillsBench (2026): LLM-authored +0.0pp, human-curated +16.2pp.
  Prevention: content comes from finding_ids, not LLM description.

Input:
  ds_user_extensions WHERE status='proposed'
  + ds_friction_signals WHERE classified_as='personalization' (via compiled_from)

Output:
  ds_user_extensions.content = JSON threshold_override or option_override
  ds_user_extensions.compiled_from updated with finding_ids cited
  extension_type updated to reflect the actual compiled override type

On failure:
  No content written. Friction signal classified_as reset to NULL (deferred).
  Caller receives CompilationResult with success=False and error message.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Minimum dismissals to compile a personalization extension.
# Below this: insufficient evidence — compilation fails.
MIN_DISMISSALS = 2

# Days of dismissal history to consider
WINDOW_DAYS = 30

# Severity ordering for threshold analysis
_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


@dataclass
class CompilationResult:
    success: bool
    extension_id: str | None = None
    content: dict[str, Any] | None = None
    finding_ids_cited: list[str] = field(default_factory=list)
    error: str | None = None
    signal_deferred: bool = False


class PersonalizationCompiler:
    """Compiles personalization extensions from dismissal evidence.

    All content is derived from real finding_ids — never from LLM authorship.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    # ── Public API ────────────────────────────────────────────────────────

    def compile_all(self) -> list[CompilationResult]:
        """Compile all pending personalization extensions.

        Returns list of CompilationResult, one per eligible proposed extension.
        """
        proposals = self._find_proposals()
        results = []
        for proposal in proposals:
            result = self._compile_one(proposal)
            results.append(result)
            if result.success:
                logger.info(
                    "Compiled personalization for extension %s (rule=%s, %d findings cited)",
                    proposal["extension_id"],
                    proposal["rule_id"],
                    len(result.finding_ids_cited),
                )
            else:
                logger.warning(
                    "Compilation failed for extension %s: %s",
                    proposal["extension_id"],
                    result.error,
                )
        return results

    def compile_one(self, extension_id: str) -> CompilationResult:
        """Compile a single extension by ID."""
        proposals = self._find_proposals(extension_id=extension_id)
        if not proposals:
            return CompilationResult(
                success=False,
                extension_id=extension_id,
                error=f"Extension {extension_id!r} not found or not eligible for personalization compilation",
            )
        return self._compile_one(proposals[0])

    # ── Discovery ─────────────────────────────────────────────────────────

    def _find_proposals(self, extension_id: str | None = None) -> list[dict[str, Any]]:
        """Find proposed extensions with personalization classification."""
        params: list[Any] = []
        id_clause = ""
        if extension_id:
            id_clause = "AND e.extension_id = ?"
            params.append(extension_id)

        try:
            rows = self.conn.execute(
                f"""
                SELECT
                    e.extension_id,
                    e.skill_id,
                    e.extension_type,
                    e.compiled_from,
                    fs.signal_id,
                    fs.rule_id,
                    fs.context AS fs_context,
                    fs.classified_as
                FROM ds_user_extensions e
                JOIN ds_friction_signals fs
                    ON json_extract(e.compiled_from, '$.friction_signal_id') = fs.signal_id
                WHERE e.status = 'proposed'
                  AND fs.classified_as = 'personalization'
                  AND (e.content IS NULL OR e.content = '' OR e.content = '{{}}')
                  {id_clause}
                ORDER BY e.created_at
                """,
                params,
            ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("Failed to find proposals: %s", exc)
            return []
        return [dict(r) for r in rows]

    # ── Compilation ───────────────────────────────────────────────────────

    def _compile_one(self, proposal: dict[str, Any]) -> CompilationResult:
        extension_id = proposal["extension_id"]
        skill_id = proposal["skill_id"]
        rule_id = proposal.get("rule_id")
        signal_id = proposal["signal_id"]

        # Read actual dismissal evidence from findings table
        findings = self._fetch_dismissals(skill_id, rule_id)

        # SkillsBench defense: fail if insufficient evidence
        if len(findings) < MIN_DISMISSALS:
            self._defer_signal(signal_id)
            return CompilationResult(
                success=False,
                extension_id=extension_id,
                error=(
                    f"Insufficient dismissal evidence: found {len(findings)} dismissed findings "
                    f"for skill={skill_id!r} rule={rule_id!r} (minimum: {MIN_DISMISSALS}). "
                    f"Signal returned to deferred state."
                ),
                signal_deferred=True,
            )

        # Derive the override type from the evidence
        content, override_type = self._derive_override(skill_id, rule_id, findings)
        finding_ids = [f["finding_id"] for f in findings]

        # Update compiled_from with finding_ids cited (mandatory)
        existing_compiled = json.loads(proposal.get("compiled_from") or "{}")
        existing_compiled["finding_ids"] = finding_ids
        new_compiled_from = json.dumps(existing_compiled)

        # Write to DB
        try:
            self.conn.execute(
                """
                UPDATE ds_user_extensions
                SET content = ?, compiled_from = ?, extension_type = ?
                WHERE extension_id = ?
                """,
                (json.dumps(content), new_compiled_from, override_type, extension_id),
            )
            self.conn.commit()
        except Exception as exc:
            return CompilationResult(
                success=False,
                extension_id=extension_id,
                error=f"DB write failed: {exc}",
            )

        return CompilationResult(
            success=True,
            extension_id=extension_id,
            content=content,
            finding_ids_cited=finding_ids,
        )

    def _fetch_dismissals(self, skill_id: str, rule_id: str | None) -> list[dict[str, Any]]:
        """Fetch actual dismissed findings for this skill/rule from findings table."""
        params: list[Any] = [skill_id]
        rule_clause = ""
        if rule_id:
            rule_clause = "AND (rule_id = ? OR rule_id IS NULL AND ? IS NULL)"
            params.extend([rule_id, rule_id])

        try:
            rows = self.conn.execute(
                f"""
                SELECT finding_id, rule_id, severity, dismissed_at, dismissed_reason,
                       scan_id, created_at
                FROM findings
                WHERE dismissed_at IS NOT NULL
                  AND introduced_by_skill_id = ?
                  AND dismissed_at >= datetime('now', '-{WINDOW_DAYS} days')
                  {rule_clause}
                ORDER BY dismissed_at DESC
                """,
                params,
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(r) for r in rows]

    def _derive_override(
        self, skill_id: str, rule_id: str | None, findings: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], str]:
        """Derive threshold_override or option_override from dismissal evidence.

        Returns (content_dict, extension_type).
        The content is built from the observed finding data — no LLM involved.
        """
        dismissal_count = len(findings)
        finding_ids = [f["finding_id"] for f in findings]
        dismissed_severities = [f["severity"] for f in findings if f.get("severity")]
        dismissed_reasons = [f["dismissed_reason"] for f in findings if f.get("dismissed_reason")]
        distinct_scans = len({f.get("scan_id") for f in findings if f.get("scan_id")})

        # Check severity distribution to determine override type
        severity_ranks = [_SEVERITY_RANK.get(s, 0) for s in dismissed_severities]
        max_dismissed_rank = max(severity_ranks) if severity_ranks else 0

        if max_dismissed_rank <= _SEVERITY_RANK["medium"]:
            # Operator only dismisses low/medium for this rule → raise threshold to high
            override_type = "option_override"
            rationale = (
                f"Operator dismissed {dismissal_count} findings from {skill_id!r} "
                f"(rule={rule_id!r}) across {distinct_scans} scans. "
                f"All dismissed at severity ≤ medium. "
                f"Compiled override: raise threshold to high for this rule."
            )
            content: dict[str, Any] = {
                "extension_type": "option_override",
                "skill_id": skill_id,
                "rule_id": rule_id,
                "option": "severity_threshold",
                "value": "high",
                "compiled_evidence": {
                    "dismissal_count": dismissal_count,
                    "finding_ids": finding_ids,
                    "dismissed_severities": dismissed_severities[:10],
                    "dismissed_reasons": dismissed_reasons[:10],
                    "distinct_sources": distinct_scans,
                },
                "rationale": rationale,
            }
        else:
            # Operator dismisses findings including high/critical → suppress rule entirely
            override_type = "threshold_override"
            rationale = (
                f"Operator dismissed {dismissal_count} findings from {skill_id!r} "
                f"(rule={rule_id!r}) across {distinct_scans} scans, "
                f"including high-severity findings. "
                f"Compiled override: suppress rule {rule_id!r}."
            )
            content = {
                "extension_type": "threshold_override",
                "skill_id": skill_id,
                "rule_id": rule_id,
                "action": "suppress",
                "scope": "all",
                "compiled_evidence": {
                    "dismissal_count": dismissal_count,
                    "finding_ids": finding_ids,
                    "dismissed_severities": dismissed_severities[:10],
                    "dismissed_reasons": dismissed_reasons[:10],
                    "distinct_sources": distinct_scans,
                },
                "rationale": rationale,
            }

        return content, override_type

    # ── Signal deferral ───────────────────────────────────────────────────

    def _defer_signal(self, signal_id: str) -> None:
        """Reset friction signal to unclassified when compilation fails."""
        try:
            self.conn.execute(
                """
                UPDATE ds_friction_signals
                SET classified_as = NULL, classified_at = NULL,
                    classification_confidence = NULL, classification_reason = NULL
                WHERE signal_id = ?
                """,
                (signal_id,),
            )
            self.conn.commit()
        except Exception as exc:
            logger.warning("Failed to defer signal %s: %s", signal_id, exc)

    # ── Read helpers ──────────────────────────────────────────────────────

    def get_pending_compilation(self, limit: int = 50) -> list[dict[str, Any]]:
        """Proposed personalization extensions without compiled content."""
        try:
            rows = self.conn.execute(
                """
                SELECT
                    e.extension_id,
                    e.skill_id,
                    e.extension_type,
                    e.compiled_from,
                    e.created_at,
                    fs.signal_id,
                    fs.rule_id,
                    fs.context AS fs_context,
                    fs.classification_reason
                FROM ds_user_extensions e
                JOIN ds_friction_signals fs
                    ON json_extract(e.compiled_from, '$.friction_signal_id') = fs.signal_id
                WHERE e.status = 'proposed'
                  AND fs.classified_as = 'personalization'
                  AND (e.content IS NULL OR e.content = '' OR e.content = '{}')
                ORDER BY e.created_at
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(r) for r in rows]
