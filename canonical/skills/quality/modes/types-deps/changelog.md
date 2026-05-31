# Changelog — ds-quality:types-deps

## 1.2.0 — 2026-05-31

Rust support (Phase 4). All ecosystems complete: Python, TypeScript/JS, Go, Rust.
- typ-001 reframed for Rust (cargo build/test/check in CI)
- dep-001 ported: cargo audit (RustSec advisory DB)
- dep-002 ported: Cargo.lock + cargo tree --locked (library vs binary severity)
- 5 rules skip: typ-002 (no any type), typ-003 (no suppress mechanism), typ-004 (compiler enforces), dep-003 (no standard tooling), dep-007 (compiler enforces circular dep prevention)
- Stack detector: Rust detection added (Cargo.toml signal)

## 1.0.0 — 2026-05-30

Initial release (Phase 18.5.2).

**8 rules:**
- typ-001: Type-checker does not cover all production source dirs
- typ-002: Any used at non-boundary site (candidate/confirm)
- typ-003: # type: ignore without justification comment
- typ-004: Function missing return type annotation
- dep-001: CVE gate is non-blocking (severity from real pip-audit output)
- dep-002: Dependency lock not in sync or absent
- dep-003: No license gate configured
- dep-007: Runtime circular import between Python modules (candidate/confirm)

**Key calibrations baked in at release:**
- Project-agnostic: all config rules discover structure; no hardcoded dir names
- typ-002: auto-accept clears dict[str,Any] + boundary patterns at AST level
- dep-007: TYPE_CHECKING guards excluded at AST level before candidates generated
- dep-001: severity from real pip-audit output, not CI config alone
- dep-003: tool-pointing output; does not prescribe allowlist contents

**Boundaries established:**
- pr-security-scan:dependency-audit owns CVE findings + pinning + unused (dep-004/005/006 reserved)
- ops (18.6.3) owns the tooling changes that close the gaps this skill reports
- code-quality owns import ordering; types-deps owns runtime cycles
