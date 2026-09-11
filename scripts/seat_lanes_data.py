"""The operator's 28-seat review bench, plus the one seat it has no equivalent for.

WHY A DATA TABLE AND A GENERATOR RATHER THAN HAND-WRITTEN YAML. Twenty-nine seats and
thirty lanes, each owing four prose fields of at least forty characters plus exactly one
enforcement key, is a shape where a hand-typed file goes wrong silently -- a missing
`measurement` reads as an ordinary entry. The registry gate is the check, and this table
is the source, so a seat added later is one row rather than a block of YAML to imitate.

THE ELEVEN EXISTING LANES KEEP THEIR ENFORCEMENT. Each already has a working detector or
a graded eval; they are RE-SEATED onto the bench seat that asks the same question, never
rewritten. Folding them in is the point: the bench enumerates DOMAINS OF DEFECT and the
nine registered lanes enumerated SHAPES OF VERIFICATION FAILURE, and several were the
same question filed twice under two names, which is how a lane stops being falsifiable.

THE TWENTY-NINTH SEAT. Ten of the eleven map onto a bench seat. `a-write-no-event-can-
reconstruct` does not: no bench seat asks whether a row survives being rebuilt from its
own events, because that is a property of this substrate rather than of review practice.
It keeps a seat of its own, which is what makes the roster 29 and not 28.

Unit counts and PR precedents are the operator's, from real review history.
"""

from __future__ import annotations

import json
import pathlib
import re

#: seat -> (question, signature, precedent, measurement, enforcement)
#: `enforcement` is ("detector", cmd) | ("eval", path) | ("judgment", why)
SEATS: dict[str, tuple[str, str, str, str, tuple[str, str]]] = {}


def seat(name, *, question, signature, precedent, measurement, detector=None, eval=None, why=None):
    if detector:
        enforcement = ("detector", detector)
    elif eval:
        enforcement = ("eval", eval)
    else:
        enforcement = ("judgment", why)
    SEATS[name] = (question, signature, precedent, measurement, enforcement)


# ── Permanent bench (7) ──────────────────────────────────────────────────────
seat(
    "Chair and verdict owner",
    question="What is the single merge recommendation here, and is every finding's"
    " severity calibrated against it rather than stated in isolation?",
    signature="Many opinions and no verdict. Findings arrive at assorted severities with"
    " nothing reconciling them, so the author receives twenty-seven views instead of one"
    " decision and picks whichever is cheapest.",
    precedent="The review history already speaks this way -- 'Merge recommendation:"
    " request changes' -- so the verdict is an existing artefact, not a new ceremony.",
    measurement="Severity calibration is a judgement across a whole review; there is"
    " nothing to count in a single diff, and a detector that fired per-finding would be"
    " grading the parts while the seat exists to grade the whole.",
    why="A verdict is one recommendation over a set of findings that do not exist until"
    " the other seats have run, so nothing can be computed from the diff alone. It"
    " becomes an eval once convene() returns a finding set worth grading.",
)
seat(
    "Evidence referee",
    question="Which SHA and which command prove this claim, and does reverting the fix"
    " actually turn the check red?",
    signature="A claim with no reproduction. The author's summary is taken as the"
    " finding, the fix is read rather than run, and nobody checks that the guard fails"
    " when the guarded thing is broken.",
    precedent="platform#850's mutation table: enforcement verified adversarially by"
    " reverting the fix and requiring red, rather than by reading the diff. 1,185 units.",
    measurement="Whether a claim carries a reproduction is checkable in the review"
    " artefact, but whether the reproduction PROVES the claim requires running it against"
    " a mutated tree, which is a graded exercise rather than a static scan.",
    why="No review artefact in this repo yet carries a per-finding reproduction command,"
    " so there is no field to check. It becomes an eval the moment a verdict records the"
    " command that proves each finding -- which is this seat's own first deliverable.",
)
seat(
    "Reviewer's reviewer",
    question="Does every finding still hold against current HEAD, and which ones should"
    " be withdrawn?",
    signature="A finding that was true at review time and is false now, or was never"
    " true. Nobody re-checks, so the author argues with a stale objection and the"
    " reviewer's overreach costs more than the defect.",
    precedent="sarob's withdrawn ADR renumber on platform#850 and markgalpin's"
    " self-correction on dogfood-appliances#17. 215 dismissed reviews is this function"
    " happening informally.",
    measurement="Re-checking a finding means re-running its own check at a newer commit,"
    " which the finding must carry to be re-checkable at all -- so this seat depends on"
    " the Evidence referee's output and is graded on the pair.",
    why="It audits other seats' findings, which do not exist until they have run, so it"
    " has no input at diff time. It becomes an eval once a verdict carries per-finding"
    " reproductions that can be replayed at HEAD.",
)
seat(
    "Merge-order steward",
    question="How far behind its base is this, is it the tree that actually ships, and"
    " does anything still-open have to land first?",
    signature="A branch reviewed in isolation. It is clean against its own base, stale"
    " against main, and the merged tree behaves differently from either.",
    precedent="dogfood-appliances#34: a clean textual merge producing an invalid"
    " lockfile. release#140: a superseded duplicate. 1,262 units.",
    measurement="Distance from base and merge-state are both computable from git without"
    " judgement, which is why this one is a detector and not prose.",
    detector="py -m core.gates.branch_freshness",
)
seat(
    "Claim and closure auditor",
    question="Does the PR body, the comments and the docs say what the code does, and"
    " will `Closes #N` close the right issue?",
    signature="A description that describes an intention. Acceptance criteria partly met"
    " and reported as met, or a closing keyword pointed at an issue this head cannot"
    " satisfy.",
    precedent="platform#834 would have auto-closed the wrong issue; platform#701's 'this"
    " head cannot close #733'. 2,638 units, the second-largest theme.",
    measurement="Whether a caller sees something different is derivable from the diff;"
    " whether the change SAYS so is a judgement about prose, so this is graded rather"
    " than detected.",
    eval="tests/evals/test_review_lane_behaviour_change_enumerated.py",
)
seat(
    "Gate-integrity engineer",
    question="Is this a gate or a report? What does it do when the thing it checks is"
    " absent, unreportable, or failing?",
    signature="A workflow that reports is not a gate. Required checks that never report"
    " because a path filter excluded them, always() where success() was meant, `bash -e`"
    " without pipefail swallowing a red plan.",
    precedent="release#7's masked plan failure, platform#621's cached merge ref,"
    " release#141's fail-open scan matrix. 1,578 units.",
    measurement="The admitting predicate and the delivering predicate can be compared"
    " where both are code, and the disagreement is counted rather than argued -- which is"
    " what made this an eval instead of prose.",
    eval="tests/evals/test_review_lane_predicate_parity.py",
)
seat(
    "Test-integrity inquisitor",
    question="This test is green. Show me it going red -- what does it look like when the"
    " thing it protects is broken?",
    signature="An assertion true by construction, new logic with no committed test, a"
    " happy path standing in for coverage, or a flake answered with a longer timeout"
    " instead of a root cause.",
    precedent="platform#853: timeout inflation offered in place of a diagnosis. 1,923" " units.",
    measurement="Vacuity is graded, not detected: a test that cannot fail is only"
    " provable by mutating the code it guards and observing that it stays green.",
    eval="tests/evals/test_review_lane_a_test_that_cannot_fail.py",
)

# ── Security bench (5) ───────────────────────────────────────────────────────
seat(
    "AuthZ and identity",
    question="Which principal is this, what may it do, and what happens to the sessions"
    " that already exist when that answer changes?",
    signature="Permission derive-and-intersect that widens, a token class mistaken for"
    " another, admin scope acquired by a path nobody enumerated, or a lifecycle where"
    " revocation does not revoke.",
    precedent="platform#846's principal and token-class confusion; platform#533, where"
    " re-enabling an account resurrects JWTs issued before it was disabled. Largest"
    " single theme at 3,245 units.",
    measurement="Deriving the effective permission set needs the authorization model,"
    " not the diff -- two intersecting grants are correct or catastrophic depending on"
    " the principal, which no static scan of a changed file can decide.",
    why="There is no machine-readable authorization model in this repo to diff a change"
    " against. It becomes a detector the day the permission derivation is expressed as"
    " data rather than as code paths.",
)
seat(
    "Untrusted input and abuse limits",
    question="What is the full capability surface of the thing being guarded, as opposed"
    " to what the guard's own rule list says about it?",
    signature="A guard that enumerates the attacks it knows. The format has a mechanism"
    " the rule list never named -- a PAX header, a nested archive, a decompression ratio"
    " -- and the guard reports clean.",
    precedent="platform#737's PAX/tar traversal, platform#429 validating a raw request"
    " value for truthiness rather than as an id, platform#720 returning 500 where the"
    " documented path is fail-closed.",
    measurement="The gap is between a format's real surface and a rule list, and only"
    " reading the format's specification closes it -- which is a graded exercise, not a"
    " pattern a scanner can hold.",
    eval="tests/evals/test_review_lane_the_surface_outside_the_rules.py",
)
seat(
    "Secrets and data-at-rest",
    question="Where does this secret come to rest, who can read it there, and what" " rotates it?",
    signature="A credential written somewhere durable with the wrong mode or the wrong"
    " scope -- a cluster dump in plaintext, a secret store with no condition, a PAT"
    " seeded into a script that ships.",
    precedent="platform#595's plaintext cluster dumps and file modes; release#140's"
    " unconditioned ClusterSecretStore. 485 records.",
    measurement="High-entropy strings are detectable and the existing security-scan gate"
    " finds them; what this seat adds is scope and rotation, which are properties of the"
    " deployment rather than of the text.",
    why="Scope and rotation live in cluster and provider configuration this repo does not"
    " contain, so there is nothing local to compute against. The literal-secret half is"
    " already covered by the security-scan gate.",
)
seat(
    "Supply chain and provenance",
    question="What exactly is being installed and published here, and does the identity"
    " signing it match the identity that built it?",
    signature="A lockfile valid on the branch and invalid on the merge, a tag where a"
    " digest was meant, a signature check that trusts any dispatch ref, or a name that"
    " resolves to somebody else's package.",
    precedent="fulcrum-gateway#811 publishing and attesting under one identity;"
    " platform#647's signature verification trusting any dispatch ref; the third-party"
    " fulcrum PyPI name. 1,421 units.",
    measurement="Pinning and digest-versus-tag are mechanically checkable and worth a"
    " detector later; provenance -- whether the signing identity is the building identity"
    " -- needs the workflow's runtime trust relationships.",
    why="Requires resolving registry and workflow identities outside this repo. The"
    " pinning half could become a detector over lockfiles and action refs without"
    " waiting for the rest.",
)
seat(
    "Cloud IAM and IaC",
    question="Which external identity can assume this role, and what can it reach once it" " has?",
    signature="An OIDC trust subject matched loosely, a policy pairing CreateRole with"
    " PassRole on a wildcard resource, an unpinned provider, or a default region that"
    " silently places data elsewhere.",
    precedent="release#7's Azure exact-subject requirement; privilege-escalation"
    " primitives from Resource '*'; demo#6's region defaults. 315 records, nearly all in"
    " release.",
    measurement="Trust-policy subject matching is checkable against a declared allowed"
    " set, and would make a detector -- but this repo ships no Terraform or cloud IAM,"
    " so a detector here would examine zero sites and report clean forever.",
    why="No IaC in this repository for a detector to examine, and a detector that"
    " examines nothing reports clean, which is the compared-nothing-reported-clean shape"
    " this registry exists to refuse.",
)

# ── Delivery bench (2) ───────────────────────────────────────────────────────
seat(
    "GitOps and rollout safety",
    question="What is the blast radius when this reconciles automatically, and what does"
    " prune remove that nobody listed?",
    signature="Automation whose failure mode is deletion. Self-heal and prune acting on"
    " an incomplete inventory, or an optional mount that silently disables a provider"
    " rather than failing.",
    precedent="release#185, where an automated prune could remove a working HTTPS"
    " endpoint; optional: true secret mounts disabling a provider quietly.",
    measurement="Blast radius depends on live cluster inventory, which is not in the"
    " diff; the same manifest is safe or destructive depending on what is deployed.",
    why="Needs cluster state to compute what a prune would remove. Dream Studio ships no"
    " GitOps manifests today, so this seat is registered for projects that do rather"
    " than for this one.",
)
seat(
    "Release and version model",
    question="Does the version this produces mean what the ecosystem consuming it thinks"
    " it means?",
    signature="A tag treated as a release, an upgrade task scaffolded and presented as"
    " validation, or a version string that is legal here and illegal to the platform"
    " that reads it.",
    precedent="dogfood-appliances#33 treating 'tag exists' as 'content released';"
    " release#138's scaffolded upgrade tasks presented as validation; Apple's numeric"
    " CFBundleShortVersionString. 452 records.",
    measurement="Version-format law is per-ecosystem and mechanically checkable where the"
    " ecosystem is known; the harder half -- whether a tag means a release -- depends on"
    " the publishing pipeline's own semantics.",
    why="The format rules differ per target ecosystem and this repo publishes to none of"
    " them yet. The released-version sentinel is already guarded by its own migration"
    " gate.",
)

# ── Correctness bench (5) ────────────────────────────────────────────────────
seat(
    "Distributed state and concurrency",
    question="This wait is bounded per item. How many items can there be, and does"
    " anything bound the total?",
    signature="A per-item timeout with no aggregate deadline, a process-local cache in a"
    " multi-replica deployment, or a guard evaluated outside the transaction it is meant"
    " to protect.",
    precedent="platform#701's process-local cache across replicas; platform#689's guard"
    " outside the transaction; platform#696's stale-cache authorization leak; demo#68's"
    " ledger double-spend.",
    measurement="A per-item wait with no enclosing deadline is a shape visible in the"
    " code, countable across the tree, and the count was small enough to hold at zero --"
    " which is why it is a detector.",
    detector="py -m core.gates.aggregate_deadline",
)
seat(
    "Data and migration",
    question="Does this migration go forward and back, and does the schema still hold"
    " every invariant afterwards?",
    signature="Forward-only in practice, numbering that collides or skips, a constraint"
    " relaxed to make a migration pass, or orphan rows nobody counted.",
    precedent="platform#848, the migration-hygiene guard itself. 834 units.",
    measurement="Numbering, contiguity and rollback presence are mechanically checkable"
    " and this repo already has migration gates covering them; what remains is whether"
    " the data still means the same thing, which is graded.",
    why="Dream Studio already runs migration-risk and migration-authority gates for the"
    " mechanical half. This seat exists so the semantic half -- does the row still mean"
    " what it meant -- has somewhere to be asked.",
)
seat(
    "Contract and protocol",
    question="The code says mechanisms X and Y make this claim true. Does the contract"
    " document name both?",
    signature="A decision record that names one of two mechanisms. The contract is"
    " accurate about what it mentions and silent about the half that is also load"
    " bearing, so the next author removes it.",
    precedent="platform#721's response shape against the issue's acceptance criteria;"
    " fulcrum-gateway#513's spec drifting from the code. 1,207 units combined.",
    measurement="Whether a document names every mechanism the code depends on requires"
    " reading both and deciding what counts as a mechanism -- there is no list to diff"
    " against, which is why this stayed judgement.",
    why="Naming every mechanism a claim depends on requires reading the code's intent,"
    " not its text. It becomes an eval when contracts declare their mechanisms in a form"
    " a grader can compare against the diff.",
)
seat(
    "Failure semantics",
    question="The producer's vocabulary has more members than the consumer has branches."
    " What does the far end do with the ones it does not handle?",
    signature="A confident silent default. An unknown status becomes a plausible known"
    " one, a truncation is not reported, an exception is swallowed and the caller is told"
    " everything succeeded.",
    precedent="platform#583, where an unknown status becomes 'Backlog' -- a value"
    " rendered as another value's meaning. 1,952 units.",
    measurement="The two vocabularies are both readable and the gap between them is"
    " countable, but deciding whether a default is confident or correct needs the"
    " domain -- so it is graded on real translation sites.",
    eval="tests/evals/test_review_lane_status_survives_translation.py",
)
seat(
    "Observability and audit trail",
    question="A value is produced and honestly computed. Does anything actually read it,"
    " and does every path that matters leave a record?",
    signature="A produced value with no reader, or a failure path that returns before it"
    " audits. The diagnostic a document promises and the code never emits.",
    precedent="platform#495, where a token-store failure returns 503 with nothing"
    " audited. 934 units.",
    measurement="Reachability from a producer to a reader is traceable in code, but"
    " whether a reader is the RIGHT one, and whether an unaudited path matters, is a"
    " judgement the grader makes on real call chains.",
    eval="tests/evals/test_review_lane_value_reaches_a_reader.py",
)

# ── Product-surface bench (4) ────────────────────────────────────────────────
seat(
    "Design-system conformance",
    question="Does this component take the promotion path, and does the styling actually"
    " reach the browser?",
    signature="A token bypassed for a raw value, a component that never enters the"
    " barrel, or a stylesheet that is written, reviewed, merged, and never served.",
    precedent="platform#709: a 625-line stylesheet that never reached the browser. 1,545" " units.",
    measurement="Token-versus-raw-value and barrel export are both greppable and would"
    " make a detector in a repo with a design system; whether the CSS is delivered needs"
    " a build, which is the half that actually bit.",
    why="Dream Studio ships no design system or frontend bundle, so a detector would"
    " examine zero sites. Registered for the projects the round table is called from,"
    " not for this one.",
)
seat(
    "Accessibility",
    question="Can this be operated without a mouse, and does every control have a name a"
    " screen reader will say?",
    signature="An ARIA ownership tree that does not match the visual one, a collapsed nav"
    " whose controls lose their accessible names, a tooltip with no association and no"
    " Escape.",
    precedent="platform#713's ARIA ownership trees. Real but thin at 71 records --"
    " essentially one reviewer on one stack, which is itself the finding.",
    measurement="Automated accessibility checking is mature and would be a detector in a"
    " repo with markup; 71 records across one reviewer says the coverage gap is human,"
    " not tooling.",
    why="No rendered markup in this repository to check. The thinness of the evidence --"
    " one reviewer, one stack -- is the reason to register the seat rather than a reason"
    " to skip it.",
)
seat(
    "Frontend behavior and payload",
    question="Does this control do what it looks like it does, and what did it cost to"
    " download?",
    signature="A control that looks live and is dead, a hooks-rules violation that only"
    " shows under a specific render order, or a payload nobody measured.",
    precedent="platform#817's search field that looked functional and was inert;"
    " platform#834's 903 KiB reduction. 2,371 units combined.",
    measurement="Bundle size is measurable in CI and hooks rules are lintable; the"
    " looks-live-and-is-dead class needs a rendered page, which is where the expensive"
    " findings were.",
    why="No frontend in this repository. Registered so a project convening this table"
    " from its own tree is asked the question, which is the reason the table was made"
    " portable.",
)
seat(
    "CLI and operator ergonomics",
    question="Can an operator run this from a clean box using only what the docs say?",
    signature="Help text that contradicts the defaults, a deprecated alias the"
    " documentation still recommends, an exit code that reports success on failure, or a"
    " runbook with a missing step.",
    precedent="fulcrum-gateway#645's deprecated aliases still recommended by docs;"
    " fulcrum-gateway#215's help text contradicting defaults. 641 records.",
    measurement="Help text can be diffed against declared defaults mechanically, and"
    " Dream Studio is CLI-first, so this is the seat most likely to earn a real detector"
    " next -- it is judgement only because nobody has built it yet.",
    why="Comparing help text against actual default values needs a parse of both, which"
    " is buildable here and simply is not built. This is the strongest detector"
    " candidate on the bench.",
)

# ── Domain bench (3) ─────────────────────────────────────────────────────────
seat(
    "Agent and plugin runtime",
    question="What does this cap or namespace do to the model rather than to the" " operator?",
    signature="A limit that misleads the thing consuming it. A silent truncation the"
    " agent reads as the whole input, a manifest placeholder that ships, an allowlist"
    " that widens a profile nobody reviewed.",
    precedent="fulcrum-gateway#18's silent 10,000-byte truncation misleading the model;"
    " fulcrum-gateway#648's MCP allowlists in agent profiles. 824 records.",
    measurement="Manifest and placeholder checks are mechanical; the load-bearing half --"
    " a cap that misleads the model -- requires knowing what the consumer infers from a"
    " truncated value, which is judgement.",
    why="Whether a truncation misleads depends on what the consumer infers from it, and"
    " the consumer is a model. Registered because Dream Studio is an agent runtime and"
    " this is its own failure surface.",
)
seat(
    "Mission-domain consequence",
    question="Weighted by mission effect rather than code severity, what is the worst"
    " thing this change permits?",
    signature="A control enforced as vocabulary rather than as a ceiling. A marking that"
    " does not follow the data, a dissemination rule that is advisory, an air-gap"
    " assumption contradicted by a default URL.",
    precedent="platform#504's classification ceilings enforced as vocabulary;"
    " platform#673's map toggling a CUI layer and marking nothing, called the"
    " highest-weighted finding in that review; fulcrum-gateway#53's default SaaS URLs.",
    measurement="Mission weight is the seat's whole point and is not derivable from code"
    " -- the platform#673 finding was low code-severity and highest mission-severity,"
    " which no measurement of the diff would have surfaced.",
    why="Mission consequence is an external judgement about what the software is used"
    " for, and cannot be computed from the change. It is the one seat where a human"
    " re-weighting the others is the mechanism.",
)
seat(
    "Governance canon and board",
    question="Does this contradict another document that is also in force?",
    signature="Two canonical documents authorizing and forbidding the same act, an ADR"
    " edited rather than superseded, or canon propagated to one repo and not its"
    " siblings.",
    precedent="planning#28, where CONTRIBUTING authorized what TRIAGE forbade. 735" " records.",
    measurement="Cross-document contradiction needs the semantics of both documents;"
    " ADR immutability and numbering are mechanical and this repo already gates the"
    " numbering half.",
    why="Detecting that two documents contradict each other requires reading both for"
    " meaning. The mechanical half -- ADR numbering and immutability -- is already"
    " covered by existing docs gates.",
)

# ── Hygiene bench (2) ────────────────────────────────────────────────────────
seat(
    "Docs, style, and attribution",
    question="Does anything shipping here carry a name, a path, or a trailer that should"
    " not leave this machine?",
    signature="AI attribution trailers on commits, a personal absolute path in a shipped"
    " file, a required section missing from SECURITY.md, or an entry-point link that"
    " 404s.",
    precedent="dogfood-appliances#2's PII and personal paths shipping to contractors;"
    " demo#60's 404ing entry-point links. This repo removed five Co-Authored-By trailers"
    " from main on 2026-09-10 for exactly this reason.",
    measurement="Every one of these is mechanically checkable and Dream Studio already"
    " gates most of them -- operator_absolute_path, docs-drift and the atlas-leak gate --"
    " so the detector here is aggregation rather than new detection.",
    why="The constituent checks exist as separate gates already; what is missing is one"
    " lane that names them as a family so a new member is added here rather than"
    " invented somewhere else.",
)
seat(
    "Code quality and structure",
    question="Is this reachable, is it duplicated, and does it sit on the right side of a"
    " module boundary?",
    signature="Dead code kept because deleting it felt risky, a second copy of a rule"
    " that must agree with the first, or a layering violation that makes the next change"
    " cost more.",
    precedent="2,351 units, and the operator's note that this is the seat most often"
    " folded into others -- which is the argument for giving it one of its own.",
    measurement="Dead symbols and duplication are countable and Dream Studio's leanness"
    " gate already reports them; the judgement is which findings are worth acting on,"
    " which the gate deliberately leaves advisory.",
    why="The leanness gate already measures this and is advisory on purpose, because the"
    " count is large and the severity is contextual. This lane exists so the advisory"
    " output has a seat that owns triaging it.",
)

# ── The twenty-ninth: no bench equivalent ────────────────────────────────────
seat(
    "Event-substrate custodian",
    question="If this record were rebuilt from its events tomorrow, would it still be"
    " here, and would it still say the same thing?",
    signature="A row written straight into a projection. It is correct today and gone"
    " after a rebuild, or present with a field the replay could not reproduce.",
    precedent="Measured on this authority 2026-09-10: 493 of 956 work orders and 1706 of"
    " 3311 tasks had no creation event, and 459 rows held a status no event type could"
    " produce. A rebuild is the recovery tool.",
    measurement="Projection target tables are derived from each projection's own"
    " target_tables and the write sites are countable -- 6 of 6 examined and emitting --"
    " which is small enough to hold at zero, so it is a detector.",
    detector="py -m core.gates.event_backed_write",
)


# ── The industry standards each seat is measured against ─────────────────────
#
# THE OPERATOR SHIPPED WITH REVIEWERS HELD TO PUBLISHED STANDARDS, and a seat that asks a
# good question against nothing external is one person's taste. Naming the standard makes
# the finding arguable on something other than seniority, gives the author a document to
# read rather than an opinion to satisfy, and lets a lane's `why` say precisely what a
# detector would have to implement.
#
# ONLY WHERE ONE GENUINELY APPLIES. Several seats -- the Chair, the Evidence referee, the
# Reviewer's reviewer -- govern review process itself, and inventing a standard for them
# would be the decoration this registry exists to refuse. They are absent on purpose.
STANDARDS: dict[str, tuple[str, ...]] = {
    "Claim and closure auditor": ("Conventional Commits 1.0.0", "Keep a Changelog 1.1.0"),
    "Gate-integrity engineer": ("OpenSSF Scorecard", "SLSA v1.0 Build L2+"),
    "Test-integrity inquisitor": ("ISO/IEC/IEEE 29119-4 test techniques",),
    "AuthZ and identity": (
        "OWASP ASVS v4.0 V4 Access Control",
        "OWASP Top 10 A01:2021 Broken Access Control",
        "NIST SP 800-63B session lifecycle",
    ),
    "Untrusted input and abuse limits": (
        "OWASP ASVS v4.0 V5 Validation, Sanitization and Encoding",
        "OWASP Top 10 A03:2021 Injection",
        "CWE-22 path traversal",
        "CWE-409 decompression bomb",
    ),
    "Secrets and data-at-rest": (
        "OWASP ASVS v4.0 V6 Stored Cryptography",
        "CWE-312 cleartext storage of sensitive information",
        "NIST SP 800-57 key management",
    ),
    "Supply chain and provenance": (
        "SLSA v1.0",
        "NIST SP 800-218 SSDF",
        "OpenSSF Scorecard",
        "SPDX or CycloneDX SBOM",
        "Sigstore signature verification",
    ),
    "Cloud IAM and IaC": (
        "CIS Benchmarks",
        "NIST SP 800-53 AC family",
        "CWE-269 improper privilege management",
    ),
    "GitOps and rollout safety": (
        "CIS Kubernetes Benchmark",
        "NIST SP 800-190 container security",
    ),
    "Release and version model": (
        "Semantic Versioning 2.0.0",
        "Keep a Changelog 1.1.0",
    ),
    "Distributed state and concurrency": (
        "CWE-362 race condition",
        "CWE-367 time-of-check time-of-use",
    ),
    "Data and migration": ("ACID transaction properties", "ISO/IEC 9075 SQL constraints"),
    "Contract and protocol": (
        "OpenAPI 3.1",
        "JSON Schema 2020-12",
        "RFC 9457 problem details",
        "Semantic Versioning 2.0.0 for API surface",
    ),
    "Failure semantics": (
        "CWE-703 improper check or handling of exceptional conditions",
        "CWE-754 improper check for unusual conditions",
        "Saltzer and Schroeder fail-safe defaults",
    ),
    "Observability and audit trail": (
        "OWASP ASVS v4.0 V7 Error Handling and Logging",
        "OWASP Top 10 A09:2021 Security Logging and Monitoring Failures",
        "NIST SP 800-92 log management",
        "OpenTelemetry semantic conventions",
    ),
    "Design-system conformance": ("W3C Design Tokens Community Group format",),
    "Accessibility": (
        "WCAG 2.2 Level AA",
        "WAI-ARIA 1.2",
        "EN 301 549",
        "Section 508",
    ),
    "Frontend behavior and payload": ("WCAG 2.2 Level AA", "Core Web Vitals"),
    "CLI and operator ergonomics": (
        "POSIX Utility Syntax Guidelines (IEEE Std 1003.1)",
        "GNU coding standards for command-line interfaces",
    ),
    "Mission-domain consequence": (
        "32 CFR Part 2002 CUI",
        "DoDI 5200.48 CUI marking",
        "NIST SP 800-171",
        "EO 13526 classification",
    ),
    "Governance canon and board": ("ISO/IEC/IEEE 42010 architecture description",),
    "Docs, style, and attribution": (
        "Diataxis documentation framework",
        "Keep a Changelog 1.1.0",
        "SPDX licence identifiers",
    ),
    "Code quality and structure": (
        "PEP 8",
        "PEP 484 type hints",
        "CWE-561 dead code",
    ),
}


#: Seats holding a SECOND lane. The Machinist and the Interpreter each held two before
#: this roster existed, and folding every seat down to one lane would have silently
#: dropped `an-untested-fallback-lane` -- a detector that runs today.
EXTRA_LANES: dict[str, tuple[str, str, str, str, tuple[str, str]]] = {
    "Test-integrity inquisitor": (
        "This fallback exists because the primary path can be unavailable. Does any test"
        " ever take it?",
        "A fallback nothing exercises. It is written for the day the primary path fails,"
        " and the first time it runs in anger is the first time it runs at all.",
        "Carried from the Machinist's lane, which found untested fallback branches across"
        " this tree and has held the count at zero since.",
        "Fallback branches are countable in the source and the count was small enough to"
        " drive to zero and hold, which is what made a detector the right instrument.",
        ("detector", "py -m core.gates.untested_fallback"),
    ),
}


# ── Relevance scope ──────────────────────────────────────────────────────────
#
# THE OPERATOR'S STANDING DIRECTIVE IS THAT CAPABILITIES FIRE ON RELEVANCE, and with 20
# judgment lanes printing unconditionally the table became a wall nobody reads -- which is
# the Machinist's own signature turned on the review surface. A one-line CSS change must
# not be asked about OIDC trust subjects.
#
# CONSERVATIVE BY CONSTRUCTION: a lane with NO scope always fires. Only seats whose domain
# is unambiguously bound to a file shape are scoped, because the cost of wrongly hiding a
# lane is a defect nobody was asked about, while the cost of wrongly showing one is a line
# of output. Absence here means "always relevant", not "forgotten".
SCOPES: dict[str, tuple[str, ...]] = {
    "Cloud IAM and IaC": ("*.tf", "*.tfvars", "**/terraform/**", "**/*iam*"),
    "GitOps and rollout safety": (
        "**/k8s/**",
        "**/helm/**",
        "**/kustomize/**",
        "**/charts/**",
        "**/zarf*",
    ),
    "Supply chain and provenance": (
        "requirements*.txt",
        "**/*.lock",
        "package.json",
        "pyproject.toml",
        ".github/workflows/**",
        "**/uv.lock",
    ),
    "Gate-integrity engineer": (
        ".github/workflows/**",
        "canonical/workflows/**",
        "core/gates/**",
        "hooks/**",
        "runtime/hooks/**",
    ),
    "Data and migration": ("**/migrations/**", "**/*.sql", "core/event_store/**"),
    "CLI and operator ergonomics": ("interfaces/cli/**", "**/*runbook*", "docs/operations/**"),
    "Design-system conformance": ("**/*.css", "**/*.scss", "**/*.tsx", "**/*.jsx"),
    "Accessibility": ("**/*.html", "**/*.tsx", "**/*.jsx", "**/*.vue"),
    "Frontend behavior and payload": (
        "**/*.tsx",
        "**/*.jsx",
        "**/*.ts",
        "**/*.js",
        "**/*.css",
    ),
    "Agent and plugin runtime": (
        "canonical/skills/**",
        "canonical/agents/**",
        ".mcp.json",
        "integrations/marketplace/**",
    ),
    "Governance canon and board": ("docs/**", "canonical/**", "*.md"),
    "Docs, style, and attribution": ("docs/**", "*.md", "**/*.md"),
    "Secrets and data-at-rest": (
        "**/*.env*",
        "**/secret*",
        "**/*credential*",
        ".github/workflows/**",
    ),
    "Release and version model": (
        "**/.released_version",
        "**/version*",
        ".github/workflows/**",
        "CHANGELOG.md",
    ),
}


# ── The eleven lanes that already existed, carried over VERBATIM ─────────────
#
# The rename was meant to be only a rename. Regenerating these from fresh prose destroyed the
# evidence they carried -- measurements recording 421 predicates prototyped and
# rejected, 2108 dict keys, 6249 test functions, 4 formats with their channel counts --
# and an independent reviewer caught it through the eval fixtures, which assert on those
# exact numbers. A measurement is the load-bearing field: it is how a lane claiming "not
# detectable" shows its work, and rewriting it as description threw that away.
#
# So the original question, signature, precedent, measurement and enforcement are
# carried verbatim from the registry as it stood at 772f721f~1. Only the seat changes.
RESEATED: dict[str, dict] = {
    "the-other-half-enforced-by-nothing": {
        "seat": "Gate-integrity engineer",
        "question": "Two sites decide the same question. Does "
        "the second consult every predicate the "
        "first does, or a subset of them?",
        "signature": 'A fix makes site B "share the predicate" '
        "with site A, and shares one of the two "
        "that A actually requires. The comment "
        "claims the two cannot drift; that is "
        "true of one predicate and false of the "
        "pair.",
        "precedent": "The Warden, plat#814 (blocker-class, and "
        "the same defect the Herald had blocked "
        "on). Delivery shared `_pat_rejected` "
        "(revoked-or-expired) with the acceptance "
        "paths at app/auth.py:393+396 and :409 — "
        "but those also require "
        "`_user_is_active`, and delivery "
        "consulted only the first. Reproduced "
        "with a control: a disabled account had "
        "`_pat_rejected=False`, "
        "`_user_is_active=False`, auth "
        "accepts=False, file written=True. A "
        "credential was DELIVERED that "
        "authentication refuses. The Herald's "
        'sentence — "treats expired PATs as '
        "deliverable even though authentication "
        'rejects them" — applied verbatim with '
        "`disabled` swapped for `expired`.",
        "measurement": "A DETECTOR WAS PROTOTYPED AND REJECTED "
        "ON EVIDENCE. Collecting every private "
        "predicate consulted in a boolean test "
        "across the tree found 421 of them and "
        '26 "subset-suspects" — and '
        "spot-checking the 26 showed they are "
        "arity differences "
        "(`_table_exists(conn)` beside "
        "`_table_exists(conn, table)`), module "
        "aliases (`_yaml`), and unrelated "
        "decisions in different files. The "
        'detector has no notion of "the same '
        'question", which is the entire content '
        "of the finding. So this lane is "
        "graded, and the number is recorded "
        "here so the next person does not "
        "re-derive it.",
        "enforcement": ("eval", "tests/evals/test_review_lane_predicate_parity.py"),
    },
    "an-untested-fallback-lane": {
        "seat": "Test-integrity inquisitor",
        "question": "This fallback exists because the primary path can "
        "be unavailable. Does any test ever enter it, or do "
        "they all take the primary path?",
        "signature": "A platform or exception fallback whose tests all "
        "run the other branch — so the test that validates "
        "the fix cannot run on the platform the fallback "
        "exists for.",
        "precedent": "The Machinist, gw#858. `fallback_lock` / "
        "`_pending_queue_thread_lock` had zero test hits; "
        "every ack test ran the flock path. The Windows "
        "lane the docstring promised was unexercised.",
        "measurement": "Deterministic and diff-scoped. Measured 10 "
        "candidates across 944 product files with "
        "name-and-handler detection alone; 14 once an "
        "audit forced the detector to also see "
        "PLATFORM-CONDITIONAL fallbacks, which it had "
        "been blind to — and gw#858 was a Windows lane, "
        "so the detector could not see the shape of its "
        "own precedent. Diff-scoped because those 10 "
        "stand today: whole-tree would be a wall on day "
        "one, and the backlog drains as those files are "
        "touched — the ratchet `normative-baseline` and "
        "`workflow-node-verification` already use.",
        "enforcement": ("detector", "py -m core.gates.untested_fallback"),
    },
    "a-per-item-wait-with-no-aggregate-deadline": {
        "seat": "Distributed state and concurrency",
        "question": "This wait is bounded per item. "
        "How many items can there be, and "
        "does anything bound the total?",
        "signature": "A module that already solved "
        "unbounded stall for one loop "
        "grows a per-item retry in "
        "another, with no aggregate "
        "deadline — so the ceiling "
        "multiplies by a data-dependent "
        "count and passes the timeout the "
        "module itself cites.",
        "precedent": "The Machinist, gw#849 — the "
        "strongest finding of the pass. "
        "The module's own comment 40 "
        "lines above the new code says a "
        "per-slug ceiling times an "
        "agent's skill count is loop "
        "stall time, and set "
        "`_LOCK_BATCH_BUDGET_S = 5.0` for "
        "exactly that reason. The new "
        "per-card retry was 2 sleeps x "
        "0.5s inside `for sid in ids:` "
        "with no aggregate deadline: ~20s "
        "at 20 equipped skills, plus the "
        "equip retry's own 1.0s, scaling "
        "linearly past the 30s timeout "
        "the operator control surface "
        "uses.",
        "measurement": "Deterministic ONLY once "
        "sharpened to the "
        "multiplication shape, and the "
        "sharpening came from a false "
        "positive. The first cut — a "
        "sleep in a loop, in a module "
        "that defines a budget constant "
        "— found 1 candidate, "
        "`core/work_orders/artifacts.py:216`, "
        "and reading it showed "
        "`_LOCK_ATTEMPTS = 4` with a "
        "0.15s backoff: 0.90s worst "
        "case, not inside any outer "
        "per-item loop. Bounded, and "
        "not the finding. Requiring "
        "NESTING — a sleeping loop "
        "inside another loop, neither "
        "consulting a deadline — drops "
        "DS's tree to 0, so this one "
        "runs whole-tree rather than "
        "diff-scoped.",
        "enforcement": ("detector", "py -m " "core.gates.aggregate_deadline"),
    },
    "a-contract-that-names-one-of-two-mechanisms": {
        "seat": "Contract and protocol",
        "question": "The code says mechanisms X and Y "
        "make this claim true. Does the "
        "contract document name both, or "
        "only the one that was there "
        "first?",
        "signature": "A normative line is generic "
        "enough to stay true while the "
        "decision record beneath it "
        "still names a single mechanism "
        "— so availability now rests on "
        "two things and the contract "
        "admits one.",
        "precedent": "The Archivist. The spec's "
        "normative line "
        "(GATEWAY-HOSTED-AGENT-SESSION-001:274, "
        '"a transient failure is '
        "absorbed by retrying the "
        'fetch") is generic and '
        "genuinely true. But ADR-024 "
        'point 4 still says "The equip '
        'fetch retries", naming one of '
        "the two mechanisms availability "
        "now depends on, while the "
        "code's own docstring says the "
        'per-card retry "is what makes '
        "gw-ADR-024's availability claim "
        'true rather than aspirational." '
        "Same shape he blocked #837 on.",
        "measurement": "MEASURED AS ZERO SUBSTRATE, "
        "which is why this is the one "
        "lane with no detector and no "
        "eval. `docs/adr/` contains "
        "exactly two files, "
        "`ADR-000-template.md` and "
        "`README.md` — no decision "
        "record has been written, so "
        "there is nothing for a "
        "checker to compare a code "
        "claim against. A detector "
        "would grep for `ADR-\\d+` "
        "citations, collect the "
        "mechanisms citing each, and "
        "assert the record names them; "
        "against zero records it would "
        "pass vacuously, which reads "
        "like enforcement and is not. "
        "This lane was ALSO the one an "
        "audit caught with no "
        "`measurement` field at all, "
        "while the registry header "
        "claimed every lane carries "
        "one — so the gate now "
        "requires it.",
        "enforcement": (
            "judgment",
            "THERE IS NOTHING TO CHECK "
            "AGAINST YET. This lane "
            "compares a code claim to the "
            "decision record it cites, "
            "and `docs/adr/` in this repo "
            "holds only "
            "`ADR-000-template.md` and a "
            "README — no ADR has been "
            "written. A detector would "
            "grep for `ADR-\\d+` "
            "citations, collect the "
            "mechanisms citing each one, "
            "and assert the ADR names "
            "them; with zero ADRs it "
            "would pass vacuously, which "
            "is worse than an honest "
            "declaration. Convert this "
            "lane the moment the first "
            "real ADR lands.",
        ),
    },
    "a-branch-behind-its-base": {
        "seat": "Merge-order steward",
        "question": "How far behind its base is this branch, and did " "anyone ask it to sync?",
        "signature": "A PR that trial-merges clean while being far "
        "enough behind that the review read a tree nobody "
        "will ship.",
        "precedent": "The Surveyor. In the pasted pass plat#812 and #814 "
        "were 38 commits behind and gw#849 and #858 were 5 "
        "behind; all four trial-merged clean, and the "
        "Herald asked #812 to sync explicitly. Clean "
        "trial-merge is not currency.",
        "measurement": "Trivially deterministic — `git rev-list --count "
        "HEAD..origin/main` — and currently PROSE: "
        'CLAUDE.md says "Never push to stale/old branches '
        '— check branch freshness first", enforced by '
        "nothing. ADVISORY rather than blocking, because "
        "a deliberately behind branch is legitimate (a "
        "revert, a hotfix off a tag) and blocking it "
        "would be a wall; the lane's job is that nobody "
        "reviews a stale tree without knowing it.",
        "enforcement": ("detector", "py -m core.gates.branch_freshness"),
    },
    "an-unenumerated-behaviour-change": {
        "seat": "Claim and closure auditor",
        "question": "What does a caller see differently after "
        "this change, and does the change say so?",
        "signature": "A response contract changes — a status "
        "code, a new raise on an existing path, a "
        "changed return type — and the PR body "
        "enumerates everything except that.",
        "precedent": "The Herald, gw#858. A second ack now "
        "raises instead of returning 200, and the "
        "consumer is the local UI. The change was "
        "real, the body did not name it.",
        "measurement": "A SIBLING OF AN EXISTING GATE, not a new "
        "one. `evidence-backed-output` already "
        "audits what a push publishes — the "
        "commit messages of the commits being "
        "pushed and the lines added to "
        'CHANGELOG.md — so the mechanism for "the '
        'outbound document must say it" exists. '
        "What is missing is the diff side: "
        "recognising that a 200 became a raise. "
        "That half is graded for now because "
        '"what a caller sees differently" is not '
        "decidable from a textual diff in "
        "general, and the honest move is to "
        "extend the existing gate rather than "
        "stand up a second one that audits the "
        "same documents.",
        "enforcement": ("eval", "tests/evals/test_review_lane_behaviour_change_enumerated.py"),
    },
    "a-produced-value-with-no-reader": {
        "seat": "Observability and audit trail",
        "question": "A value is produced and honestly computed. "
        "Does anything actually read it, and when "
        "nothing does, what does the default say in "
        "its place?",
        "signature": "A producer returns several fields; the "
        "consumer destructures one. The unread field "
        'would have said "still loading" or "the '
        'request failed", so a fallback speaks '
        "instead -- and the fallback MAKES A "
        "POSITIVE CLAIM. A placeholder reading "
        '"no_data" is indistinguishable from a real '
        "measurement of nothing, so a broken fetch "
        "and an empty result render identically. A "
        'fallback admitting "unknown" would be '
        "untidy; one asserting a measurement is the "
        "compared-nothing-reported-clean family.",
        "precedent": "The Interpreter, an external review pass. A "
        "fetch hook returned `{get, isLoading, "
        "stateById}` and both views destructured "
        "only `get`, so `isLoading` and `stateById` "
        "had no production consumer and a failed "
        "fetch drew a hollow radar claiming "
        '"measured, nothing found". An earlier '
        "review of the same code had reasoned that a "
        "spinner keyed off `isLoading` would hang "
        "forever; the finder checked and there was "
        "no spinner. In this repo the same shape is "
        "WO 48bd8ab3 (2026-09-09): "
        "`contract_docs_drift_gate` filtered domains "
        "on `status`, a key the dicts do not carry "
        "(they carry `freshness_status`), so "
        "`record_gate_bypass` was unreachable -- 350 "
        "recorded bypasses across 16 gates and zero "
        "for docs-drift.",
        "measurement": "A DETECTOR WAS PROTOTYPED AND REJECTED ON "
        "EVIDENCE. Collecting every string key "
        "returned in a dict literal across `git "
        "ls-files '*.py'` and subtracting every "
        "key read anywhere as a subscript, a "
        "`.get()`/`.pop()`/`.setdefault()` "
        "argument or an `in` test measured 2108 "
        "distinct keys produced, 588 never read "
        "in-tree, across 198 files. Sampling "
        "showed why that count is a wall rather "
        "than a finding: most are API response "
        "fields consumed by the dashboard, or keys "
        "serialised to JSON for a reader outside "
        "Python entirely. A consumer in another "
        "language is invisible to the analysis, "
        "which is precisely the shape of the "
        "precedent -- a React view reading a "
        "Python-shaped hook -- so a detector would "
        "fire 588 times and still miss the "
        "instance that created the lane. Graded "
        "against a fixture instead.",
        "enforcement": ("eval", "tests/evals/test_review_lane_value_reaches_a_reader.py"),
    },
    "a-status-the-far-end-does-not-handle": {
        "seat": "Failure semantics",
        "question": "The producer's vocabulary has more "
        "members than the consumer has branches. "
        "What does the consumer render for the "
        "member it does not know?",
        "signature": "A status enum grows a member -- or "
        "always had one -- and the consumer "
        "branches on the ones it knows and lets "
        "the rest fall to a default. The "
        "default is a MEMBER OF THE SAME "
        "VOCABULARY rather than an error, so "
        "the unknown status renders as a "
        "different, plausible reading instead "
        "of failing. Checking that the KEYS "
        "match the producer is what makes this "
        "easy to miss: the envelope is verified "
        "and the meaning inside it is not.",
        "precedent": "The Interpreter, the same external "
        "review pass. "
        "`measure_network_reliability` emits "
        "`not_applicable` today for agents that "
        "do not heartbeat; the radar renderer "
        "branched on its known statuses and let "
        "the rest fall through to a numeric "
        "zero, drawing a normal-weight spoke to "
        "the centre vertex -- reading as 0% "
        "uptime for an agent whose uptime was "
        "never measurable. The finder's "
        'diagnosis: "I checked that the six '
        "axis keys matched the server and never "
        'asked what the statuses render as."',
        "measurement": "SEPARATED FROM ITS SIBLING LANE "
        "DELIBERATELY, after asking what each "
        "remedy is: there the consumer does "
        "not exist and the fix is to add one; "
        "here the consumer exists and is "
        "wrong, and the fix is to make its "
        "branch set match the producer's "
        "vocabulary or fail loudly on a "
        "member it does not know. One lane "
        "answering both would carry two "
        "questions and one verdict, which is "
        "how a lane stops being falsifiable. "
        "Graded for the same measured reason "
        "as the sibling -- the 588-of-2108 "
        "analysis that cannot see a "
        "non-Python consumer cannot see a "
        "non-Python branch set either -- and "
        "additionally because a vocabulary "
        "member can arrive from a database "
        "column, a config file or a "
        "provider's API without appearing as "
        "a literal anywhere, so a detector "
        "restricted to the both-sides-Python "
        "case would pass on the very shape "
        "that produced the finding.",
        "enforcement": ("eval", "tests/evals/test_review_lane_status_survives_translation.py"),
    },
    "a-test-that-cannot-fail": {
        "seat": "Test-integrity inquisitor",
        "question": "This test is green. Show me it going red — what does "
        "it look like when the thing it guards is broken?",
        "signature": "A test with assertions on computed values, reading "
        "as thorough, whose verdict does not actually depend "
        "on the thing it tests. It passes against the "
        "correct code AND against the defect it claims to "
        "catch. Often it has MORE assertions than a real "
        'test of the same subject, which is why "it has '
        'assertions" and "it can fail" get confused. Two '
        "ordinary shapes: it only ever passes inputs that "
        "should succeed, so the refusing branch is never "
        "exercised; or it asserts on a value the test itself "
        "constructed rather than on the subject's answer.",
        "precedent": "The most productive family in this repo, and every "
        "instance was found by an independent auditor rather "
        "than by the suite containing it. WO a9fa2368: a "
        "non-mutation test hashed the live database's FILE "
        "BYTES, so it failed WITHOUT a mutation (WAL "
        "checkpointing rewrites those bytes on a benign "
        "read) and could not fail FOR the real reason "
        "(conftest redirects the database session-wide, so "
        "nothing in pytest reaches the live file) -- proved "
        "by removing the override and watching a "
        "connection-recording version still pass. WO "
        "5db3755e: a control test asserted a hand-typed "
        "table of booleans against itself, never executing "
        "the fixture it claimed to reproduce; two further "
        "tautologies passed under a checker mutated to "
        "report nothing. WO eac7f657: a coverage report and "
        "the executor shared a PATTERN but each applied it, "
        "and deleting the report's own `.strip()` left all "
        "30 of its tests green while an indented ` "
        "TEST-CHECK: x` became a criterion the executor runs "
        "and the report calls prose.",
        "measurement": "TWO STATIC SHAPES WERE PROTOTYPED AND BOTH "
        "REJECTED. Across 6249 test functions, 79 have no "
        "assertion of any kind and 3 assert only on "
        "literals. Both populations are almost entirely "
        "legitimate: the 79 are "
        "`tests/evals/test_dependency_chain.py`'s "
        "deliberate `*_unknown` / `*_untested` markers, "
        "which exist to record what is NOT covered, and "
        "the 3 are intentional probes for other gates. "
        "Decisively, zero of the real instances above "
        "would have been caught -- every one had "
        "assertions on computed values. A detector would "
        "flag 82 legitimate tests and none of the defects, "
        "which is a wall and decoration at once. The only "
        "reliable answer is to mutate the subject and "
        "watch, which is a reviewer's act rather than a "
        "gate's.",
        "enforcement": ("eval", "tests/evals/test_review_lane_a_test_that_cannot_fail.py"),
    },
    "a-write-no-event-can-reconstruct": {
        "seat": "Event-substrate custodian",
        "question": "If this record were rebuilt from its events "
        "tomorrow, would it still be here?",
        "signature": "A row written straight into a projection "
        "table, with no canonical event beside it. "
        "Nothing fails and the row reads as "
        "durable, because the projection is a real "
        "table and the write really happened -- but "
        "`pre_rebuild` truncates that table before "
        "replaying events, so a replay cannot "
        "reconstruct what no event describes. Often "
        "arrives by copying a sibling write site "
        "rather than the designated writer.",
        "precedent": "The Custodian, WO 17466550, measured "
        "2026-09-10: 493 of 949 work orders and "
        "1706 of 3286 tasks in the live authority "
        "carry no creation event, so a rebuild "
        "deletes 52% of both -- and a rebuild is "
        "the disaster-recovery tool, so the defect "
        "bites hardest exactly when it is reached "
        "for. Verified by resolution rather than by "
        "reading the comment that asserts it: "
        "`pre_rebuild` is absent from both "
        "projections' `__dict__` and both bind to "
        "`framework_projection.py`, whose default "
        "does `DELETE FROM` each declared target. "
        "The source was one unfixed sibling -- "
        "`_insert_gap_work_orders` writes both "
        "tables with no event, while "
        "`_attach_gap_tasks` was fixed and carries "
        'a comment saying its author "copied the '
        "shape of the sibling-spawn INSERT instead "
        "of the task-creation path in "
        'mutations.py", naming this exact function '
        "as the wrong shape and never returning to "
        "it. Related: WO a08206a9, where ownership "
        "records SHAs that squash-merge discarded "
        "(10 of 35 on one work order), and WO "
        "6935afa5, where a drain writes status with "
        "no event.",
        "measurement": "A DETECTOR, AND THE COUNT IS WHY. The "
        "target tables are DERIVED from each "
        "projection's own `target_tables` "
        "declaration -- the set `pre_rebuild` "
        "truncates, so the actual blast radius -- "
        "which measures 6 tables rather than the "
        "2 this defect was found in; a hardcoded "
        "list would have exempted the other 4, "
        "the same subset-of-what-it-writes shape "
        "as WO b56cca8a. Across the tree, 214 "
        "functions INSERT into one of those "
        "tables and 211 emit no event, but only 4 "
        "are outside `tests/`: a fixture building "
        "rows directly is what a fixture IS, so "
        "tests are out of scope. Of the 4, three "
        "are `prove`'s DISPOSABLE scratch "
        "authority (declared at the site, since "
        "emitting there would write the "
        "operator's live spool -- the defect WO "
        "8bd297f1 fixed, 4194 connections "
        "measured) and one is the genuine "
        "finding. So the gate reports exactly 1, "
        "which is small enough to hold at zero. "
        "ADVISORY until WO 17466550 fixes that "
        "write, because a blocking gate that "
        "ships red teaches people to bypass it.",
        "enforcement": ("detector", "py -m core.gates.event_backed_write"),
    },
    "a-channel-outside-the-accounting": {
        "seat": "Untrusted input and abuse limits",
        "question": "What is the full capability surface of the "
        "thing being guarded, independent of what "
        "the guard says about itself?",
        "signature": "A guard declares its dimensions -- caps, "
        "allowed values, a rule -- and enforces "
        "every one correctly. The adversarial "
        "inputs are derived from that list, so they "
        "all probe stated limits and all get "
        "refused, and the review reports the guard "
        "safe. The defect is a mechanism of the "
        "underlying FORMAT or LIBRARY that the "
        "guard's accounting never sees: bytes "
        "consumed and expanded internally before "
        "anything is handed back, so no accounting "
        "the caller writes can count them. Three "
        "variants of one shape: verifying that a "
        "rule is ENFORCED rather than whether the "
        "rule is RIGHT; verifying a producer's "
        "transitions rather than what RENDERS; "
        "verifying the caps a guard DECLARES rather "
        "than a channel outside its accounting. "
        "Each time the review took its frame from "
        "the artifact under review.",
        "precedent": "The Cartographer, an external review pass "
        "on `_declaration_members`. A reviewer "
        "built ten archives -- a member over the "
        "per-member cap, members summing past the "
        "total cap, more members than the member "
        "cap, the wrong container, empty bytes -- "
        'ran them through the guard and wrote "Ten '
        "for ten, on both container formats... "
        "genuinely safe rather than merely "
        'bounded." PAX headers and GNU long-name '
        "were reachable the whole time, because "
        "`tarfile` consumes and expands the header "
        "internally and yields only the regular "
        "member, so `member.isfile()` never sees "
        "it. Every one of the ten cases was derived "
        "from a limit the guard declares, and PAX "
        "is not a way to exceed a declared cap. "
        "THREE PASSES MISSED IT -- the author "
        "twice, plus a review of this module "
        "specifically for security -- and it was "
        "found by reasoning about `tarfile` rather "
        "than about the guard, which is what makes "
        "it a missing question rather than a lapse. "
        "The recorded correction: derive "
        "adversarial inputs from the parser's "
        "capability surface (PAX, GNU "
        "long-name/long-link, sparse members, "
        "nested compression), not the guard's rule "
        "list.",
        "measurement": "A DETECTOR WAS PROTOTYPED, MEASURED "
        "SMALL, AND REJECTED ANYWAY -- for a "
        "better reason than volume. For each "
        "format this repo parses in production, "
        "it asked whether the test corpus "
        "mentions that format's documented side "
        "channels: 4 formats, being csv (5 "
        "production sites, 0 of 3 channels named "
        "in tests), json (275 sites, 1 of 4), "
        "yaml (43 sites, 3 of 5) and zipfile (3 "
        "sites, 1 of 4). Four rows is actionable, "
        "not a wall, and it did surface a real "
        "gap. It is not shipped because THE "
        "SIGNAL IS A GREP STANDING IN FOR A "
        "DRIVE: \"the string 'pax' occurs "
        'somewhere under tests/" is not evidence '
        "that any guard was ever driven with a "
        "PAX header, and that substitution is "
        "precisely what "
        "`core/gates/deterministic_evidence.py` "
        "exists to report -- a gate committing "
        "the defect the repo already has a gate "
        "against would report coverage this repo "
        "does not have. Neither is the lane a "
        "detector by nature: the capability "
        "surface of a library is documented in "
        "the library, and no static read of this "
        "repo can enumerate what `tarfile` does "
        "with bytes it never yields.",
        "enforcement": ("eval", "tests/evals/test_review_lane_the_surface_outside_the_rules.py"),
    },
}


# ── The generator this file claimed to be ────────────────────────────────────
#
# AN INDEPENDENT REVIEWER FOUND THIS MODULE INERT: no render function, no entry point, and
# nothing in the repo importing it, while a commit message said the registry was generated
# from it. The YAML had in fact been produced by a throwaway inline script and the claim
# committed anyway -- which is prose with a registry entry, the exact failure this registry
# exists to refuse, committed about the mechanism built to refuse it.
#
# So the generator is real now, and `--check` makes the claim falsifiable: it re-renders
# and compares, so a hand-edit of the YAML or a change here that was never rendered fails
# rather than drifting quietly.


#: The registry's own preamble, kept HERE rather than read back out of the artifact.
#: Reading it back meant the header survived every regeneration untouched, so it still
#: described the retired five-handle bench while the body below it listed 29 generic
#: seats -- a file contradicting itself in the same commit, which is the drift this
#: registry exists to end.
_HEADER = """# Review lanes - the questions a Dream Studio review is obliged to ask.
#
# WHY THIS FILE EXISTS. Reviewers each found defects nobody else did, and each found them
# by asking one repeatable question. Those questions lived in their heads. Putting them in
# a skill's prose would put them where the operator has already said guidance goes to die:
# "a lot of prose laid on top of each other as suggestions with no rules, evals, or really
# any real test that doing anything they are supposed to."
#
# THE BENCH. 29 seats: the operator's 28-seat review bench, derived from real review
# history with unit counts per theme, plus the Event-substrate custodian, which asks
# whether a row survives being rebuilt from its own events -- a property of this substrate
# with no equivalent on the bench.
#
# EVERY LANE OWES a question, the signature of the defect, a precedent it actually came
# from, the measurement that decided how it is answered, and exactly ONE of a runnable
# detector, a graded eval, or `judgment: true` with a `why` naming what is missing. The
# `review-lane-registry` gate refuses anything else, because a lane that decays back into
# advice is a lane that stops being asked.
#
# WHERE A PUBLISHED STANDARD GOVERNS A SEAT, THE SEAT NAMES IT, so a finding is arguable
# on the standard rather than on seniority.
#
# LANES CARRY A SCOPE and fire on relevance to the change set. A lane with no scope always
# fires, and `--all` convenes every seat regardless.
#
# GENERATED from scripts/seat_lanes_data.py -- edit that table, not this file.
# `py scripts/seat_lanes_data.py --check` fails if the two have drifted.
"""


REGISTRY = pathlib.Path(__file__).resolve().parents[1] / "canonical" / "review_lanes.yml"


def _lane_id(seat: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", seat.lower()).strip("-")


def _fold(key: str, text: str, indent: str = "    ") -> str:
    out = [f"{indent}{key}: >-"]
    line = ""
    for word in text.split():
        if len(line) + len(word) + 1 > 92:
            out.append(f"{indent}  {line}")
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(f"{indent}  {line}")
    return "\n".join(out)


#: WHAT A DETECTOR LANE'S CHECK DOES NOT DECIDE, in the lane's own words.
#:
#: A detector is a narrow mechanical predicate standing in for a prose question, and the
#: two are rarely the same size. `a-branch-behind-its-base` asks "how far behind its base
#: is this branch, AND did anyone ask it to sync" and its detector counts commits -- the
#: second half is answered by nobody while the lane renders `clean`. That is reporting
#: clean on ground the check never examined.
#:
#: ONLY DETECTOR LANES CARRY THIS. An eval puts the lane's whole question to a grader and
#: a judgment lane puts it to a person; neither narrows the question to a predicate, so
#: there is nothing for them to defer. Requiring the key of them would be a box to tick.
#:
#: Every entry below is quoted from the gate's OWN declared limits, not inferred -- each
#: gate docstring states what it cannot see, and this table is where those statements
#: become visible to a reviewer reading the lane rather than the source.
DEFERS: dict[str, list[str]] = {
    "an-untested-fallback-lane": [
        "whether any test actually ENTERS the fallback branch -- any textual mention of"
        " the symbol anywhere under tests/, a comment included, clears it, so this proves"
        " a name is known to the tests rather than exercised by them",
        "a platform dispatch written as a dict keyed on platform.system(), which has no"
        " `if` node to find, and a platform predicate behind an abstracted name",
        "fallbacks in files outside this change set -- the lane is diff-scoped, so the"
        " standing backlog drains only as those files are touched",
    ],
    "a-per-item-wait-with-no-aggregate-deadline": [
        "multiplication through a CALL -- a loop whose helper sleeps in its own loop is"
        " the same defect and needs a call graph to see",
    ],
    "a-branch-behind-its-base": [
        "whether anyone ASKED this branch to sync, which lives in review comments on the"
        " pull request and not in the tree",
        "whether being behind is a problem here -- a revert off a tag or a hotfix from a"
        " release point is legitimately behind, which is why this lane is advisory",
    ],
    "a-write-no-event-can-reconstruct": [
        "a bare UPDATE that changes a projected row's state: the scan matches"
        " `INSERT INTO` and `INSERT OR REPLACE INTO` only, registered as WO 4fbe3282",
        "whether replaying the emitted event actually REPRODUCES the row -- the lane"
        " proves an event is emitted beside the write, not that its payload rebuilds it",
    ],
}


def _block(lane_id: str, seat: str, spec) -> str:
    question, signature, precedent, measurement, enforcement = spec
    lines = [f"  - id: {lane_id}", f"    seat: {json.dumps(seat)}"]
    for key, value in (
        ("question", question),
        ("signature", signature),
        ("precedent", precedent),
        ("measurement", measurement),
    ):
        lines.append(_fold(key, value))
    for key, table in (("standards", STANDARDS), ("scope", SCOPES)):
        if table.get(seat):
            lines.append(f"    {key}:")
            lines += [f"      - {json.dumps(v)}" for v in table[seat]]
    kind, value = enforcement
    if kind == "detector" and lane_id in DEFERS:
        lines.append("    defers:")
        lines += [f"      - {json.dumps(v)}" for v in DEFERS[lane_id]]
    if kind == "judgment":
        lines.append("    judgment: true")
        lines.append(_fold("why", value))
    else:
        lines.append(f"    {kind}: {value}")
    return "\n".join(lines)


def render() -> str:
    """The registry as this table says it should be.

    THE ELEVEN PRE-EXISTING LANES ARE EMITTED FROM `RESEATED`, prose and enforcement
    intact, under their new seat and keeping their original lane id. Only the seat
    changes, because only the seat was meant to. Everything else comes from `SEATS`.
    """
    header = _HEADER.rstrip()
    out = [header, "", "version: 2", "lanes:"]
    carried_seats = {lane["seat"] for lane in RESEATED.values()}
    for old_id, lane in RESEATED.items():
        spec = (
            lane["question"],
            lane["signature"],
            lane["precedent"],
            lane["measurement"],
            tuple(lane["enforcement"]),
        )
        out.append(_block(old_id, lane["seat"], spec))
    for seat_name, spec in SEATS.items():
        # A seat already answered by a carried-over lane does not also get a generated
        # one -- that would file the same question twice under one name, which is how a
        # lane stops being falsifiable.
        if seat_name in carried_seats:
            continue
        out.append(_block(_lane_id(seat_name), seat_name, spec))
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Render canonical/review_lanes.yml.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed registry differs from what this table renders.",
    )
    args = parser.parse_args(argv)
    rendered = render()
    current = REGISTRY.read_text(encoding="utf-8").replace("\r\n", "\n")
    if args.check:
        if current == rendered:
            print(f"review-lanes: OK - registry matches its generator ({len(SEATS)} seats).")
            return 0
        print(
            "review-lanes: STALE - canonical/review_lanes.yml does not match what"
            " scripts/seat_lanes_data.py renders. Re-run without --check, or the registry"
            " and the table it claims to come from have already diverged."
        )
        return 1
    REGISTRY.write_text(rendered, encoding="utf-8")
    print(
        f"review-lanes: wrote {REGISTRY} ({len(SEATS)} seats, {len(SEATS)+len(EXTRA_LANES)} lanes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
