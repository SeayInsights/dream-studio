# Architecture Decision Records

Durable, human-readable records of Dream Studio's significant design decisions. Each ADR is
the rationale **projection** of a decision — the SQLite authority (packet-store decision
record) remains the source of truth for the decision itself.

## Where ADRs live

ADR **decision records are operator-local** — they are the reasoning/thought-process behind
the design, so they live in the file DB docstore, **not** in this repository. The repo keeps
only the *descriptive system*: this convention and the format template
([ADR-000-template.md](ADR-000-template.md)).

- **Author / update:** `ds files write "adr/ADR-NNNN-kebab-title.md" --category planning`
- **Read:** `ds files read "adr/ADR-NNNN-kebab-title.md"`
- **List:** `ds files list --category planning` (the `adr/` names)

## Conventions

- One decision per docstore entry, named `adr/ADR-NNNN-kebab-title.md` (zero-padded number).
- Every ADR carries: Status, Date, Author, Context, Decision, Consequences, a
  Breaking-changes table, and Cross-references (see the template).
- Status lifecycle: **Proposed → Accepted → Superseded/Deprecated**. An Accepted ADR is
  immutable — supersede it with a new ADR, don't edit it away.

> The repo intentionally hosts no numbered ADR files — only the template + this README.
> `tests/unit/test_adr_system.py` validates the template's format and guards that no ADR
> decision body is committed to `docs/adr/`.
