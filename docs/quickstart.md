# Quick Start

This guide starts from the public repo checkout. Adapter setup is optional.

## Clone

```bash
git clone https://github.com/SeayInsights/dream-studio.git
cd dream-studio
```

## Validate The Checkout

```bash
python -m pytest tests/unit/test_actual_dashboard_telemetry_routes.py -q --tb=line
python -m pytest tests/unit/test_frontend_dashboard_telemetry_surface.py -q --tb=line
```

## Optional Claude Code Adapter

Dream Studio includes Claude Code adapter metadata under `.claude-plugin/` and `.claude/`. Use it only as one interface to Dream Studio authority:

```bash
claude code link .
```

If the adapter is installed from a local checkout, refresh adapter caches only through the documented sync commands and verify `.dream-studio` runtime state remains outside Git.

## Local Runtime State

Dream Studio runtime state belongs under the operator-local state directory:

```text
~/.dream-studio/state/studio.db
```

For tests and demos, prefer temp or injected DB paths. Do not use live runtime state for writes unless a Work Order explicitly approves it.

## First Workflow

1. Start from a goal.
2. Let Dream Studio select the next valid milestone.
3. Generate or resume a bounded Work Order.
4. Execute through an adapter or local command.
5. Validate.
6. Record evidence and telemetry.
7. Continue internally or stop at a real approval boundary.

## Next Docs

- [Product Requirements](product/dream-studio-prd.md)
- [Architecture](ARCHITECTURE.md)
- [Database](DATABASE.md)
- [Workflows](WORKFLOWS.md)
- [Operator Guide](operator-guide.md)
- [Publication Boundary](PUBLICATION_BOUNDARY.md)
