# Normative specs

Pre-implementation specs for contract-bearing work — a spec states, in RFC-2119
normative language, the contract a work order must satisfy, and is **ratified** before
that work order can close. A spec is a normative *projection* of the contract; the
canonical implementation + authority remain the source of truth (each spec names them
in its Canonical-source block). Use [`SPEC-000-template.md`](SPEC-000-template.md).

## Conventions

- One contract per file, `SPEC-NNNN-kebab-title.md`, carrying the lifecycle header,
  the RFC-2119 legend, a Canonical-source block, and numbered normative requirements.
- **Status lifecycle:** Draft → Reviewed → **Ratified** → Superseded.
- Store the spec as the work order's `api_contract` artifact (`ds files` / the WO
  artifact store) so the close gate can read its status.

## Ratified-contract gate

The `api_contract_exists` close gate (`core/work_orders/close_gates.py`, via
`core/gates/spec_ratification.py`) requires the linked spec to be **Ratified** — a
Draft/Reviewed spec blocks close. This makes "the contract is agreed and stable" a
gate, not a hope.

### Grandfather cutover

Ratification is enforced only for work orders **created on or after
`RATIFY_ENFORCED_AFTER` (2026-08-02)** — the date the gate shipped. Work orders created
before then are grandfathered: they still require the `api_contract` artifact to exist
(the prior behavior), but not a Ratified status, since their specs predate this rule.
Change `RATIFY_ENFORCED_AFTER` in `core/gates/spec_ratification.py` only with a
documented rationale.
