# ADR-0002: Hunt silent defaults (negative-space / fail-quiet) as a first-class review lens

- **Status:** Accepted
- **Date:** 2026-08-05
- **Author:** Dream Studio

> Status is one of: **Proposed** · **Accepted** · **Superseded by ADR-XXXX** · **Deprecated**.

## Context

A recurring, high-severity defect class is code that resolves an authority, an identity, or
a required piece of state by *negative space* — "if X resolves, use X; **otherwise** fall
through to a default" — or that swallows a correctness-changing failure (`except: pass`, a
bare `return None` / `""` / `[]`). The fall-through produces a plausible-but-wrong result
and **nothing alerts**. These pass every test — the happy path is exercised, the miss path
is not — and surface later as corrupted data or a false all-clear.

Dream Studio has shipped this class more than once, which is why it earns a named lens:

- **A false all-clear from a security gate.** Dream Studio's native secret scanner
  (`core/gates/secret_scan.py`) returned an *empty* finding list when its underlying `git`
  call failed — reporting "no secrets" precisely when it was blind. A fail-open gate that
  cannot tell "clean" from "never ran" is worse than no gate, because it is trusted. The
  fix was to fail **closed**: the git helper raises `SecretScanError` and the gate exits
  non-zero on a scan error, so "could not scan" is never silently "nothing found."
- **A fabricated empty store on the read path.** An analytics read path created an empty
  DuckDB store when the real one was missing, so callers saw "zero rows" instead of an
  error — indistinguishable from a genuinely empty store. The fix raises
  `AnalyticsStoreMissingError` on the read path and only creates on the write path.
- **A swallowed refresh.** A dashboard refresh wrapped its derivation in `except: pass`,
  so a broken refresh silently served stale data with no signal.

The shape is the same each time: the miss/error path defaults to a plausible value instead
of refusing, and the failure is invisible because nothing ever raises.

## Decision

We will treat the **silent-default / negative-space / fail-quiet** pattern as a first-class
review lens, hunted proactively and caught in review:

1. `ds-quality:harden` carries the lens (Phase 4) with a Dream Studio worked example and
   the remedy.
2. `ds-core:review` carries the same lens as a Stage-2 checklist item.

The remedy is **affirmative**: verify the authority/state and **refuse what you cannot
verify** (fail loud — raise / non-zero exit / 403 / block) rather than defaulting. A
refused operation gives the caller and any repair logic an explicit signal; a silent
default gives them nothing. A fallback is acceptable only when it *announces* itself
(e.g. an explicit "unknown" state), never when it masquerades as a verified value.

Alternative considered: leave this to ad-hoc reviewer judgment. Rejected — the failure is
invisible precisely because it never errors, so it must be named and hunted deliberately.

## Consequences

- Easier: a named, teachable pattern the harden/review skills apply consistently; fewer
  invisible false-all-clear and empty-vs-broken defects reach production.
- Harder: authors must write affirmative verification + explicit refusal paths instead of a
  convenient default, and add tests that exercise the *miss* path, not only the happy path.
- This ADR is the Dream Studio-owned rationale for WO R6; the lens text lives in the harden
  and review skills, and `tests/unit/test_harden_lens.py` guards its presence.

## Breaking changes

| Change | Affected surface | Migration / mitigation |
| --- | --- | --- |
| None | Documentation + skill review guidance only | No code, schema, route, or CLI change |

## Cross-references

- **Supersedes:** None
- **Superseded-by:** None
- **Decision record:** None
- **Related:** WO R6 (silent-default review lens); ADR-0001 (why ADRs); `core/gates/secret_scan.py`, `core/analytics/duckdb_store.py`; `canonical/skills/quality/modes/harden/SKILL.md`, `canonical/skills/core/modes/review/SKILL.md`
