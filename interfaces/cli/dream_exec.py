#!/usr/bin/env python3
"""Dream Exec - Execution graph CLI commands.

Provides comprehensive execution graph management and visibility.

Usage:
    # Show execution status
    dream exec status [--project <id>]

    # Show execution tree
    dream exec tree <node_id>

    # Show compiled context
    dream exec context <node_id>

    # Resume execution from node
    dream exec resume <node_id>

    # List active executions
    dream exec active

    # List blocked nodes
    dream exec blocked

    # Show metrics
    dream exec metrics <project_id>
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.execution.graph import ExecutionGraphManager
from core.execution.context_compiler import ContextCompiler
from core.execution.workflow_integration import WorkflowGraphIntegration
from core.config.database import get_connection


def cmd_status(args):
    """Show execution status."""
    with get_connection(read_only=True) as conn:
        if args.project:
            # Show status for specific project
            cursor = conn.execute(
                """
                SELECT node_type, status, COUNT(*) as count
                FROM execution_nodes
                WHERE project_id = ?
                GROUP BY node_type, status
                ORDER BY node_type, status
                """,
                (args.project,),
            )
        else:
            # Show overall status
            cursor = conn.execute("""
                SELECT node_type, status, COUNT(*) as count
                FROM execution_nodes
                GROUP BY node_type, status
                ORDER BY node_type, status
                """)

        print("=" * 70)
        print("EXECUTION STATUS")
        print("=" * 70)

        current_type = None
        for row in cursor.fetchall():
            node_type, status, count = row
            if node_type != current_type:
                if current_type is not None:
                    print()
                print(f"{node_type.upper()}:")
                current_type = node_type
            print(f"  {status:12s}: {count:4d}")

        print("=" * 70)

    return 0


def cmd_tree(args):
    """Show execution tree."""
    graph = ExecutionGraphManager()

    def print_tree(node_id: str, indent: int = 0):
        node = graph.get_node(node_id)
        if not node:
            return

        status_icon = {
            "pending": "[ ]",
            "active": "[~]",
            "completed": "[x]",
            "failed": "[!]",
            "blocked": "[-]",
            "skipped": "[ ]",
        }.get(node.status, "[?]")

        prefix = "  " * indent
        print(f"{prefix}{status_icon} {node.node_type}: {node.title}")

        if args.verbose:
            if node.started_at:
                print(f"{prefix}    Started: {node.started_at}")
            if node.completed_at:
                print(f"{prefix}    Completed: {node.completed_at}")
            if node.context_tokens:
                print(f"{prefix}    Context: {node.context_tokens} tokens")

        children = graph.get_children(node_id)
        for child in children:
            print_tree(child.node_id, indent + 1)

    print_tree(args.node_id)
    return 0


def cmd_context(args):
    """Show compiled context for a node."""
    compiler = ContextCompiler()
    compiled = compiler.compile_for_node(args.node_id)

    if not compiled:
        print(f"Failed to compile context for node: {args.node_id}")
        return 1

    if args.export:
        # Export as JSON
        context_dict = compiler.export_context(compiled)
        print(json.dumps(context_dict, indent=2))
    else:
        # Show report
        print(compiler.format_report(compiled))

    return 0


def cmd_resume(args):
    """Resume execution from a node."""
    graph = ExecutionGraphManager()
    node = graph.get_node(args.node_id)

    if not node:
        print(f"Node not found: {args.node_id}")
        return 1

    print("=" * 70)
    print("RESUME EXECUTION")
    print("=" * 70)
    print(f"Node: {node.node_type} - {node.title}")
    print(f"Status: {node.status}")
    print()

    # Check dependencies
    deps = graph.get_dependencies(args.node_id)
    if deps:
        print(f"Dependencies ({len(deps)}):")
        all_complete = True
        for dep in deps:
            target = graph.get_node(dep.target_node_id)
            if target:
                status_icon = "[x]" if target.status == "completed" else "[ ]"
                print(f"  {status_icon} {target.title} ({target.status})")
                if target.status != "completed":
                    all_complete = False

        if not all_complete:
            print("\n[WARNING] Not all dependencies are completed")
            print("Resume anyway? (y/N): ", end="")
            if input().lower() != "y":
                print("Cancelled")
                return 0
        print()

    # Get compiled context
    compiler = ContextCompiler()
    compiled = compiler.compile_for_node(args.node_id)

    if compiled:
        print(f"Compiled Context: {compiled.total_tokens} tokens")
        print(f"Token Savings: {compiled.savings_pct:.1f}%")
        print()

        if args.show_context:
            print("Context Preview:")
            print(compiler.format_report(compiled))

    print("=" * 70)
    print("[INFO] To execute this node, integrate with workflow system")
    print("       (Phase 5 integration in progress)")
    print("=" * 70)

    return 0


def cmd_active(args):
    """List active executions."""
    with get_connection(read_only=True) as conn:
        cursor = conn.execute("""
            SELECT node_id, node_type, title, started_at,
                   (julianday('now') - julianday(started_at)) * 24 * 60 as runtime_minutes
            FROM execution_nodes
            WHERE status = 'active'
            ORDER BY started_at ASC
            """)

        rows = cursor.fetchall()

        if not rows:
            print("No active executions")
            return 0

        print("=" * 70)
        print("ACTIVE EXECUTIONS")
        print("=" * 70)

        for row in rows:
            node_id, node_type, title, started_at, runtime_min = row
            print(f"{node_type:8s} {title[:40]:40s} {runtime_min:6.1f}m")
            if args.verbose:
                print(f"         {node_id}")
                print(f"         Started: {started_at}")
                print()

        print("=" * 70)
        print(f"Total: {len(rows)} active")

    return 0


def cmd_blocked(args):
    """List blocked nodes."""
    with get_connection(read_only=True) as conn:
        cursor = conn.execute("""
            SELECT
                en.node_id,
                en.node_type,
                en.title,
                COUNT(ed.dependency_id) as blocking_count
            FROM execution_nodes en
            JOIN execution_dependencies ed ON en.node_id = ed.source_node_id
            JOIN execution_nodes blocker ON ed.target_node_id = blocker.node_id
            WHERE en.status = 'blocked'
              AND blocker.status != 'completed'
              AND ed.dependency_type = 'blocks'
            GROUP BY en.node_id
            ORDER BY blocking_count DESC
            """)

        rows = cursor.fetchall()

        if not rows:
            print("No blocked nodes")
            return 0

        print("=" * 70)
        print("BLOCKED NODES")
        print("=" * 70)

        for row in rows:
            node_id, node_type, title, blocking_count = row
            print(f"{node_type:8s} {title[:40]:40s} blocked by {blocking_count}")
            if args.verbose:
                print(f"         {node_id}")
                print()

        print("=" * 70)
        print(f"Total: {len(rows)} blocked")

    return 0


def cmd_metrics(args):
    """Show execution metrics for a project."""
    integration = WorkflowGraphIntegration()
    summary = integration.get_execution_summary(args.project_id)

    print("=" * 70)
    print("EXECUTION METRICS")
    print("=" * 70)
    print(f"Project: {args.project_id[:16]}...")
    print()

    # Node metrics
    print("NODES BY TYPE AND STATUS")
    print("-" * 70)
    for node_type, statuses in summary["metrics"].items():
        total = sum(statuses.values())
        print(f"{node_type.upper()}:")
        for status, count in statuses.items():
            pct = (count / total * 100) if total > 0 else 0
            print(f"  {status:12s}: {count:4d} ({pct:5.1f}%)")
        print()

    # Token metrics
    token_stats = summary["token_stats"]
    print("TOKEN METRICS")
    print("-" * 70)
    print(f"Average Context: {token_stats['avg_context_tokens']:.0f} tokens")
    print(f"Total Context: {token_stats['total_context_tokens']:,} tokens")
    print(f"Nodes with Context: {token_stats['nodes_with_context']}")

    # Calculate savings estimate
    if token_stats["nodes_with_context"] > 0:
        baseline_total = 7500 * token_stats["nodes_with_context"]
        actual_total = token_stats["total_context_tokens"]
        savings_pct = ((baseline_total - actual_total) / baseline_total) * 100
        print(f"\nEstimated Savings: {savings_pct:.1f}%")
        print(f"  (vs baseline: {baseline_total:,} tokens)")

    print("=" * 70)

    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Dream Exec - Execution graph management")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Status command
    status_parser = subparsers.add_parser("status", help="Show execution status")
    status_parser.add_argument("--project", "-p", help="Filter by project ID")
    status_parser.set_defaults(func=cmd_status)

    # Tree command
    tree_parser = subparsers.add_parser("tree", help="Show execution tree")
    tree_parser.add_argument("node_id", help="Root node ID")
    tree_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed info")
    tree_parser.set_defaults(func=cmd_tree)

    # Context command
    context_parser = subparsers.add_parser("context", help="Show compiled context")
    context_parser.add_argument("node_id", help="Node ID")
    context_parser.add_argument("--export", action="store_true", help="Export as JSON")
    context_parser.set_defaults(func=cmd_context)

    # Resume command
    resume_parser = subparsers.add_parser("resume", help="Resume execution from node")
    resume_parser.add_argument("node_id", help="Node ID to resume from")
    resume_parser.add_argument("--show-context", action="store_true", help="Show compiled context")
    resume_parser.set_defaults(func=cmd_resume)

    # Active command
    active_parser = subparsers.add_parser("active", help="List active executions")
    active_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed info")
    active_parser.set_defaults(func=cmd_active)

    # Blocked command
    blocked_parser = subparsers.add_parser("blocked", help="List blocked nodes")
    blocked_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed info")
    blocked_parser.set_defaults(func=cmd_blocked)

    # Metrics command
    metrics_parser = subparsers.add_parser("metrics", help="Show execution metrics")
    metrics_parser.add_argument("project_id", help="Project ID")
    metrics_parser.set_defaults(func=cmd_metrics)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
