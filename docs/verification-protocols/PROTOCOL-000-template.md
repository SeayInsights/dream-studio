# PROTOCOL-NNNN: <what is being verified>

- **Status:** Draft <!-- Draft | Active | Superseded by PROTOCOL-XXXX -->
- **Date:** YYYY-MM-DD
- **Author:** <name>
- **Applies to:** <the high-risk WO class / subsystem this protocol governs>

> A verification protocol is a **re-runnable, scope-constrained** review script: it tells a
> fresh-context reviewer exactly where to look, what to reconstruct, and how to resolve
> conflicts — so the same review yields the same verdict no matter who (or which agent) runs
> it. `ds work-order verify --protocol PROTOCOL-NNNN` runs the independent review under this
> protocol's constraints. Every protocol carries the four rule blocks below.

## 1. Scope constraint (hard)

Inspect **ONLY** the sources listed here. Do **NOT** open anything outside this set — no
tests, no docs, no prior review notes, no commit messages — unless a rule below names it.

- **Inspect:** <exact paths / modules / SQL objects — e.g. `core/event_store/`, `spool/`>
- **Never open:** <the things that would bias the review — e.g. the tests that assert the
  behavior, the docstrings that describe intent, previous verdicts>

Rationale: a bounded input set makes the review deterministic and defeats
"reads the test, confirms the test" circularity.

## 2. Shape, not current behavior (anti-bias)

Reconstruct what the code **should** be — its intended *shape* — from the sources in scope,
and compare the actual code to that. Do **not** infer the spec *from* the current behavior
(that just certifies whatever exists). State the expected shape first, in the reviewer's own
words, **before** looking at whether the code matches.

## 3. Conflict rule (spec/intent wins)

When the code disagrees with the specification / stated intent, the **spec/intent wins** —
the divergence is a finding against the code, not a redefinition of the spec. Record the
conflict; never "explain away" a spec violation as the code's intended behavior.

## 4. Re-runnable by fresh context (explicit)

This protocol MUST be executable by a reviewer with **no prior knowledge** of this work.
It names every input, needs no conversation history, and produces the same verdict on a
re-run. Gaps found still become new work orders (the existing `verify` gap→WO behavior is
preserved) — the protocol constrains *how* the review looks, not *what happens to* findings.

## Verdict shape

- **Reconstruction:** <the expected shape, stated before comparison>
- **Divergences:** <each place the code differs from the reconstructed shape — spec wins>
- **Verdict:** PASS / FINDINGS (each finding → a work order)
