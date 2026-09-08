"""Gate: a workflow node says how its effect is verified, or says it is not.

THE DEFECT THIS EXISTS FOR, measured 2026-09-08. Operator, on the orchestrator: it "doesn't
do fucking shit." Accurate. ZERO of ~150 nodes across 18 canonical workflows declared a
``completion_check`` -- 0/14 in ``execute-work-orders.yaml``, 0/15 in ``idea-to-pr.yaml``,
0/12 in ``feature-research.yaml``, and so on for every file.

The machinery was built (WO 1db6de49) precisely so a node's effect could be observed
independently of what an agent claims. ``runner.py::_completion_verdict`` is correct,
template-resolving, bounded, and documents its own reasoning at length. Nothing used it.
That is a mechanism with no caller at the MANIFEST level -- one layer above where
``core/gates/reachability.py`` looks, since that gate reads Python definitions and not YAML
fields.

What it costs. A ``command:`` node's text is a PROMPT; the runner's own comment says
"(LLM instruction prompt)". It is written to a context file, handed to ``ds-core:build``,
and the runner advances. With no ``completion_check`` the node lands ``unverified`` --
honest, and useless: the live run ``orch-verify-1788306820`` sat at 1/14 for days, three
nodes "executed" in 0.01-0.03s.

THE RULE. Every node in a CHANGED workflow file declares either a ``completion_check`` or
an inline ``UNVERIFIED BY DESIGN: <reason>`` comment. Not every node CAN be checked -- 11
of the orchestrator's 14 need an authority id or the previous node's PR number, and one
needs a negative assertion the check vocabulary cannot express -- so the gate demands a
STATED position rather than a check. An unverifiable node is acceptable; an unexamined one
is not.

DIFF-SCOPED on purpose. Roughly 136 nodes in other workflows still declare nothing, and
failing the whole tree would make this gate a wall on day one and get it switched off. It
stops the next one, and the backlog drains as those files are touched -- the same ratchet
``normative-baseline`` uses.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

WORKFLOW_DIR = "canonical/workflows"

#: An inline declaration that a node is deliberately unverifiable, and why. The reason is
#: mandatory: "unverified" with no cause is the silence this gate exists to end.
_UNVERIFIED_RE = re.compile(r"UNVERIFIED BY DESIGN:\s*(?P<reason>\S.*)")

#: Shorter than this is not a reason.
_MIN_REASON_CHARS = 20


def changed_workflow_files(base_ref: str | None = None) -> list[str]:
    """Workflow manifests this change set touches, staged or committed.

    Untracked files are included: ``git diff`` never reports one, and a new workflow is
    exactly the case this gate most needs to see -- the gitignore-phantom gate was written
    after that same blind spot.
    """
    base = base_ref or os.environ.get("DREAM_STUDIO_BASE_REF") or "origin/main"
    paths: set[str] = set()
    for argv in (
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                argv,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0:
            continue
        for line in (proc.stdout or "").splitlines():
            name = line.strip().replace("\\", "/")
            if name.startswith(WORKFLOW_DIR) and name.endswith((".yaml", ".yml")):
                paths.add(name)
    return sorted(paths)


def _node_blocks(text: str) -> list[tuple[str, str]]:
    """``(node_id, block_text)`` for each node, split on the list-item boundary.

    Read as TEXT rather than parsed YAML because the declaration may be an inline COMMENT,
    which a parser discards -- and a gate that could not see the comment it requires would
    demand something it cannot observe.
    """
    blocks: list[tuple[str, str]] = []
    current_id: str | None = None
    current: list[str] = []
    for line in text.splitlines():
        match = re.match(r"\s*-\s+id:\s*(?P<id>\S+)", line)
        if match:
            if current_id is not None:
                blocks.append((current_id, "\n".join(current)))
            current_id = match.group("id")
            current = [line]
            continue
        if current_id is not None:
            if re.match(r"^[A-Za-z_]", line):  # a new top-level key ends the node list
                blocks.append((current_id, "\n".join(current)))
                current_id, current = None, []
                continue
            current.append(line)
    if current_id is not None:
        blocks.append((current_id, "\n".join(current)))
    return blocks


def _offenders_in(rel: str) -> list[dict]:
    path = REPO_ROOT / rel
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return offenders_in_text(text, rel)


def offenders_in_text(text: str, label: str = "<text>") -> list[dict]:
    """Findings for one manifest's TEXT. Public so tests can call it with constructed
    input -- absent, empty, malformed, a reason that is a shrug -- rather than editing a
    real manifest. Mutating a real input tests the input; it does not test the checker."""
    rel = label
    offenders: list[dict] = []
    for node_id, block in _node_blocks(text):
        # Horizontal whitespace only. `\s*\S` spans the NEWLINE -- so
        # `completion_check:` with an empty value matched the next line's text and an
        # empty check read as present. Found by a constructed-input test, not by reading.
        has_check = bool(re.search(r"^[^\S\n]*completion_check:[^\S\n]*\S", block, re.MULTILINE))
        declared = _UNVERIFIED_RE.search(block)
        if has_check:
            continue
        if declared is None:
            offenders.append(
                {
                    "workflow": rel,
                    "node": node_id,
                    "message": (
                        f"node {node_id!r} declares neither a completion_check nor an"
                        " inline 'UNVERIFIED BY DESIGN: <reason>'. Without one the runner"
                        " marks it `unverified` and advances, so the workflow reports"
                        " progress nobody observed -- which is why a live orchestrator run"
                        " sat at 1 of 14 nodes with three of them 'executed' in under a"
                        " tenth of a second. An unverifiable node is acceptable; an"
                        " unexamined one is not."
                    ),
                }
            )
            continue
        reason = declared.group("reason").strip()
        if len(reason) < _MIN_REASON_CHARS:
            offenders.append(
                {
                    "workflow": rel,
                    "node": node_id,
                    "message": (
                        f"node {node_id!r} is declared unverifiable with no usable reason"
                        f" ({reason!r}). Name what the check would have to observe and"
                        " what prevents it, in at least"
                        f" {_MIN_REASON_CHARS} characters, so someone can later close it."
                    ),
                }
            )
    return offenders


def run(base_ref: str | None = None) -> dict:
    """Scan the workflow manifests this change set touches."""
    files = changed_workflow_files(base_ref)
    offenders: list[dict] = []
    for rel in files:
        offenders.extend(_offenders_in(rel))
    return {
        "status": "fail" if offenders else "pass",
        "workflows_checked": files,
        "offenders": offenders,
    }


def main() -> int:
    result = run()
    if result["status"] != "pass":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\nworkflow-node-verification: FAILED - {len(result['offenders'])} node(s) say"
            " nothing about how their effect is verified.",
            file=sys.stderr,
        )
        return 1
    checked = result["workflows_checked"]
    if not checked:
        print("workflow-node-verification: OK - no workflow manifest changed.")
    else:
        print(
            "workflow-node-verification: OK - every node in"
            f" {len(checked)} changed workflow(s) declares how it is verified."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
