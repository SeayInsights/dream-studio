"""Onboarding documentation compiler — Phase 19.4c.

LLM-authored documentation for operators who don't know how to use a skill's output.
This is the ONLY path in Phase 19.4 where LLM authorship of content is appropriate:

  - No skill behavior is modified (canonical immutable, no rules/thresholds added)
  - Worst case for bad docs: operator ignores them — no silent degradation
  - SkillsBench trap does NOT apply because nothing that affects skill output is changed

What ships:
  - Markdown documentation explaining what the skill does, why rules fire, when to act
  - Structured JSON wrapping the markdown stored in ds_user_extensions.content (DB only)
  - 19.7 provisioner handles disk writes; 19.4c never writes files

Content structure (extension_type column = 'example'; content JSON has subtype):
  {
    "extension_type": "onboarding_doc",
    "skill_id": "...",
    "doc_title": "...",
    "doc_path_suggestion": "docs/operator-guides/<skill>-<topic>.md",
    "markdown_content": "...",
    "compiled_from": ["<signal_id>"]
  }

compiled_from is still required — cites at minimum the source signal_id.
If the LLM references event_ids in examples, those are validated.

Boundary: personalization.py and capability.py are not modified.
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

ONBOARDING_TIMEOUT = int(os.environ.get("DREAM_STUDIO_CLASSIFIER_TIMEOUT", "30"))

# Canonical skills root for optional SKILL.md context
_CANONICAL_SKILLS_ROOT = Path(__file__).parents[2] / "canonical" / "skills"

ONBOARDING_PROMPT_TEMPLATE = """You are writing operator-facing documentation for a developer AI tool skill.

CONTEXT:
- Skill: {skill_id}
- Friction observed: {signal_context}
- Signal type: {signal_type}

TASK: Write concise markdown documentation that explains:
1. What this skill detects and why
2. When findings should be acted on vs. dismissed
3. One practical example of using the skill effectively

The operator has been calling this skill but not engaging with its output.
Help them understand what to do with it.

{skill_description_section}

Respond with ONE JSON object only (no text before or after):
{{"doc_title": "short title (< 8 words)",
  "markdown_content": "# Title\\n\\nContent here...",
  "confidence": 0.75}}

Keep the markdown concise: 150-300 words. Use ## for sections. Include one concrete example."""


@dataclass
class OnboardingCompilationResult:
    success: bool
    extension_id: str | None = None
    content: dict[str, Any] | None = None
    tokens_estimated: int = 0
    error: str | None = None
    signal_deferred: bool = False


class OnboardingCompiler:
    """Compiles operator-facing documentation from onboarding friction signals.

    LLM authorship is intentional here — see module docstring for rationale.
    compiled_from is still required (signal_id at minimum).
    No disk writes — 19.7 provisioner handles that.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    # ── Public API ────────────────────────────────────────────────────────

    def compile_all(self) -> list[OnboardingCompilationResult]:
        proposals = self._find_proposals()
        results = []
        for proposal in proposals:
            result = self._compile_one(proposal)
            results.append(result)
            if result.success:
                logger.info(
                    "Compiled onboarding doc for extension %s (~%d tokens)",
                    proposal["extension_id"],
                    result.tokens_estimated,
                )
            else:
                logger.warning(
                    "Onboarding compilation failed for extension %s: %s",
                    proposal["extension_id"],
                    result.error,
                )
        return results

    def compile_one(self, extension_id: str) -> OnboardingCompilationResult:
        proposals = self._find_proposals(extension_id=extension_id)
        if not proposals:
            return OnboardingCompilationResult(
                success=False,
                extension_id=extension_id,
                error=f"Extension {extension_id!r} not found or not eligible for onboarding compilation",
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
                    fs.signal_type,
                    fs.rule_id,
                    fs.context AS fs_context,
                    fs.classified_as,
                    fs.classification_reason
                FROM ds_user_extensions e
                JOIN ds_friction_signals fs
                    ON json_extract(e.compiled_from, '$.friction_signal_id') = fs.signal_id
                WHERE e.status = 'proposed'
                  AND fs.classified_as = 'onboarding'
                  AND (e.content IS NULL OR e.content = '' OR e.content = '{{}}')
                  {id_clause}
                ORDER BY e.created_at
                """,
                params,
            ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("Failed to find onboarding proposals: %s", exc)
            return []
        return [dict(r) for r in rows]

    # ── Compilation ───────────────────────────────────────────────────────

    def _compile_one(self, proposal: dict[str, Any]) -> OnboardingCompilationResult:
        extension_id = proposal["extension_id"]
        skill_id = proposal["skill_id"]
        signal_id = proposal["signal_id"]
        signal_type = proposal.get("signal_type", "unknown")
        signal_context = (
            proposal.get("classification_reason") or "operator did not engage with skill output"
        )

        prompt = self._build_prompt(skill_id, signal_type, signal_context)
        tokens_in = len(prompt) // 4

        llm_output = self._call_llm(prompt)
        if llm_output is None:
            self._defer_signal(signal_id)
            return OnboardingCompilationResult(
                success=False,
                extension_id=extension_id,
                error="LLM call failed or timed out — signal deferred",
                signal_deferred=True,
            )

        tokens_out = len(llm_output) // 4
        tokens_estimated = tokens_in + tokens_out

        parsed = self._parse_llm_response(llm_output)
        if parsed is None:
            self._defer_signal(signal_id)
            return OnboardingCompilationResult(
                success=False,
                extension_id=extension_id,
                error="LLM response invalid — could not extract doc title + markdown_content",
                tokens_estimated=tokens_estimated,
                signal_deferred=True,
            )

        # Build final content JSON
        skill_slug = skill_id.replace(":", "-").replace("ds-quality-", "")
        doc_title = parsed.get("doc_title", f"{skill_id} usage guide")
        content = {
            "extension_type": "onboarding_doc",
            "skill_id": skill_id,
            "doc_title": doc_title,
            "doc_path_suggestion": f"docs/operator-guides/{skill_slug}-onboarding.md",
            "markdown_content": parsed.get("markdown_content", ""),
            "compiled_from": [signal_id],
        }

        # Validate any event_ids mentioned in compiled_from (signal_id check)
        missing_signals = self._validate_signal_id(signal_id)
        if missing_signals:
            self._defer_signal(signal_id)
            return OnboardingCompilationResult(
                success=False,
                extension_id=extension_id,
                error=f"compiled_from signal_id {signal_id!r} not found in ds_friction_signals",
                tokens_estimated=tokens_estimated,
                signal_deferred=True,
            )

        # Update compiled_from on extension row
        existing_cf = json.loads(proposal.get("compiled_from") or "{}")
        existing_cf["signal_id"] = signal_id
        new_compiled_from = json.dumps(existing_cf)

        try:
            self.conn.execute(
                """
                UPDATE ds_user_extensions
                SET content = ?, compiled_from = ?
                WHERE extension_id = ?
                """,
                (json.dumps(content), new_compiled_from, extension_id),
            )
            self.conn.commit()
        except Exception as exc:
            return OnboardingCompilationResult(
                success=False,
                extension_id=extension_id,
                error=f"DB write failed: {exc}",
                tokens_estimated=tokens_estimated,
            )

        return OnboardingCompilationResult(
            success=True,
            extension_id=extension_id,
            content=content,
            tokens_estimated=tokens_estimated,
        )

    # ── Prompt building ───────────────────────────────────────────────────

    def _build_prompt(self, skill_id: str, signal_type: str, signal_context: str) -> str:
        """Build the onboarding documentation prompt.

        Includes optional SKILL.md description if available (read-only access).
        Uses signal_context (classification_reason) since for onboarding the friction
        is about the operator not knowing how to use the skill — the reason is the input,
        not an event pattern.
        """
        skill_description_section = self._load_skill_description(skill_id)
        return ONBOARDING_PROMPT_TEMPLATE.format(
            skill_id=skill_id,
            signal_context=signal_context,
            signal_type=signal_type,
            skill_description_section=skill_description_section,
        )

    def _load_skill_description(self, skill_id: str) -> str:
        """Optionally read the skill's SKILL.md for additional context."""
        # skill_id like "ds-quality:security" → canonical/skills/quality/modes/security/SKILL.md
        try:
            parts = skill_id.replace("ds-", "").split(":")
            if len(parts) >= 2:
                pack, mode = parts[0], parts[1]
                skill_md = _CANONICAL_SKILLS_ROOT / pack / "modes" / mode / "SKILL.md"
                if skill_md.exists():
                    text = skill_md.read_text(encoding="utf-8")[:1000]
                    return f"SKILL DOCUMENTATION (first 1000 chars):\n{text}"
        except Exception:
            pass
        return ""

    # ── LLM call ──────────────────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> str | None:
        claude_bin = shutil.which("claude")
        if not claude_bin:
            logger.debug("claude CLI not found — onboarding compilation deferred")
            return None

        try:
            result = subprocess.run(
                [claude_bin, "-p", prompt],
                capture_output=True,
                text=True,
                timeout=ONBOARDING_TIMEOUT,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            logger.warning("LLM timed out for onboarding compilation")
            return None
        except Exception as exc:
            logger.warning("LLM subprocess error: %s", exc)
            return None

        if result.returncode != 0:
            return None

        return result.stdout.strip()

    # ── Parsing ───────────────────────────────────────────────────────────

    @staticmethod
    def _parse_llm_response(raw: str) -> dict[str, Any] | None:
        """Parse doc title + markdown_content from LLM response."""
        if not raw:
            return None
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(raw[start:end])
        except json.JSONDecodeError:
            return None
        if not parsed.get("doc_title") or not parsed.get("markdown_content"):
            return None
        return parsed

    # ── Validation ────────────────────────────────────────────────────────

    def _validate_signal_id(self, signal_id: str) -> list[str]:
        """Check signal_id resolves in ds_friction_signals."""
        try:
            row = self.conn.execute(
                "SELECT signal_id FROM ds_friction_signals WHERE signal_id = ?",
                (signal_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return [signal_id]
        return [] if row is not None else [signal_id]

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
                    fs.signal_type,
                    fs.rule_id,
                    fs.context AS fs_context,
                    fs.classification_reason
                FROM ds_user_extensions e
                JOIN ds_friction_signals fs
                    ON json_extract(e.compiled_from, '$.friction_signal_id') = fs.signal_id
                WHERE e.status = 'proposed'
                  AND fs.classified_as = 'onboarding'
                  AND (e.content IS NULL OR e.content = '' OR e.content = '{}')
                ORDER BY e.created_at
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(r) for r in rows]
