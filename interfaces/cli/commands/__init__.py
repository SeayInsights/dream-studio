"""Per-command-group modules for the Dream Studio CLI hub (ds.py).

Each module in this package:
- Defines one command group's argument parser via ``register(subcommands)``
- Dispatches commands via ``dispatch(args, ...)``
- Contains all implementation functions for that group
- Imports shared utilities from ``interfaces.cli.cli_utils``

Import each module directly:
    from interfaces.cli.commands import project, work_order, skill, ...
    from interfaces.cli.commands import eval as eval_cmd  # avoids shadowing built-in
"""
