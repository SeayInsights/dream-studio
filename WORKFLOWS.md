# Dream Studio Workflows

Dream Studio workflows are route-first and evidence-backed. They are not prompt chains. A workflow should select the next valid milestone, execute bounded Work Orders, validate the result, record evidence, and continue until a real stop gate appears.

## Core Workflow

```mermaid
flowchart TD
    Goal["Operator goal"]
    Authority["PRD + stage gates"]
    Route["Route decision"]
    WO["Work Order"]
    Execute["Adapter/tool execution"]
    Validate["Focused validation"]
    Evidence["Evidence + telemetry"]
    Dashboard["Dashboard attention"]
    Gate{"Stop gate?"}
    Continue["Continue internally"]
    Approval["Operator approval"]

    Goal --> Authority --> Route --> WO --> Execute --> Validate --> Evidence --> Dashboard --> Gate
    Gate -->|no| Continue --> Route
    Gate -->|yes| Approval
```

## Stop Gates

Dream Studio must stop for live runtime mutation, live DB mutation or migration, cleanup execution, deletion, archive execution, push, tag, merge, deploy, history rewrite, secret access, broad scope expansion, failed validation that cannot be fixed inside scope, or ambiguous product decisions.

See [docs/WORKFLOWS.md](docs/WORKFLOWS.md) for detailed workflow guidance.
