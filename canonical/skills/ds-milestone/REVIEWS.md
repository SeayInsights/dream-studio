# ds-milestone — review history

Moved out of `SKILL.md`. These notes were HTML comments: invisible in rendered
markdown but fully present in the bytes an agent loads, so they were charged as
context on every invocation while instructing nothing. They are kept here as the
audit trail. Do not put review notes back in SKILL.md.

---

Last reviewed 2026-06-20 — WO-P20-CLOSE-LAG (fix/wo-p20-close-lag): core/milestones/close.py close_milestone() now calls sync_tick() after emitting the milestone.completed spool event so business_milestones.status reflects 'complete' immediately — callers no longer need a manual flush. No skill-surface, mode, routing, or gate behavior change — close mode still calls close_milestone().

---

Reviewed 2026-07-05 — WO 6d978483 (PEP 585/604 modernization [2/2]): source files in this domain received mechanical type-annotation modernization only (PEP 585 builtin generics, PEP 604 unions, datetime.UTC) via ruff UP safe autofixes. No contract, behavior, schema, routing, API-shape, or CLI-surface change — reviewed, no doc content change needed.

---

Reviewed 2026-07-23 — WO-FILESDB-P3 S3b-2 (feat/milestone-gate-docstore-reader): the four close gate checks (design-audit / security-audit / harden-results / cwv-results) now read their artifacts via core.milestones.artifacts.read_milestone_artifact — the files.db docstore first (name 'milestones/<id>/<file>'), disk-fallback during the .planning→docstore transition. Same four gate checks, same pass/fail semantics; only the artifact READ path moved. No skill-surface, mode, routing, or gate-behavior change — close mode still calls close_milestone().

---

Reviewed 2026-07-23 — WO 05fc434d (fix/milestone-close-deleted-terminal): core/milestones/close.py::close_milestone open-WO precondition now treats "deleted" as terminal alongside "closed"/"cancelled" (_TERMINAL_WO_STATUSES). A work order retired via a work_order.deleted event (status='deleted') is removed, not outstanding, so it must not block milestone close — the open-WO check is a hard precondition (not force-bypassable), so the terminal set must be complete. Surfaced closing the Files-in-Database milestone (a deleted stale-advisory WO blocked it). Same close flow + gate sequence; only the open-WO terminal-status set widened. No ds-milestone mode, routing keyword, or CLI-surface change — close mode still calls close_milestone().

---

Reviewed 2026-08-08 — WO-GATE-HAS-UI (Platform Gate Corrections): core/milestones/close.py::_evaluate_milestone_artifacts CHECK 1 (design audit) is now has_ui-aware — a non-UI infrastructure milestone (no ui_component/ui_page WO) is no longer REQUIRED to produce a website:critique design-audit.md, mirroring the existing Core Web Vitals check. A design-audit present on any milestone still has its Score: N/M >= 3 bar enforced; security-audit + harden-results stay universal. core/milestones/queries.py get_milestone_status open_gate_checks preview drops design_audit for non-UI milestones to match. close/main SKILL.md gate list updated (design audit is UI-only). No ds-milestone mode, routing keyword, or CLI-surface change — close mode still calls close_milestone(); status mode still calls get_milestone_status().

---

Reviewed 2026-08-05 — WO 4d495283 / P3 (feat/prd-rescore-engine): additive read-path param only, NO milestone-surface change. core/milestones/artifacts.py::read_milestone_artifact gains an OPTIONAL db_path keyword so the PRD+SOW rescore engine (core/prd/) and isolated tests can read a non-default files.db docstore; default db_path=None preserves the exact existing behavior, and the milestone close gates still read their artifacts through the same helper unchanged. No ds-milestone mode, routing keyword, CLI surface, or close/gate-behavior change — close mode still calls close_milestone().

---

Reviewed 2026-08-05 — WO 742c84f8 / P4 (feat/prd-cli-and-autorefresh): core/milestones/close.py::close_milestone gains a best-effort PRD+SOW auto-refresh on its SUCCESS path (after sync_tick, before return): it calls core/prd/rescore.py::rescore_prd for the milestone's project so the derived PRD+Statement-of-Work living document (docstore prd/prd-sow.md) reflects the just-completed milestone. Wrapped in try/except and swallowed (SPEC-0001 R12) — it can NEVER block, fail, or change the outcome of a milestone close; the returned result dict is unchanged. No new gate, no ds-milestone mode/routing/CLI-surface change, no studio.db table. The refresh is also runnable on demand via the new `ds prd rescore` / `ds prd show` command group (interfaces/cli/commands/prd.py).

---

Reviewed 2026-08-08 — WO-SECGATE-BLOCKED-TOKEN (Gate & CI Hardening): core/milestones/close.py CHECK 2 (security audit) now flags a BLOCKED *finding marker* via the shared core/gates/security_verdict.py::is_security_blocked, not a naive `"BLOCKED" in text` substring — so an honest "No BLOCKED findings" / "0 BLOCKED" summary no longer false-fails the gate (it blocked the Attribution Coherence milestone close). close mode gate list updated (item 3). No ds-milestone mode, routing keyword, or CLI-surface change — close mode still calls close_milestone(); same gate, sharper predicate.

---

Reviewed 2026-08-18 — WO-VERIFY-PROVENANCE (b5ddac3e, Adversarial Verification Integrity): milestone close artifact checks (design-audit / security-audit / harden-results / cwv-results) are now provenance-aware. core/milestones/artifacts.py gains read_milestone_artifact_with_envelope (read_milestone_artifact unwraps transparently); core/milestones/close.py::_evaluate_milestone_artifacts takes project_root and REJECTS an ENVELOPED audit artifact when ANY commit landed after its recorded HEAD (whole-repo staleness — a milestone audit covers the whole surface, so any later commit potentially invalidates it; failure names the regenerating skill). Legacy envelope-less artifacts keep historical acceptance. Same gate list, same close_milestone() return shape, no ds-milestone mode, routing keyword, or CLI-surface change.

---

Reviewed 2026-09-08 - WO fc2916a4 (feat/substrate-guardrails): MILESTONE STATUS NOW HAS ONE DEFINITION, in the new core/milestones/status.py: MILESTONE_COMPLETE, MILESTONE_DONE_STATUSES, MILESTONE_ABANDONED_STATUSES, MILESTONE_STATUSES, is_complete() and is_open(). Measured on the live authority: business_milestones.status holds complete (45 rows), pending (43) and deleted (2), while core/work_orders/milestones_classify.py tested membership of a two-member set naming a past-tense variant the column has never held. A phantom member is harmless until someone writes it, at which point every reader omitting it silently disagrees -- the business_tasks.status equivalent made a diagnostic report every work order 0-done. NO GATE, NO MODE, NO CLI CHANGE: milestones_classify._milestone_complete imports is_complete instead of spelling the set, and core/milestones/close.py writes MILESTONE_COMPLETE instead of the literal. The close gates (design_critique, security_scan, hardening), their thresholds, the artifact provenance checks and the milestone close/list surfaces are all unchanged, and `ds milestone close` behaves identically. is_open() treats an UNKNOWN status as still-open, because absorbing an unrecognised value into complete is the direction that lets a milestone close over work nobody did. WORKFLOW STEP status is deliberately NOT unified: _first_pending_step tests a step vocabulary that shares the word complete and also carries skipped, which is not a milestone status -- unifying two vocabularies because they overlap is how the wrong one gets applied, so the separation is pinned by a test rather than left to memory. Verified by running the REAL MilestoneProjection and inspecting the status it writes, not by reading its SQL. 9 tests in tests/unit/test_milestone_status_vocabulary.py; rule a-vocabulary-has-one-definition-per-domain in canonical/rules.yml, enforced by the blocking rule-registry gate.
