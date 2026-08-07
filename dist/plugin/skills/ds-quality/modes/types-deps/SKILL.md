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

## Cross-Language Support (Phase 1: TypeScript)

**Types-deps Phase 1** extends all non-circular rules to TypeScript. dep-007 (circular imports) remains Python-only (Phase 2 adds TypeScript `import type` exclusion; Phase 3/4 adds Go/Rust).

**Universal rules** (typ-002, typ-004): Same concept, TypeScript syntax equivalents.
- typ-002: `any` (TypeScript) = `Any` (Python). Same LLM boundary classification.
- typ-004: Exported functions without `: ReturnType`. Same summary format.

**Portable rules** (typ-003, dep-002): Same detection logic, different patterns.
- typ-003: `// @ts-ignore` / `// @ts-expect-error` without justification. Skip on Go/Rust.
- dep-002: package-lock.json/yarn.lock/pnpm-lock.yaml. One lock covers all deps in JS/TS.

**Tool-analog rules** (typ-001, dep-001, dep-003): Same concept, different ecosystem tools.
- typ-001: tsconfig.json `include`/`exclude` instead of pyrightconfig.json.
- dep-001: npm audit/yarn audit instead of pip-audit.
- dep-003: license-checker instead of pip-licenses.

**Stack detection:** `detect_stack().test_framework` identifies the ecosystem. TypeScript detection via tsconfig.json / package.json. Results dispatch to TypeScript-specific detection steps.

**Proving ground:** DreamySuite (builds/dreamysuite) — TypeScript, tsconfig.json, package-lock.json, real CVE-potential dependencies, circular import risk.

### Go Support (Phase 3)

**Applies (5 rules):**
- **typ-001** reframed: "go build/test ./... in CI" instead of "type checker config"
- **typ-002**: `interface{}`/`any` with Go-specific auto-accept patterns (json.Unmarshal, map[string]interface{}, reflect.ValueOf, fmt variadic)
- **dep-001**: govulncheck in CI (golang.org/x/vuln — official tool)
- **dep-002**: go.sum presence + go mod verify + go mod tidy no-op
- **dep-003**: go-licenses/wwhrd/licensed in CI (not standard — presence check only)

**Skips (3 rules — compiler auto-satisfies):**
- **typ-004**: Go requires explicit return types syntactically. 100% auto-satisfied. Skip.
- **dep-007**: Go compiler rejects all circular imports. No escape hatch. Skip.
- **typ-003**: No type suppression comment syntax in Go. //nolint is a linter pragma. Skip.

**Tooling degradation:** If `go` not in PATH, govulncheck and go mod verify/tidy checks skip gracefully with informational note. Static file inspection (CI YAML, go.sum presence, .go file reads) works without Go installed.

**Proving ground:** github.com/cli/cli

### Rust Support (Phase 4)

**Applies (3 rules):** typ-001 (reframed), dep-001 (cargo audit), dep-002 (Cargo.lock + cargo tree --locked; library vs binary severity)

**Skips (5 rules):** typ-002 (no `any` type — language prevents), typ-003 (no suppress mechanism), typ-004 (compiler enforces), dep-003 (no standard tooling), dep-007 (Cargo rejects all circular crate deps)

**Proving ground:** ripgrep (github.com/BurntSushi/ripgrep)
