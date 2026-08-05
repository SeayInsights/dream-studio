# Architecture Decision Records

Durable, human-readable records of Dream Studio's significant design decisions. Each
ADR is the rationale **projection** of a decision — the SQLite authority (packet-store
decision record) remains the source of truth for the decision itself. See
[ADR-0001](ADR-0001-record-architecture-decisions.md) for why this practice exists and
[ADR-000-template.md](ADR-000-template.md) for the format.

## Conventions

- One decision per file, named `ADR-NNNN-kebab-title.md` (zero-padded sequential number).
- Every ADR carries: Status, Date, Author, Context, Decision, Consequences, a
  Breaking-changes table, and Cross-references.
- Status lifecycle: **Proposed → Accepted → Superseded/Deprecated**. An Accepted ADR is
  immutable — supersede it with a new ADR, don't edit it away.
- Add every new ADR to the index below. `tests/unit/test_adr_system.py` fails if the
  index and the `docs/adr/` files drift apart or an ADR is missing a required section.

## Index

| ADR | Title | Status | Date |
| --- | --- | --- | --- |
| [0001](ADR-0001-record-architecture-decisions.md) | Record architecture decisions in ADRs | Accepted | 2026-07-24 |
| [0002](ADR-0002-silent-default-review-lens.md) | Hunt silent defaults (negative-space / fail-quiet) as a review lens | Accepted | 2026-08-05 |
