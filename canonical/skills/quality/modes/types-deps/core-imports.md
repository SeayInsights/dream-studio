# Types-Deps Mode — Core Imports

## Imported Modules

### ds-core/git.md
**Usage:** Scope determination for `--changed` mode.
**Pattern:** `git diff --name-only main...HEAD`
**Impact if changed:** --changed scope breaks; fall back to --full-repo.

### canonical/skills/quality/references/types-deps-best-practices.md
**Usage:** Authoritative source for all 8 rules (Section M-types + Section K).
**Impact if changed:** `source.item` text in rules.yml may need updating.

### pyproject.toml (project file)
**Usage:** Source dir discovery (typ-001), type checker config discovery (typ-001),
dependency declaration (dep-001, dep-002, dep-003).
**Impact if changed:** Source dir list updates; type checker coverage may change.

### pyrightconfig.json (if present)
**Usage:** typ-001 — reads "include" array to determine type checker coverage.
**Impact if changed:** typ-001 finding changes when checker scope expands.

### .github/workflows/*.yml (CI config)
**Usage:** dep-001 — scans for CVE tool steps and continue-on-error flags.
**Impact if changed:** dep-001 finding updates when CI is modified.

---

## Static Tools

### Python ast stdlib (ALWAYS available)
**Usage:** typ-002 (Any boundary detection + auto-accept), typ-003 (type:ignore grep),
typ-004 (missing return annotation), dep-007 (import graph + cycle detection with
TYPE_CHECKING exclusion).
**Notes:** All AST analysis runs in-process — fast, no subprocess, no Windows OOM risk.

### pip-audit (INSTALLED in requirements-dev.txt, >= 2.7)
**Usage:** dep-001 — run actual CVE scan to set severity from real output.
**Fallback:** If pip-audit not available or requirements file missing: report enforcement
gap at high severity without CVE count.

### No additional tools installed
- pyright: config-inspection only (read pyrightconfig.json), not invoked as process
- pip-licenses: NOT installed; dep-003 reports its ABSENCE as the finding
- importlab / pydeps: NOT installed; dep-007 uses stdlib ast only

---

## LLM Confirmation Rules

Rules requiring LLM confirm pass: **typ-002**, **dep-007**.

| Rule | What AST clears | What LLM sees |
|------|----------------|---------------|
| typ-002 | dict[str,Any], boundary param names, boundary fn prefixes | Unguarded Any at potentially-interior sites |
| dep-007 | TYPE_CHECKING guards, function-level imports | Unguarded module-level cycles |

**No pre-committed demotion criterion** (unlike tst-002/tst-008) — these rules have
binary candidates, not judgment-dependent findings. The LLM confirmation is a classification
step, not a semantic call.

---

## Skill Boundary Partners

### ds-quality:pr-security-scan:dependency-audit (complementary, reserves dep-004/005/006)
- security-scan owns: CVE findings (vulnerabilities), version pinning on PR diffs, unused packages
- types-deps owns: CVE gate enforcement status (dep-001), dev lock (dep-002), license gate (dep-003)
- dep-004/005/006 are deliberately reserved — not implemented here — for security-scan's territory.
- Reports cross-reference when both may fire on the same PR.

### ds-quality:code-quality (complementary)
- code-quality owns: import ordering (Section D: std→third-party→internal→relative)
- types-deps owns: runtime circular imports (dep-007); type annotation discipline
- Cross-reference: code-quality M-partial ↔ typ-001 (checker existence vs. checker scope)

### ds-quality:ops (18.6.3, future)
- types-deps REPORTS gaps; ops CLOSES them (expands pyright config, makes pip-audit blocking,
  adds license CI step). Neither skill duplicates the other's role.

---

## Maintenance Notes

**When pyright scope changes in this project:**
1. Re-run typ-001 to update the coverage gap finding.
2. After pyright covers all source dirs, typ-001 passes — no rule migration needed.

**When dep-001 resolves (pip-audit made blocking):**
1. Re-run dep-001 to confirm the finding clears.
2. The rule stays active — it will re-fire if CI config reverts to continue-on-error.

**When 18.6.3 (ops) ships:**
- Review whether typ-001 / dep-001 config recommendations should cross-reference ops:fix mode.

**When first audit completes:**
- Update metadata.yml quality_metrics with measured token usage and execution time.
- Check typ-002 false-positive rate: if many confirmations return benign_boundary,
  expand auto_accept_patterns in config.yml with project-specific boundary patterns.
- Check dep-007 false-positive rate: if LLM is confirming many broken_at_runtime,
  update the AST exclusion logic.
