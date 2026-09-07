"""Gate: a decided question has ONE supported read, and re-deriving it is refused.

THE DEFECT THIS EXISTS FOR, and it happened repeatedly. Asked whether thirteen work orders
could be closed, a survey called ``check_close_gates`` and looked for ``result["gates"]``.
The real keys are ``gates_pass`` and ``gate_failures``. ``dict.get`` on a wrong key returns
``None``, ``None`` is falsy, so "no failures found" -- and all thirteen were reported
CLOSABLE while every one was blocked on ``independent_review``. The operator was told work
was ready to close, more than once, and it was not.

The shape was documented correctly in ``canonical/skills/ds-workorder/modes/close/SKILL.md``
the whole time. So this is not a docs-drift problem and no doc fix would prevent it. The
defect is structural: answering a yes/no question through a dict lookup makes the PERMISSIVE
answer the default outcome of any mistake -- the same fail-open shape as
``core/gates/fail_open_probe.py``, one level up, in the code that ASKS rather than the code
that answers.

THE RULE. When a question has a function that answers it directly, that function is the only
supported read, and the raw fields it interprets may only be touched where they are produced.
``closability()`` returns ``(can_close, reasons)``; a tuple cannot be mis-keyed, and an
unpacking error is immediate and loud instead of silently optimistic. So ``gates_pass`` and
``gate_failures`` are readable inside the module that builds them and nowhere else.

The same applies to a VOCABULARY. ``TASK_DONE_STATUSES`` is the one definition of what a
finished task looks like; a survey that hardcoded ``('done', 'completed')`` reported every
work order as 0-done, because the stored value is ``complete``. Both mistakes are a caller
substituting its own copy of something the substrate already states once.

SQL IS DELIBERATELY OUT OF SCOPE. A first cut also flagged a status literal near
``business_tasks`` in query text. It named five lines containing no status comparison at all
-- a 400-character DOTALL window had bridged unrelated statements -- and Dream Studio
assembles SQL from literals concatenated across lines, which a regex over source text cannot
segment. A check that names the wrong line is worse than no check, so only the AST half
survives: a literal collection that re-spells the vocabulary.

WHAT THIS IS NOT. It is not a general "did you spell the key right" checker -- these result
dicts are assembled dynamically, so their key sets are not statically knowable, and a gate
that guessed at them would be the same defect in a new place. It enforces a short, explicit
table of contracts instead, and says so.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class Contract:
    """One decided question, its supported read, and where the raw fields may be touched."""

    def __init__(
        self,
        *,
        name: str,
        supported_read: str,
        fields: frozenset[str],
        owners: frozenset[str],
        why: str,
    ) -> None:
        self.name = name
        self.supported_read = supported_read
        self.fields = fields
        self.owners = owners
        self.why = why


CONTRACTS: tuple[Contract, ...] = (
    Contract(
        name="close-readiness",
        supported_read="core.work_orders.close.closability(...) -> (can_close, reasons)",
        fields=frozenset({"gates_pass", "gate_failures"}),
        owners=frozenset(
            {
                "core/work_orders/close_main.py",
                "core/work_orders/close.py",
                "core/gates/single_read_path.py",
                "tests/unit/test_single_read_path_gate.py",
                # Tests OF the producer. A test asserting that check_close_gates returns
                # gates_pass=True and gate_failures==[] is testing the very shape this
                # contract protects; it has to read the raw fields to do that.
                "tests/unit/test_work_order_close_extraction.py",
                "tests/unit/test_wo_lifecycle_surface.py",
            }
        ),
        why=(
            "A survey read result['gates'] instead of gates_pass/gate_failures, got None,"
            " and reported 13 blocked work orders CLOSABLE. Call closability() -- a tuple"
            " cannot be mis-keyed."
        ),
    ),
    Contract(
        name="task-done-vocabulary",
        supported_read="runtime.lib.enforcement.TASK_DONE_STATUSES",
        fields=frozenset(),
        owners=frozenset(
            {
                # The definition, and the standalone hook copy it is held in parity with.
                "core/work_orders/task_status.py",
                "runtime/lib/enforcement.py",
                "core/gates/single_read_path.py",
                "tests/unit/test_single_read_path_gate.py",
                "tests/unit/test_task_status_vocabulary.py",
                # MILESTONE status is a different vocabulary that happens to share the word
                # `complete`, and unifying it is its own change. Registered as work order
                # fc2916a4-386e-4bc1-a37f-70036c82001d rather than left as a silent exemption -- the no-deferred-findings
                # rule means an exemption with no work order behind it is a dropped finding.
                "core/work_orders/milestones_classify.py",
            }
        ),
        why=(
            "A survey hardcoded ('done', 'completed') and reported every work order 0-done;"
            " the stored value is 'complete'. There is one definition -- use it."
        ),
    ),
)

#: A tuple/list/set literal of task-status strings, written out instead of imported. Only
#: flagged when it pairs a done-ish word with another status word, so an ordinary string
#: like "complete" in a message is untouched.
_DONE_WORDS = frozenset({"complete", "completed", "done"})
_STATUS_WORDS = _DONE_WORDS | frozenset({"pending", "cancelled", "deleted", "in_progress"})


def _rel(path: Path, repo_root: Path) -> str:
    try:
        out = str(path.relative_to(repo_root))
    except ValueError:
        out = str(path)
    return out.replace(chr(92), "/")


def _field_reads(tree: ast.AST, fields: frozenset[str]) -> list[tuple[int, str]]:
    """Every `x["field"]` and `x.get("field")` for a watched field."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and node.slice.value in fields
        ):
            found.append((node.lineno, str(node.slice.value)))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in fields
        ):
            found.append((node.lineno, str(node.args[0].value)))
    return found


def _hardcoded_status_sets(tree: ast.AST) -> list[int]:
    """Literal collections that re-spell the task-status vocabulary."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            continue
        values = [
            e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
        if len(values) < 2 or len(values) != len(node.elts):
            continue
        vals = set(values)
        if vals & _DONE_WORDS and vals <= _STATUS_WORDS:
            lines.append(node.lineno)
    return lines


def _offenders_in(path: Path, repo_root: Path) -> list[dict]:
    rel = _rel(path, repo_root)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []

    offenders: list[dict] = []
    for contract in CONTRACTS:
        if rel in contract.owners:
            continue
        if contract.fields:
            for lineno, field in _field_reads(tree, contract.fields):
                offenders.append(
                    {
                        "path": rel,
                        "line": lineno,
                        "contract": contract.name,
                        "message": (
                            f"reads {field!r} directly. That field is interpreted by"
                            f" {contract.supported_read}, which is the only supported read."
                            f" {contract.why}"
                        ),
                    }
                )
        if contract.name == "task-done-vocabulary":
            for lineno in _hardcoded_status_sets(tree):
                offenders.append(
                    {
                        "path": rel,
                        "line": lineno,
                        "contract": contract.name,
                        "message": (
                            "spells out the task-status vocabulary as a literal. Import"
                            f" {contract.supported_read} instead. {contract.why}"
                        ),
                    }
                )
    return offenders


def _iter_sources(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root in ("core", "runtime", "interfaces", "integrations", "projections", "tests"):
        base = repo_root / root
        if not base.is_dir():
            continue
        files.extend(p for p in sorted(base.rglob("*.py")) if "__pycache__" not in p.parts)
    return files


def run(repo_root: Path = REPO_ROOT) -> dict:
    """Scan repo_root. Parameterised so this gate's own tests can prove it FAILS."""
    offenders: list[dict] = []
    files = _iter_sources(repo_root)
    for path in files:
        offenders.extend(_offenders_in(path, repo_root))
    return {
        "status": "fail" if offenders else "pass",
        "files_scanned": len(files),
        "contracts": [c.name for c in CONTRACTS],
        "offenders": offenders,
    }


def main() -> int:
    result = run()
    if result["status"] != "pass":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\nsingle-read-path: FAILED - {len(result['offenders'])} caller(s) re-derive an"
            " answer the substrate already states once.",
            file=sys.stderr,
        )
        return 1
    print(
        f"single-read-path: OK - {result['files_scanned']} file(s) scanned,"
        f" {len(result['contracts'])} contract(s) honoured."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
