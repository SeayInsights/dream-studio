# Review Mode — Changelog

## [2.1.1] — 2026-09-27

### Fixed
- `audit/SKILL.md` Step 5's operator-level `../suppressions.yml` check read as
  unconditional, but no `suppressions.yml` template has ever shipped anywhere in
  this repo (unlike the rule-level `suppressions` in `rules.yml`, which are real and
  populated). Reworded the step to say so plainly and to treat a missing file as a
  silent no-op rather than an error — consistent with this mode's own `jit-pending`
  status below (functional but not yet validated on a real codebase). Sibling audit
  skills (`code-health:code-quality`, `code-health:testing`, `data:database`) already
  phrase this same check as conditional ("if exists"); this mode's copy did not,
  and was the one actually caught referencing a nonexistent file. Not fabricating a
  template with no real backing.

## [2.1.0] — 2026-09-27

### Changed
- `quality:pr-security-scan` absorbed as a fourth sub-mode, `panel`, alongside `diff`/`audit`/
  `build` — a skill-fleet audit found it doing the same job as this skill (severity-tagged
  findings + ship/blocked verdict from a diff/PR) via a genuinely different mechanism (parallel
  OWASP/STRIDE analyst subagents, any-reject synthesis, rather than a single freeform pass or a
  fixed rule engine). Moved its `SKILL.md`, `modes.yml`, `analysts/*.yml` (14 files), and
  `gotchas.yml` from `canonical/skills/quality/modes/pr-security-scan/` to
  `panel/` under this mode; its own `config.yml`/`metadata.yml`/`changelog.md` were folded into
  this mode's own (this file, `../config.yml`, `../metadata.yml`) rather than duplicated.
- Quality's `SKILL.md`'s `secure:`/`security review:` redirect, which pointed at the unrelated
  `ds-fullstack:secure` pipeline-security-sweep mode, now points at `panel` with panel's own
  trigger keywords (`secure:`, `/secure`, `review architecture:`, `threat model:`).
- See `core-imports.md`'s "2026-09-27 — `panel` absorbed from `quality:pr-security-scan`" for
  the full rationale.

## [2.0.0] — 2026-09-26

### Changed
- `quality:security`'s `audit`/`build` rule engine (22 rules, `rules.yml`) merged into this
  mode as two new sub-modes alongside the existing diff-review methodology (moved to a new
  `diff/` sub-mode), as part of the pack-split campaign's security merge. This mode's own name
  changed from `security` to `review` (the mode it merged into); its rule engine's skill_id
  remains `"security"` in Python (dispatcher/DB/telemetry layer) — only its canonical/dist
  location and pack changed.
- `core-imports.md`'s prior "Do not merge these skills" note rewritten into a sub-mode
  boundary explanation (diff vs audit vs build), since the operator approved doing exactly that.
- Confidence thresholds, severity scales, and model tiers differ between diff (opus, ≥8/10,
  HIGH/MEDIUM) and audit/build (sonnet, 0.75, 5-tier critical..info) — kept separate per
  sub-mode rather than forced into one scale; see `config.yml`'s `diff:` section.

## [1.1.0] — 2026-08-02

### Added
- Note that credential scanning has an **automated baseline** (WO R4): the scheduled
  `security-baseline` workflow runs the native full-history secret scanner
  (`core/gates/secret_scan.py`); `audit` is for on-demand deep scans, not the baseline.

## [1.0.0] — 2026-05-27

### Added
- Initial implementation (phase 18.4.1 — first skill in quality skills layer)
- 22 rules from launch-readiness-checklist.md section 3 + regulatory-anchors.md sections J/L/N
- `audit` mode: --changed (default), --full-repo, --sample scope modes
- `build` mode: static-only pre-generation enforcement; no LLM call
- rules.yml schema with full fields: id, severity, category, source, regulatory_anchors (section + standard + anchor_ref), detection (type + static + llm with context_scope), triggers, remediation, suppressions (with expires), applies_to, action
- Static fallback to LLM when gitleaks/bandit/semgrep not installed — degradation logged in audit report (not silent)
- Per-rule `action.build_mode: null` for ops-only/architectural rules (sec-016, sec-022)
- File-hash + rule-id caching for LLM passes
- suppressions: per-rule path globs and inline comment patterns; operator-level suppressions.yml with expires field (default 90 days)
- Token budgets as roadmap estimates; Batch 7 will update with measured values

### Status
`jit-pending` — fully functional but not yet validated on a real codebase.
Token budgets are estimates pending 18.4.1 Batch 7 measurement.
First real audit (Batch 7) runs both --changed (recent Dream Studio PR) and --full-repo modes.
