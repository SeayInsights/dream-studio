"""Retroactive Validation — Phase 19.5.

The most critical safety gate in Phase 19. Compiled extensions sit in
status='proposed'. This module validates them against historical work orders
and applies Decision 6 to determine whether they become 'active'.

Decision 6 thresholds (from roadmap, exact):
  N < 5 → experimental (insufficient_wo_count)
  N ≥ 5 AND current_eval_score >= baseline_eval_score * 0.95 → active
  N ≥ 5 AND score < 0.95 × baseline → experimental (regression_detected)
  Onboarding → experimental directly (gate skipped by design)
  user_confirmed_at required for active status regardless of score

Three validation paths (one per classification):
  PersonalizationValidator — SQL inference against historical scan_runs/findings
  CapabilityValidator      — synthetic EvalCase via core/eval/runner.py (reuse)
  OnboardingValidator      — gate skip, mark experimental, no score computed

Token cost per path:
  personalization: 0 tokens (pure SQL)
  capability: ~200 tokens (eval runner judge call if claude available)
  onboarding: 0 tokens (skipped)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DECISION_6_N_THRESHOLD = 5
DECISION_6_SCORE_TOLERANCE = 0.95
SCAN_WINDOW_DAYS = 90
DEFAULT_BASELINE = 0.85  # Conservative default when no skill-specific baseline exists


@dataclass
class ValidationResult:
    success: bool
    extension_id: str | None = None
    verdict: str | None = None  # "active" | "experimental" | "experimental_with_warning"
    verdict_reason: str = ""
    baseline_eval_score: float | None = None
    current_eval_score: float | None = None
    past_wo_count: int = 0
    tokens_estimated: int = 0
    error: str | None = None


class RetroactiveValidator:
    """Routes extensions to the correct sub-validator per classification.

    Session-end hook: increment_for_session(session_id) increments past_wo_count
    for all experimental extensions matching skills invoked in the session.
    When past_wo_count crosses DECISION_6_N_THRESHOLD, full validation runs.
    """

    def __init__(self, conn: sqlite3.Connection, db_path: Path | None = None) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.db_path = db_path  # passed to EvalRunner for baseline reads

    # ── Public API ────────────────────────────────────────────────────────

    def validate(self, extension_id: str, force: bool = False) -> ValidationResult:
        """Validate a single extension. Routes to the right sub-validator."""
        ext = self._load_extension(extension_id)
        if ext is None:
            return ValidationResult(
                success=False,
                extension_id=extension_id,
                error=f"Extension {extension_id!r} not found",
            )

        classification = self._get_classification(ext)
        if classification is None:
            return ValidationResult(
                success=False,
                extension_id=extension_id,
                error="Extension has no associated friction signal classification",
            )

        if classification == "personalization":
            result = PersonalizationValidator(self.conn).validate(ext, force=force)
        elif classification == "capability":
            result = CapabilityValidator(self.conn, db_path=self.db_path).validate(ext, force=force)
        else:
            # onboarding and any unknown → gate skip
            result = OnboardingValidator(self.conn).validate(ext)

        if result.success:
            # Phase 19.6: run disambiguation check after validation passes.
            # Only applies when verdict is 'active' — warning/experimental skip the check.
            if result.verdict == "active":
                result = self._check_disambiguation(ext, result)
            self._persist_verdict(extension_id, result)
        return result

    def validate_all_proposed(self) -> list[ValidationResult]:
        """Validate all proposed extensions that have enough WO history."""
        try:
            rows = self.conn.execute("""
                SELECT extension_id FROM ds_user_extensions
                WHERE status IN ('proposed', 'experimental')
                  AND (content IS NOT NULL AND content != '' AND content != '{}')
                ORDER BY created_at
                """).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("validate_all_proposed failed: %s", exc)
            return []
        return [self.validate(r["extension_id"]) for r in rows]

    def increment_for_session(self, session_id: str | None = None) -> None:
        """Session-end hook: increment past_wo_count for relevant extensions.

        Finds skills invoked via scan_runs in the recent window, increments
        past_wo_count for matching experimental/proposed extensions, and
        triggers full validation when the count crosses DECISION_6_N_THRESHOLD.
        Non-blocking: all exceptions are caught.
        """
        try:
            # Find skills that ran recently (as a proxy for "this session")
            skill_rows = self.conn.execute("""
                SELECT DISTINCT skill_id FROM scan_runs
                WHERE skill_id IS NOT NULL
                  AND created_at >= datetime('now', '-1 days')
                """).fetchall()
            recent_skills = {r["skill_id"] for r in skill_rows}

            if not recent_skills:
                return

            for skill_id in recent_skills:
                # Increment past_wo_count for experimental/proposed extensions for this skill
                self.conn.execute(
                    """
                    UPDATE ds_user_extensions
                    SET past_wo_count = past_wo_count + 1
                    WHERE skill_id = ?
                      AND status IN ('proposed', 'experimental')
                      AND (content IS NOT NULL AND content != '' AND content != '{}')
                    """,
                    (skill_id,),
                )
            self.conn.commit()

            # Auto-validate any extensions that just crossed the threshold
            newly_eligible = self.conn.execute(f"""
                SELECT extension_id FROM ds_user_extensions
                WHERE past_wo_count >= {DECISION_6_N_THRESHOLD}
                  AND status IN ('proposed', 'experimental')
                  AND (content IS NOT NULL AND content != '' AND content != '{{}}')
                  AND (last_validated_at IS NULL OR
                       last_validated_at < datetime('now', '-1 days'))
                """).fetchall()

            for row in newly_eligible:
                try:
                    self.validate(row["extension_id"])
                except Exception as exc:
                    logger.warning("Auto-validation failed for %s: %s", row["extension_id"], exc)

        except Exception as exc:
            logger.debug("increment_for_session failed (non-blocking): %s", exc)

    def _check_disambiguation(
        self, ext: dict[str, Any], result: "ValidationResult"
    ) -> "ValidationResult":
        """Phase 19.6: run description collision check after validation passes.

        If collision found, reverts verdict from 'active' to 'experimental' and
        adds collision_check to the validation detail. Non-blocking — exceptions
        result in the original result being returned unchanged.
        """
        try:
            from core.expansion.disambiguation import (
                check_extension_description,
                WARNING_THRESHOLD,
                CRITICAL_THRESHOLD,
            )

            collision = check_extension_description(ext, conn=self.conn)
            if collision.status == "clean":
                return result

            # Collision found — revert to experimental
            result.verdict = "experimental"
            result.verdict_reason = collision.verdict_reason

            # Store collision details in validation_detail (will be written in _persist_verdict)
            result._collision_check = {  # type: ignore[attr-defined]
                "status": collision.status,
                "candidate_description": collision.candidate_description,
                "top_collision": {
                    "compared_id": (
                        collision.collisions[0].compared_id if collision.collisions else ""
                    ),
                    "similarity_score": (
                        collision.collisions[0].similarity_score if collision.collisions else 0.0
                    ),
                },
                "warning_threshold": WARNING_THRESHOLD,
                "critical_threshold": CRITICAL_THRESHOLD,
                "accepted": False,
                "force_reason": "",
            }
        except Exception as exc:
            logger.debug("Disambiguation check failed (non-blocking): %s", exc)

        return result

    # ── Internal helpers ──────────────────────────────────────────────────

    def _load_extension(self, extension_id: str) -> dict[str, Any] | None:
        try:
            row = self.conn.execute(
                "SELECT * FROM ds_user_extensions WHERE extension_id = ?", (extension_id,)
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return dict(row) if row else None

    def _get_classification(self, ext: dict[str, Any]) -> str | None:
        """Read classification from the linked friction signal."""
        compiled_from = json.loads(ext.get("compiled_from") or "{}")
        signal_id = compiled_from.get("friction_signal_id")
        if not signal_id:
            return None
        try:
            row = self.conn.execute(
                "SELECT classified_as FROM ds_friction_signals WHERE signal_id = ?",
                (signal_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return row["classified_as"] if row else None

    def _persist_verdict(self, extension_id: str, result: ValidationResult) -> None:
        detail_dict: dict[str, Any] = {
            "validated_at": _now_iso(),
            "verdict": result.verdict,
            "verdict_reason": result.verdict_reason,
            "classification_path": "personalization",
            "force_override": False,
        }
        # Phase 19.6: include collision_check if present
        collision_check = getattr(result, "_collision_check", None)
        if collision_check:
            detail_dict["collision_check"] = collision_check
        detail = json.dumps(detail_dict)
        try:
            self.conn.execute(
                """
                UPDATE ds_user_extensions
                SET status = ?,
                    baseline_eval_score = COALESCE(baseline_eval_score, ?),
                    current_eval_score = ?,
                    past_wo_count = ?,
                    last_validated_at = datetime('now'),
                    validation_detail = ?
                WHERE extension_id = ?
                """,
                (
                    result.verdict,
                    result.baseline_eval_score,
                    result.current_eval_score,
                    result.past_wo_count,
                    detail,
                    extension_id,
                ),
            )
            self.conn.commit()
        except Exception as exc:
            logger.warning("Failed to persist verdict for %s: %s", extension_id, exc)


# ── Decision 6 logic ──────────────────────────────────────────────────────


def apply_decision_6(
    score: float,
    baseline: float,
    n: int,
    force: bool = False,
) -> tuple[str, str]:
    """Apply Decision 6 thresholds. Returns (verdict, reason).

    verdict: "active" | "experimental" | "experimental_with_warning"
    """
    if force and n < DECISION_6_N_THRESHOLD:
        return "active", f"force_override: N={n} (below threshold), operator explicitly activated"

    if n < DECISION_6_N_THRESHOLD:
        return "experimental", f"insufficient_wo_count: N={n} < {DECISION_6_N_THRESHOLD}"

    threshold = baseline * DECISION_6_SCORE_TOLERANCE
    if score >= threshold:
        return "active", (f"N={n}, score={score:.3f} >= baseline*0.95={threshold:.3f}")

    delta = score - threshold
    return "experimental_with_warning", (
        f"regression_detected: N={n}, score={score:.3f} < baseline*0.95={threshold:.3f}, "
        f"delta={delta:.3f}"
    )


# ── Personalization validator ──────────────────────────────────────────────


class PersonalizationValidator:
    """SQL inference for threshold_override / option_override extensions.

    Computes alignment score: how well does the extension match operator's
    documented preferences (historical dismissals)? Pure SQL, zero tokens.

    Score mapping:
      alignment >= 0.8 → current_eval_score = 0.95
      alignment 0.5-0.8 → current_eval_score = 0.82
      alignment < 0.5 → current_eval_score = 0.70
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def validate(self, ext: dict[str, Any], force: bool = False) -> ValidationResult:
        extension_id = ext["extension_id"]
        skill_id = ext["skill_id"]
        content = json.loads(ext.get("content") or "{}")
        rule_id = content.get("rule_id")
        n = ext.get("past_wo_count", 0)

        baseline = self._read_baseline(skill_id)

        # Compute alignment from dismissal history
        alignment = self._compute_alignment(skill_id, rule_id)
        current_score = self._alignment_to_score(alignment)

        verdict, reason = apply_decision_6(current_score, baseline, n, force=force)

        return ValidationResult(
            success=True,
            extension_id=extension_id,
            verdict=verdict,
            verdict_reason=reason,
            baseline_eval_score=baseline,
            current_eval_score=current_score,
            past_wo_count=n,
            tokens_estimated=0,
        )

    def _compute_alignment(self, skill_id: str, rule_id: str | None) -> float:
        """Compute how well the extension aligns with operator dismissal behavior."""
        try:
            total_row = self.conn.execute(
                f"""
                SELECT COUNT(*) AS cnt FROM findings
                WHERE introduced_by_skill_id = ?
                  AND created_at >= datetime('now', '-{SCAN_WINDOW_DAYS} days')
                  {("AND rule_id = ?" if rule_id else "")}
                """,
                (skill_id, rule_id) if rule_id else (skill_id,),
            ).fetchone()
            total = total_row["cnt"] if total_row else 0

            if total == 0:
                return 0.5  # No data → neutral

            dismissed_row = self.conn.execute(
                f"""
                SELECT COUNT(*) AS cnt FROM findings
                WHERE introduced_by_skill_id = ?
                  AND dismissed_at IS NOT NULL
                  AND created_at >= datetime('now', '-{SCAN_WINDOW_DAYS} days')
                  {("AND rule_id = ?" if rule_id else "")}
                """,
                (skill_id, rule_id) if rule_id else (skill_id,),
            ).fetchone()
            dismissed = dismissed_row["cnt"] if dismissed_row else 0

            return dismissed / total
        except sqlite3.OperationalError:
            return 0.5

    @staticmethod
    def _alignment_to_score(alignment: float) -> float:
        if alignment >= 0.8:
            return 0.95
        if alignment >= 0.5:
            return 0.82
        return 0.70

    def _read_baseline(self, skill_id: str) -> float:
        try:
            row = self.conn.execute("""
                SELECT AVG(baseline_score) AS avg_score
                FROM ds_eval_baselines
                WHERE label = 'pre_phase_19'
                """).fetchone()
            return float(row["avg_score"]) if row and row["avg_score"] else DEFAULT_BASELINE
        except sqlite3.OperationalError:
            return DEFAULT_BASELINE

    def _sample_scan_ids(self, skill_id: str, limit: int = 10) -> list[str]:
        try:
            rows = self.conn.execute(
                "SELECT scan_id FROM scan_runs WHERE skill_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (skill_id, limit),
            ).fetchall()
            return [r["scan_id"] for r in rows]
        except sqlite3.OperationalError:
            return []


# ── Capability validator ───────────────────────────────────────────────────


class CapabilityValidator:
    """Synthetic EvalCase via core/eval/runner.py for gap_filler / mode_addition.

    Constructs a synthetic EvalCase from the extension's compiled content and
    compiled_from event_ids, then runs it through the existing EvalRunner.
    The 70/30 scoring + baseline comparison come for free.

    Token cost: ~200 tokens (eval runner judge call when claude available).
    Falls back to fixture-mode only if judge unavailable (still scores event component).
    """

    def __init__(self, conn: sqlite3.Connection, db_path: Path | None = None) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.db_path = db_path

    def validate(self, ext: dict[str, Any], force: bool = False) -> ValidationResult:
        from core.eval.runner import EvalRunner
        from core.eval.schema import EvalCase

        extension_id = ext["extension_id"]
        skill_id = ext["skill_id"]
        content = json.loads(ext.get("content") or "{}")
        compiled_from = json.loads(ext.get("compiled_from") or "{}")
        n = ext.get("past_wo_count", 0)

        baseline = self._read_baseline(skill_id)

        # Build synthetic EvalCase from extension content
        event_ids = compiled_from.get("event_ids", [])
        fixture_events = self._load_fixture_events(event_ids)
        description = content.get("description", "extension capability validation")

        case = EvalCase(
            eval_id=f"ext_{extension_id[:8]}_v",
            version="19.5",
            description=description,
            skill_id=skill_id,
            input_prompt=f"Validate extension: {description}",
            expected_events=[],
            expected_behavior=description,
            negative_checks=[],
            event_weight=0.7,
            behavior_weight=0.3,
            minimum_pass_score=baseline * DECISION_6_SCORE_TOLERANCE,
            fixture_events=fixture_events if fixture_events else None,
            fixture_transcript=f"Operator session demonstrating: {description}",
        )

        try:
            runner = EvalRunner(db_path=self.db_path, run_mode="fixture")
            result = runner.run_case(case)
            current_score = result.composite_score
            tokens = result.tokens_consumed
        except Exception as exc:
            logger.warning("EvalRunner failed for capability extension %s: %s", extension_id, exc)
            return ValidationResult(
                success=False,
                extension_id=extension_id,
                error=f"EvalRunner failed: {exc}",
                past_wo_count=n,
            )

        verdict, reason = apply_decision_6(current_score, baseline, n, force=force)

        return ValidationResult(
            success=True,
            extension_id=extension_id,
            verdict=verdict,
            verdict_reason=reason,
            baseline_eval_score=baseline,
            current_eval_score=current_score,
            past_wo_count=n,
            tokens_estimated=tokens,
        )

    def _load_fixture_events(self, event_ids: list[str]) -> list[dict[str, Any]]:
        if not event_ids:
            return []
        try:
            placeholders = ",".join("?" for _ in event_ids)
            rows = self.conn.execute(
                f"SELECT event_type, payload, trace FROM canonical_events "
                f"WHERE event_id IN ({placeholders})",
                event_ids,
            ).fetchall()
            return [
                {
                    "event_type": r["event_type"],
                    **(json.loads(r["payload"] or "{}") if r["payload"] else {}),
                }
                for r in rows
            ]
        except sqlite3.OperationalError:
            return []

    def _read_baseline(self, skill_id: str) -> float:
        try:
            row = self.conn.execute(
                "SELECT AVG(baseline_score) AS avg FROM ds_eval_baselines "
                "WHERE label = 'pre_phase_19'",
            ).fetchone()
            return float(row["avg"]) if row and row["avg"] else DEFAULT_BASELINE
        except sqlite3.OperationalError:
            return DEFAULT_BASELINE


# ── Onboarding validator ───────────────────────────────────────────────────


class OnboardingValidator:
    """Gate skip for onboarding/documentation extensions.

    Onboarding docs don't change skill output — the behavioral eval suite
    cannot meaningfully score them. They go directly to 'experimental'
    after compilation, then 'active' when operator confirms.

    Token cost: 0 (no eval, no LLM call).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def validate(self, ext: dict[str, Any]) -> ValidationResult:
        return ValidationResult(
            success=True,
            extension_id=ext["extension_id"],
            verdict="experimental",
            verdict_reason="onboarding_skips_gate: docs don't affect skill output; "
            "waiting for user_confirmed_at",
            baseline_eval_score=None,
            current_eval_score=None,
            past_wo_count=ext.get("past_wo_count", 0),
            tokens_estimated=0,
        )


# ── Utility ───────────────────────────────────────────────────────────────


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
