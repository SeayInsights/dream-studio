"""ds integrate command group — AI tool integration management."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from interfaces.cli.cli_utils import _print

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``integrate`` subparser tree to *subcommands*."""
    from integrations.detector import SUPPORTED_TOOLS as _SUPPORTED_TOOLS

    integrate = subcommands.add_parser(
        "integrate", help="Manage AI tool integrations (detect, install, doctor)"
    )
    integrate_sub = integrate.add_subparsers(dest="integrate_command", required=True)

    integrate_sub.add_parser("detect", help="List detected AI tools and their config roots")
    integrate_sub.add_parser("status", help="One-line integration health summary per tool")

    integrate_doctor = integrate_sub.add_parser(
        "doctor", help="Full health report for a specific tool"
    )
    integrate_doctor.add_argument("tool", nargs="?", default="claude_code")

    integrate_plan = integrate_sub.add_parser(
        "plan", help="Print the dry-run file operation plan for a tool"
    )
    integrate_plan.add_argument("tool", choices=list(_SUPPORTED_TOOLS))
    integrate_plan.add_argument("--scope", choices=["user", "project"], default=None)

    integrate_install = integrate_sub.add_parser(
        "install", help="Install integration for a tool (requires --dry-run or --execute)"
    )
    integrate_install.add_argument("tool", choices=list(_SUPPORTED_TOOLS))
    integrate_install.add_argument("--scope", choices=["user", "project"], default=None)
    install_mode_group = integrate_install.add_mutually_exclusive_group()
    install_mode_group.add_argument(
        "--dry-run", action="store_true", default=False, help="Simulate; writes nothing"
    )
    install_mode_group.add_argument(
        "--execute", action="store_true", default=False, help="Write files"
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from integrations.detector import detect_all, detect_claude_code
    from integrations.health import doctor
    from integrations.installer.base import RefusalError
    from integrations.installer.claude_code import ClaudeCodeInstaller
    from integrations.manifest import get_ds_home

    canonical_root = source_root / "canonical"
    ds_home = dream_studio_home or get_ds_home()

    if args.integrate_command == "detect":
        tools = detect_all()
        return _print(
            {
                "model_name": "dream_studio_integrate_detect",
                "derived_view": True,
                "primary_authority": False,
                "tools": [
                    {"tool_id": t.tool_id, "scope": t.scope, "config_root": str(t.config_root)}
                    for t in tools
                ],
            }
        )

    if args.integrate_command == "status":
        tools = detect_all()
        statuses: list[dict[str, Any]] = []
        for t in tools:
            result = doctor(
                t.tool_id,
                t.config_root,
                ds_home=ds_home,
                canonical_root=canonical_root,
            )
            statuses.append(
                {
                    "tool_id": t.tool_id,
                    "scope": t.scope,
                    "state": result["state"],
                }
            )
        return _print(
            {
                "model_name": "dream_studio_integrate_status",
                "derived_view": True,
                "primary_authority": False,
                "tools": statuses,
            }
        )

    if args.integrate_command == "doctor":
        tool_id = getattr(args, "tool", "claude_code")
        scope = getattr(args, "scope", None)
        detected = detect_claude_code(scope_override=scope)
        result = doctor(
            detected.tool_id,
            detected.config_root,
            ds_home=ds_home,
            canonical_root=canonical_root,
        )
        return _print(
            {
                "model_name": "dream_studio_integrate_doctor",
                "derived_view": True,
                "primary_authority": False,
                **result,
            }
        )

    if args.integrate_command == "plan":
        scope = getattr(args, "scope", None)
        detected = detect_claude_code(scope_override=scope)
        installer = ClaudeCodeInstaller(
            detected.config_root,
            detected.scope,
            canonical_root=canonical_root,
            ds_home=ds_home,
        )
        plan = installer.plan()
        return _print(
            {
                "model_name": "dream_studio_integrate_plan",
                "derived_view": True,
                "primary_authority": False,
                "tool": "claude_code",
                "scope": detected.scope,
                "config_root": str(detected.config_root),
                "plan": plan.summary(),
            }
        )

    if args.integrate_command == "install":
        scope = getattr(args, "scope", None)
        dry_run = getattr(args, "dry_run", False)
        execute = getattr(args, "execute", False)

        if not dry_run and not execute:
            raise RefusalError(
                "ds integrate install requires --dry-run or --execute. "
                "Use --dry-run to simulate, --execute to write files."
            )

        mode = "dry_run" if dry_run else "execute"

        # Phase 20: native-AGENTS.md tools use the generic installer (AGENTS.md only,
        # no hooks/skills). Claude Code keeps its dedicated installer below.
        tool_id = getattr(args, "tool", "claude_code")
        if tool_id != "claude_code":
            from integrations.installer.agents_target import AgentsTargetInstaller

            installer = AgentsTargetInstaller(
                tool_id,
                project_root=Path.cwd(),
                canonical_root=canonical_root,
            )
            result = installer.install(mode)
            return _print(
                {
                    "model_name": "dream_studio_integrate_install",
                    "derived_view": True,
                    "primary_authority": False,
                    "tool": tool_id,
                    **result,
                }
            )

        detected = detect_claude_code(scope_override=scope)
        # B.3: install the git pre-push hook into the cwd's repo (if any).
        # Tests do NOT pass cwd, so the operator's real .git/hooks/ is untouched.
        cwd = Path.cwd()
        git_repo_root = cwd if (cwd / ".git").is_dir() else None
        # Read skip_hook_install from ~/.dream-studio/config.json if present.
        _skip_hook = False
        try:
            _cfg_path = (ds_home or (Path.home() / ".dream-studio")) / "config.json"
            if _cfg_path.is_file():
                import json as _json

                _skip_hook = bool(
                    _json.loads(_cfg_path.read_text(encoding="utf-8")).get(
                        "skip_hook_install", False
                    )
                )
        except Exception:
            pass
        installer = ClaudeCodeInstaller(
            detected.config_root,
            detected.scope,
            canonical_root=canonical_root,
            ds_home=ds_home,
            git_repo_root=git_repo_root,
            skip_hook_install=_skip_hook,
        )
        result = installer.install(mode)
        return _print(
            {
                "model_name": "dream_studio_integrate_install",
                "derived_view": True,
                "primary_authority": False,
                **result,
            }
        )

    raise RuntimeError(f"Unknown integrate subcommand: {args.integrate_command}")
