# ds-quality:types-deps — Type Safety and Dependency Health

## Mode dispatch

0. **Progressive disclosure check:** Apply the portable skill contract before dispatching.

1. Parse the mode from the argument (first word).
2. If no mode given, default to `audit`.
3. Read `modes/<mode>/SKILL.md` completely before executing.
4. If `gotchas.yml` exists in this directory, read it before executing.
5. Follow the mode's instructions exactly.

| Mode | File | Keywords |
|------|------|---------|
| audit | audit/SKILL.md | audit:, types audit:, deps audit:, dependency audit:, type safety: |
| build | build/SKILL.md | build:types-deps, generate types:, add annotations:, fix imports: |

## What This Skill Does

`audit` — retrospective type-safety and dependency-health scan. Four type rules (annotation
coverage, Any discipline, type:ignore hygiene, type-checker scope) + four dependency rules
(CVE gate enforcement, lock file completeness, license gate presence, circular imports).
Scope variants: `--changed` (default), `--full-repo`, `--sample`. Config/project rules
(typ-001, dep-001, dep-002, dep-003) always run regardless of scope — they are project-level
findings, not per-file findings. Code rules (typ-002, typ-003, typ-004, dep-007) respect scope.

`build` — guidance for adding type annotations to existing code and maintaining dependency
hygiene. Runs static-only checks first, then provides structured guidance. Does NOT modify
CI config, lock files, or type-checker configuration.

## Source Authority

Rules defined in `rules.yml`. Source standards in
`canonical/skills/quality/references/types-deps-best-practices.md`.

## Project-agnostic constraint (critical)

**This skill runs in the user's projects, not only Dream Studio.** All config rules (typ-001,
dep-001, dep-002, dep-003) discover the current project's structure rather than assuming any
specific directory layout. They do NOT hardcode `core/`, `interfaces/`, `spool/`, or any
Dream Studio-specific names. Source dirs are discovered from pyproject.toml or root-level
package scan. Type checker coverage is discovered from pyrightconfig.json / mypy.ini /
pyproject.toml. The enforcement gap finding reports *this project's* actual coverage gap.

## Skill Boundary

**types-deps owns:**
- Type checker enforcement scope (does it cover all source?)
- `Any` discipline (boundary vs. interior leakage)
- `# type: ignore` hygiene
- Annotation coverage on public functions
- CVE gate enforcement status (blocking vs. advisory)
- Dependency lock completeness (production + dev)
- License gate presence
- Python runtime circular imports

**Code-quality (18.4.3) owns:**
- Import ordering (Section D: std → third-party → internal → relative)
- Code structure concerns (one-concept-per-file, file size, etc.)
- Whether a type checker is installed at all (M-partial: "type checker automated")

**pr-security-scan:dependency-audit owns:**
- Actual CVE findings (the specific vulnerabilities discovered in deps)
- Version pinning correctness on PR diffs
- Unused packages on PR diffs

**ds-security owns:**
- Client-facing security scanning (Semgrep, SARIF ingestion, client repos)

**ops (18.6.3, future) owns:**
- The tooling changes that close gaps this skill reports:
  - Expanding pyrightconfig.json to cover more source dirs
  - Making pip-audit blocking in CI
  - Adding license gate step to CI
  - Configuring `--strict` mode

**Cross-references:**
- `typ-001` (scope gap) ↔ `cq-M-partial` (type checker exists): CQ fires if no checker;
  types-deps fires if checker exists but doesn't cover all source.
- `dep-007` (circular imports) ↔ `cq-D-import-order` (ordering): ordering is code-quality;
  runtime cycles are types-deps.
- `dep-001` (CVE gate) ↔ `pr-security-scan:dependency-audit` (CVE findings): security-scan
  owns the vulnerabilities; types-deps owns whether the gate actually blocks them.
