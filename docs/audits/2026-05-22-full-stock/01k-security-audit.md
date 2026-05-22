# Pass 1k — Security Audit
*Phase 1 analysis | 2026-05-22*
*Focus: Intents #2 (brownfield security intake) and #3 (security as SDLC gate)*

---

## Stated Architectural Intents

All five architectural intents apply. Intents 2 and 3 are the primary subject of this pass.

1. **SQLite-first authority** — all runtime STATE must be SQLite-backed. File-based state is v1 rot.
2. **Security audit during brownfield onboarding** ← PRIMARY FOCUS — security skills run during project intake; findings stored in SQLite.
3. **Security audit as SDLC lifecycle gate** ← PRIMARY FOCUS — greenfield projects must pass security audit before going live.
4. **Canonical events as the spine** — all state changes flow through canonical_events. Direct table writes without event emission are anomalies.
5. **Marker file authority for attribution** — .dream-studio-project markers are identity source; ds_projects is metadata storage.

**Summary verdict before detail:** Intent 2 has zero implementation. Intent 3 has a named gate with a file-based resolver that does not invoke any security skill. The security infrastructure is architecturally large but operationally dormant — all 8 ds-security modes have never been invoked, all security DB tables have 0 rows, and the one automatic security mechanism (on-security-scan hook) is advisory-only with no persistence path.

---

## Security Infrastructure Catalog

### 1. ds-security Skill Modes (8)

All 8 modes live at `canonical/skills/security/modes/<mode>/SKILL.md`. The pack is installed at `~/.claude/skills/ds-security/SKILL.md` (+23 bytes over canonical). Zero `skill.invoked` events for any ds-security mode in the 6-day observation window (2026-05-17 to 2026-05-22). Zero rows in any security DB table.

---

#### 1.1 scan

- **What it is:** `canonical/skills/security/modes/scan/SKILL.md` — orchestration mode
- **What it does:** Generates GitHub Actions workflows and Semgrep rule configs from client profile; ingests SARIF/JSON results from CI into file-based store; does not run scans locally
- **Current state:** ACCESSIBLE — installed, routable via `scan:` keyword, functional SKILL.md, no automatic trigger
- **Evidence:** Zero invocations. File store at `~/.dream-studio/security/scans/{client}/{repo}/{date}/` has no confirmed population. `sec_sarif_findings` (0 rows), `sec_cve_matches` (0 rows).
- **Intent 2 alignment (brownfield intake):** NO — scan mode is a CI orchestration tool for org-level work, not a project intake scanner
- **Intent 3 alignment (SDLC gate):** NO — scan mode is not wired as a post-build gate resolver. The `security_scan` gate in ds_work_order_types resolves via file presence check (`security-scan.md`), not via skill invocation
- **Storage:** File-based (`~/.dream-studio/security/scans/{client}/`). SQLite tables exist but are not write targets in the SKILL.md.
- **Notes:** Designed for PLMarketing/Kroger client work. The `security-audit.yaml` workflow uses `skill: scan` for `generate-rules` and `ingest-results` nodes — this is the only workflow connection, and security-audit.yaml has never run.

---

#### 1.2 review

- **What it is:** `canonical/skills/security/modes/review/SKILL.md` — code-level vulnerability analysis
- **What it does:** 3-phase code review (context research, comparative analysis, vulnerability assessment) against git diff; outputs markdown findings report; confidence ≥8 filter applied
- **Current state:** ACCESSIBLE — routable via `review:` keyword, fully documented, no automatic trigger
- **Evidence:** Zero invocations. No findings persisted anywhere.
- **Intent 2 alignment (brownfield intake):** NO
- **Intent 3 alignment (SDLC gate):** NO — workflow nodes for security review in idea-to-pr.yaml and comprehensive-review.yaml use `skill: pr-security-scan` (ds-quality), not `ds-security review`
- **Storage:** Markdown output only. No SQLite write path defined in SKILL.md.
- **Notes:** Uses Opus model (the only ds-security mode doing so). Distinct from ds-quality pr-security-scan — review is deeper (Opus, 3-phase methodology) vs pr-security-scan (Sonnet, confidence-filtered). The workflow integration routes to the lighter mode, not this one.

---

#### 1.3 dast

- **What it is:** `canonical/skills/security/modes/dast/SKILL.md` — dynamic application security testing
- **What it does:** Orchestrates ZAP + Nuclei against web app targets defined in client profile; can execute locally (unlike scan which is CI-only); ingests results into file store
- **Current state:** ACCESSIBLE — routable via `dast:` keyword, no automatic trigger
- **Evidence:** Zero invocations. `sec_sarif_findings` (0 rows).
- **Intent 2 alignment (brownfield intake):** NO
- **Intent 3 alignment (SDLC gate):** NO — wired only in security-audit.yaml (never run)
- **Storage:** File-based (`~/.dream-studio/security/scans/{client}/{target}/{date}/`).
- **Notes:** security-audit.yaml has a `dast-scan` node (`skill: dast`). That workflow has never run.

---

#### 1.4 binary-scan

- **What it is:** `canonical/skills/security/modes/binary-scan/SKILL.md` — executable analysis
- **What it does:** YARA rules, checksec configs, strings extraction against binary targets; generates analysis scripts; ingests results to file store
- **Current state:** ACCESSIBLE — routable via `binary-scan:` keyword, no automatic trigger
- **Evidence:** Zero invocations. No file artifacts.
- **Intent 2 alignment (brownfield intake):** NO
- **Intent 3 alignment (SDLC gate):** NO — wired only in security-audit.yaml (never run)
- **Storage:** File-based (same pattern as scan/dast).
- **Notes:** Windows platform note in SKILL.md (checksec vs winchecksec). Platform detection is a manual step.

---

#### 1.5 mitigate

- **What it is:** `canonical/skills/security/modes/mitigate/SKILL.md` — per-finding fix recommendations
- **What it does:** Generates actionable mitigations (code diff, verification test, effort estimate, compliance impact) for findings from scan/dast; reads from `~/.dream-studio/security/scans/{client}/unified-findings.json`; writes to `~/.dream-studio/security/datasets/{client}/mitigations.csv`
- **Current state:** ACCESSIBLE — routable via `mitigate:` keyword, no automatic trigger
- **Evidence:** Zero invocations. No mitigation artifacts.
- **Intent 2 alignment (brownfield intake):** NO
- **Intent 3 alignment (SDLC gate):** PARTIAL (downstream only) — wired as a dependency in security-audit.yaml but this workflow has never run. Also referenced in the pre-build gate for authentication work order type (`api_contract_and_security_review`) — gate name only, not a confirmed skill invocation.
- **Storage:** File-based (`~/.dream-studio/security/datasets/{client}/mitigations.*`).
- **Notes:** Model: Sonnet (most complex remediation reasoning). SKILL.md explicitly states "this skill never modifies client code directly."

---

#### 1.6 comply

- **What it is:** `canonical/skills/security/modes/comply/SKILL.md` — compliance framework mapping
- **What it does:** Maps scan findings to SOC 2, NIST CSF, OWASP ASVS, CWE Top 25 controls; identifies coverage gaps; generates audit-ready evidence documents; writes to `~/.dream-studio/security/datasets/{client}/compliance.csv`
- **Current state:** ACCESSIBLE — routable via `comply:` keyword, no automatic trigger
- **Evidence:** Zero invocations. No compliance artifacts.
- **Intent 2 alignment (brownfield intake):** NO
- **Intent 3 alignment (SDLC gate):** NO — wired only in security-audit.yaml (never run), parallel with mitigate
- **Storage:** File-based (`~/.dream-studio/security/datasets/{client}/compliance.csv`).
- **Notes:** SKILL.md distinguishes between "zero findings because we scanned and found none" vs "zero findings because no rule covers this control" — a useful coverage gap distinction that has no activation path.

---

#### 1.7 netcompat

- **What it is:** `canonical/skills/security/modes/netcompat/SKILL.md` — network/proxy compatibility analyzer
- **What it does:** Analyzes code for Zscaler/corporate proxy compatibility issues; generates Semgrep rules from Jinja2 templates; produces per-repo compatibility score; writes to `~/.dream-studio/security/datasets/{client}/netcompat.csv`
- **Current state:** ACCESSIBLE — routable via `netcompat:` keyword, no automatic trigger
- **Evidence:** Zero invocations.
- **Intent 2 alignment (brownfield intake):** NO
- **Intent 3 alignment (SDLC gate):** NO — wired only in security-audit.yaml (never run)
- **Storage:** File-based.
- **Notes:** Most domain-specific mode — Kroger/PLMarketing corporate network context. No applicability to general project intake.

---

#### 1.8 dashboard

- **What it is:** `canonical/skills/security/modes/dashboard/SKILL.md` — ETL orchestration + Power BI export
- **What it does:** Full security ETL pipeline from raw scan results to Power BI-ready CSVs; reads from upstream skill outputs; scores by CVSS and business impact; exports to `~/Downloads/` (Power BI template)
- **Current state:** ACCESSIBLE — routable via `security dashboard:` keyword, no automatic trigger
- **Evidence:** Zero invocations.
- **Intent 2 alignment (brownfield intake):** NO
- **Intent 3 alignment (SDLC gate):** NO — final reporting step in security-audit.yaml (never run). Reads from file-backed upstream outputs; no SQLite reads or writes.
- **Storage:** File-based (CSVs, Power BI template copy).
- **Notes:** Terminal node of the security pipeline. All upstream nodes must have run for this to produce meaningful output. Storage references `docs/security-storage-layout.md` — all storage is file-system, no SQLite.

---

### 2. ds-quality pr-security-scan Mode

- **What it is:** Mode in `canonical/skills/quality/modes/secure/SKILL.md` (canonical name: `secure`; installed/routing name: `pr-security-scan`)
- **What it does:** Code-level security review using confidence-filtered pattern matching; outputs `review-<node-id>-findings.md`; intended for pre-merge security review of diffs
- **Current state:** ACCESSIBLE — routable via `pr-security-scan:` keyword. Zero observed invocations.
- **Evidence:** Zero `skill.invoked` events for ds-quality or quality:pr-security-scan.
- **Intent 2 alignment (brownfield intake):** NO — not wired into any intake workflow
- **Intent 3 alignment (SDLC gate):** YES (workflow-wired, never executed) — this is the mode referenced in `idea-to-pr.yaml` (`review-security` node), `comprehensive-review.yaml` (`review-security` node), and `project-audit.yaml` (`secure` node). These workflows represent the only path through which security review is integrated into the SDLC lifecycle. All three workflows are dormant.
- **Distinction from ds-security review:** pr-security-scan is lighter (Sonnet, pattern-matching confidence filter, markdown output only). ds-security review is deeper (Opus, 3-phase methodology, dedicated anti-patterns). Workflows use pr-security-scan; ds-security review is never invoked by any workflow.
- **Mode name mismatch:** The canonical SKILL.md at `canonical/skills/quality/SKILL.md` references `modes/secure/SKILL.md` and keyword `secure:`, but the installed pack, packs.yaml, and all routing tables use `pr-security-scan`. The canonical source file has not been updated to reflect the rename.

---

### 3. on-security-scan.py Hook

- **What it is:** `runtime/hooks/quality/on-security-scan.py` — PostToolUse Edit|Write handler dispatched by `on-edit-dispatch.py`
- **What it does:** On every Edit or Write tool use, calls `control.analysis.security_patterns.scan_for_patterns(content)` to check for high-signal anti-patterns; if findings exist, calls `security_patterns.print_warning(file_path, findings)` which prints advisory warnings to stdout
- **Current state:** WIRED (advisory only) — fires on every Edit/Write via `on-edit-dispatch.py` dispatcher. 5 timing entries in `hook-timing.jsonl` confirming activation.
- **Evidence:** 5 invocations recorded in hook-timing.jsonl. Zero rows in `sec_hook_checks` table. No canonical events emitted. No findings persisted.
- **What it does NOT do:**
  - Does not write to `sec_hook_checks` table
  - Does not write to `security_findings` table
  - Does not emit canonical events
  - Does not block — advisory only, always returns normally
  - Does not write to any file
- **Intent 2 alignment (brownfield intake):** NO — fires on writes, not on project intake
- **Intent 3 alignment (SDLC gate):** NO — advisory only, no gate enforcement
- **Architectural role:** This is the only security mechanism that fires automatically. It is a content-level lint, not a gate. The gap between what fires (lightweight pattern check, 5 times in 6 days) and what the architecture intends (security audit at intake and gate enforcement) is the largest single observation of this pass.
- **Notes:** The `sec_hook_checks` table was designed to receive hook-based security check records. The hook does not write to it. The gap between the table's existence and its 0-row state is the direct evidence that the hook-to-DB write path was never implemented.

---

### 4. guardrails/ Infrastructure

#### 4.1 enforcement.py

- **What it is:** `guardrails/enforcement.py` — content-level enforcement detectors
- **What it does:** Pure text-function detectors for placeholder patterns (bracket-wrapped, bare placeholder words, common phrases). No DB, no IO, no logging.
- **Current state:** SCAFFOLDED — code is complete and tested (has compiled .pyc). Not registered as a hook. Not called by any hook in the live chain. `guardrail_decisions` has 0 rows, `guardrail_rules_audit` has 0 rows.
- **Intent 2 alignment:** NO
- **Intent 3 alignment:** NO
- **Notes:** This is a code quality enforcement tool, not a security scanner. The module is named "enforcement" but its content detects placeholder anti-patterns, not security violations. No call site in the active hook chain.

#### 4.2 evaluator.py

- **What it is:** `guardrails/evaluator.py` — guardrail rule evaluator with block/require_approval/advisory decision engine
- **What it does:** Loads rules from YAML files (`guardrails/rules/`), queries activity_log for trigger conditions, returns allow/block/require_approval/advisory decision, logs to `guardrail_decisions` table, emits CanonicalEventEnvelope
- **Current state:** SCAFFOLDED — complete implementation with spool integration and proper event emission. Not registered as any hook. Not called from any active code path. `guardrail_decisions` has 0 rows.
- **Evidence:** `guardrail_decisions`: 0 rows. `guardrail_rules_audit`: 0 rows. settings.json shows no hook registration for guardrails/evaluator.py.
- **Intent 2 alignment:** NO
- **Intent 3 alignment:** NO — would be the most direct path to implementing a blocking security gate if wired. Currently inert.
- **Notes:** The evaluator accepts `--rule-file`, `--event-id`, `--action-type` CLI args. It could be invoked from a hook. The absence of a settings.json registration is the single missing wire.

#### 4.3 security.yaml (guardrail rules)

- **What it is:** `guardrails/rules/security.yaml` — 5 guardrail rule definitions
- **What it does:** Defines rules GR-001 through GR-005: block_commit_with_secrets, require_approval_critical_vulns, block_eval_usage, block_shell_injection_risk, warn_private_key_in_source
- **Current state:** STUB — rules are defined but trigger on `event_type: "hook_finding.created"`, an event type that has never been emitted (0 rows in any security table, 0 rows in hook_findings). Pilot mode is on (`action: "advisory"` for all rules, not `block`). The conversion dates (`convert_to_block: "2026-05-13"`) have passed with no change.
- **Intent 2 alignment:** NO
- **Intent 3 alignment:** NO
- **Notes:** All 5 rules reference `event_type: "hook_finding.created"` as their trigger. The `hook_findings` table has 0 rows. The trigger event has never been emitted by any hook. The rules are syntactically valid YAML with no active evaluation path. The pilot-mode conversion dates (2026-05-13) passed 9 days ago with no upgrade.

#### 4.4 Scanner Stubs (giskard_scanner.py, llm_guard_scorer.py, rebuff_validator.py)

- **What they are:** `guardrails/scanners/*.py` — LLM vulnerability scanners
- **What they do:** Pattern-based stub implementations of Giskard LLM scanning, LLM Guard output scoring, and Rebuff prompt injection detection. All three are stubs because the real libraries are incompatible with Python 3.12 (documented in each file's docstring).
- **Current state:** STUB — all three are stub implementations using pattern-matching heuristics. Not called from any hook, not invoked from any skill, not wired to any flow.
- **Intent 2 alignment:** NO
- **Intent 3 alignment:** NO
- **Notes:** These are LLM safety scanners (prompt injection, PII leakage, toxicity, hallucination) rather than code security scanners. Their domain is AI output safety, not SAST/DAST/CVE scanning. The Python version incompatibility note references Python 3.14 in two files and Python 3.12 in one — minor inconsistency in the stub documentation.

---

### 5. Security Database Tables

All 12 security-relevant DB tables have 0 rows.

| Table | Schema present | Rows | Write path active |
|-------|---------------|------|------------------|
| sec_cve_matches | YES | 0 | No — no CVE scanner wired |
| sec_hook_checks | YES | 0 | No — on-security-scan hook does not write here |
| sec_manual_reviews | YES | 0 | No — ds-security review does not write here |
| sec_sarif_findings | YES | 0 | No — scan mode writes to filesystem, not here |
| security_findings | YES | 0 | No — no confirmed write path in active code |
| guardrail_decisions | YES | 0 | No — evaluator.py not wired |
| guardrail_rules_audit | YES | 0 | No — evaluator.py not wired |
| hook_findings | YES | 0 | No — no hook emits hook_finding.created events |
| risk_register | YES | 0 | No — no risk assessment workflow active |
| risk_mitigations | YES | 0 | No — depends on risk_register |
| compliance_review_flags | YES | 0 | No |
| production_readiness_findings | YES | 0 | No — production-readiness.yaml never run |

**Additional finding — github_repo_security_findings (0 rows):** A separate `github_repo_security_findings` table exists as part of the GitHub repo evaluation schema. This table is also 0 rows and has no active write path in the live system.

**vw_security_summary:** A view that unions sec_sarif_findings, sec_cve_matches, sec_manual_reviews, and sec_hook_checks into a unified findings schema. The API route `GET /api/v1/security/findings` checks whether this view has the required columns and falls back to direct table queries if not. Because all source tables are 0 rows, this view returns 0 rows regardless.

**Write-path analysis:** The `ds-security scan` SKILL.md specifies storage at `~/.dream-studio/security/scans/{client}/{repo}/{date}/` (file-backed). The `sec_sarif_findings` table was designed to receive ingested SARIF data, but no ETL script or hook connects the file store to this table. The two storage paths — skill-specified file paths and SQLite schema — are orphaned from each other.

---

### 6. Security API Routes

Located at `projections/api/routes/security.py`. Five endpoints:

| Route | Method | What it does |
|-------|--------|-------------|
| `/security/findings` | GET | Aggregates from vw_security_summary or fallback to security_findings + sec_sarif_findings. Returns 0 findings (all source tables empty). |
| `/security/sarif` | GET | Direct query of sec_sarif_findings. Returns 0 rows. |
| `/security/cve` | GET | Direct query of sec_cve_matches. Returns 0 rows. |
| `/security/reviews` | GET | Direct query of sec_manual_reviews. Returns 0 rows. |
| `/security/stats` | GET | Aggregates counts from all 5 security tables + trend over N days. All zeros. |
| `/security/sarif/import` | POST | SARIF file upload endpoint. **STUBBED** — saves to temp file, then returns `{"imported": 0, "skipped": 0, "errors": ["SARIF parser not yet implemented (task T007)"]}`. |

- **Current state:** ACCESSIBLE (endpoints exist, API starts, routes respond) but return empty data. The SARIF import endpoint is the only action endpoint, and it is explicitly stubbed pending T007.
- **Intent 2 alignment:** NO — read-only API surface. No write path from project intake to these tables.
- **Intent 3 alignment:** NO — no route enforces a gate. Routes are read surfaces for a dashboard that has nothing to display.
- **Source status field:** All GET responses include a `source_status.classification` field. With empty tables, this returns `"empty by design"` — the API is self-documenting about its emptiness.
- **Notes:** The API is complete and correct as a read surface. The gap is upstream — no data producer exists to populate the tables it reads from.

---

### 7. Security in Workflows

#### 7.1 idea-to-pr.yaml

- **Security nodes:** `review-security` (parallel with review-code, review-tests, review-perf, review-docs) using `skill: pr-security-scan`
- **Current state:** DORMANT (0 runs). Security node is architecturally wired.
- **Findings persistence:** `review-review-security-findings.md` (file). Report node saves to `~/.dream-studio/secure/reports/` (file). GitHub issues created for HIGH/CRITICAL (GitHub API call, not SQLite).
- **Intent 3 alignment:** PARTIAL — the security node exists and is parallel with other reviews. However: (a) it uses pr-security-scan not ds-security, (b) findings go to file not SQLite, (c) the workflow has never run.

#### 7.2 comprehensive-review.yaml

- **Security nodes:** `review-security` using `skill: pr-security-scan`
- **Current state:** DORMANT (0 runs). Most complete review workflow.
- **Findings persistence:** File-backed report at `~/.dream-studio/secure/reports/`. GitHub issue creation for HIGH/CRITICAL.
- **Intent 3 alignment:** PARTIAL — security review is present as a first-class parallel node. Same caveats as idea-to-pr.yaml.

#### 7.3 project-audit.yaml

- **Security nodes:** `secure` node using `skill: pr-security-scan` (note: skill name `secure` here, not `pr-security-scan` — mapping appears to be via runner alias)
- **Current state:** DORMANT (0 runs). All three review types (harden, secure, review) are parallel.
- **Findings persistence:** File-backed at `~/.dream-studio/secure/reports/`. GitHub issues for HIGH/CRITICAL.
- **Intent 3 alignment:** PARTIAL — represents the most complete gate-before-ship pattern. Dormant.

#### 7.4 security-audit.yaml

- **Security nodes:** Full pipeline — intake, generate-rules, dast-scan, binary-scan, ingest-scans (gate), mitigate + comply + netcompat-analyze (parallel, gate), post-scan-review-synthesis, dashboard-generate, executive-report
- **Current state:** DORMANT (0 runs). All ds-security modes (scan, dast, binary-scan, mitigate, comply, netcompat, dashboard) are wired here.
- **Findings persistence:** Entirely file-based. No SQLite write step.
- **Intent 2 alignment:** NO — not an intake workflow. Designed for org-level client security analysis.
- **Intent 3 alignment:** NO — on-demand client tool, not a project SDLC gate. Requires explicit invocation with a client profile.

#### 7.5 audit-to-fix.yaml

- **Security nodes:** Parameterized — when invoked with `audit=secure`, routes through `pr-security-scan`. The `audit` parameter must be explicitly passed.
- **Current state:** DORMANT (0 runs). No default security behavior.
- **Intent 3 alignment:** CONDITIONAL — can function as a security gate if caller passes the right parameter. No automatic triggering path.

#### 7.6 production-readiness.yaml

- **Security nodes:** `build-gate` node references "the 47 enterprise security controls." The workflow has a `run_policy.full_review_events` list that includes `project_intake`, `deployment`, `external_project_onboarding`, and others.
- **Current state:** DORMANT (0 runs). The `production_readiness_findings` table has 0 rows.
- **Intent 2 alignment (brownfield intake):** DOCUMENTED — `project_intake` and `external_project_onboarding` are listed as full-review events. But this workflow has never run.
- **Intent 3 alignment:** DOCUMENTED — `release_merge` and `deployment` are full-review events. But this workflow has never run, and the `persist-authority-records` node that would write to SQLite has never executed.
- **Notes:** This is the most architecturally aligned workflow for both intents 2 and 3. It references SQLite writes explicitly (`persist-authority-records` node), it covers intake and deployment events, and the `security-by-default-development-lifecycle-gate.md` contract governs its behavior. Its 0-run history is the single most significant finding for intents 2 and 3.

#### 7.7 studio-onboard.yaml

- **Security nodes:** NONE. The workflow has 13 confirmed nodes from the 2026-05-18 run (raw_workflow_nodes). No security step appears in the workflow YAML.
- **Current state:** RAN TWICE (2026-05-18). The only workflow that has actually executed.
- **Intent 2 alignment:** NOT ALIGNED — studio-onboard is the brownfield intake workflow. It has no security node. The 2026-05-18 run completed without any security audit step.
- **Intent 3 alignment:** N/A — onboarding, not deployment.

#### 7.8 pre-push.yaml

- **Security nodes:** NONE. Gates are: format-check, lint-check, skill-sync, test-suite, atlas-leak, docs-drift. No security scan.
- **Current state:** Has a registered git hook (`hooks/git/pre-push`). Activation state unclear — not in hook-timing.jsonl chain.
- **Intent 3 alignment:** NOT ALIGNED — no security gate before push.

---

### 8. Security Gate in the Work Order System

- **Gate name:** `security_scan`
- **Appears in ds_work_order_types for:** api_endpoint, authentication (also as pre-build gate via `api_contract_and_security_review`), saas_feature, data_pipeline, deployment, infrastructure — 6 of 10 types
- **Resolver location:** `core/work_orders/close.py`

**Gate resolver — confirmed implementation:**
```python
if gate_name == "security_scan":
    scan_path = wo_dir / "security-scan.md"
    if not scan_path.is_file():
        return False, "security_scan: security-scan.md not found"
    content = scan_path.read_text(encoding="utf-8")
    if "BLOCKED" in content.upper():
        return False, "security_scan: security-scan.md contains BLOCKED"
    return True, ""
```

- **What the resolver does:** Checks for the presence of a file named `security-scan.md` in the work order directory. If the file exists and does not contain the word "BLOCKED", the gate passes.
- **What the resolver does NOT do:**
  - Does not invoke ds-security
  - Does not query the `security_findings` SQLite table
  - Does not verify that a real security scan was performed
  - Does not require any finding disposition
- **Current state:** WIRED (gate logic exists and would run at work-order close time) but FILE-BASED. The gate is a file presence check masquerading as a security control.
- **Intent 1 alignment (SQLite-first):** VIOLATES — the gate resolves from a file, not SQLite.
- **Intent 3 alignment:** NAMED but not SUBSTANTIVE — the gate exists, closes the work order if the file is present, but does not enforce that a real scan ran or that findings were resolved.

---

### 9. security-by-default-development-lifecycle-gate.md Contract

- **Location:** `docs/contracts/security-by-default-development-lifecycle-gate.md`
- **What it says:** Full applicable 47-control review is required at: project intake, release/merge readiness, publication, deployment/live cutover, dependency/runtime/security/database/Docker changes, major architecture changes, external project onboarding, and scheduled dogfood gates. Findings must include project, file, line, severity, control id, status, evidence, remediation path. SQLite is the finding authority.
- **Current state:** DOCUMENTED INTENT with zero implementation. The contract specifies SQLite-backed findings, 47-control coverage, project-level applicability tracking, and intake-time review. None of these are active.
- **Intent 2 alignment:** The contract explicitly calls for security review at `project_intake` and `external_project_onboarding`. studio-onboard.yaml (the intake workflow) has no security step.
- **Intent 3 alignment:** The contract calls for security review at `release_merge` and `deployment`. pre-push.yaml has no security step. The `security_scan` gate resolves via file presence, not 47-control review.
- **Notes:** This contract is the clearest statement of what the security architecture is supposed to do. The gap between this contract and the current state is the full scope of the remediation problem.

---

## Wiring State Summary

### Catalog: WIRED / ACCESSIBLE / SCAFFOLDED / STUB

| Artifact | Type | State | Intent2 | Intent3 |
|---------|------|-------|---------|---------|
| ds-security:scan | Skill mode | ACCESSIBLE | NO | NO |
| ds-security:review | Skill mode | ACCESSIBLE | NO | NO |
| ds-security:dast | Skill mode | ACCESSIBLE | NO | NO |
| ds-security:binary-scan | Skill mode | ACCESSIBLE | NO | NO |
| ds-security:mitigate | Skill mode | ACCESSIBLE | NO | PARTIAL |
| ds-security:comply | Skill mode | ACCESSIBLE | NO | NO |
| ds-security:netcompat | Skill mode | ACCESSIBLE | NO | NO |
| ds-security:dashboard | Skill mode | ACCESSIBLE | NO | NO |
| ds-quality:pr-security-scan | Skill mode | ACCESSIBLE | NO | PARTIAL |
| on-security-scan.py hook | Hook handler | WIRED (advisory) | NO | NO |
| guardrails/enforcement.py | Guardrail module | SCAFFOLDED | NO | NO |
| guardrails/evaluator.py | Guardrail module | SCAFFOLDED | NO | NO |
| guardrails/rules/security.yaml | Guardrail rules | STUB | NO | NO |
| guardrails/scanners/giskard_scanner.py | Scanner | STUB | NO | NO |
| guardrails/scanners/llm_guard_scorer.py | Scanner | STUB | NO | NO |
| guardrails/scanners/rebuff_validator.py | Scanner | STUB | NO | NO |
| sec_cve_matches | DB table | SCAFFOLDED (0 rows) | NO | NO |
| sec_hook_checks | DB table | SCAFFOLDED (0 rows) | NO | NO |
| sec_manual_reviews | DB table | SCAFFOLDED (0 rows) | NO | NO |
| sec_sarif_findings | DB table | SCAFFOLDED (0 rows) | NO | NO |
| security_findings | DB table | SCAFFOLDED (0 rows) | NO | NO |
| guardrail_decisions | DB table | SCAFFOLDED (0 rows) | NO | NO |
| guardrail_rules_audit | DB table | SCAFFOLDED (0 rows) | NO | NO |
| hook_findings | DB table | SCAFFOLDED (0 rows) | NO | NO |
| risk_register | DB table | SCAFFOLDED (0 rows) | NO | NO |
| risk_mitigations | DB table | SCAFFOLDED (0 rows) | NO | NO |
| compliance_review_flags | DB table | SCAFFOLDED (0 rows) | NO | NO |
| production_readiness_findings | DB table | SCAFFOLDED (0 rows) | NO | NO |
| GET /security/findings | API route | ACCESSIBLE (returns 0) | NO | NO |
| GET /security/sarif | API route | ACCESSIBLE (returns 0) | NO | NO |
| GET /security/cve | API route | ACCESSIBLE (returns 0) | NO | NO |
| GET /security/reviews | API route | ACCESSIBLE (returns 0) | NO | NO |
| GET /security/stats | API route | ACCESSIBLE (returns 0) | NO | NO |
| POST /security/sarif/import | API route | STUB (T007) | NO | NO |
| idea-to-pr.yaml:review-security | Workflow node | ACCESSIBLE (dormant) | NO | PARTIAL |
| comprehensive-review.yaml:review-security | Workflow node | ACCESSIBLE (dormant) | NO | PARTIAL |
| project-audit.yaml:secure | Workflow node | ACCESSIBLE (dormant) | NO | PARTIAL |
| security-audit.yaml (all nodes) | Workflow | ACCESSIBLE (dormant) | NO | NO |
| audit-to-fix.yaml (audit=secure) | Workflow | ACCESSIBLE (dormant) | NO | PARTIAL |
| production-readiness.yaml | Workflow | SCAFFOLDED (0 runs) | PARTIAL (documented) | PARTIAL (documented) |
| studio-onboard.yaml | Workflow | WIRED (ran twice) | NO | N/A |
| pre-push.yaml | Workflow | WIRED (git hook) | N/A | NO |
| security_scan gate (WO close) | Gate resolver | WIRED (file-based) | NO | NAMED ONLY |
| security-by-default-development-lifecycle-gate.md | Contract | DOCUMENTED | DOCUMENTED | DOCUMENTED |

### State Counts

| State | Count | Notes |
|-------|-------|-------|
| WIRED | 3 | on-security-scan.py (advisory), studio-onboard.yaml (no security step), security_scan gate (file-based only) |
| ACCESSIBLE | 22 | All ds-security modes, pr-security-scan, API routes, dormant workflow nodes |
| SCAFFOLDED | 14 | guardrails/enforcement.py + evaluator.py, all security DB tables (0 rows), production-readiness.yaml |
| STUB | 5 | guardrails/rules/security.yaml (trigger events never emitted), 3 scanner stubs, SARIF import endpoint |

**Observation:** 3 things are WIRED. Of those 3, none actually satisfy Intent 2 or Intent 3. The highest-state artifacts (WIRED) are a hook that only prints advisory text, an onboarding workflow with no security step, and a gate that checks for a file's existence.

---

## Three Questions — Answered

### Q1: How Much of the Security Audit Infrastructure Exists?

The infrastructure is architecturally large and operationally empty.

**What exists:**
- 8 fully documented ds-security skill modes with SKILL.md specifications, anti-pattern guidance, storage layouts, and client profile conventions
- 1 ds-quality pr-security-scan mode wired into 3 dormant workflows
- 1 automatic security hook (on-security-scan.py) firing on every Edit/Write
- A complete guardrail evaluator (evaluator.py) with block/require_approval/advisory decision engine
- 5 guardrail security rules defined in security.yaml
- 3 scanner stub implementations (Giskard, LLM Guard, Rebuff)
- 12 security DB tables covering SARIF findings, CVE matches, manual reviews, hook checks, guardrail decisions, risk register, compliance flags, and production readiness findings
- A unified vw_security_summary view
- 6 API endpoints under /api/v1/security/*
- 6 workflows with security nodes (idea-to-pr, comprehensive-review, project-audit, security-audit, audit-to-fix, production-readiness)
- A 172-line contract document defining the security lifecycle policy
- A 47-control security review framework in docs/contracts/

**What has actually operated:**
- on-security-scan.py has fired 5 times (all advisory, no persistence)
- Zero security skill invocations
- Zero rows in any security DB table
- Zero workflow runs involving security nodes
- security_scan gate has never been reached (no work orders with api_endpoint, authentication, saas_feature, data_pipeline, deployment, or infrastructure types have been closed)

**Ratio:** The infrastructure is approximately 5-10% operational and 90-95% scaffolding.

---

### Q2: How Much of It Is Wired into Operator-Facing Workflows?

**Operator action → invocation chain → security artifact map:**

| Operator Action | Chain | Security Artifact Reached |
|----------------|-------|--------------------------|
| `ds project scope <project>` or `ds-project:scope` | scope mode → register_project, create_milestone, create_work_order → no security step | NONE |
| `workflow: studio-onboard` | studio-onboard.yaml → 13 nodes (confirmed 2 runs) → no security node | NONE |
| `workflow: idea-to-pr` | idea-to-pr.yaml → review-security node → `skill: pr-security-scan` → findings.md | pr-security-scan (dormant) |
| `workflow: production-readiness` | production-readiness.yaml → 5 nodes → persist-authority-records → production_readiness_findings | production_readiness_findings table (never run) |
| `ds workflow run pre-push` or git pre-push | pre-push.yaml → 6 gates (format, lint, skill-sync, test-suite, atlas-leak, docs-drift) | NONE |
| `ds work-order close <id>` (for api_endpoint type) | close.py → check_close_gates → security_scan gate → wo_dir/security-scan.md presence check | File presence check only |
| `ds-security scan:` (manual invocation) | scan SKILL.md → GitHub Actions workflow generation → file store at ~/.dream-studio/security/ | File store only; no SQLite |
| `GET /api/v1/security/findings` | security.py → vw_security_summary or fallback tables → 0 rows returned | Empty response |
| `POST /api/v1/security/sarif/import` | security.py → stubbed, returns T007 error | Nothing |

**Wiring summary:** Two paths exist where security artifacts are nominally reachable — the idea-to-pr/comprehensive-review/project-audit workflow chain (via pr-security-scan) and the work order close gate chain (via security_scan file check). Both are dormant (0 runs) or trivially bypassable (file presence only). No path from any operator action reaches ds-security or writes to any security DB table.

---

### Q3: What Constitutes the Gap to Intents #2 and #3?

Observation only — catalog of wiring that does not currently exist.

**For Intent 2 — Security audit during brownfield onboarding:**

1. `studio-onboard.yaml` has no security node. A security scan step (at minimum `pr-security-scan`, ideally `production-readiness` at intake level) needs to be added after discovery.

2. `ds-project:scope` mode (the SKILL.md) has no security audit step in any phase. Phase 1 (Brownfield Check) references `analyze:intelligence` only. A security step is absent from all 5 phases.

3. No invocation path connects project registration to any security skill or security DB table. When `register_project` writes to ds_projects, no downstream trigger fires a security check.

4. `production-readiness.yaml` lists `project_intake` as a full-review event in its `run_policy.full_review_events`, but the workflow is never invoked during project intake. It is not called by studio-onboard.yaml or ds-project:scope.

5. The `security-by-default-development-lifecycle-gate.md` contract states security review is required at `external_project_onboarding`, but this event type is a documented category, not a wired trigger.

**For Intent 3 — Security audit as SDLC lifecycle gate:**

6. The `security_scan` gate in `core/work_orders/close.py` resolves via file presence check (`security-scan.md`), not via any security skill invocation or SQLite query. Any operator can create this file manually and pass the gate without running a scan.

7. The `guardrails/evaluator.py` is not registered in `settings.json`. The evaluator can load `guardrails/rules/security.yaml` and emit blocking decisions, but it is never invoked. Adding one settings.json hook entry (PostToolUse Edit|Write, matching the evaluator CLI) would activate it.

8. The guardrail rules in `security.yaml` trigger on `event_type: "hook_finding.created"`, but no hook emits this event type. `on-security-scan.py` prints findings to stdout but does not write to `hook_findings` or emit `hook_finding.created`. The rule trigger event needs a producer.

9. `sec_sarif_findings` has a complete schema for receiving SARIF data, but the `POST /security/sarif/import` endpoint is stubbed (T007). No automatic path from `ds-security scan:ingest` writes to this table; the SKILL.md specifies file storage only.

10. `pre-push.yaml` has 6 gates but no security scan. A `security: pr-security-scan` node before the push gate does not exist.

11. `idea-to-pr.yaml`, `comprehensive-review.yaml`, and `project-audit.yaml` have security nodes using `pr-security-scan`, but findings from these nodes write to `.md` files, not to the `security_findings` or `sec_manual_reviews` SQLite tables. The security findings persistence for workflow-run results has no SQLite write path.

12. `production-readiness.yaml` has a `persist-authority-records` node that would write to SQLite, but this workflow has never run and is not in any default invocation path.

13. The `ds-security:review` mode (the deeper Opus-based code reviewer) is never invoked by any workflow. The workflow chain uses `pr-security-scan` (lighter). The two security review surfaces operate independently with no handoff.

14. `security_findings` table has columns for `introduced_by_agent_id`, `introduced_by_skill_id`, `introduced_by_workflow_id`, `introduced_by_hook_id` — attribution fields that would allow per-finding traceability back to the action that introduced the vulnerability. No write path populates these columns.

---

## Findings

**F01: The security infrastructure is a complete architecture with no active data producers.** Every table, every API route, every skill mode exists as a coherent system. Nothing writes to the tables. The system is a read surface without a write path.

**F02: The only automatic security mechanism (on-security-scan.py) has no persistence path.** 5 invocations, 0 findings persisted, 0 events emitted, 0 DB rows written. The hook's intent (lightweight pattern check) is implemented, but the next layer (persist finding → trigger guardrail evaluation → record decision) is absent.

**F03: The security_scan gate is a file presence check, not a scan requirement.** An operator can pass the gate for api_endpoint, authentication, saas_feature, data_pipeline, deployment, or infrastructure work orders by creating `security-scan.md` without any words in all-caps spelling "BLOCKED". This is a naming deception — the gate is named `security_scan` but does not require a scan.

**F04: Intent 2 has no implementation whatsoever.** The brownfield intake path (studio-onboard.yaml, ds-project:scope) has zero security steps. The two runs of studio-onboard.yaml confirm this — no security node appeared in the 13-node execution.

**F05: Intent 3 has documented gate names but file-based resolvers.** The gate names (`security_scan`) exist in the work order type registry. The resolver in close.py is file-based, violating Intent 1 (SQLite-first) in addition to not invoking any security skill.

**F06: The guardrail evaluator is the most complete unactivated artifact.** evaluator.py has proper CanonicalEventEnvelope emission, SQLite writes to guardrail_decisions, and a CLI interface. A single settings.json hook registration entry would activate it. The rules it would evaluate (security.yaml) have a broken trigger event (hook_finding.created never emitted), but the evaluator infrastructure is otherwise complete.

**F07: All 8 ds-security modes are client-pipeline tools, not project-level SDLC gates.** Every mode is designed for PLMarketing/Kroger org-level client work. None has a mode that operates at the project level (individual repo, individual WO). The security skill set as designed answers "how do I manage a client's security posture?" not "how do I gate my own project builds?"

**F08: The production-readiness workflow is the correct architectural answer for both intents but has never run.** production-readiness.yaml covers project_intake (Intent 2) and release_merge/deployment (Intent 3), lists SQLite writes as explicit goals (`persist-authority-records` node), and references the 47-control framework. Its 0-run history is the entire gap.

**F09: Workflow security nodes use ds-quality:pr-security-scan, not ds-security:review.** The three dormant workflows with security nodes use a lighter scan mode. The deeper ds-security:review (Opus, 3-phase methodology) has no workflow integration and has never been invoked. The investment in ds-security:review has no active utilization path.

**F10: The contract document (security-by-default-development-lifecycle-gate.md) is precise and accurate as an intent statement.** The 172-line contract specifies exactly what should exist. The gap is entirely implementation, not specification.

---

## Intent Divergence

### Intent 2 — Security audit during brownfield onboarding

**Alignment score: 0/10.** Zero implementation. The intake path (studio-onboard.yaml, ds-project:scope, register_project) has no security step in any layer — workflow YAML, SKILL.md, or function layer. The contract calls for it. The production-readiness workflow documents it. It does not execute.

### Intent 3 — Security audit as SDLC lifecycle gate

**Alignment score: 2/10.** The gate name exists in ds_work_order_types (2 points), but the resolver is file-based (−3), dormant workflows have security nodes but have never run (1 point recovered), and no workflow security finding writes to SQLite (−1). The net result is a gate that is named but not enforced, wired by name but not by substance.

### Intent 1 — SQLite-first authority (security dimension)

**Alignment score: 1/10 for security-specific state.** Security DB tables are fully schema-migrated (positive). All actual security data (scan results, findings, guardrail decisions, compliance flags) lives in files or nowhere. The `security_scan` gate resolves via file. The dashboard reports from SQLite but SQLite is empty.

### Intent 4 — Canonical events as spine (security dimension)

**Alignment score: 0/10.** No security-namespace events in canonical_events (0 of 1,853 events). The guardrail evaluator would emit proper CanonicalEventEnvelopes if activated. Nothing currently emits `security.*` or `hook_finding.*` events.

---

## Open Questions

1. **What populates `security-scan.md`?** The `security_scan` gate passes if this file exists in the work order directory without "BLOCKED". Is there a skill, workflow, or script intended to create this file? Or is it expected to be operator-written? If operator-written, the gate is trivially bypassable.

2. **Is security-audit.yaml intended as the SDLC gate, or is production-readiness.yaml?** These serve different purposes (client org-level security pipeline vs. project readiness gate), but the distinction is not enforced anywhere in the SDLC chain.

3. **What is the intended write path from `ds-security scan:ingest` to `sec_sarif_findings`?** The SKILL.md specifies file storage. The table exists. No ETL script or API endpoint currently connects them (the SARIF import endpoint is stubbed as T007). Was a separate ingest script planned?

4. **Is the `api_contract_and_security_review` pre-build gate for the authentication work order type different from `security_scan`?** It appears as a pre-build gate (not post-build) for authentication WO type. No resolver for this specific gate name exists in `core/work_orders/close.py` — it would fail the gate check with "unknown gate" or similar. This may be a configuration error in the WO type definition.

5. **What is the intended trigger for production-readiness.yaml?** It is not invoked by studio-onboard.yaml, not invoked by ds-project:scope, not invoked by any work order type as a workflow_template. Is it intended to be invoked manually by the operator, or is there a planned automatic trigger?

6. **The guardrail rules reference `event_type: "hook_finding.created"` as their trigger, but this event is never emitted. Was `on-security-scan.py` intended to emit this event type, or was there a separate hook planned?** The `hook_findings` table schema matches what `on-security-scan.py` could write if modified to persist findings.
