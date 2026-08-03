# SPEC-NNNN: <short imperative title>

<!-- Lifecycle header — every normative spec carries this block. -->
- **Status:** Draft
- **Date:** YYYY-MM-DD
- **Author:** <name>
- **Governs:** <the contract this spec is normative for — e.g. `POST /api/v1/...`, a schema, a route family>

> **Status lifecycle:** **Draft → Reviewed → Ratified → Superseded**.
> A spec that governs a contract-bearing work order must be **Ratified** before that
> work order can close (the `api_contract_exists` gate reads this status). Ratification
> means the normative requirements are agreed and stable — not "written". A changed
> contract is a new spec that supersedes this one (set this one's Status to
> `Superseded by SPEC-XXXX`).

## RFC-2119 legend

Requirement levels use [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) / RFC 8174
keywords, interpreted as described there:

- **MUST** / **MUST NOT** / **REQUIRED** / **SHALL** — an absolute requirement or prohibition.
- **SHOULD** / **SHOULD NOT** / **RECOMMENDED** — a strong default; deviations need a stated reason.
- **MAY** / **OPTIONAL** — truly discretionary.

Keywords are normative only in UPPERCASE.

## Canonical source

<!-- What authority/code is the source of truth this spec is normative over. The spec
     is a normative projection of the contract, not a second source of truth. -->

- **Canonical implementation:** <path(s) — e.g. `projections/api/routes/foo.py`>
- **Authority / schema:** <table, event type, or store this contract reads/writes>
- **Verified by:** <test / TEST-CHECK node id that proves conformance>

## Context

The problem and the forces. Why this contract exists and what it must satisfy.

## Normative requirements

State the contract as numbered, testable requirements using the RFC-2119 keywords.

- **R1.** The endpoint **MUST** …
- **R2.** The response **MUST** include … ; it **SHOULD** …
- **R3.** On invalid input the endpoint **MUST** return … ; it **MUST NOT** …

## Contract shape

Request / response (or schema / event) shape the requirements above refer to — types,
required vs optional fields, status codes, error envelope.

## Consequences and non-goals

What this commits us to, what is explicitly out of scope, and the migration/compat
story for consumers.

## Cross-references

- **Supersedes:** <SPEC-XXXX, or "None">
- **Superseded-by:** <SPEC-XXXX, or "None">
- **Governing ADR:** <ADR-XXXX if a design decision underlies this contract, or "None">
- **Decision record / WO:** <ids>
