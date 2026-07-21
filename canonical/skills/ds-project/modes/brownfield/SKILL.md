# ds-project:brownfield — Multi-project discovery and bulk registration

**Invocation:** `ds-project brownfield:`, `brownfield-onboard:`, `register existing projects:`

**Entry points:**
- `studio-onboard` workflow (via WO-V first-run flow when existing repos detected)
- Explicit user trigger: `ds project brownfield-onboard` or `brownfield-onboard:`

**Wraps:**
- `core.projects.discovery.discover_project_candidates(search_root, github_entity, max_depth)` — enumerate candidates
- `core.projects.bulk_intake.bulk_acquire(candidates, source_root, dream_studio_home)` — bulk register
- `core.projects.mutations.set_project_vision(project_id, vision_statement)` — capture vision on project entity
- `core.projects.mutations.defer_project_audit(project_id, audit_type)` — defer readiness audit

---

## What this mode does

Registers multiple existing projects into Dream Studio in one pass — no full scope interview. After bulk registration, optionally captures vision and defers or schedules readiness audits.

**This mode is NOT for:**
- Scoping new greenfield projects (use `ds-project:scope`)
- Managing an already-registered project (use `ds-project:manage`)

---

## Flow

### Step 1 — Determine search root

Ask: "Where are your projects? Enter a directory path to scan, or press Enter to use the parent of the current directory."
- Default: parent of the current working directory.
- Accept the user's input or the default.

Also ask (one question at a time): "Do you want to enumerate a GitHub org or user's repos as well? Enter an org/username, or leave blank to skip."
- Requires `gh auth status` to succeed. If gh is not authenticated, skip silently.

### Step 2 — Discover candidates

Call:
```python
from core.projects.discovery import discover_project_candidates
from pathlib import Path

candidates = discover_project_candidates(
    Path(search_root),
    github_entity=github_entity or None,
    max_depth=3,
)
```

Present the results as a numbered list:
```
Found N project candidates:
  1. myapp          (~/builds/myapp)           [python, .git]
  2. dashboard      (~/builds/dashboard)       [node, .git]
  3. api-service    (github: org/api-service)  [GitHub only — no local clone]
  ...
```

Ask: "Select which to register (e.g., '1 2 3', 'all', or 'none')."

### Step 3 — Bulk register selected

For each selected candidate with a local path, call:
```python
from core.projects.bulk_intake import bulk_acquire

result = bulk_acquire(selected_candidates, source_root=source_root)
```

Report results:
- Registered: N new projects
- Skipped: M already registered (idempotent)
- GitHub-only: K repos without local clone (list URLs)
- Errors: J failed (list with reasons)

### Step 4 — Capture vision (optional, per project)

For each newly-registered project, offer:
"Do you want to add a brief vision statement for [project name]? (Stored on the project entity, not in a separate doc.)"

If yes, prompt for vision (1–3 sentences). Then call:
```python
from core.projects.mutations import set_project_vision
set_project_vision(project_id, vision_statement)
```

Skip this step if the user says "skip" or "no" for all projects.

### Step 5 — Deferred audits

For each newly-registered project, offer:
"Run a readiness audit for [project name] now, or defer to later?"
- Options: (1) Run now — invoke `ds-quality:security` for this project
           (2) Defer — schedule for later; will surface when the project is opened

If deferred, call:
```python
from core.projects.mutations import defer_project_audit
defer_project_audit(project_id, audit_type="security")
```

Default is deferred. A notice will appear the next time the project is activated or a work order is started.

### Step 6 — Summary

Report:
```
Brownfield onboarding complete.
  Registered: N projects
  Skipped:    M already registered
  Visions captured: K
  Audits deferred:  J (run `ds project audit <id>` when ready)
```

### Step 7 — Adaptive routing (recommended audits per project)

Each registered project dict carries `recommended_dispatches` (from
`core.projects.adaptive_routing.recommend_dispatches`, computed off the detected
stack signals). Surface the fit-for-stack `ds-quality` modes so the operator can
route to relevant audits instead of a generic prompt — do NOT auto-run them:
```
Recommended audits (by detected stack):
  myapp (fastapi, postgres):  ds-quality: backend-api, database, ops
  dashboard (react):          ds-quality: frontend-ux
```
Present only; the operator chooses which to invoke.

### Step 8 — Offer to run recommended audits + aggregate findings (confirmation-gated)

After surfacing the recommendations (Step 7), OFFER to run them — this is
confirmation-gated and never auto-runs (Rule 2 / Rule 5):
```
Run any of the recommended audits now? Enter the modes to run
(e.g. 'backend-api database'), or 'none' to skip.
```
For each mode the operator picks, invoke the corresponding `ds-quality` mode for
that project. Do NOT invoke any mode the operator did not pick.

Once the approved audits have run — their findings are persisted to the
`security_events` spine — fold the results into the per-project readiness report
and the proposed stabilization scope:
```python
from core.projects.acquisition import aggregate_readiness

report = aggregate_readiness(project_id, dispatches=project["recommended_dispatches"])
```
Present a per-project readiness section from `report["readiness_report"]` (finding
count, severity breakdown, the findings sourced from those audits) and the
proposed `report["stabilization_scope"]` — the severity-ordered items to tackle
first. If the operator then scopes the project, the stabilization scope becomes
the basis for its stabilization milestone.

`aggregate_readiness` only READS findings the approved audits already persisted —
it never triggers a run. If the operator ran no audits, the readiness section
reports zero findings and the stabilization scope is empty.

---

## Rules

1. Never write to prd_* tables — vision goes on `business_projects.vision_statement` only.
2. Default audit action is deferred — never schedule automatically without user confirmation.
3. GitHub-only entries (no local path) are listed but not registered — inform user to clone first.
4. Respect max_depth=3 for folder discovery — do not recurse indefinitely.
5. Recommended audits (Step 7/8) are present-only — offer, never auto-run. Findings
   aggregation (`aggregate_readiness`) consumes operator-approved audit results only.
