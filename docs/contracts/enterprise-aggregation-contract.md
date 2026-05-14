# Enterprise Aggregation Contract

Phase: 13B - Enterprise/Org/ML Aggregation Boundaries

Dream Studio enterprise, organization, and ML capabilities are optional derived consumers. They may analyze explicit redacted or aggregate inputs, create derived reports, and write enterprise-local model artifacts, but they do not own local canonical runtime state.

## Authority Principles

1. The main Dream Studio local runtime database remains authoritative.
2. Enterprise/org/ML features are optional derived consumers unless a later contract explicitly grants a narrower authority.
3. Enterprise code must not read `~/.dream-studio/state/studio.db` or backup files by default.
4. Enterprise code may consume only explicit operator-selected inputs or redacted/aggregate projection packages.
5. Enterprise model artifacts are derived enterprise-local artifacts.
6. Organization graphs, reports, dashboards, and recommendations are derived aggregate projections.
7. Enterprise tests are not normal main validation until imports, state isolation, and identifiers are contracted.
8. Enterprise, Docker, dashboards, telemetry, adapters, and org analytics are not canonical authority.

## Allowed Enterprise Inputs

Allowed inputs are:

- explicit operator-selected repository paths;
- explicit operator-selected files or directories;
- redacted projection export packages;
- aggregate projection export packages;
- aggregate governance/security summaries;
- aggregate research/source summaries with privacy classifications preserved;
- explicit temp/test databases created by isolated tests.

Allowed inputs must identify:

- source type;
- source path or package id;
- privacy/export classification;
- redaction status;
- operator intent;
- generation timestamp;
- originating contract, when applicable.

## Forbidden Live DB Defaults

Enterprise integration must not default to:

- `~/.dream-studio/state/studio.db`;
- `~/.dream-studio/state/studio.db.bak`;
- `~/.dream-studio/state/studio.db.pre-restore.bak`;
- unchecked home-directory discovery of Dream Studio runtime state;
- automatic reads of native local runtime state for training, forecasting, org reports, or benchmarks.

Any adjacent enterprise code that references the live DB path is a pre-integration blocker. It may be inventoried and tested as a blocker, but it must not be promoted into main runtime or normal validation. Phase 13C removes known adjacent enterprise live DB defaults; guardrails should fail if they return.

## Redacted/Aggregate Projection Package Expectations

Future enterprise inputs should be packages, not implicit live reads. A package must include:

- package id;
- source contracts used to create it;
- included projection names;
- excluded private tables and fields;
- redaction or aggregate policy;
- schema/version metadata;
- generation timestamp;
- operator-selected destination;
- checksum or manifest when practical.

Packages must exclude raw private local state by default, including raw memory, raw sessions, raw token rows, raw event payloads, backup files, and unredacted research payloads.

## Explicit Operator-Selected Inputs

Enterprise CLI/API surfaces may accept an explicit path selected by the operator. Such paths must be treated as input evidence, not authority. Selecting a path does not grant permission to mutate local runtime state, repair schema skew, run migrations, or upload private state.

## ML Artifact Classification

ML artifacts include model files, serialized estimators, metadata JSON, evaluation reports, benchmark outputs, and forecast outputs.

They are classified as derived enterprise-local artifacts. They may be deleted, refreshed, or regenerated without changing canonical Dream Studio state. They must require explicit output path semantics before promotion into normal workflows.

## Org Graph And Report Classification

Organization graphs, capability ontologies, VP metrics, engineering debt reports, consolidation reports, and security/compliance views are derived aggregate projections.

They may inform operator decisions, but they must not:

- rewrite local canonical state;
- create canonical workflow, execution, decision, memory, event, or governance records;
- become cloud/org/global truth;
- override local projection, governance, research, or adapter contracts.

## Import Boundary Rules

The enterprise repo must not depend on main repo internals such as `core.*` or `projections.*` by accident. Future integration must use a named shim or export package contract.

Until such a shim exists, imports from main runtime internals in the adjacent enterprise repo are classified as pre-integration blockers. They are not allowed in promoted normal validation. Phase 13C removes known adjacent enterprise main-internal imports; guardrails should fail if they return.

## Enterprise Test Promotion Rules

Enterprise tests are package-local until all of these are true:

- tests use isolated temp state;
- tests do not read the native runtime DB by default;
- tests do not write native DBs, backups, model output directories, or report directories unless explicitly temp-scoped;
- tests avoid retired or legacy skill identifier forms;
- tests import enterprise modules through the contracted package boundary;
- tests are explicitly named in the main validation surface.

The main repo may inspect adjacent enterprise tests statically. It must not silently promote them into normal validation while known blockers remain.

## Privacy And Export Constraints

Enterprise/org/ML surfaces may consume aggregate or redacted exports only. Raw/private local state remains local/private unless a later export contract defines redaction and import behavior.

Enterprise outputs must preserve privacy classification and must not become upstream authority on re-import.

## Relationship To Other Contracts

- State contract: local canonical runtime state remains authoritative.
- Event contract: enterprise outputs are not canonical events unless a future local import contract validates and writes them.
- Projection contract: enterprise reads projections as derived snapshots and may produce derived aggregate projections.
- Governance contract: enterprise may consume aggregate governance summaries, not raw private governance payloads.
- Research/source contract: enterprise may consume redacted or aggregate research artifacts; research remains advisory evidence.
- Adapter contract: enterprise does not make model/provider metadata canonical.
- Portable execution contract: enterprise is an optional rendering or analytics consumer, not a primitive authority.

## Violations

Violations include:

- default reads of live native DB state;
- writes to canonical workflow, orchestration, execution, memory, decision, event, or governance authority tables;
- automatic cloud/org/global sync;
- schema migrations for enterprise integration before a contract and tests exist;
- importing main repo internals without a named shim;
- promoting enterprise tests into normal validation while known blockers remain;
- treating enterprise recommendations, forecasts, models, reports, or org graphs as canonical truth.

## Schema Posture

Phase 13B adds no schema migrations. Any future enterprise persistence or import path must first define table ownership, privacy/export classification, replay/rebuild rules, and executable boundary tests.
