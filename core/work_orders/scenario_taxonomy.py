"""The scenario taxonomy the verify plane steps through.

EXTRACTED, NOT INVENTED. This lived inside _FALSIFICATION_PROMPT_TEMPLATE in
verify_prompts.py, reachable only by the falsification grader. It is this
repository's own precedent for stepping through failure scenarios methodically,
and it has been producing the sharpest findings in recent work: the `SELECT 1`
acceptance criterion that proves only a database connection exists, the
stored-PASS-versus-re-execution question, the projection-lag window between a
task-done event and the read that trusts it.

It is here so the ORCHESTRATOR's diagnosis can walk the same classes. A reviewer
who improvises a checklist covers what occurs to them; one that walks a fixed
taxonomy also covers the classes that do not. The operator asked whether there was
a best practice for stepping through scenarios worth adding -- there was, and it
was already here, reachable by one caller.

ONE DEFINITION, TWO CONSUMERS. Duplicating it would let the grader and the
orchestrator drift into judging by different lists, which is the same drift the
two-registry and two-splice defects were.
"""

SCENARIO_TAXONOMY = """
Scenario taxonomy. Consider EVERY class; skip a class only when it genuinely
cannot apply to this diff (do not pad with irrelevant scenarios):

(1) crash_mid_write — the process dies between a write and the read that trusts
    it. Durable state left half-written, a marker present without its payload.
(2) race_between_writers — two processes/sessions write the same state
    concurrently; last-write-wins clobber, lost update, interleaved partial rows.
(3) version_skew — writer and reader run different code/schema versions; a field
    added or renamed on one side only; a stale deployed copy of the same module.
(4) partial_failure — a multi-step operation succeeds partway (store A written,
    store B not), with no reconciliation to detect the split.
(5) malformed_input — hostile or corrupt input reaches a parser: truncated JSON,
    wrong types, unexpected encodings, paths with spaces/quotes/globs.
(6) interrupted_io — a file move, copy, or fsync interrupted; a lock held; a disk
    full; a network read cut mid-stream.
(7) reachability_vs_config — CRITICAL for anything returning a secret, token,
    credential, signed URL, or privileged response: identify what the value is
    actually VALID AGAINST (bind address, requesting client address, token
    audience/binding, real network exposure) versus what the code CHECKS (a URL
    string, an env flag, a mode name, a display value). Flag any case where a
    different knob can open the hole while the guard still believes it is closed.
(8) empty_absent_state — the happy path assumes rows/files/config exist; what
    happens on a fresh install, an empty table, a missing artifact, a first run.
"""

# `taxonomy_classes()` -- the class names alone, derived from the text above -- lived
# here and was removed when this work was split from the orchestrator branch. Its only
# caller is the diagnosis prompt in `control/execution/workflow/runner.py`, which asks a
# fresh reviewer for a line per named class; that code is not on this branch, so the
# function had no call site and the `reachability` gate refused it. Correctly: a
# mechanism with no caller cannot do the thing it was built to do.
#
# It returns with its caller. Do not re-add it here on the assumption something will
# want it.
