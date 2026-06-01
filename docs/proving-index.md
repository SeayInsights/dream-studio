# Proving Index — Quality Skills Cross-Ecosystem Coverage

Proves which skill × ecosystem combinations have been validated with real findings
on real external repositories. "Proven" means: a PR was opened with actual findings
pasted from running the audit on that repo, not just declaring support in rules.yml.

Last updated: 2026-06-01

---

## Security (ds-quality:security)

| Ecosystem | Proven? | Proving Repo | PR / Evidence | Date | Summary |
|-----------|---------|--------------|---------------|------|---------|
| Python | ✓ | dream-studio-clean | Baseline (internal) | 2026-04 | 22+ rules fire on real Python codebase; founding proving ground |
| TypeScript/JS | ✓ | DreamySuite | PR #127 description | 2026-05-31 | sec rules fire on TS files alongside testing rules |
| Go | DECLARED | — | rules.yml only | — | Declared in applies_to; no external run with pasted findings |
| Rust | DECLARED | — | rules.yml only | — | Declared in applies_to; no external run with pasted findings |
| Shell/YAML | DECLARED | — | rules.yml only | — | Declared; no dedicated external proving run |

---

## Code Quality (ds-quality:code-quality)

| Ecosystem | Proven? | Proving Repo | PR / Evidence | Date | Summary |
|-----------|---------|--------------|---------------|------|---------|
| Python | ✓ | dream-studio-clean | Baseline (internal) | 2026-04 | Core proving ground; all cq-* rules fire on Python |
| TypeScript/JS | ✓ | DreamySuite | PR #127 description | 2026-05-31 | LLM-fallback path fires for TS; cq rules produce real findings |
| Go | DECLARED | — | rules.yml only | — | Declared in applies_to; no external Go proving run |

---

## Testing (ds-quality:testing)

| Ecosystem | Proven? | Proving Repo | PR / Evidence | Date | Summary |
|-----------|---------|--------------|---------------|------|---------|
| Python | ✓ | dream-studio-clean | Baseline (internal) | 2026-04 | All tst-* rules fire on Python test suite |
| TypeScript (vitest) | ✓ | DreamySuite | PR #127 description | 2026-05-31 | 9 universal rules detect on 11 vitest test files; 0 false-fires; tst-011/015 candidate/confirm confirmed; coverage via coverage-final.json |

---

## Types & Dependencies (ds-quality:types-deps)

| Ecosystem | Proven? | Proving Repo | PR / Evidence | Date | Summary |
|-----------|---------|--------------|---------------|------|---------|
| Python | ✓ | dream-studio-clean | Baseline (internal) | 2026-04 | typ-002, dep-007 candidate/confirm proven |
| TypeScript (Phase 1) | ✓ | DreamySuite | PR #128+#129 description + PR #130 proving paste | 2026-05-31 | 7 non-circular rules proven; dep-001 fires (no CVE gate); dep-002 PASS; typ-003 PASS (0 @ts-ignore); typ-004 FIRE (~15-20 missing return types); typ-002 boundary-any auto-accepted; dep-007 PAIR (runtime cycle fires / import type silent) |
| Go | ✓ | github.com/cli/cli | PR #131 description | 2026-05-31 | 5 rules ported; govulncheck PASS (0 CVEs, 61 deps); go mod verify PASS; typ-001 PASS (go test in CI); typ-002 0 over-fires on boundary interface{}; 3 rules skip (compiler) |
| Rust | ✓ | ripgrep (BurntSushi) | PR #132+#133 description | 2026-05-31 | 3 rules ported; cargo audit PASS (0 CVEs, 61 deps); dep-001 FIRE (no cargo audit in ripgrep CI); dep-002 PASS; typ-001 PASS (cargo build in CI); 5 rules skip (compiler/no-any) |

---

## Database (ds-quality:database)

| Ecosystem | Proven? | Proving Repo | PR / Evidence | Date | Summary |
|-----------|---------|--------------|---------------|------|---------|
| SQLite (Python) | ✓ | dream-studio-clean | PR #134 description | 2026-06-01 | db-013 PASS (timeout=30.0); db-022 PASS (WAL mode); db-016 PASS (backup code exists) |
| Cloudflare D1 | ✓ | DreamySuite | PR #134 description | 2026-06-01 | db-004 FIRE (status column no CHECK on 0002_sites.sql:9); db-002 FIRE (FK no ON DELETE on 0040); db-001/007/021 PASS; db-016 auto-pass (D1 managed); db-022 FIRE (D1 eventual consistency awareness) |
| Postgres | PARTIAL | Fixture only | PR #134 description | 2026-06-01 | Postgres fixture proves db-022 skips on non-SQLite; no real Postgres repo run |
| MySQL | DECLARED | — | rules.yml only | — | Declared in applies_to; no proving run |
| MongoDB | DECLARED | — | rules.yml only | — | Declared in applies_to; no proving run |

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✓ | Proven — real findings pasted from real external repo in a PR |
| PARTIAL | Some rules proven (fixture/smoke), not full proving run |
| DECLARED | Declared in rules.yml applies_to but no external proving run done |
