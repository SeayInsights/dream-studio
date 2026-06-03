"""Capability compiler — Phase 19.4b.

LLM-as-summarizer compilation of capability extensions from observed event data.
The LLM reads verbatim canonical_events rows and summarizes the pattern — it does
NOT author content from a description.

SkillsBench defense (structural, same discipline as 19.4a):
  - Prompt contains raw event JSON rows from canonical_events (verbatim)
  - Prompt does NOT contain classification_reason or pre-summarized text
  - LLM output MUST cite real event_ids from the input
  - Every cited event_id is validated against canonical_events before write
  - Fake or missing IDs → compilation fails, signal deferred
  - Empty compiled_from → compilation fails

Single-candidate discipline:
  - Prompt forces ONE JSON output (no multi-option hedging)
  - If LLM cannot commit to one candidate → compilation fails, signal deferred

Boundary with 19.4a:
  - core/expansion/personalization.py is not modified
  - Same ds_user_extensions table, same compiled_from pattern
  - New: CapabilityCompilationResult includes tokens_estimated

Configuration: core/expansion/config.yml (capability_event_cap, session_cap, etc.)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).parent / "config.yml"


def _load_config() -> dict[str, Any]:
    try:
        import yaml

        return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_event_cap() -> int:
    cfg = _load_config()
    return int(cfg.get("capability", {}).get("event_cap", 50))


def _get_min_evidence() -> int:
    cfg = _load_config()
    return int(cfg.get("capability", {}).get("min_evidence_events", 2))


def _get_llm_timeout() -> int:
    env = os.environ.get("DREAM_STUDIO_CLASSIFIER_TIMEOUT")
    if env:
        return int(env)
    cfg = _load_config()
    return int(cfg.get("capability", {}).get("llm_timeout", 30))


# ── Prompt template (load-bearing — verbatim events only) ─────────────────

CAPABILITY_PROMPT_TEMPLATE = """You are analyzing raw event data from a developer AI tool to identify a missing skill capability.

RULES:
1. Respond with ONE JSON object only. No other text before or after.
2. Cite ONLY event_ids that appear verbatim in the INPUT DATA below.
3. Do NOT invent event_ids. Do NOT use IDs you infer or imagine.
4. If you cannot identify ONE confident capability, return: {{"extension_type": null, "reason": "insufficient evidence"}}

SKILL: {skill_id}

INPUT DATA ({event_count} events — these are the ONLY source you may cite):
{events_json}

Task: Identify the ONE most important capability this skill is missing, based only on the events above.
Look for patterns where Claude consistently does something that the skill does not detect or assist with.

Respond with exactly ONE of these JSON structures:

For a missing detection rule:
{{"extension_type": "gap_filler", "description": "one specific sentence from the event data only", "evidence_event_ids": ["<event_id from input>", ...], "confidence": 0.65}}

For a missing invocation mode:
{{"extension_type": "mode_addition", "description": "one specific sentence from the event data only", "evidence_event_ids": ["<event_id from input>", ...], "confidence": 0.65}}

For insufficient evidence:
{{"extension_type": null, "reason": "insufficient evidence"}}"""


# ── Result type ──────────────────────────────────────────────────────────


@dataclass
class CapabilityCompilationResult:
    success: bool
    extension_id: str | None = None
    content: dict[str, Any] | None = None
    event_ids_cited: list[str] = field(default_factory=list)
    tokens_estimated: int = 0
    error: str | None = None
    signal_deferred: bool = False


# ── Compiler ─────────────────────────────────────────────────────────────


class CapabilityCompiler:
    """Compiles capability extensions from canonical_events via LLM summarization.

    The LLM reads verbatim event rows and summarizes the pattern. It cannot
    author content — it can only describe what it observes in the provided data.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    # ── Public API ────────────────────────────────────────────────────────

    def compile_all(self) -> list[CapabilityCompilationResult]:
        """Compile all pending capability extensions."""
        proposals = self._find_proposals()
        results = []
        for proposal in proposals:
            result = self._compile_one(proposal)
            results.append(result)
            if result.success:
                logger.info(
                    "Compiled capability for extension %s (%d events cited, ~%d tokens)",
                    proposal["extension_id"],
                    len(result.event_ids_cited),
                    result.tokens_estimated,
                )
            else:
                logger.warning(
                    "Compilation failed for extension %s: %s",
                    proposal["extension_id"],
                    result.error,
                )
        return results

    def compile_one(self, extension_id: str) -> CapabilityCompilationResult:
        """Compile a single capability extension by ID."""
        proposals = self._find_proposals(extension_id=extension_id)
        if not proposals:
            return CapabilityCompilationResult(
                success=False,
                extension_id=extension_id,
                error=f"Extension {extension_id!r} not found or not eligible for capability compilation",
            )
        return self._compile_one(proposals[0])

    # ── Discovery ─────────────────────────────────────────────────────────

    def _find_proposals(self, extension_id: str | None = None) -> list[dict[str, Any]]:
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
                  AND fs.classified_as = 'capability'
                  AND (e.content IS NULL OR e.content = '' OR e.content = '{{}}')
                  {id_clause}
                ORDER BY e.created_at
                """,
                params,
            ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("Failed to find capability proposals: %s", exc)
            return []
        return [dict(r) for r in rows]

    # ── Compilation ───────────────────────────────────────────────────────

    def _compile_one(self, proposal: dict[str, Any]) -> CapabilityCompilationResult:
        extension_id = proposal["extension_id"]
        skill_id = proposal["skill_id"]
        signal_id = proposal["signal_id"]

        # Fetch verbatim event rows
        events = self._fetch_events(skill_id)
        if len(events) < _get_min_evidence():
            self._defer_signal(signal_id)
            return CapabilityCompilationResult(
                success=False,
                extension_id=extension_id,
                error=(
                    f"Insufficient event data: found {len(events)} events for "
                    f"skill={skill_id!r} (minimum: {_get_min_evidence()}). "
                    f"Signal returned to deferred state."
                ),
                signal_deferred=True,
            )

        # Build prompt from VERBATIM event data (no pre-summarization)
        prompt, known_event_ids = self._build_prompt(skill_id, events)
        tokens_in = len(prompt) // 4

        # Call LLM
        llm_output = self._call_llm(prompt)
        if llm_output is None:
            self._defer_signal(signal_id)
            return CapabilityCompilationResult(
                success=False,
                extension_id=extension_id,
                error="LLM call failed or timed out — signal deferred",
                signal_deferred=True,
            )

        tokens_out = len(llm_output) // 4
        tokens_estimated = tokens_in + tokens_out

        # Parse single-candidate response
        parsed = self._parse_llm_response(llm_output, known_event_ids=known_event_ids)
        if parsed is None:
            self._defer_signal(signal_id)
            return CapabilityCompilationResult(
                success=False,
                extension_id=extension_id,
                error=(
                    "LLM response invalid: could not extract single candidate with "
                    "valid evidence_event_ids — signal deferred"
                ),
                tokens_estimated=tokens_estimated,
                signal_deferred=True,
            )

        if parsed.get("extension_type") is None:
            self._defer_signal(signal_id)
            return CapabilityCompilationResult(
                success=False,
                extension_id=extension_id,
                error=f"LLM reported insufficient evidence: {parsed.get('reason', 'no reason given')}",
                tokens_estimated=tokens_estimated,
                signal_deferred=True,
            )

        cited_ids = parsed.get("evidence_event_ids", [])

        # Validate compiled_from: every cited ID must resolve in canonical_events
        missing = self._validate_compiled_from(cited_ids)
        if missing:
            self._defer_signal(signal_id)
            return CapabilityCompilationResult(
                success=False,
                extension_id=extension_id,
                error=(
                    f"SkillsBench defense: {len(missing)} cited event_id(s) do not exist "
                    f"in canonical_events: {missing[:3]}. Signal deferred."
                ),
                tokens_estimated=tokens_estimated,
                signal_deferred=True,
            )

        if len(cited_ids) < _get_min_evidence():
            self._defer_signal(signal_id)
            return CapabilityCompilationResult(
                success=False,
                extension_id=extension_id,
                error=(
                    f"Empty or insufficient compiled_from: cited {len(cited_ids)} event_id(s), "
                    f"minimum {_get_min_evidence()} required. Signal deferred."
                ),
                tokens_estimated=tokens_estimated,
                signal_deferred=True,
            )

        # Build final content JSON
        content = {
            "extension_type": parsed["extension_type"],
            "skill_id": skill_id,
            "description": parsed.get("description", ""),
            "compiled_examples": [{"event_id": eid, "from_compilation": True} for eid in cited_ids],
            "compiled_from": cited_ids,
            "confidence": float(parsed.get("confidence", 0.65)),
        }

        # Update compiled_from JSON on the extension row
        existing_compiled = json.loads(proposal.get("compiled_from") or "{}")
        existing_compiled["event_ids"] = cited_ids
        new_compiled_from = json.dumps(existing_compiled)

        try:
            self.conn.execute(
                """
                UPDATE ds_user_extensions
                SET content = ?, compiled_from = ?, extension_type = ?
                WHERE extension_id = ?
                """,
                (
                    json.dumps(content),
                    new_compiled_from,
                    parsed["extension_type"],
                    extension_id,
                ),
            )
            self.conn.commit()
        except Exception as exc:
            return CapabilityCompilationResult(
                success=False,
                extension_id=extension_id,
                error=f"DB write failed: {exc}",
                tokens_estimated=tokens_estimated,
            )

        return CapabilityCompilationResult(
            success=True,
            extension_id=extension_id,
            content=content,
            event_ids_cited=cited_ids,
            tokens_estimated=tokens_estimated,
        )

    # ── Event loading ─────────────────────────────────────────────────────

    def _fetch_events(self, skill_id: str) -> list[dict[str, Any]]:
        """Fetch canonical_events related to a skill (verbatim rows)."""
        event_cap = _get_event_cap()
        try:
            rows = self.conn.execute(
                """
                SELECT event_id, event_type, created_at, payload, trace
                FROM canonical_events
                WHERE json_extract(trace, '$.skill_specifier') = ?
                   OR (
                       event_type IN ('skill.invoked', 'tool.execution.completed',
                                      'task.completed', 'work_order.closed')
                       AND json_extract(trace, '$.project_id') IN (
                           SELECT DISTINCT json_extract(trace, '$.project_id')
                           FROM canonical_events
                           WHERE json_extract(trace, '$.skill_specifier') = ?
                       )
                   )
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (skill_id, skill_id, event_cap),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(r) for r in rows]

    # ── Prompt building ───────────────────────────────────────────────────

    def _build_prompt(self, skill_id: str, events: list[dict[str, Any]]) -> tuple[str, set[str]]:
        """Build the LLM prompt from VERBATIM event rows.

        Returns (prompt, set_of_known_event_ids).

        CRITICAL: This prompt must NOT contain classification_reason or any
        pre-summarized text. Only raw event data.
        """
        known_ids: set[str] = set()
        event_lines: list[str] = []

        for event in events:
            eid = event.get("event_id", "")
            known_ids.add(eid)
            # Include verbatim event data (truncated for safety)
            event_repr = json.dumps(
                {
                    "event_id": eid,
                    "event_type": event.get("event_type"),
                    "created_at": event.get("created_at"),
                    "trace": json.loads(event.get("trace") or "{}"),
                },
                default=str,
            )
            event_lines.append(event_repr)

        events_json = "\n".join(event_lines)
        prompt = CAPABILITY_PROMPT_TEMPLATE.format(
            skill_id=skill_id,
            event_count=len(events),
            events_json=events_json,
        )
        return prompt, known_ids

    # ── LLM call ──────────────────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> str | None:
        """Call Claude Code subprocess. Returns raw response or None on failure."""
        claude_bin = shutil.which("claude")
        if not claude_bin:
            logger.debug("claude CLI not found — capability compilation deferred")
            return None

        try:
            result = subprocess.run(
                [claude_bin, "-p", prompt],
                capture_output=True,
                text=True,
                timeout=_get_llm_timeout(),
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            logger.warning("LLM timed out for capability compilation")
            return None
        except Exception as exc:
            logger.warning("LLM subprocess error: %s", exc)
            return None

        if result.returncode != 0:
            logger.warning(
                "claude returned exit %d: %s",
                result.returncode,
                (result.stderr or "")[:200],
            )
            return None

        return result.stdout.strip()

    # ── Parsing ───────────────────────────────────────────────────────────

    @staticmethod
    def _parse_llm_response(
        raw: str, known_event_ids: set[str] | None = None
    ) -> dict[str, Any] | None:
        """Parse single-candidate JSON from LLM response.

        Enforces single-candidate discipline: rejects lists, multi-option
        responses, and responses where cited IDs are not in known_event_ids.

        Returns parsed dict or None if invalid.
        """
        if not raw:
            return None

        # Extract JSON object from possible surrounding text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return None

        try:
            parsed = json.loads(raw[start:end])
        except json.JSONDecodeError:
            return None

        # Allow null-type for "insufficient evidence" response
        ext_type = parsed.get("extension_type")
        if ext_type is None:
            return parsed  # valid "insufficient evidence" response

        # Validate extension_type
        if ext_type not in ("gap_filler", "mode_addition"):
            return None

        # Validate evidence_event_ids exists and is a list
        cited = parsed.get("evidence_event_ids")
        if not isinstance(cited, list) or len(cited) == 0:
            return None

        # If known_event_ids provided, reject any cited IDs not in the input
        # (prevents phantom grounding: LLM citing events it wasn't shown)
        if known_event_ids is not None:
            for eid in cited:
                if eid not in known_event_ids:
                    logger.warning(
                        "LLM cited event_id %r not in input events (phantom grounding)", eid
                    )
                    return None

        # Require description
        if not parsed.get("description", "").strip():
            return None

        return parsed

    # ── Validation ────────────────────────────────────────────────────────

    def _validate_compiled_from(self, event_ids: list[str]) -> list[str]:
        """Validate that every event_id resolves in canonical_events.

        Returns list of missing IDs (empty = all valid).
        This is the structural SkillsBench defense.
        """
        if not event_ids:
            return ["empty: no event_ids cited"]
        missing = []
        for eid in event_ids:
            try:
                row = self.conn.execute(
                    "SELECT event_id FROM canonical_events WHERE event_id = ?", (eid,)
                ).fetchone()
            except sqlite3.OperationalError:
                missing.append(eid)
                continue
            if row is None:
                missing.append(eid)
        return missing

    # ── Signal deferral ───────────────────────────────────────────────────

    def _defer_signal(self, signal_id: str) -> None:
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
        """Pending capability extensions without compiled content."""
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
                  AND fs.classified_as = 'capability'
                  AND (e.content IS NULL OR e.content = '' OR e.content = '{}')
                ORDER BY e.created_at
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(r) for r in rows]
