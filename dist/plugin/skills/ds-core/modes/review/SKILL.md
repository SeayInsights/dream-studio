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

`canonical/review_lanes.yml` is the source of truth for these, not this list. Each lane is
held by a **seat at the round table**, and the seat says what it watches — the Warden (a
guard enforced on one half), the Machinist (the real machine: which lane runs, and how long
it takes), the Archivist (the record names every mechanism), the Surveyor (distance from the
tree that ships), the Herald (a caller sees something different). Each is answered by a
runnable detector, a graded eval, or a declared judgment; the `review-lane-registry` gate
refuses a lane that is none of those. Run the detectors; ask the graded ones yourself.

9. **The Warden — the other half enforced by nothing** — *two sites decide the same question; does the
   second consult every predicate the first does, or a subset?* A fix "shares the predicate"
   and shares one of the two the other site requires, under a comment saying the two cannot
   drift — true of one predicate, false of the pair. Graded:
   `tests/evals/test_review_lane_predicate_parity.py`. Not a detector on purpose: a
   prototype found 26 candidates among 421 predicates and every one was an arity difference,
   a module alias, or an unrelated decision, because parsing has no notion of *the same
   question*.
10. **The Machinist — an untested fallback lane** — *this fallback exists because the primary path can be
    unavailable; does any test enter it?* Detector: `py -m core.gates.untested_fallback`
    (diff-scoped). A fallback runs only in the condition nobody develops in, so it is the
    code most likely to be wrong and least likely to be noticed.
11. **The Machinist — a per-item wait with no aggregate deadline** — *this wait is bounded per item; how
    many items can there be, and does anything bound the total?* Detector:
    `py -m core.gates.aggregate_deadline`. Every wait bounded and nothing bounding the
    product is a stall that scales with the data.
12. **The Archivist — a contract that names one of two mechanisms** — *the code says X and Y make this claim
    true; does the decision record name both, or only the one that was there first?*
    Declared judgment: this repo has no ADRs yet, so a detector would pass vacuously.
13. **The Surveyor — a branch behind its base** — *how far behind is this, and did anyone ask it to sync?*
    Detector: `py -m core.gates.branch_freshness` (advisory). A clean trial-merge says the
    texts do not collide, not that you read the tree that will ship.
14. **The Herald — an unenumerated behaviour change** — *what does a caller see differently, and does the
    change say so?* Graded:
    `tests/evals/test_review_lane_behaviour_change_enumerated.py`. A status code becoming a
    raise, with the PR body enumerating everything except that.

## Fast scan mode
When invoked with Haiku for fast scan:
1. Scan for: secrets, debug leftovers, obvious bugs, missing error handling
2. Output: `FAST SCAN: CLEAN` or `FAST SCAN: FINDINGS` with bullet list

## Subagent review (for larger changes)

**See:** ../../orchestration.md — Review loop pattern, reviewer prompt template

Dispatch spec reviewer first, then code quality reviewer after spec passes. Review loops continue until all issues resolved.

Each reviewer returns a JSON object matching the schema in ../../orchestration.md:
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
