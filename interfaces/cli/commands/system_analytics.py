"""ds system command group — contract-atlas/policy/analytics-ingest/context-packet.

Split from interfaces/cli/commands/system.py (WO-GF-CLI-split). The facade at
interfaces/cli/commands/system.py re-exports this module's public+private
surface; interfaces/cli/commands/system_dispatch.py composes register_analytics()/
dispatch_analytics() together with the other three group siblings.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from interfaces.cli.cli_utils import _changed_files_from_args, _print, _with_conn

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------

#: Commands handled by this group.
ANALYTICS_COMMANDS = frozenset(
    {
        "contract-atlas",
        "contract-atlas-refresh",
        "policy",
        "analytics-ingest",
        "context-packet",
    }
)


def register_analytics(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach contract-atlas/policy/analytics-ingest/context-packet subparsers."""

    subcommands.add_parser("contract-atlas", help="Show Contract Atlas summary")
    atlas_refresh = subcommands.add_parser(
        "contract-atlas-refresh",
        help="Plan or refresh Contract Atlas lifecycle exports",
    )
    atlas_refresh.add_argument("--output-dir", default=None)
    atlas_refresh.add_argument("--execute", action="store_true", default=False)
    atlas_refresh.add_argument("--include-private", action="store_true", default=False)
    atlas_refresh.add_argument("--changed-file", action="append", default=[])
    atlas_refresh.add_argument("--changed-files", default=None)
    atlas_refresh.add_argument("--docs-reviewed-no-change", action="append", default=[])

    policy = subcommands.add_parser("policy", help="Preview a policy decision")
    policy.add_argument("--actor", default="operator")
    policy.add_argument("--action", default="read_only_action")
    policy.add_argument("--target", default=None)
    policy.add_argument("--approved", action="store_true", default=False)

    analytics_ingest = subcommands.add_parser(
        "analytics-ingest", help="Import normalized analytics facts into SQLite authority"
    )
    analytics_ingest.add_argument("--file", required=True, help="Normalized analytics JSON payload")
    analytics_ingest.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Write records. Omit for dry-run planning.",
    )

    packet = subcommands.add_parser("context-packet", help="Preview a context packet")
    packet.add_argument("--adapter", default="codex")
    packet.add_argument("--packet-type", default="resume")
    packet.add_argument("--surface", dest="packet_type", help="Alias for --packet-type")
    packet.add_argument("--project-id", default="dream-studio")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch_analytics(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Route a contract-atlas/policy/analytics-ingest/context-packet command."""
    from core.analytics_ingestion import load_analytics_payload
    from core.shared_intelligence.contract_atlas import build_contract_atlas
    from core.shared_intelligence.contract_atlas_lifecycle import refresh_contract_atlas_exports
    from core.shared_intelligence.context_packets import generate_shared_context_packet
    from core.shared_intelligence.platform_hardening import evaluate_policy_decision

    if args.command == "policy":
        return _print(
            {
                "model_name": "dream_studio_policy_decision_preview",
                "derived_view": True,
                "primary_authority": False,
                "execution_authorized": False,
                **evaluate_policy_decision(
                    actor=args.actor,
                    action=args.action,
                    target=args.target,
                    scope={},
                    approved=bool(args.approved),
                ),
            }
        )

    if args.command == "contract-atlas":
        return _with_conn(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            callback=lambda conn: build_contract_atlas(
                conn,
                repo_root=source_root,
                project_id="dream-studio",
            ),
        )

    if args.command == "contract-atlas-refresh":
        changed_files = _changed_files_from_args(args)
        return _with_conn(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            callback=lambda conn: refresh_contract_atlas_exports(
                conn,
                repo_root=source_root,
                output_dir=Path(args.output_dir).resolve() if args.output_dir else None,
                project_id="dream-studio",
                changed_files=changed_files,
                reviewed_no_change_domains=args.docs_reviewed_no_change,
                include_private=bool(args.include_private),
                execute=bool(args.execute),
            ),
        )

    if args.command == "context-packet":
        return _with_conn(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            callback=lambda conn: generate_shared_context_packet(
                conn,
                packet_id=f"dry-run-{args.adapter}-{args.packet_type}",
                adapter_id=args.adapter,
                packet_type=args.packet_type,
                project_id=args.project_id,
                persist=False,
            ),
        )

    if args.command == "analytics-ingest":
        payload = load_analytics_payload(args.file)
        return _analytics_ingest(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            payload=payload,
            execute=bool(args.execute),
        )

    return 1


# ---------------------------------------------------------------------------
# Implementation helpers
# ---------------------------------------------------------------------------


def _analytics_ingest(
    *,
    source_root: Path,
    dream_studio_home: Path | None,
    payload: dict[str, Any],
    execute: bool,
) -> int:
    from core.event_store.studio_db import _connect
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError(
            "Dream Studio SQLite authority is missing. Run rehearsal-install for a rehearsal "
            "home, or install/bootstrap the real runtime through an approved update plan."
        )
    from core.analytics_ingestion import ingest_analytics_payload

    with _connect(paths.sqlite_path) as conn:
        return _print(ingest_analytics_payload(conn, payload, execute=execute))
