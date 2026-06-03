# Proving Index — Quality Skills Cross-Ecosystem Coverage

Proves which skill × ecosystem combinations have been validated with real findings
on real external repositories. "Proven" means: a PR was opened with actual findings
pasted from running the audit on that repo, not just declaring support in rules.yml.

Last updated: 2026-06-03

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

## Backend-API (ds-quality:backend-api)

| Ecosystem | Proven? | Proving Repo | PR / Evidence | Date | Summary |
|-----------|---------|--------------|---------------|------|---------|
| Python (FastAPI) | ✓ | dream-studio-clean + fastapi-template | PR #142 description | 2026-06-01 | 12 rules; api-001 FIRE (no Pydantic on /api/v1/ml/recommend); api-003 FIRE (no rate limiting); api-009 PASS (JWT in projections/api/); api-007 FIRE (password-recovery/{email} exposes user existence on 404) |
| Node.js (Express) | ✓ | hagopj13/node-express-boilerplate | PR #142 description | 2026-06-01 | api-001 FIRE (paginate query params not validated); api-002 FIRE (CORS *); api-003 FIRE (no rate limit on /auth/login); api-007 PASS (uniform error handler) |
| Go (Gin/Chi/Echo) | DECLARED | — | rules.yml only | — | Declared in applies_to; no external Go proving run |
| Rust (Axum/Actix) | DECLARED | — | rules.yml only | — | Declared in applies_to; no external Rust proving run |

---

## Frontend-UX (ds-quality:frontend-ux)

| Ecosystem | Proven? | Proving Repo | PR / Evidence | Date | Summary |
|-----------|---------|--------------|---------------|------|---------|
| React/Next.js | ✓ | DreamySuite | PR #144 description | 2026-06-02 | ux-006 FIRE: StoryTimelineBlock.tsx:90 key={i} index as key; ux-007 FIRE: RegistryCards.tsx (537 LOC), ScheduleTimeline.tsx (542 LOC), ContentCardBlock.tsx (347 LOC); ux-010 FIRE: HomeHeroBlock.tsx hardcoded strings; ux-002 PASS: LoginForm.tsx correct htmlFor/id matching |
| Vue/Svelte/Angular | DECLARED | — | rules.yml Phase 2 | — | Phase 2 scope; 10 universal rules apply; hooks rules skip |

---

## Architecture (ds-quality:architecture)

| Ecosystem | Proven? | Proving Repo | PR / Evidence | Date | Summary |
|-----------|---------|--------------|---------------|------|---------|
| Python (backend) | ✓ | dream-studio-clean | PR #145 description | 2026-06-02 | arch-001 FIRE: core/projections/framework.py ProjectionEngine (22 methods, >400 LOC); arch-004 FIRE ×2: core/design_briefs/mutations.py:37 + core/health/status.py:22 core imports interfaces; arch-009 FIRE: projections/api/routes/shared_intelligence.py (31 import targets) |
| TypeScript/Next.js (frontend) | ✓ | DreamySuite | PR #145 description | 2026-06-02 | arch-001 FIRE (frontend threshold 300): ContentCardBlock.tsx (372L), RegistryBlock.tsx (323L), VenueMapBlock.tsx (312L) — all SILENT at backend threshold (500) → calibration proven; arch-003 FIRE: editor-v2/inspector/editors/ (depth 8 > threshold 3); arch-002 FIRE: RegistryBlock.tsx (9 external imports > frontend threshold 8) |
| Go | DECLARED | — | rules.yml only | — | Declared in applies_to; no Go proving run |
| Rust | DECLARED | — | rules.yml only | — | Declared in applies_to; no Rust proving run |

---

## Ops (ds-quality:ops)

| Ecosystem | Proven? | Proving Repo | PR / Evidence | Date | Summary |
|-----------|---------|--------------|---------------|------|---------|
| Python (service) | ✓ | dream-studio-clean | PR #146 description | 2026-06-02 | ops-001 FIRE: print() in main.py:173, spool/ingestor.py, dispatcher.py; ops-007 FIRE: config validated lazily in projections/config/settings.py; ops-011 FIRE: urllib fallback path in dispatcher.py lacks timeout; ops-012 FIRE: single-stage Dockerfile (no multi-stage); ops-005/006/008/010/013 PASS; ops-013 SILENT (no k8s manifests) |
| TypeScript/Node.js | DECLARED | — | rules.yml only | — | Declared in applies_to; no external TS proving run |
| Go | DECLARED | — | rules.yml only | — | Declared in applies_to; no Go proving run |

---

## Database Compliance (ds-quality:database-compliance)

| Ecosystem | Proven? | Proving Repo | PR / Evidence | Date | Summary |
|-----------|---------|--------------|---------------|------|---------|
| TypeScript/D1 (Next.js) | ✓ | DreamySuite | PR #149 description | 2026-06-03 | dbc-001 FIRE: contact table (name/email/phone) no classification annotations; dbc-005 FIRE: no automated purge/TTL for guest data; dbc-009 FIRE: no consent table or consent columns; dbc-011 FIRE: address/gift fields disproportionate to RSVP purpose; dbc-006 PASS: DELETE /guests/:id exists; dbc-007 PASS: ON DELETE CASCADE on site FK |
| Python | NEGATIVE PROOF | dream-studio-clean | PR #149 description | 2026-06-03 | 0 findings confirmed — has_pii_schema=False (event store has no PII columns); validates auto-skip on operator data |
| Go | DECLARED | — | rules.yml only | — | Declared in applies_to; no Go proving run |

---

## Pre-Launch (ds-quality:pre-launch)

| Ecosystem | Proven? | Proving Repo | PR / Evidence | Date | Summary |
|-----------|---------|--------------|---------------|------|---------|
| TypeScript (consumer) | ✓ | DreamySuite | PR #150 description | 2026-06-03 | pl-001 FIRE T1: no ToS; pl-002 FIRE T1: no Privacy Policy (consumer+PII); pl-011 FIRE T1: no runbook; pl-012 FIRE T1: no rollback; pl-007 PASS: CHANGELOG current |
| Python (developer-tool) | NEGATIVE PROOF | dream-studio-clean | PR #150 description | 2026-06-03 | pl-001/002 SILENT (developer-tool type — correct, not broken); pl-009 FIRE T1: non-semver tags (ph-X.Y.Z format); pl-011 FIRE T2 (warning only, not blocking for dev tool); pl-007 PASS |

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✓ | Proven — real findings pasted from real external repo in a PR |
| PARTIAL | Some rules proven (fixture/smoke), not full proving run |
| DECLARED | Declared in rules.yml applies_to but no external proving run done |
