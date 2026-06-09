"""Gap Classifier — Phase 19.3.

Hybrid SQL-first (Tier 1) + LLM-fallback (Tier 2) classifier that determines
what kind of problem a friction signal represents.

Classification outputs (load-bearing for 19.4):
  capability      — skill can't do something it should; 19.4 proposes gap_filler or mode_addition
  personalization — skill does it but not how this operator wants; 19.4 proposes threshold/option override
  onboarding      — operator doesn't know how to use the skill; 19.4 generates docs, no skill modification

Tier 1 (SQL heuristics):
  Deterministic rules over signal_type, frequency, cross-rule/cross-skill patterns.
  Returns classification + confidence >= 0.8 for clear cases. Returns None for ambiguous.

Tier 2 (LLM via Claude Code subprocess):
  For cases Tier 1 can't decide. Same subprocess pattern as core/eval/judge.py.
  No API key required — uses local Claude Code CLI.
  Returns 0.6-0.79 confidence range.

Deferral:
  Insufficient data or LLM unavailable → classified_as stays NULL.

Consumer contract for ds learn review (CLI):
    SELECT * FROM ds_friction_signals
    WHERE classified_as IS NOT NULL
      AND classification_skipped = 0
      AND extension_id IS NULL
    ORDER BY classification_confidence DESC

Consumer contract for 19.4 (Guided Expansion):
    SELECT * FROM ds_friction_signals
    WHERE classified_as IS NOT NULL
      AND classification_skipped = 0
      AND extension_id IS NOT NULL  -- only after operator confirmation in ds learn review
    ORDER BY classified_at
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

CLASSIFIER_TIMEOUT = int(os.environ.get("DREAM_STUDIO_CLASSIFIER_TIMEOUT", "30"))

TIER1_CONFIDENCE = 0.85
TIER2_CONFIDENCE_MIN = 0.6
TIER2_CONFIDENCE_MAX = 0.79

# Thresholds for Tier 1 heuristics
DISMISSAL_HIGH_THRESHOLD = 5  # ≥5 dismissals = strong personalization signal
DISMISSAL_CROSS_RULE_THRESHOLD = 3  # ≥3 distinct rules same skill = capability
PARTIAL_COMPLETION_THRESHOLD = 3  # ≥3 ignored scans = actionable signal
PATTERN_GAP_LOW_CONFIDENCE = 0.3  # confidence < 0.3 in workflow_pattern = strong capability signal

CLASSIFIER_PROMPT_TEMPLATE = """You are classifying a skill friction signal for a developer tool.

Signal:
- Type: {signal_type}
- Skill: {skill_id}
- Rule (if applicable): {rule_id}
- Occurrences: {occurrence_count}
- Distinct sources: {distinct_sources}

Related signals for this skill ({related_count} total):
{related_summary}

Classify as exactly one of:
  capability      — skill fundamentally cannot do something it should do
  personalization — skill does it, but not how this operator wants it done
  onboarding      — operator does not know how to use the skill's output

Respond ONLY with valid JSON, no other text:
{{"classification": "capability|personalization|onboarding", "confidence": 0.65, "reason": "one sentence"}}"""


@dataclass
class ClassificationResult:
    classification: str | None  # None = deferred
    confidence: float | None
    reason: str
    tier: str  # "tier1" | "tier2" | "deferred"
    tokens_estimated: int = 0


class GapClassifier:
    """Hybrid SQL+LLM classifier for friction signals."""

    def __init__(self, conn: sqlite3.Connection, session_id: str | None = None) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.session_id = session_id

    def classify_all(self, project_id: str | None = None) -> dict[str, Any]:
        """Classify all unclassified, non-skipped signals.

        Returns summary dict: {classified: int, deferred: int, errors: list}
        """
        params: list[Any] = []
        project_clause = ""
        if project_id:
            project_clause = "AND project_id = ?"
            params.append(project_id)

        try:
            rows = self.conn.execute(
                f"""
                SELECT * FROM ds_friction_signals
                WHERE classified_as IS NULL
                  AND (classification_skipped IS NULL OR classification_skipped = 0)
                  {project_clause}
                ORDER BY created_at
                """,
                params,
            ).fetchall()
        except Exception as exc:
            return {"classified": 0, "deferred": 0, "errors": [str(exc)], "tokens_total": 0}

        summary: dict[str, Any] = {"classified": 0, "deferred": 0, "errors": [], "tokens_total": 0}

        for row in rows:
            try:
                result = self._classify_signal(dict(row))
                if result.classification is not None:
                    self._write_classification(row["signal_id"], result)
                    summary["classified"] += 1
                    summary["tokens_total"] += result.tokens_estimated
                else:
                    summary["deferred"] += 1
            except Exception as exc:
                msg = f"classify error for {row['signal_id']}: {exc}"
                logger.warning(msg)
                summary["errors"].append(msg)

        logger.info(
            "GapClassifier: classified=%d deferred=%d errors=%d tokens=%d",
            summary["classified"],
            summary["deferred"],
            len(summary["errors"]),
            summary["tokens_total"],
        )
        return summary

    def classify_signal(self, signal_id: str) -> ClassificationResult:
        """Classify a single signal by ID. Writes result to DB."""
        row = self.conn.execute(
            "SELECT * FROM ds_friction_signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Signal {signal_id!r} not found")
        result = self._classify_signal(dict(row))
        if result.classification is not None:
            self._write_classification(signal_id, result)
        return result

    # ── Classification logic ──────────────────────────────────────────────

    def _classify_signal(self, signal: dict[str, Any]) -> ClassificationResult:
        """Tier 1 first; Tier 2 if ambiguous; deferred if neither decides."""
        # Minimum data gate: require >=2 occurrences AND >=2 distinct sources.
        # Enforced before both Tier 1 and Tier 2 — a single occurrence is noise.
        context = json.loads(signal.get("context") or "{}")
        if int(context.get("occurrence_count", 0)) < 2 or int(context.get("distinct_scans", 0)) < 2:
            return ClassificationResult(
                classification=None,
                confidence=None,
                reason="Insufficient data (< 2 occurrences or < 2 sources) — deferred",
                tier="deferred",
            )

        tier1 = self._tier1_classify(signal)
        if tier1 is not None:
            return tier1

        tier2 = self._tier2_classify(signal)
        if tier2 is not None:
            return tier2

        return ClassificationResult(
            classification=None,
            confidence=None,
            reason="Ambiguous signal — deferred for future classification",
            tier="deferred",
        )

    # ── Tier 1: SQL heuristics ────────────────────────────────────────────

    def _tier1_classify(self, signal: dict[str, Any]) -> ClassificationResult | None:
        stype = signal.get("signal_type", "")
        skill_id = signal.get("skill_id") or "unknown"
        rule_id = signal.get("rule_id")
        context = json.loads(signal.get("context") or "{}")
        occurrence_count = int(context.get("occurrence_count", 0))
        distinct_scans = int(context.get("distinct_scans", 0))
        project_id = signal.get("project_id")

        if stype == "dismissed_finding":
            return self._heuristic_dismissed_finding(
                skill_id, rule_id, occurrence_count, distinct_scans, project_id
            )
        if stype == "partial_completion":
            return self._heuristic_partial_completion(
                skill_id, occurrence_count, distinct_scans, project_id
            )
        if stype == "pattern_gap":
            return self._heuristic_pattern_gap(signal, context)
        return None

    def _heuristic_dismissed_finding(
        self,
        skill_id: str,
        rule_id: str | None,
        occurrence_count: int,
        distinct_scans: int,
        project_id: str | None,
    ) -> ClassificationResult | None:
        # How many distinct rules are dismissed for this skill?
        distinct_rules = self.conn.execute(
            """
            SELECT COUNT(DISTINCT rule_id) AS cnt
            FROM ds_friction_signals
            WHERE signal_type = 'dismissed_finding'
              AND skill_id = ?
              AND (classification_skipped IS NULL OR classification_skipped = 0)
            """,
            (skill_id,),
        ).fetchone()["cnt"]

        # Rule dismissed many times across multiple sources → personalization
        if rule_id and occurrence_count >= DISMISSAL_HIGH_THRESHOLD:
            reason = (
                f"Rule {rule_id!r} dismissed {occurrence_count}× across "
                f"{distinct_scans} scans — consistent operator preference"
            )
            return ClassificationResult(
                classification="personalization",
                confidence=TIER1_CONFIDENCE,
                reason=reason,
                tier="tier1",
            )

        # Many distinct rules dismissed for same skill → capability (skill too noisy)
        if distinct_rules >= DISMISSAL_CROSS_RULE_THRESHOLD:
            reason = (
                f"{distinct_rules} distinct rules dismissed for {skill_id!r} — "
                f"skill fires too broadly across rule categories"
            )
            return ClassificationResult(
                classification="capability",
                confidence=TIER1_CONFIDENCE,
                reason=reason,
                tier="tier1",
            )

        return None

    def _heuristic_partial_completion(
        self,
        skill_id: str,
        occurrence_count: int,
        distinct_scans: int,
        project_id: str | None,
    ) -> ClassificationResult | None:
        if distinct_scans < PARTIAL_COMPLETION_THRESHOLD:
            return None

        # Cross-project ignored output → capability (not useful across contexts)
        distinct_projects = self.conn.execute(
            """
            SELECT COUNT(DISTINCT project_id) AS cnt
            FROM ds_friction_signals
            WHERE signal_type = 'partial_completion'
              AND skill_id = ?
              AND (classification_skipped IS NULL OR classification_skipped = 0)
            """,
            (skill_id,),
        ).fetchone()["cnt"]

        if distinct_projects > 1:
            reason = (
                f"{skill_id!r} output ignored across {distinct_projects} projects "
                f"({distinct_scans} scans) — skill doesn't produce actionable findings"
            )
            return ClassificationResult(
                classification="capability",
                confidence=TIER1_CONFIDENCE,
                reason=reason,
                tier="tier1",
            )

        # Single-project ignored output → onboarding (operator doesn't use the output)
        reason = (
            f"{skill_id!r} completed {distinct_scans} scans on this project "
            f"but findings were never acted on — operator may not know how to use output"
        )
        return ClassificationResult(
            classification="onboarding",
            confidence=0.75,  # below threshold; will escalate to Tier 2 for ambiguous cases
            reason=reason,
            tier="tier1",
        )

    def _heuristic_pattern_gap(
        self, signal: dict[str, Any], context: dict[str, Any]
    ) -> ClassificationResult | None:
        confidence_score = float(context.get("confidence_score", 1.0))
        co_occurrence_count = int(context.get("co_occurrence_count", 0))
        skill_id = signal.get("skill_id") or "unknown"

        if confidence_score < PATTERN_GAP_LOW_CONFIDENCE and co_occurrence_count >= 2:
            reason = (
                f"{skill_id!r} attempted {co_occurrence_count}× but pattern confidence "
                f"{confidence_score:.2f} never stabilized — skill missing a use case"
            )
            return ClassificationResult(
                classification="capability",
                confidence=TIER1_CONFIDENCE,
                reason=reason,
                tier="tier1",
            )
        return None

    # ── Tier 2: LLM via Claude Code subprocess ────────────────────────────

    def _tier2_classify(self, signal: dict[str, Any]) -> ClassificationResult | None:
        claude_bin = shutil.which("claude")
        if not claude_bin:
            logger.debug("claude CLI not found — Tier 2 skipped for signal %s", signal["signal_id"])
            return None

        prompt = self._build_prompt(signal)
        tokens_in = len(prompt) // 4  # rough estimate

        try:
            result = subprocess.run(
                [claude_bin, "-p", prompt],
                capture_output=True,
                text=True,
                timeout=CLASSIFIER_TIMEOUT,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            logger.warning("Tier 2 timed out for signal %s", signal["signal_id"])
            return None
        except Exception as exc:
            logger.warning("Tier 2 subprocess error for signal %s: %s", signal["signal_id"], exc)
            return None

        if result.returncode != 0:
            logger.warning(
                "claude returned exit %d for signal %s", result.returncode, signal["signal_id"]
            )
            return None

        parsed = self._parse_llm_response(result.stdout.strip())
        if parsed is None:
            return None

        tokens_out = len(result.stdout) // 4
        confidence = float(parsed.get("confidence", 0.0))

        # Clamp confidence to Tier 2 range
        confidence = min(TIER2_CONFIDENCE_MAX, max(TIER2_CONFIDENCE_MIN, confidence))

        if confidence < TIER2_CONFIDENCE_MIN:
            return None

        return ClassificationResult(
            classification=parsed.get("classification"),
            confidence=confidence,
            reason=parsed.get("reason", "LLM classification")[:300],
            tier="tier2",
            tokens_estimated=tokens_in + tokens_out,
        )

    def _build_prompt(self, signal: dict[str, Any]) -> str:
        context = json.loads(signal.get("context") or "{}")
        skill_id = signal.get("skill_id") or "unknown"

        # Get related signals for this skill
        related = self.conn.execute(
            """
            SELECT signal_type, rule_id, context
            FROM ds_friction_signals
            WHERE skill_id = ? AND signal_id != ?
              AND (classification_skipped IS NULL OR classification_skipped = 0)
            LIMIT 5
            """,
            (skill_id, signal["signal_id"]),
        ).fetchall()

        related_lines = []
        for r in related:
            rctx = json.loads(r["context"] or "{}")
            related_lines.append(
                f"  - {r['signal_type']} (rule: {r['rule_id'] or 'N/A'}, "
                f"occurrences: {rctx.get('occurrence_count', '?')})"
            )
        related_summary = "\n".join(related_lines) if related_lines else "  (none)"

        return CLASSIFIER_PROMPT_TEMPLATE.format(
            signal_type=signal.get("signal_type", "unknown"),
            skill_id=skill_id,
            rule_id=signal.get("rule_id") or "N/A",
            occurrence_count=context.get("occurrence_count", "unknown"),
            distinct_sources=context.get("distinct_scans", "unknown"),
            related_count=len(related),
            related_summary=related_summary,
        )

    @staticmethod
    def _parse_llm_response(raw: str) -> dict[str, Any] | None:
        """Parse JSON from LLM response. Returns None if unparseable."""
        if not raw:
            return None
        # Try to extract JSON if wrapped in prose
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(raw[start:end])
        except json.JSONDecodeError:
            return None
        classification = parsed.get("classification", "").lower().strip()
        if classification not in ("capability", "personalization", "onboarding"):
            return None
        return parsed

    # ── Write back ────────────────────────────────────────────────────────

    def _write_classification(self, signal_id: str, result: ClassificationResult) -> None:
        self.conn.execute(
            """
            UPDATE ds_friction_signals
            SET classified_as            = ?,
                classified_at            = datetime('now'),
                classification_confidence = ?,
                classification_reason    = ?
            WHERE signal_id = ?
            """,
            (
                result.classification,
                result.confidence,
                result.reason,
                signal_id,
            ),
        )
        self.conn.commit()

    # ── Read helpers ──────────────────────────────────────────────────────

    def get_pending_review(self, limit: int = 50) -> list[dict[str, Any]]:
        """Signals classified but not yet confirmed or skipped — for ds learn review."""
        rows = self.conn.execute(
            """
            SELECT * FROM ds_friction_signals
            WHERE classified_as IS NOT NULL
              AND (classification_skipped IS NULL OR classification_skipped = 0)
              AND extension_id IS NULL
            ORDER BY classification_confidence DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def confirm_signal(
        self,
        signal_id: str,
        *,
        extension_type_override: str | None = None,
    ) -> str:
        """Confirm a classification: creates ds_user_extensions row, links back.

        Returns the new extension_id.
        """
        row = self.conn.execute(
            "SELECT * FROM ds_friction_signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Signal {signal_id!r} not found")
        row = dict(row)

        classification = row.get("classified_as")
        if not classification:
            raise ValueError(f"Signal {signal_id!r} has no classification yet")

        # Map classification → default extension_type (19.4 will refine)
        type_map = {
            "capability": "gap_filler",
            "personalization": "option_override",
            "onboarding": "example",
        }
        ext_type = extension_type_override or type_map.get(classification, "gap_filler")

        extension_id = str(uuid.uuid4())
        compiled_from = json.dumps({"friction_signal_id": signal_id})

        self.conn.execute(
            """
            INSERT INTO ds_user_extensions (
                extension_id, skill_id, extension_type, content,
                source_signal, compiled_from, status, past_wo_count
            ) VALUES (?, ?, ?, '{}', 'friction', ?, 'proposed', 0)
            """,
            (extension_id, row.get("skill_id", "unknown"), ext_type, compiled_from),
        )

        self.conn.execute(
            "UPDATE ds_friction_signals SET extension_id = ? WHERE signal_id = ?",
            (extension_id, signal_id),
        )
        self.conn.commit()
        return extension_id

    def skip_signal(self, signal_id: str) -> None:
        """Skip a signal: will not resurface in ds learn review."""
        self.conn.execute(
            "UPDATE ds_friction_signals SET classification_skipped = 1 WHERE signal_id = ?",
            (signal_id,),
        )
        self.conn.commit()

    def defer_signal(self, signal_id: str) -> None:
        """Defer: reset classified_as to NULL so classifier re-evaluates next session."""
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
