# ds-project — review history

Moved out of `SKILL.md`. These notes were HTML comments: invisible in rendered
markdown but fully present in the bytes an agent loads, so they were charged as
context on every invocation while instructing nothing. They are kept here as the
audit trail. Do not put review notes back in SKILL.md.

---

Last reviewed 2026-06-11 — WO-MARKER-FORMAT + remediation (993ba17a): no skill surface change in either PR. PR #278: cross-project overwrite guard + JSON/UUID emitter parse. PR #279 (remediation): added db_path param to _write_project_marker() for project-existence validation against business_projects before writing. Root-cause audit note written to decision_log (decision_id 8cc3a6d0). Neither change affects the skill API seen by the adapter.

---

Last reviewed 2026-06-14 — WO-DASH-VALIDATION-GAPS (T3): update_project_path() added to core/projects/mutations.py — backfill utility for projects registered without a local directory path (e.g. via early CLI or bulk brownfield import). Emits project.path_set event for audit trail. No new skill mode, no new ds-project routing surface, no skill behavior change. Skill contract unchanged.

---

Last reviewed 2026-06-18 — WO-ATTRIBUTION-NORMALIZE: new core/projects/attribution.py (resolve_project_uuid + backfill) maps a captured project KEY (name/slug/path-basename) to the registered business_projects UUID, and fixes the capture paths (core/telemetry/execution_spine.py, control/analysis/synthesis.py) that stored free-text names / cwd basenames in execution_events.project_id instead of the UUID — which made project Activity render blank. Backfill remapped historical events to the correct per-project UUID (Dream Command stayed separate; unresolvable cwd-garbage left untouched, never fabricated). No new ds-project skill mode, routing keyword, or behavior change; the skill contract is unchanged.

---

Last reviewed 2026-06-27 — Wave 2 substrate realignment (migration 131, worktree-agent-a910d590fedb5c672): core/projects/mutations.py: defer_project_audit() removed — migration 131 drops the dormant pending_audits table (the function had no caller from any live path). No ds-project skill mode, routing keyword, or behavior change; the project-scoping/registration contract is unchanged.

---

Last reviewed 2026-07-04 — migration 140 (WO dff23cb0-950f-4607-bb30-e1a353a6f8ba): core/projects/delta.py::_get_scan_findings() and core/projects/intake.py::get_scan_summary() repointed from findings_current_status (dropped — pure derived state, FindingsProjection.fold_spine() upsert over security_events) to core/findings/current_status.py::FINDINGS_CURRENT_STATUS_SQL, deriving current_status from security_events at read time. Return shapes are unchanged. No ds-project skill mode, routing keyword, or behavior change; the project-scoping/registration contract is unchanged.

---

Reviewed 2026-07-05 — WO 6d978483 (PEP 585/604 modernization [2/2]): source files in this domain received mechanical type-annotation modernization only (PEP 585 builtin generics, PEP 604 unions, datetime.UTC) via ruff UP safe autofixes. No contract, behavior, schema, routing, API-shape, or CLI-surface change — reviewed, no doc content change needed.

---

Last reviewed 2026-07-19 — WO-BROWNFIELD-DETECT: get_project_state() now returns cwd_registered + cwd_project (core/projects/queries.py::_match_cwd_project, mirroring runtime.lib.enforcement.match_registered_project against the resolved connection). Resume Mode gains Step 1.5: when cwd_registered is false, answer "this repo isn't registered" and offer ds-project:brownfield instead of narrating the globally-active project. No new routing keyword or mode; resume stays read-only.

---

Last reviewed 2026-07-20 — WO-BROWNFIELD-ADAPTIVE (570e6c1f): brownfield acquisition now recommends the ds-quality modes that fit each detected stack. core/projects/adaptive_routing.py::recommend_dispatches maps the stack detector's already-computed skill-dispatch signals (web_framework->backend-api, frontend_framework->frontend-ux, database_type->database, container/k8s->ops, PII/compliance->database-compliance, test_framework->testing, architecture/monorepo->architecture, service/release->pre-launch) to [{pack:'ds-quality', mode, reason}]. core/projects/intake.py::detect_and_persist_stack now persists those signals in stack_json, and core/projects/acquisition.py::acquire_project (hence bulk_acquire's registered[] dicts) adds an additive recommended_dispatches field. brownfield mode Step 7 surfaces them (present-only, operator chooses; never auto-run). No new ds-project mode, routing keyword, or breaking contract change.

---

Last reviewed 2026-07-20 — WO-FILESDB-C2 ("Files in Database" milestone): core/projects/start.py::start_project no longer parses '- [ ]' checkboxes out of context.md to count open tasks — the context now lives in the authority (business_work_order_artifacts, kind='context'), not on .planning disk. The new _count_open_tasks(db_path, work_order_id) counts open tasks (status NOT IN complete/cancelled) directly from business_tasks, and the result dict adds context_in_authority (True when the context was stored in the DB; context_path is then None). No ds-project mode, routing keyword, or start_project contract change beyond the additive context_in_authority field; project scoping/registration/resume behavior is unchanged.

---

Last reviewed 2026-07-20 — WO-BROWNFIELD-OFFER-INVOKE (7f8618a4): follow-on to WO-BROWNFIELD-ADAPTIVE. core/projects/acquisition.py adds aggregate_findings(findings, dispatches) (pure) and aggregate_readiness(project_id, dispatches=…) — the latter reads the findings that operator-approved ds-quality audits already persisted (via core/projects/intake.py::get_scan_summary over the security_events spine) and folds them into a per-project readiness report (finding_count, severity_counts, provenance audits, findings) plus a severity-ordered stabilization_scope (one item per non-empty bucket, critical first, with affected files). Rule 2 preserved — the engine only CONSUMES persisted results, never auto-runs an audit. brownfield mode gains Step 8 (confirmation-gated offer to run the recommended audits, then aggregate_readiness) and Rule 5. No new ds-project mode, routing keyword, or breaking contract change; scope/resume/registration behavior is unchanged.

---

Reviewed 2026-08-19 — WO-BYPASS-TELEMETRY (2f6b5a8a, Adversarial Verification Integrity): core/projects/queries.py::get_project_state gains an ADDITIVE bypass_summary key — {last_7d_total, rules: {rule: count}, gates: {gate: count}} — aggregating recent enforcement escape-hatch activity (DS_ENFORCE=0 short-circuits, fail-opens, gate.bypassed events incl. force-closes and acknowledgment escapes) via core/health/doctor_bypass.py::bypass_audit. Resume mode MAY surface a one-line warning when last_7d_total > 0 (e.g. "3 enforcement bypasses in the last 7 days — review with ds doctor"); no existing key changed, no new mode, routing keyword, or CLI surface.

---

Reviewed 2026-08-19 — gap WO 5ed752d7 (from WO-FALSIFY-FIRST-PASS's own verify): core/projects/queries.py::get_project_state gains an ADDITIVE per-project unverified_risks key — {total, work_orders[{work_order_id, title, count, classes}], unreadable[]} — aggregating open UNVERIFIED residual risk from each non-closed WO's falsification ledger via core/work_orders/unverified_summary.py::project_unverified_summary (closed WOs are excluded: their residual risk was surfaced and accepted at close). An unreadable ledger is listed separately, never counted as zero. Resume mode MAY surface a one-line note when total > 0 (e.g. "3 unverified worst-case scenarios across 2 work orders — see ds work-order artifact <id> report --instance unverified_risks"); no existing key changed, no new mode, routing keyword, or CLI surface.

---

Reviewed 2026-08-19 — WO-MAINRED-VISIBILITY (9a9e23da): core/projects/queries.py::get_project_state gains an ADDITIVE main_ci key — {status: success|failure|running|unknown, red, conclusion, head_sha, run_url, title, reason, warning?} — reading the latest post-merge "Full CI" run for main via core/health/main_ci.py. Rationale: pr-smoke green is merge authorization, not proof main is green (the full suite runs post-merge, ubuntu-only), and main sat red across eight merges with no surface reporting it. Resume mode MAY surface the one-line main_ci.warning when red is true; it must NOT block or gate on it (someone else's red main must not stop unrelated work) and must render status unknown as unknown WITH its reason, never as green. No existing key changed, no new mode, routing keyword, or CLI surface.

---

Reviewed 2026-08-20 — WO-SEPARATE-TEST-RUNNER gap (e3a17189): core/projects/queries.py::get_project_state gains an ADDITIVE next_work_order.test_execution_warning key — one sentence, built by core/gates/merge_readiness.py::execution_caveat from the WO's stored verdict's test_execution.basis (none_registered | not_run_at_verify). Rationale: verify records whether a certification rested on RUNNING the work order's tests or on reading its code, and that distinction previously existed only at `ds work-order merge-check` — so a WO verified by a review that never executed a test was surfaced on resume as plainly certified. Resume mode SHOULD surface the line verbatim when present; it must NOT block and must NOT treat absence as either a warning or as confirmed execution (a verdict predating the field cannot answer). No existing key changed, no new mode, routing keyword, or CLI surface.

---

Reviewed 2026-08-19 — WO-MAINCI-CACHE (c14c2eea): the main_ci key on get_project_state is unchanged in shape but may now be served from a SHORT-TTL CACHE. core/projects/queries.py passes max_age_seconds=CACHE_MAX_AGE_SECONDS (300s) because project state runs on every resume and was paying a gh round trip each time — typically ~1s, worst case the full 25s timeout when gh is unreachable or unauthenticated. Every main_ci payload now carries as_of (ISO time the status was actually READ from gh) and age_seconds (0 when live, >0 when cached), and main_ci.warning states its own age, e.g. "(cached, 4 min old)". Resume mode MUST NOT present a cached status as current: when age_seconds is non-zero, say so if it surfaces the line at all — a red that has since been fixed is exactly the case an operator needs to be able to tell apart, and this surface's whole value is that what it says about main can be trusted. Caching is opt-in at the call site and the reader's default is a live read, so nothing else changes behaviour; `close` deliberately reads live. Advisory semantics are untouched: still never blocks, still renders unknown as unknown with its reason, still never fabricates green. No key removed or renamed, no new mode, routing keyword, or CLI surface.

---

Reviewed 2026-08-28 - WO-LOOP-TEXT-STALE (d26c662b), feat/type-aware-standards: get_next_work_order in core/projects/queries.py now LEFT JOINs business_milestones instead of INNER JOINing it, so a work order with no milestone is surfaced by the selector. ready_work_orders was changed to a LEFT JOIN in PR #681 and this one was not, so the two readers of the same authority disagreed about what work exists -- one open milestone-less work order was invisible to `ds project state` while appearing in the ready set. NULL order_index now sorts LAST (`m.order_index IS NULL` leads the ORDER BY); SQLite orders NULL first in ASC, which would have let a milestone-less work order jump ahead of every milestone, the opposite of "milestone order is advisory". Found by a test written to pin the autonomous loop's PROSE against the engine: the corrected prose claimed milestone-less work orders were included, the test checked, and the engine said otherwise -- the correction was false when written. No ds-project mode, routing keyword, or CLI subcommand change.
