# workflows/

YAML workflow templates defining multi-step task pipelines as directed acyclic graphs (DAGs).

## What this directory provides

Each `.yaml` file is a reusable workflow template. The `workflow` skill executes these by evaluating node dependencies, running skill invocations at each node, and tracking state in `~/.dream-studio/state/`.

## Entry point

`idea-to-pr.yaml` — the canonical full-cycle workflow (spec → plan → build → review → ship). Read it to understand the node/gate/parallel structure.

## Public interfaces

Workflows are invoked by name via the `workflow` skill: `/workflow run <name>`. The YAML schema is defined in `rules/structure/` (pending) — key fields are `nodes`, `gates`, `parallel`, and `on_failure`.

## What should never be imported directly

Workflows are declarative templates — they do not contain executable code and are not imported by Python modules. The `workflow_engine.py` and `workflow_state.py` libs consume them at runtime.

## Key invariants

- Every workflow must have a `name`, `description`, and at least one `node`
- Gate nodes must define pass/fail conditions — no implicit success
- Parallel node groups must have no data dependencies between them
- Workflow state is persisted externally (not in these files) so templates remain stateless
