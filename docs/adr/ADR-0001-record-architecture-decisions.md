# ADR-0001: Record architecture decisions in ADRs

- **Status:** Accepted
- **Date:** 2026-07-24
- **Author:** Dannis Seay

## Context

Dream Studio's significant design decisions have lived as prose scattered across code
comments (`# DECISION (WO-…)`, `# operator decision 2026-…`), commit messages, PR
bodies, and the SQLite decision records. That is durable for the runtime authority but
not *discoverable* or *readable* as a human narrative: there is no single place a
contributor (or a future agent) can read *why* the architecture is the way it is, what
alternatives were rejected, and which decisions supersede which. The runtime
`decision.recorded` events capture that a decision was made, but not its full rationale
in reviewable form.

Dream Studio is authority-first and event-sourced; any decision log must not compete
with that authority for ownership. What is missing is a *projection*: a durable,
human-readable, version-controlled record of the significant design decisions.

## Decision

We will record significant architecture and design decisions as **Architecture
Decision Records (ADRs)** — one Markdown file per decision under `docs/adr/`, following
the template in [`ADR-000-template.md`](ADR-000-template.md).

- Files are named `ADR-NNNN-kebab-title.md` with a zero-padded sequential number.
- Every ADR carries the same rigid sections: Status, Date, Author, Context, Decision,
  Consequences, a Breaking-changes table, and Cross-references.
- Status follows the lifecycle **Proposed → Accepted → Superseded/Deprecated**. An
  Accepted ADR is **immutable**: a changed decision is a *new* ADR that supersedes the
  old one; the old one is marked `Superseded by ADR-XXXX`, never edited away.
- An ADR is the human-readable **rationale projection** of a decision. The Dream Studio
  authority (the packet-store decision record) remains the source of truth for the
  decision itself; the ADR links back to it via its Cross-references.
- The index in [`README.md`](README.md) lists every ADR, and a drift check
  (`tests/unit/test_adr_system.py`) keeps the index and the required sections honest.

## Consequences

- Contributors and agents gain one discoverable narrative of the architecture's "why".
- Significant decisions now cost a short ADR to author — the `ds-core` `think` mode is
  updated to make this the default when a design decision is reached, and `plan` mode
  references the governing ADR, so the cost is paid in-flow rather than retrofitted.
- The ADR set must be maintained: a superseding decision must update the old ADR's
  status. The drift check catches missing index entries and malformed ADRs, but cannot
  judge whether a decision *should* have been recorded — that judgment stays with the
  author.
- ADRs are a projection, not authority: they must never become the place a decision is
  *stored* in lieu of the authority record.

## Breaking changes

| Change | Affected surface | Migration / mitigation |
| --- | --- | --- |
| None — additive | New `docs/adr/` tree; optional `adr_id` on the decision packet | No existing artifact, route, schema, or CLI changes; existing decisions are unaffected and may be back-filled as ADRs opportunistically. |

## Cross-references

- **Supersedes:** None
- **Superseded-by:** None
- **Decision record:** None (this meta-ADR establishes the practice itself)
- **Related:** WO R1 (`f9c5c142`); `docs/adr/ADR-000-template.md`
