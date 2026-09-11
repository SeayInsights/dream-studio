---
dream_studio:
  skill_id: ds-core
  pack: core
  mode: review
  mode_type: review
  inputs: [pr_diff, commit_history, test_results, spec_reference]
  outputs: [review_comments, approval_status, change_requests, quality_score]
  capabilities_required: [Read, Grep, Bash, Agent]
  model_preference: sonnet
  estimated_duration: 15-45min
---

# Review — Two-Stage Quality Check

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Imports
- ../../git.md — read git diff, get commit SHA
- ../../quality.md — OWASP security checks, test coverage
- ../../orchestration.md — subagent review pattern, reviewer prompt template
- ../../format.md — severity-tagged findings, review findings format, verdict statement

## Trigger
`review:`, `review commits`, `review code`, `review PR:`, or after `build` completes

## Core Principle
Spec compliance BEFORE code quality. Always. Catching "built the wrong thing" matters more than "code smells."

## Stage 1: Spec Compliance Review

**Purpose:** Did we build what was requested — nothing more, nothing less?

1. Re-read the plan/spec
2. Compare implementation to requirements line by line
3. Check for:
   - **Missing requirements** — things requested but not built
   - **Extra work** — things built but not requested (over-engineering)
   - **Misunderstandings** — right feature, wrong interpretation

**Do NOT trust self-reports.** Read the actual code. Compare to the actual spec.

```
✅ Spec compliant — all requirements met, nothing extra
❌ Issues: [list what's missing/extra with file:line references]
```

**Stage 1 must pass before moving to Stage 2.** If spec issues exist, fix them first.

## Stage 2: Code Quality Review

**Purpose:** Is the implementation well-built?

1. **Scope check** — Does the code match the plan/spec? Flag anything extra.
2. **Correctness** — Logic errors, edge cases, race conditions, null handling.
3. **Security** — OWASP Top 10 scan:
   - Injection (SQL, command, XSS)
   - Broken auth / session management
   - Sensitive data exposure
   - Missing access control
   - Security misconfiguration
   - Vulnerable dependencies
4. **Test coverage** — Are critical paths tested? Edge cases covered?
5. **Code quality** — Readability, naming, duplication, complexity.
6. **File responsibility** — Each file has one clear job with a well-defined interface?
7. **Change discipline** — Commit subjects are conventional (`feat/fix/revert(scope):`), never the GitHub-UI `Revert "..."` (the revert-format guard rejects it). For a change touching auth, an API/route/schema contract, or a migration, a change-impact affirmation is recorded (`ds work-order affirm-impact`). Both are enforced at close — flag gaps here so they are not a surprise then.
8. **Silent-default / fail-quiet (negative-space lens)** — Flag code that resolves identity, authority, or required state by elimination ("anything else → default") or swallows a correctness-changing failure (`except: pass`, bare `return None` / `""` / `[]`) so it yields a plausible-but-wrong result with **no alert**. The fix is affirmative: verify and **refuse what you cannot verify** (fail loud) rather than defaulting. *See ADR-0002:* a security scan that returned all-clear when its `git` call had actually failed — a false negative reporting success precisely when it was blind.

### Stage 2 lanes from the registry

**Convene the table before you push:**

```
py -m core.gates.round_table
```

It runs the detector lanes and reports what they found, and puts the graded and declared
lanes in front of you as questions to answer against the diff. `--no-detectors` lists the
lanes without running anything and reports `unchecked`, because a listing that ran nothing
is not a pass.

`canonical/review_lanes.yml` is the source of truth for these, not this list, and this
section is GENERATED from it — a hand-maintained copy of a registry is a second
vocabulary that silently disagrees with the first.

The bench is **29 seats**: the operator's 28-seat review bench, derived from real
review history, plus the Event-substrate custodian, which asks whether a row survives
being rebuilt from its own events — a property of this substrate with no equivalent on
the bench. Each lane is answered by a runnable detector, a graded eval, or a declared
judgment; the `review-lane-registry` gate refuses a lane that is none of those.

**Lanes fire on relevance to the change set.** A seat whose scope does not match the diff
is left out and the table says so. `--all` convenes every seat regardless — asking for
the whole bench directly is always available.

Where a published standard governs a seat, the seat names it, so a finding is arguable
on the standard rather than on seniority.

1. **Chair and verdict owner** — *What is the single merge recommendation here, and is every finding's severity calibrated against it rather than stated in isolation?*
   - shape: Many opinions and no verdict. Findings arrive at assorted severities with nothing reconciling them, so the author receives twenty-seven views instead of one decision and picks whichever is cheapest.
   - answered by: declared judgment

2. **Evidence referee** — *Which SHA and which command prove this claim, and does reverting the fix actually turn the check red?*
   - shape: A claim with no reproduction. The author's summary is taken as the finding, the fix is read rather than run, and nobody checks that the guard fails when the guarded thing is broken.
   - answered by: declared judgment

3. **Reviewer's reviewer** — *Does every finding still hold against current HEAD, and which ones should be withdrawn?*
   - shape: A finding that was true at review time and is false now, or was never true. Nobody re-checks, so the author argues with a stale objection and the reviewer's overreach costs more than the defect.
   - answered by: declared judgment

4. **Merge-order steward** — *How far behind its base is this, is it the tree that actually ships, and does anything still-open have to land first?*
   - shape: A branch reviewed in isolation. It is clean against its own base, stale against main, and the merged tree behaves differently from either.
   - answered by: detector

5. **Claim and closure auditor** — *Does the PR body, the comments and the docs say what the code does, and will `Closes #N` close the right issue?*
   - shape: A description that describes an intention. Acceptance criteria partly met and reported as met, or a closing keyword pointed at an issue this head cannot satisfy.
   - standards: Conventional Commits 1.0.0, Keep a Changelog 1.1.0
   - answered by: graded eval

6. **Gate-integrity engineer** — *Is this a gate or a report? What does it do when the thing it checks is absent, unreportable, or failing?*
   - shape: A workflow that reports is not a gate. Required checks that never report because a path filter excluded them, always() where success() was meant, `bash -e` without pipefail swallowing a red plan.
   - standards: OpenSSF Scorecard, SLSA v1.0 Build L2+
   - answered by: graded eval

7. **Test-integrity inquisitor** — *This test is green. Show me it going red -- what does it look like when the thing it protects is broken?*
   - shape: An assertion true by construction, new logic with no committed test, a happy path standing in for coverage, or a flake answered with a longer timeout instead of a root cause.
   - standards: ISO/IEC/IEEE 29119-4 test techniques
   - answered by: graded eval

8. **AuthZ and identity** — *Which principal is this, what may it do, and what happens to the sessions that already exist when that answer changes?*
   - shape: Permission derive-and-intersect that widens, a token class mistaken for another, admin scope acquired by a path nobody enumerated, or a lifecycle where revocation does not revoke.
   - standards: OWASP ASVS v4.0 V4 Access Control, OWASP Top 10 A01:2021 Broken Access Control, NIST SP 800-63B session lifecycle
   - answered by: declared judgment

9. **Untrusted input and abuse limits** — *What is the full capability surface of the thing being guarded, as opposed to what the guard's own rule list says about it?*
   - shape: A guard that enumerates the attacks it knows. The format has a mechanism the rule list never named -- a PAX header, a nested archive, a decompression ratio -- and the guard reports clean.
   - standards: OWASP ASVS v4.0 V5 Validation, Sanitization and Encoding, OWASP Top 10 A03:2021 Injection, CWE-22 path traversal, CWE-409 decompression bomb
   - answered by: graded eval

10. **Secrets and data-at-rest** — *Where does this secret come to rest, who can read it there, and what rotates it?*
   - shape: A credential written somewhere durable with the wrong mode or the wrong scope -- a cluster dump in plaintext, a secret store with no condition, a PAT seeded into a script that ships.
   - standards: OWASP ASVS v4.0 V6 Stored Cryptography, CWE-312 cleartext storage of sensitive information, NIST SP 800-57 key management
   - answered by: declared judgment

11. **Supply chain and provenance** — *What exactly is being installed and published here, and does the identity signing it match the identity that built it?*
   - shape: A lockfile valid on the branch and invalid on the merge, a tag where a digest was meant, a signature check that trusts any dispatch ref, or a name that resolves to somebody else's package.
   - standards: SLSA v1.0, NIST SP 800-218 SSDF, OpenSSF Scorecard, SPDX or CycloneDX SBOM, Sigstore signature verification
   - answered by: declared judgment

12. **Cloud IAM and IaC** — *Which external identity can assume this role, and what can it reach once it has?*
   - shape: An OIDC trust subject matched loosely, a policy pairing CreateRole with PassRole on a wildcard resource, an unpinned provider, or a default region that silently places data elsewhere.
   - standards: CIS Benchmarks, NIST SP 800-53 AC family, CWE-269 improper privilege management
   - answered by: declared judgment

13. **GitOps and rollout safety** — *What is the blast radius when this reconciles automatically, and what does prune remove that nobody listed?*
   - shape: Automation whose failure mode is deletion. Self-heal and prune acting on an incomplete inventory, or an optional mount that silently disables a provider rather than failing.
   - standards: CIS Kubernetes Benchmark, NIST SP 800-190 container security
   - answered by: declared judgment

14. **Release and version model** — *Does the version this produces mean what the ecosystem consuming it thinks it means?*
   - shape: A tag treated as a release, an upgrade task scaffolded and presented as validation, or a version string that is legal here and illegal to the platform that reads it.
   - standards: Semantic Versioning 2.0.0, Keep a Changelog 1.1.0
   - answered by: declared judgment

15. **Distributed state and concurrency** — *This wait is bounded per item. How many items can there be, and does anything bound the total?*
   - shape: A per-item timeout with no aggregate deadline, a process-local cache in a multi-replica deployment, or a guard evaluated outside the transaction it is meant to protect.
   - standards: CWE-362 race condition, CWE-367 time-of-check time-of-use
   - answered by: detector

16. **Data and migration** — *Does this migration go forward and back, and does the schema still hold every invariant afterwards?*
   - shape: Forward-only in practice, numbering that collides or skips, a constraint relaxed to make a migration pass, or orphan rows nobody counted.
   - standards: ACID transaction properties, ISO/IEC 9075 SQL constraints
   - answered by: declared judgment

17. **Contract and protocol** — *The code says mechanisms X and Y make this claim true. Does the contract document name both?*
   - shape: A decision record that names one of two mechanisms. The contract is accurate about what it mentions and silent about the half that is also load bearing, so the next author removes it.
   - standards: OpenAPI 3.1, JSON Schema 2020-12, RFC 9457 problem details, Semantic Versioning 2.0.0 for API surface
   - answered by: declared judgment

18. **Failure semantics** — *The producer's vocabulary has more members than the consumer has branches. What does the far end do with the ones it does not handle?*
   - shape: A confident silent default. An unknown status becomes a plausible known one, a truncation is not reported, an exception is swallowed and the caller is told everything succeeded.
   - standards: CWE-703 improper check or handling of exceptional conditions, CWE-754 improper check for unusual conditions, Saltzer and Schroeder fail-safe defaults
   - answered by: graded eval

19. **Observability and audit trail** — *A value is produced and honestly computed. Does anything actually read it, and does every path that matters leave a record?*
   - shape: A produced value with no reader, or a failure path that returns before it audits. The diagnostic a document promises and the code never emits.
   - standards: OWASP ASVS v4.0 V7 Error Handling and Logging, OWASP Top 10 A09:2021 Security Logging and Monitoring Failures, NIST SP 800-92 log management, OpenTelemetry semantic conventions
   - answered by: graded eval

20. **Design-system conformance** — *Does this component take the promotion path, and does the styling actually reach the browser?*
   - shape: A token bypassed for a raw value, a component that never enters the barrel, or a stylesheet that is written, reviewed, merged, and never served.
   - standards: W3C Design Tokens Community Group format
   - answered by: declared judgment

21. **Accessibility** — *Can this be operated without a mouse, and does every control have a name a screen reader will say?*
   - shape: An ARIA ownership tree that does not match the visual one, a collapsed nav whose controls lose their accessible names, a tooltip with no association and no Escape.
   - standards: WCAG 2.2 Level AA, WAI-ARIA 1.2, EN 301 549, Section 508
   - answered by: declared judgment

22. **Frontend behavior and payload** — *Does this control do what it looks like it does, and what did it cost to download?*
   - shape: A control that looks live and is dead, a hooks-rules violation that only shows under a specific render order, or a payload nobody measured.
   - standards: WCAG 2.2 Level AA, Core Web Vitals
   - answered by: declared judgment

23. **CLI and operator ergonomics** — *Can an operator run this from a clean box using only what the docs say?*
   - shape: Help text that contradicts the defaults, a deprecated alias the documentation still recommends, an exit code that reports success on failure, or a runbook with a missing step.
   - standards: POSIX Utility Syntax Guidelines (IEEE Std 1003.1), GNU coding standards for command-line interfaces
   - answered by: declared judgment

24. **Agent and plugin runtime** — *What does this cap or namespace do to the model rather than to the operator?*
   - shape: A limit that misleads the thing consuming it. A silent truncation the agent reads as the whole input, a manifest placeholder that ships, an allowlist that widens a profile nobody reviewed.
   - answered by: declared judgment

25. **Mission-domain consequence** — *Weighted by mission effect rather than code severity, what is the worst thing this change permits?*
   - shape: A control enforced as vocabulary rather than as a ceiling. A marking that does not follow the data, a dissemination rule that is advisory, an air-gap assumption contradicted by a default URL.
   - standards: 32 CFR Part 2002 CUI, DoDI 5200.48 CUI marking, NIST SP 800-171, EO 13526 classification
   - answered by: declared judgment

26. **Governance canon and board** — *Does this contradict another document that is also in force?*
   - shape: Two canonical documents authorizing and forbidding the same act, an ADR edited rather than superseded, or canon propagated to one repo and not its siblings.
   - standards: ISO/IEC/IEEE 42010 architecture description
   - answered by: declared judgment

27. **Docs, style, and attribution** — *Does anything shipping here carry a name, a path, or a trailer that should not leave this machine?*
   - shape: AI attribution trailers on commits, a personal absolute path in a shipped file, a required section missing from SECURITY.md, or an entry-point link that 404s.
   - standards: Diataxis documentation framework, Keep a Changelog 1.1.0, SPDX licence identifiers
   - answered by: declared judgment

28. **Code quality and structure** — *Is this reachable, is it duplicated, and does it sit on the right side of a module boundary?*
   - shape: Dead code kept because deleting it felt risky, a second copy of a rule that must agree with the first, or a layering violation that makes the next change cost more.
   - standards: PEP 8, PEP 484 type hints, CWE-561 dead code
   - answered by: declared judgment

29. **Event-substrate custodian** — *If this record were rebuilt from its events tomorrow, would it still be here, and would it still say the same thing?*
   - shape: A row written straight into a projection. It is correct today and gone after a rebuild, or present with a field the replay could not reproduce.
   - answered by: detector

## Fast scan mode
When invoked with Haiku for fast scan:
1. Scan for: secrets, debug leftovers, obvious bugs, missing error handling
2. Output: `FAST SCAN: CLEAN` or `FAST SCAN: FINDINGS` with bullet list

## Subagent review (for larger changes)

**See:** ../../orchestration.md — Review loop pattern, reviewer prompt template

Dispatch spec reviewer first, then code quality reviewer after spec passes. Review loops continue until all issues resolved.

### The dispatched reviewer convenes the table — it does not invent a checklist

**Operator rule.** A review is run by an agent that did not write the code, and that agent
reviews through `canonical/review_lanes.yml`, not through questions it thought of on the
spot. A hand-written checklist is one agent's taste on the day; the registry is 29 seats
derived from real review history, each held to a published standard where one governs.

This is rule `dispatched-review-convenes-the-round-table` in `canonical/rules.yml`,
enforced by the tests named there. The dispatch prompt instructs the subagent to:

1. Run `py -m core.gates.round_table` (add `--json` for a machine-readable report, `--all`
   to convene the whole bench rather than the lanes relevant to this diff).
2. Report the detector lanes as the table found them — `clean`, `FOUND`, or `UNRUN`. An
   `UNRUN` lane is NOT a clean lane and must not be reported as one.
3. Answer **every** lane in the `ASKED OF YOU` section against the diff. Each answer is
   either a concrete defect with `file:line` and how it fails, or "no finding" with one
   sentence naming what was checked. A lane the reviewer did not examine is reported as
   **not examined** — never silently omitted, and never folded into "no findings".
4. Respect the lanes the table declares it is not deciding. A lane prints
   `NOT DECIDED HERE: …` for the half of its question its check does not answer; that half
   is the reviewer's to answer, which is the whole reason it is printed.
5. Report an `ABSTAINED` seat as abstained, not as clean.

**Why the subagent and not the caller.** The author of a change cannot convene a table
against their own work and have the result mean anything — the seats would be read by the
party they are meant to constrain. `ds work-order verify` convenes the table itself and
records the seats on the verdict; `independent_review` then refuses a verdict that convened
no lane. The subagent path is the same rule applied to reviews that do not run through a
work order.

**When the change set edits the table itself** — `canonical/review_lanes.yml`,
`core/gates/round_table.py`, `scripts/seat_lanes_data.py`, or
`core/gates/review_lane_registry.py` — the report says `SELF-REVIEW` at the top. The lens
and the subject are the same artifact. That is not a reason to skip the review; it is a
reason the report must not be read as independent, and a second reviewer who did not write
the registry change should answer the seats that govern review process itself
(Chair and verdict owner, Evidence referee, Reviewer's reviewer, Grader-integrity).

Each reviewer returns a JSON object matching the schema in ../../orchestration.md, extended
with the table's own output:

```json
{
  "seats": [
    {"lane": "a-write-no-event-can-reconstruct", "seat": "Event-substrate custodian",
     "answer": "no finding | not examined | <the defect>", "location": "file:line"}
  ]
}
```

The base schema:
```json
{
  "signal": "compliant | non_compliant",
  "confidence": 0.0-1.0,
  "summary": "One sentence verdict",
  "issues": [
    {
      "requirement": "the requirement from spec",
      "issue": "what is wrong",
      "location": "file:line",
      "fix": "specific, actionable fix"
    }
  ]
}
```
Parse `result.signal`: `compliant` → next stage. `non_compliant` → re-dispatch implementer with `result.issues`.

## Findings format

**See:** ../../format.md — Review findings format

Use two-stage format: Stage 1 (spec compliance) → Stage 2 (code quality with severity tags) → Summary with verdict
```

## Review to a fixed point (operator rule, 2026-09-03)

**One review round is a sample, not a verdict.** Keep reviewing until a round produces NO
CODE CHANGE. Cap: **20 rounds**.

```
round N:  independent review  ->  findings  ->  fix  ->  round N+1
converged when a round's findings require no edit to the code
```

Why the rule exists, from the run that produced it: five rounds on one branch raised 32
blocking findings, and **rounds 2 through 5 each found new defects in the fixes written for
the previous round** — several of them regressions that made the code strictly worse than
before the fix. Round 4's decisive finding was that the workflow under review could not
reach a terminal status at all, so three rounds had been spent polishing logic above a
graph that halted; round 5 then found that round 4's own fix for it had moved the dead end
to the next node rather than removing it. A single round would have shipped any of those.

Rules for running the loop:

- **A round that changes code is not converged**, however small the change. The last three
  regressions were each introduced by a "small" fix.
- **Use a CLEAN-SLATE reviewer each round.** Continuing the same agent inherits its
  conclusions; the point is a reader who has not already decided.
- **Give the reviewer the history**, not just the diff: what the previous rounds found, and
  which fixes are new. Round 5's brief listing the eight prior changes is why it could
  check whether they held.
- **Demand CONFIRMED versus PLAUSIBLE** — did the reviewer run something, or read
  something. Every confirmed finding across those five rounds was real; the split is what
  makes a report actionable rather than a worry list.
- **Hunt the three shapes that recur**, because they are invisible to a passing suite:
  a mechanism with no caller; a test that cannot fail for its stated reason; a claim the
  code does not support. Those were 26 of the 32 findings.

  Re-measure such a count when you cite it. The first version of this section said "24",
  the total through round 4, and round 5's eight findings made it stale the same day — a
  stale number inside the rule that tells you to distrust stale numbers.
- **When two consecutive rounds find defects in the previous round's fixes, SPLIT** rather
  than keep patching: land the part that drew no findings, hold the part that keeps
  regressing. That is what got the artifact-lock half shipped while the orchestrator half
  went four more rounds.
- **Hitting the cap is a finding.** 20 rounds without convergence means the change is not
  reviewable at this size — split it or reconsider the design, and record which.

## Next in pipeline
→ `verify` (once converged) or back to `build` (if findings need fixing)

## Anti-patterns
- Reviewing without reading the spec/plan first
- Skipping Stage 1 (spec compliance) and jumping to code quality
- "Looks good" with no specific findings listed
- Flagging style preferences as High severity
- Skipping security checks because "it's internal"
- Trusting self-reports instead of reading the code
- **Acting on stale findings (L1)** — before fixing any finding from a review report, verify
  it still exists: grep or read the file. Reports go stale within hours of being written.
- **Leaving findings unannotated after fixing (L5)** — after each finding is resolved, add
  `[FIXED: <commit-sha>]` inline in the review report. An unmarked report misleads the next
  session into re-fixing already-resolved issues.

## Two passes the bounded review keeps skipping (operator rule, 2026-09-08)

Claim-verification is bounded and produces clean output. Adversarial input enumeration is
open-ended. Offered both, a review takes the bounded one — measured across seven reviews in
one session, every time. These two passes are therefore MANDATORY, not optional depth.

**1. A validator is tested by CALLING it, never by mutating its input.**
When the subject is a validator, guard, gate, or parser: import it and call it with
constructed inputs — absent, empty, malformed, duplicated, out-of-order, wrong-typed —
BEFORE touching the real file. Editing the real input tests the input; it does not test the
checker. A checker that returns clean on a file you just edited has shown only that it reads
that file.

This is `compared-nothing-reported-clean` one level up: the review itself compared nothing.
Measured in one session — a survey read `result["gates"]` where the producer writes
`gates_pass`/`gate_failures`, got `None`, and reported thirteen blocked work orders as
CLOSABLE; a query used `completed` where the column holds `complete` and reported every work
order 0-done; a gate's 400-character DOTALL window named five lines containing no status
comparison at all. Each was found by RUNNING the checker against constructed input. None was
findable by reading it.

**2. Scope-to-diff bounds where you hunt. It does not bound what the diff INVALIDATES.**
Every diff gets one explicit pass asking which surrounding claims it just made false:
- a docstring or comment describing the behaviour that was replaced
- a comment quoting a literal the diff removed (which can trip the pin that forbids it)
- a test whose NAME no longer matches what it asserts
- a count, measurement, or figure quoted in a header or module docstring
- an acceptance criterion pointing at a node id the diff renamed
- a `Reviewed`/`Last reviewed` trailer whose claim the diff contradicts

Four instances in one session, all found after the review and none by it: a gate docstring
still asserting a corrected figure, a docstring claiming a module imports only the standard
library when it already imported the repo lazily, a comment quoting the literal it had just
replaced, and a parity test asserting a constant appeared inside each loop — stale the moment
the policy moved into a shared helper.

Report both passes explicitly. "No adversarial inputs found to fail" is a finding; silence
is indistinguishable from not having looked, which is the thing being corrected.
