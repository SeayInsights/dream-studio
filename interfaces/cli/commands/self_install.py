"""ds self-install: install Dream Studio into its home as a versioned app.

See core/self_install.py for the layout and the ordering that
keeps a failed install from switching anything.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from interfaces.cli.cli_utils import _print


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    cmd = subcommands.add_parser(
        "self-install",
        help="Install Dream Studio into <home>/app from a git commit, or roll back",
        description=(
            "Build Dream Studio from `git archive <ref>` of a clean checkout, install it "
            "non-editable into <home>/app/<version>-<sha>/venv, back up and migrate the "
            "authority with the new app, then switch <home>/app/current and write the one "
            "launcher <home>/bin/ds.cmd. Nothing is switched if any step before that fails. "
            "Use the global --home to choose the home."
        ),
    )
    cmd.add_argument(
        "--repo",
        default=None,
        help="Git checkout to build from (default: the checkout this ds runs from)",
    )
    cmd.add_argument("--ref", default="HEAD", help="Commit to build (default HEAD)")
    cmd.add_argument(
        "--config-root",
        action="append",
        default=None,
        help=(
            "After switching, run the new app's `integrate install claude_code` for this "
            "Claude Code config root (repeatable). No git pre-push hook is ever written."
        ),
    )
    cmd.add_argument(
        "--dry-run", action="store_true", help="Print every write it would make; write nothing"
    )
    cmd.add_argument(
        "--rollback",
        action="store_true",
        help="Switch back to the app recorded in <home>/app/previous (with --dry-run: plan only)",
    )


def dispatch(args: argparse.Namespace, *, dream_studio_home: Path | None) -> int:
    from core.config.paths import home_dir
    from core.self_install import (
        SelfInstallError,
        default_repo,
        resolve_plan,
        rollback,
        self_install,
    )

    home = (dream_studio_home or home_dir()).resolve()
    if args.rollback:
        result = rollback(home, dry_run=bool(args.dry_run))
        _print(result)
        return 0 if result.get("ok") else 1

    repo = Path(args.repo).resolve() if args.repo else default_repo()
    if repo is None:
        _print(
            {
                "ok": False,
                "error": "this ds runs from an installed app; pass --repo <git checkout>",
            }
        )
        return 1
    try:
        plan = resolve_plan(
            home=home,
            repo=repo,
            ref=args.ref,
            config_roots=[Path(r) for r in (args.config_root or [])],
        )
    except SelfInstallError as exc:
        _print({"ok": False, "error": str(exc)})
        return 1
    result = self_install(plan, dry_run=bool(args.dry_run))
    _print(result)
    return 0 if result.get("ok") else 1
