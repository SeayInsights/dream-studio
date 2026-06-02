# Frontend-UX — Audit Mode

## Metadata
- **Pack:** quality
- **Mode:** frontend-ux:audit
- **Type:** diagnostic
- **Model:** sonnet
- **Inputs:** source_root, scope_mode, target_path
- **Outputs:** frontend_ux_audit_report

## Before you start
1. Read `../gotchas.yml` if it exists.
2. Read `../rules.yml` fully — all 10 Phase 1 rules.
3. Detect frontend framework from `detect_stack().frontend_framework`.

## Trigger
`ds-quality:frontend-ux:audit`, `ux audit:`, `frontend audit:`, `a11y check:`

## Step 1 — Detect Framework and File Scope

**Framework detection via `detect_stack().frontend_framework`:**
- nextjs: scan `src/app/**/page.tsx`, `src/app/**/*.tsx`, `src/components/**/*.tsx`
- react (standalone): scan `src/**/*.tsx`, `src/**/*.jsx`
- vue: scan `src/**/*.vue` (skip React hooks rules)
- svelte: scan `src/**/*.svelte` (skip React hooks rules)
- angular: scan `src/**/*.component.ts` (skip React hooks rules)

**Exclusions:**
- `node_modules/`, `*.test.tsx`, `*.spec.tsx`, `*.stories.tsx`
- `src/lib/effects/` — third-party animation components (suppressed by default)

## Step 2 — Static Pass

Rules with static detection:
- **ux-006**: regex `.map(` constructs without `key=` prop — fire immediately
- **ux-012**: AST parse `useEffect` second arg vs body references — fire immediately

## Step 3 — Candidate/Confirm Pass

Rules requiring LLM semantic confirmation:
- **ux-001**: regex finds `<img` → LLM confirms alt is meaningful (not empty, not file path)
- **ux-002**: regex finds `<input` without `<label>` → LLM confirms missing or misleading
- **ux-005**: regex finds `aria-*` → LLM confirms semantic correctness

## Step 4 — LLM Semantic Pass

Pure-judgment rules:
- **ux-003**: keyboard accessibility of interactive elements
- **ux-004**: focus management in modals/overlays
- **ux-007**: component LOC + reuse judgment
- **ux-010**: hardcoded user-facing strings (i18n gap)
- **ux-013**: stale closure in callbacks

## Step 5 — Generate Report

Group by severity (Critical → High → Medium). Include framework detected and scope.
