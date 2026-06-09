# Security Mode — Changelog

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
