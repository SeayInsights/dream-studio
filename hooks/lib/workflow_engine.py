"""Workflow evaluation engine — pure logic layer.

Contains all stateless/pure functions used by the workflow CLI:
  - File locking primitive
  - YAML node extraction
  - Template resolution and condition evaluation
  - Ready-node computation

No direct filesystem I/O beyond reading YAML. All state I/O lives in
workflow_state.py, which imports from here.
"""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths           # noqa: E402
from lib.workflow_validate import parse_workflow  # noqa: E402
from lib.context_handoff import HANDOFF_PCT, URGENT_PCT  # noqa: E402


# ── File locking ──────────────────────────────────────────────────────


@contextmanager
def _file_lock(lock_path: Path, timeout: float = 5.0) -> Generator[None, None, None]:
    """Cross-platform atomic file lock using O_CREAT|O_EXCL."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                try:
                    lock_path.unlink(missing_ok=True)
                except OSError:
                    pass
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                break
            time.sleep(0.01)
    try:
        yield
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


# ── YAML node extraction ───────────────────────────────────────────────


def _extract_node_ids(yaml_path: str) -> list[str]:
    """Extract node IDs from workflow YAML, skipping block scalar content."""
    try:
        data = parse_workflow(yaml_path)
        return [n["id"] for n in data.get("nodes", []) if "id" in n]
    except Exception:
        pass
    # Fallback: naive parse that tracks block scalars to avoid false matches
    ids = []
    block_indent: int | None = None
    with open(yaml_path, encoding="utf-8", newline="") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            stripped = line.strip()
            if not stripped:
                continue
            indent = len(line) - len(line.lstrip())
            if stripped.endswith("|") or stripped.endswith("|−") or stripped.endswith(">"):
                block_indent = indent
                continue
            if block_indent is not None:
                if indent > block_indent:
                    continue
                block_indent = None
            if stripped.startswith("- id:"):
                node_id = stripped.split(":", 1)[1].strip()
                if node_id:
                    ids.append(node_id)
    return ids


# ── Template resolution ────────────────────────────────────────────────


def _resolve_ref(ref: str, wf: dict) -> str | None:
    """Resolve a node.field reference against workflow state. Returns None if missing."""
    if "." not in ref:
        return None
    node_id, field = ref.rsplit(".", 1)
    node = wf.get("nodes", {}).get(node_id)
    if node is None:
        return None
    return str(node.get(field, ""))


def _resolve_session_ref(filename: str, session_dir: str | None) -> str | None:
    """Resolve a session:<filename> reference. Returns None if no session dir or empty result."""
    if not session_dir:
        return None
    try:
        from lib.session_cache import read_session_file, read_all_session_files
        if filename in ("*", "all"):
            result = read_all_session_files(session_dir)
        else:
            result = read_session_file(session_dir, filename)
        return result if result else None
    except ImportError:
        return None


def resolve_templates(text: str, wf: dict, session_dir: str | None = None) -> str:
    """Resolve all {{ref}} templates in text.

    Supported patterns:
      {{node_id.field}}    — resolved via workflow state
      {{session:filename}} — resolved via session_cache
    Unresolved templates are left as-is.
    """
    def _replace(m: re.Match) -> str:
        ref = m.group(1)
        if ref.startswith("session:"):
            filename = ref[len("session:"):]
            val = _resolve_session_ref(filename, session_dir)
            return val if val is not None else m.group(0)
        val = _resolve_ref(ref, wf)
        return val if val is not None else m.group(0)

    return re.sub(r"\{\{(.+?)\}\}", _replace, text)


def _coerce(val: str) -> int | float | str:
    """Coerce a string value to int, float, or str. Resolves 'quality-score' alias."""
    if val == "quality-score":
        score_path = paths.meta_dir() / "quality-score.json"
        if score_path.is_file():
            try:
                return float(
                    json.loads(score_path.read_text(encoding="utf-8"))
                    .get("overall_score", 0)
                )
            except (json.JSONDecodeError, OSError, ValueError):
                pass
        return 0.0
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


# ── Condition evaluation ───────────────────────────────────────────────


def _evaluate(expr: str, wf: dict) -> bool:
    """Evaluate a condition expression against workflow state.

    Parses operator position from the raw expression BEFORE resolving templates,
    so `==` inside a resolved node output value cannot corrupt the split.
    """

    def _resolve(s: str) -> tuple[str, bool]:
        unresolved = False

        def _replace(m: re.Match) -> str:
            nonlocal unresolved
            val = _resolve_ref(m.group(1), wf)
            if val is None:
                unresolved = True
                return ""
            return val

        result = re.sub(r"\{\{(.+?)\}\}", _replace, s)
        if "{{" in result or "}}" in result:
            unresolved = True
        return result, unresolved

    # Find first top-level operator (not inside {{ }})
    found_op = None
    found_pos = -1
    for op in ("!=", ">=", "<=", "==", ">", "<"):
        start = 0
        while True:
            idx = expr.find(op, start)
            if idx < 0:
                break
            before = expr[:idx]
            if before.count("{{") - before.count("}}") == 0:
                found_op = op
                found_pos = idx
                break
            start = idx + 1
        if found_op:
            break

    if found_op and found_pos >= 0:
        raw_left = expr[:found_pos].strip()
        raw_right = expr[found_pos + len(found_op):].strip()
        left_resolved, left_missing = _resolve(raw_left)
        right_resolved, right_missing = _resolve(raw_right)
        if left_missing or right_missing:
            return False
        left_val = _coerce(left_resolved.strip())
        right_val = _coerce(right_resolved.strip())
        if isinstance(left_val, (int, float)) and isinstance(right_val, (int, float)):
            return {
                "==": left_val == right_val, "!=": left_val != right_val,
                ">": left_val > right_val,   "<": left_val < right_val,
                ">=": left_val >= right_val,  "<=": left_val <= right_val,
            }[found_op]
        left_str, right_str = str(left_val), str(right_val)
        if found_op == "==":
            return (left_str == right_str
                    or left_str.startswith(right_str + ":")
                    or right_str.startswith(left_str + ":"))
        if found_op == "!=":
            return (left_str != right_str
                    and not left_str.startswith(right_str + ":")
                    and not right_str.startswith(left_str + ":"))
        return False

    resolved, has_unresolved = _resolve(expr)
    if has_unresolved:
        return False
    return bool(resolved.strip())


# ── Output compression ────────────────────────────────────────────────


def compress_node_output(raw_output: str, compress_type: str) -> str | None:
    """Compress node output according to the compress_type.

    Currently supported: "findings" (via findings_summarizer).
    Returns compressed JSON string, or None on failure (caller falls back to raw).
    """
    if compress_type != "findings":
        return None
    try:
        from lib.findings_summarizer import summarize_findings
        result = summarize_findings(raw_output)
        if result and result.get("total", 0) > 0:
            return json.dumps(result, indent=2)
        return None
    except (ImportError, Exception):
        return None


# ── Context budget guard ───────────────────────────────────────────────


def _check_context_budget(n_agents: int) -> str | None:
    """Check remaining context budget before dispatching parallel agents.

    Reads ~/.dream-studio/state/context.json (written by on-context-threshold).
    Returns None when dispatch is safe, "warn" when the user should confirm,
    or "block" when dispatch must be skipped entirely.

    Callers should handle each return value:
      None   → proceed normally
      "warn" → prompt user; if non-interactive, write warning to state and skip
      "block" → skip wave entirely, write WARNING status to state
    """
    context_file = paths.state_dir() / "context.json"
    if not context_file.is_file():
        return None

    try:
        data = json.loads(context_file.read_text(encoding="utf-8"))
        pct = float(data.get("pct", data.get("used_pct", 0)))
    except Exception:
        return None

    if pct <= 0:
        return None

    if pct >= URGENT_PCT:
        print(
            f"[workflow] Context at {pct:.0f}% — too high to dispatch parallel agents safely. "
            f"Run /compact or start a new session.",
            flush=True,
        )
        return "block"

    if pct >= HANDOFF_PCT:
        msg = (
            f"[workflow] Context at {pct:.0f}%. Dispatching {n_agents} parallel agent(s) "
            f"may push into auto-compact. Continue? (y/n): "
        )
        if not sys.stdin.isatty():
            print(
                f"[workflow] Context at {pct:.0f}% — non-interactive session, "
                f"skipping parallel dispatch of {n_agents} agent(s).",
                flush=True,
            )
            return "block"
        try:
            answer = input(msg).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "block"
        if answer not in ("y", "yes"):
            return "block"

    return None


# ── Ready-node computation ─────────────────────────────────────────────


def _compute_ready_nodes(
    yaml_nodes: dict,
    state_nodes: dict,
    wf: dict,
) -> tuple[list[str], list[str]]:
    """Return (ready, skipped_by_condition) from yaml and state data.

    Pure function — no I/O. Callers handle writing skipped nodes back to state.
    """
    skipped_by_condition: list[str] = []
    ready: list[str] = []

    for nid, ynode in yaml_nodes.items():
        snode = state_nodes.get(nid, {})
        if snode.get("status") != "pending":
            continue

        deps = ynode.get("depends_on", [])
        if isinstance(deps, str):
            deps = [deps]

        trigger_rule = ynode.get("trigger_rule", "all_success")
        dep_statuses = [state_nodes.get(d, {}).get("status", "pending") for d in deps]

        deps_met = False
        if not deps:
            deps_met = True
        elif trigger_rule == "all_success":
            deps_met = all(s == "completed" for s in dep_statuses)
        elif trigger_rule == "all_done":
            deps_met = all(s in ("completed", "failed", "skipped") for s in dep_statuses)
        elif trigger_rule == "one_success":
            deps_met = any(s == "completed" for s in dep_statuses)

        if not deps_met:
            continue

        condition = ynode.get("condition")
        if condition:
            try:
                condition_met = _evaluate(condition, wf)
            except Exception:
                condition_met = False
            if not condition_met:
                skipped_by_condition.append(nid)
                continue

        ready.append(nid)

    return ready, skipped_by_condition
