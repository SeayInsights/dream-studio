#!/usr/bin/env python3
"""Workflow state management CLI.

Chief-of-Staff calls these commands during workflow execution instead
of manually reading/editing JSON. One Bash call per state change.

Commands:
  start  <name> <yaml-path>                          → init workflows.json, print key
  update <key> <node-id> <status> [--output] [--duration]  → update node
  pause  <key> <node-id> <gate-name>                  → pause at gate
  resume <key>                                         → resume from gate
  abort  <key>                                         → cancel workflow
  status [<key>]                                       → print state
  eval   <key> <expression>                            → evaluate condition, exit 0=true 1=false
  next   <key>                                         → list nodes ready to execute

Pure evaluation logic lives in workflow_engine.py. This module handles
all CLI parsing, state I/O, and command dispatch.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths                                        # noqa: E402
from lib.workflow_validate import parse_workflow             # noqa: E402
from lib.workflow_engine import (                            # noqa: E402
    _file_lock, _extract_node_ids,
    _evaluate, _resolve_ref, _coerce,
    _compute_ready_nodes, _check_context_budget,
)

SCHEMA_VERSION = 1


# ── State I/O ─────────────────────────────────────────────────────────


def _state_path() -> Path:
    return paths.state_dir() / "workflows.json"


def _checkpoint_path() -> Path:
    return paths.state_dir() / "workflow-checkpoint.json"


def _state_lock():
    """Lock for atomic read-modify-write on workflows.json."""
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    return _file_lock(p.parent / f"{p.name}.lock")


def _read_state() -> dict:
    p = _state_path()
    if not p.is_file():
        return {"schema_version": SCHEMA_VERSION, "active_workflows": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("schema_version", 1) > SCHEMA_VERSION:
            print(f"Error: workflows.json schema_version {data.get('schema_version')} "
                  f"exceeds supported ({SCHEMA_VERSION})", file=sys.stderr)
            sys.exit(1)
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading workflows.json: {e}", file=sys.stderr)
        sys.exit(1)


def _write_state(data: dict) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    out = {**data, "schema_version": SCHEMA_VERSION}
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")


def _write_checkpoint(workflow_key: str, node_id: str | None, status: str) -> None:
    p = _checkpoint_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "workflow_key": workflow_key,
        "last_node": node_id,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, indent=2), encoding="utf-8")


def _get_workflow(data: dict, key: str) -> dict:
    wf = data.get("active_workflows", {}).get(key)
    if not wf:
        print(f"Error: workflow '{key}' not found", file=sys.stderr)
        sys.exit(1)
    return wf


# ── Commands ──────────────────────────────────────────────────────────


def cmd_start(args: argparse.Namespace) -> None:
    yaml_path = args.yaml_path
    if not Path(yaml_path).is_file():
        print(f"Error: file not found: {yaml_path}", file=sys.stderr)
        sys.exit(1)

    node_ids = _extract_node_ids(yaml_path)
    if not node_ids:
        print(f"Error: no nodes found in {yaml_path}", file=sys.stderr)
        sys.exit(1)

    key = f"{args.name}-{int(time.time())}"
    now = datetime.now(timezone.utc).isoformat()

    with _state_lock():
        data = _read_state()
        data.setdefault("active_workflows", {})[key] = {
            "workflow": args.name,
            "started": now,
            "status": "running",
            "current_node": None,
            "yaml_path": str(Path(yaml_path).resolve()),
            "nodes": {nid: {"status": "pending"} for nid in node_ids},
            "gates_passed": [],
            "gates_pending": [],
        }
        _write_state(data)
    _write_checkpoint(key, None, "running")

    print(key)
    print(f"[workflow] {args.name} started — {len(node_ids)} nodes initialized")


def cmd_update(args: argparse.Namespace) -> None:
    with _state_lock():
        data = _read_state()
        wf = _get_workflow(data, args.key)
        nodes = wf.get("nodes", {})

        if args.node_id not in nodes:
            print(f"Error: node '{args.node_id}' not in workflow", file=sys.stderr)
            sys.exit(1)

        now = datetime.now(timezone.utc).isoformat()
        node = nodes[args.node_id]
        node["status"] = args.status

        if args.status == "running" and "started" not in node:
            node["started"] = now
        if args.status in ("completed", "failed", "skipped"):
            node["finished"] = now
        if args.output is not None:
            node["output"] = args.output
        if args.duration is not None:
            node["duration_s"] = args.duration

        wf["current_node"] = args.node_id

        statuses = [n.get("status") for n in nodes.values()]
        if all(s in ("completed", "skipped") for s in statuses):
            wf["status"] = "completed"
        elif all(s in ("completed", "skipped", "failed") for s in statuses):
            wf["status"] = "completed_with_failures"

        _write_state(data)
    _write_checkpoint(args.key, args.node_id, args.status)

    done = sum(1 for s in statuses if s in ("completed", "skipped"))
    print(f"[workflow] {wf['workflow']} — Node {args.node_id} "
          f"{args.status.upper()} ({done}/{len(nodes)} done)")


def cmd_pause(args: argparse.Namespace) -> None:
    with _state_lock():
        data = _read_state()
        wf = _get_workflow(data, args.key)

        wf["status"] = "paused"
        wf["current_node"] = args.node_id
        pending = wf.setdefault("gates_pending", [])
        if args.gate_name not in pending:
            pending.append(args.gate_name)

        _write_state(data)
    _write_checkpoint(args.key, args.node_id, "paused")

    nodes = wf.get("nodes", {})
    done = sum(1 for n in nodes.values() if n.get("status") in ("completed", "skipped"))
    print(f"[workflow] {wf['workflow']} — PAUSED at gate \"{args.gate_name}\" "
          f"on node \"{args.node_id}\" ({done}/{len(nodes)} done)")


def cmd_resume(args: argparse.Namespace) -> None:
    with _state_lock():
        data = _read_state()
        wf = _get_workflow(data, args.key)

        pending = wf.get("gates_pending", [])
        if pending:
            gate = pending.pop(0)
            passed = wf.setdefault("gates_passed", [])
            passed.append(f"{wf.get('current_node')}:{gate}")

        wf["status"] = "running"
        _write_state(data)
    _write_checkpoint(args.key, wf.get("current_node"), "running")
    print(f"[workflow] {wf['workflow']} — RESUMED")


def cmd_abort(args: argparse.Namespace) -> None:
    with _state_lock():
        data = _read_state()
        wf = _get_workflow(data, args.key)

        for node in wf.get("nodes", {}).values():
            if node.get("status") in ("pending", "running", "blocked_by_deps"):
                node["status"] = "skipped"

        wf["status"] = "aborted"
        _write_state(data)
    _write_checkpoint(args.key, wf.get("current_node"), "aborted")
    print(f"[workflow] {wf['workflow']} — ABORTED")


def cmd_status(args: argparse.Namespace) -> None:
    data = _read_state()
    workflows = data.get("active_workflows", {})

    if not workflows:
        print("No workflows.")
        return

    targets = {args.key: workflows[args.key]} if args.key else workflows
    for key in targets:
        if key not in workflows:
            print(f"Error: workflow '{key}' not found", file=sys.stderr)
            sys.exit(1)

    for key, wf in targets.items():
        name = wf.get("workflow", key)
        nodes = wf.get("nodes", {})
        done = sum(1 for n in nodes.values() if n.get("status") in ("completed", "skipped"))
        print(f"[workflow] {name} ({key}) — {wf.get('status', '?')} ({done}/{len(nodes)} done)")

        if args.key:
            for nid, node in nodes.items():
                s = node.get("status", "pending")
                out = node.get("output", "")
                dur = node.get("duration_s")
                line = f"  {s:12s} {nid}"
                if out:
                    line += f" -> {out[:60]}"
                if dur:
                    line += f" ({dur}s)"
                print(line)

            pending_gates = wf.get("gates_pending", [])
            if pending_gates:
                print(f"  Gates pending: {', '.join(pending_gates)}")

            cp = _checkpoint_path()
            if cp.is_file():
                try:
                    checkpoint = json.loads(cp.read_text(encoding="utf-8"))
                    if checkpoint.get("workflow_key") == key:
                        print(f"  Checkpoint: {checkpoint.get('last_node')} "
                              f"@ {checkpoint.get('timestamp', '?')[:19]}")
                except (json.JSONDecodeError, OSError):
                    pass


def cmd_eval(args: argparse.Namespace) -> None:
    data = _read_state()
    wf = _get_workflow(data, args.key)
    result = _evaluate(args.expression, wf)
    print("true" if result else "false")
    sys.exit(0 if result else 1)


def cmd_next(args: argparse.Namespace) -> None:
    data = _read_state()
    wf = _get_workflow(data, args.key)

    if wf.get("status") == "paused":
        gate = (wf.get("gates_pending") or ["?"])[0]
        node = wf.get("current_node", "?")
        print(f"paused: {node} (gate: {gate})")
        return

    if wf.get("status") in ("completed", "completed_with_failures", "aborted"):
        print("done")
        return

    yaml_path = wf.get("yaml_path")
    if not yaml_path or not Path(yaml_path).is_file():
        print(f"Error: YAML not found at {yaml_path}", file=sys.stderr)
        sys.exit(1)

    yaml_data = parse_workflow(yaml_path)
    yaml_nodes = {n["id"]: n for n in yaml_data.get("nodes", []) if "id" in n}
    state_nodes = wf.get("nodes", {})

    ready, skipped_by_condition = _compute_ready_nodes(yaml_nodes, state_nodes, wf)

    if skipped_by_condition:
        now = datetime.now(timezone.utc).isoformat()
        for nid in skipped_by_condition:
            state_nodes[nid]["status"] = "skipped"
            state_nodes[nid]["finished"] = now
            state_nodes[nid]["output"] = "SKIPPED: condition false"
        with _state_lock():
            data2 = _read_state()
            wf2 = data2.get("active_workflows", {}).get(args.key, {})
            for nid in skipped_by_condition:
                wf2.get("nodes", {}).setdefault(nid, {}).update(state_nodes[nid])
            _write_state(data2)
        print(f"skipped (condition false): {', '.join(skipped_by_condition)}")

    if not ready:
        running = [nid for nid, n in state_nodes.items() if n.get("status") == "running"]
        if running:
            print(f"waiting: {', '.join(running)} still running")
        elif not skipped_by_condition:
            print("blocked: no nodes ready (check for failed dependencies)")
        return

    # Check context budget before dispatching parallel agents
    if len(ready) > 1:
        budget_result = _check_context_budget(len(ready))
        if budget_result == "block":
            now = datetime.now(timezone.utc).isoformat()
            with _state_lock():
                data2 = _read_state()
                wf2 = data2.get("active_workflows", {}).get(args.key, {})
                for nid in ready:
                    wf2.get("nodes", {}).setdefault(nid, {}).update({
                        "status": "skipped",
                        "finished": now,
                        "output": "WARNING: parallel dispatch skipped — context budget too high",
                    })
                _write_state(data2)
            _write_checkpoint(args.key, ready[0], "skipped")
            print(f"skipped (context budget): {', '.join(ready)}")
            return

    has_gate = {nid: yaml_nodes[nid]["gate"] for nid in ready if yaml_nodes[nid].get("gate")}
    model_map = {nid: yaml_nodes[nid]["model"] for nid in ready if yaml_nodes[nid].get("model")}

    print(f"ready: {', '.join(ready)}")
    if len(ready) > 1:
        print("  (parallel — these share the same dependency wave)")
    for nid in ready:
        parts = []
        if nid in has_gate:
            parts.append(f"gate={has_gate[nid]}")
        if nid in model_map:
            parts.append(f"model={model_map[nid]}")
        skill = yaml_nodes[nid].get("skill")
        cmd = yaml_nodes[nid].get("command")
        if skill:
            parts.append(f"skill={skill}")
        elif cmd:
            parts.append("command")
        if parts:
            print(f"  {nid}: {', '.join(parts)}")


# ── CLI ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(prog="workflow_state", description="Workflow state CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("start", help="Initialize a new workflow")
    p.add_argument("name")
    p.add_argument("yaml_path")

    p = sub.add_parser("update", help="Update a node's status")
    p.add_argument("key")
    p.add_argument("node_id")
    p.add_argument("status", choices=["pending", "running", "completed", "failed", "skipped"])
    p.add_argument("--output")
    p.add_argument("--duration", type=float)

    p = sub.add_parser("pause", help="Pause at a gate")
    p.add_argument("key")
    p.add_argument("node_id")
    p.add_argument("gate_name")

    p = sub.add_parser("resume", help="Resume from a gate")
    p.add_argument("key")

    p = sub.add_parser("abort", help="Cancel the workflow")
    p.add_argument("key")

    p = sub.add_parser("status", help="Print workflow state")
    p.add_argument("key", nargs="?")

    p = sub.add_parser("eval", help="Evaluate a condition expression")
    p.add_argument("key")
    p.add_argument("expression")

    p = sub.add_parser("next", help="List nodes ready to execute")
    p.add_argument("key")

    args = parser.parse_args()
    cmds = {
        "start": cmd_start, "update": cmd_update, "pause": cmd_pause,
        "resume": cmd_resume, "abort": cmd_abort, "status": cmd_status,
        "eval": cmd_eval, "next": cmd_next,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
