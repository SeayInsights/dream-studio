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
  write_posture: read-only
  lifecycle: published
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
ds review                 # the lanes this change set is relevant to
ds review --all           # the whole bench regardless of relevance
ds review --pr 812        # the files a pull request touches
ds review --no-detectors  # list the lanes without running anything
```

It runs the detector lanes and reports what they found, and puts the graded and declared
lanes in front of you as questions to answer against the diff. `--no-detectors` reports
`unchecked`, because a listing that ran nothing is not a pass.

`canonical/review_lanes.yml` is the source of truth for the bench, not this file. The
table below is GENERATED from it by `py -m integrations.compiler.review_skill --write` and
checked by the generated-artifacts gate — a hand-maintained copy of a registry is a second
vocabulary that silently disagrees with the first, and this section was one. It announced
29 seats and named four the registry no longer had.

<!-- GENERATED:bench begin -- py -m integrations.compiler.review_skill --write -->

The bench is **10 seats** and **26 lanes**: 1 answered by a detector, 6 graded by an eval, and 19 by judgment — which is what the reviewer agents are for.

| Seat | Lanes | Answered by |
| --- | --- | --- |
| Access and reach | `authz-and-identity`, `cloud-iam-and-iac`, `secrets-and-data-at-rest` | judgment |
| Boundary semantics | `a-channel-outside-the-accounting`, `a-produced-value-with-no-reader`, `a-status-the-far-end-does-not-handle` | graded |
| Chair and verdict owner | `chair-and-verdict-owner` | judgment |
| Claim integrity | `a-contract-that-names-one-of-two-mechanisms`, `an-unenumerated-behaviour-change`, `governance-canon-and-board` | graded, judgment |
| Finding integrity | `evidence-referee`, `reviewer-s-reviewer` | judgment |
| Gate and test integrity | `a-test-that-cannot-fail`, `code-quality-and-structure`, `the-other-half-enforced-by-nothing` | graded, judgment |
| Interface conformance | `accessibility`, `design-system-conformance`, `frontend-behavior-and-payload` | judgment |
| Irreversible operations | `data-and-migration`, `gitops-and-rollout-safety` | judgment |
| Publication and provenance | `release-and-version-model`, `supply-chain-and-provenance` | judgment |
| The receiver's view | `agent-and-plugin-runtime`, `cli-and-operator-ergonomics`, `docs-style-and-attribution`, `mission-domain-consequence` | detector, judgment |

Each seat but the chair compiles to an agent under `canonical/agents/review-*.md` carrying its own lanes — the question, the defect signature, the precedent it came from and the governing standard. The chair has no agent: a subagent sees only its own lanes, and reconciling findings it was never given is not a question it can answer. **The caller is the chair.**

<!-- GENERATED:bench end -->

**Lanes fire on relevance to the change set.** A seat whose scope does not match the diff
is left out and the table says so. `--all` convenes every seat regardless — asking for
the whole bench directly is always available.

Where a published standard governs a seat, the seat names it, so a finding is arguable
on the standard rather than on seniority.

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
spot. A hand-written checklist is one agent's taste on the day; the registry is derived
from real review history, each lane held to a published standard where one governs.

This is rule `dispatched-review-convenes-the-round-table` in `canonical/rules.yml`.

#### The loop

`ds review` is the CLI door to `core.gates.round_table`; every step below goes through it.
**A lane answers by testing, in a container built from the commit under review — never by
reading and opining.** That is the reason the bench is lanes and not hardcoded seats.

**1. Commit, then dispatch the round.**

```
ds review --dispatch --work-order <id>            # reviews HEAD
ds review --dispatch --work-order <id> --pr 812   # reviews the PR's head commit
```

It builds the lane image from exactly that commit (`git archive`, so uncommitted edits,
untracked files and every `studio.db` stay out), records the round on the work order, and
returns the outstanding lanes — the table's `ASKED OF YOU` section — grouped by the
reviewer that owns them. Lanes that still hold an open finding from an earlier round are
always included, so a fix cannot escape re-review by moving files. The chair's lanes come
back with a `null` reviewer: **you are the chair**. Docker must be running; without it
there is no review to dispatch, and the door says so rather than falling back to reading.

**2. Convene each reviewer, in parallel**, with the diff, its own lane ids and the work
order id. Each agent is compiled from its seat and carries the question, the defect
signature, the precedent and the standard. It tests in the lane container:

```
ds review --run "python -m pytest tests/unit/test_x.py::test_y -q" --work-order <id>
```

No network and no host state, and every run starts fresh, so a reviewer can break
anything in there. It must never modify the working tree to test something. It returns
one answer per lane:

```json
[{"lane": "a-test-that-cannot-fail",
  "verdict": "pass | finding | cannot-tell",
  "reproduction": {"command": "python -m pytest /tmp/t.py -q", "exit_code": 1},
  "evidence": "what the output shows, and file:line of the defect",
  "why": "one or two sentences tying it to the lane's signature",
  "check": "TEST-CHECK: tests/unit/test_x.py::test_y   (findings only, optional)"}]
```

**DON'T** answer the specialist lanes yourself in one pass. Until the reviewers existed
the table ended at "N lane(s) need a person", and that is exactly what happened.

**3. Record what came back.**

```
ds review --record answers.json --reviewer review-gate-and-test-integrity --work-order <id>
```

The door **re-runs every reproduction** in a fresh container from the round's image and
refuses any answer whose exit code does not match what the reviewer reported. It also
refuses a lane the reviewer was not dispatched, a finding with no evidence, and a pass or
finding with no reproduction. With Docker down it records nothing. It reports which of
that reviewer's lanes are **still unanswered**.

**4. Ask whether the review still holds the work order.**

```
ds review --status --work-order <id>              # exits 1 while it blocks
ds review --findings --work-order <id> --as-tasks  # files open findings as tasks
```

It blocks on an unanswered lane and on any open finding — **whether or not the finding
could be filed as a task**. Filing is for tracking the work; a finding with no executable
check yet blocks exactly as hard.

**5. Fix, commit, dispatch again.** Each dispatch is a new round against the new commit.
A finding is resolved only when a later round answers that lane with a verified pass, and
the record says which round resolved it — nothing is overwritten. This loop is one work
order's work, and it ends when `--status` stops blocking, not when a reviewer stops
talking.

#### What the answers must preserve

- **A lane the reviewer did not examine is reported as not examined**, never silently
  omitted and never folded into "no finding". Leaving it out of the answers does exactly
  that: `--record` lists it as unanswered, and an unanswered lane holds the work order.
- **`cannot-tell` is an answer.** Carry it. It is what keeps a lane honest when the lane
  could not be tested, and folding it into "no finding" is how a lane stops being asked
  while still appearing to be answered. It must say what would have been needed.
- **An `UNRUN` detector lane is not a clean lane** and must not be reported as one.
- **An `ABSTAINED` seat is abstained**, not clean.
- **Respect what a lane declares it is not deciding.** A lane prints `NOT DECIDED HERE: …`
  for the half of its question its check does not answer; that half is the reviewer's,
  which is the whole reason it is printed.

**Why the subagent and not the caller.** The author of a change cannot convene a table
against their own work and have the result mean anything — the seats would be read by the
party they are meant to constrain. `ds work-order verify` convenes the table itself and
records the seats on the verdict; `independent_review` then refuses a verdict that convened
no lane. The subagent path is the same rule applied to reviews that do not run through a
work order.

**When the change set edits the table itself** — `canonical/review_lanes.yml`,
`core/gates/round_table.py`, `scripts/seat_lanes_data.py`,
`core/gates/review_lane_registry.py`, `core/work_orders/review_answers.py`, or
`core/gates/lane_sandbox.py` — the report
says `SELF-REVIEW` at the top. The lens and the subject are the same artifact. That is not
a reason to skip the review; it is a reason the report must not be read as independent, and
a second reviewer who did not write the change should answer the seats that govern review
process itself (Chair and verdict owner, Finding integrity).

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
