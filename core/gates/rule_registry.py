"""Gate: every registered rule is either enforced by a runnable check, or declared guidance.

Operator, on the substrate: it is "a lot of prose laid on top of each other as suggestions
with no rules, evals, or really any real test that doing anything they are supposed to".
Measured 2026-09-04: 2,172 normative statements (MUST / NEVER / ALWAYS / REQUIRED /
DO NOT) across canonical/skills (772), docs (1,283), canonical/workflows (103) and the two
root instruction files (14). Nothing distinguished a statement something enforces from one
nothing does.

This gate does not attempt to enforce 2,172 sentences -- that is not a reachable state, and
some of them are judgment no check can settle. It enforces the property that makes the
distinction real:

  1. Every entry in canonical/rules.yml carries EITHER `enforced_by` or `guidance: true`.
     An entry with neither is refused. A rule nobody classified is the status quo this
     exists to end.
  2. Every `enforced_by` target must EXIST and be COLLECTABLE. A pytest node id that
     collects nothing is not a check -- pytest exits 5 for no-tests-collected and 4 for a
     usage error, and neither is a failure, so a gate reading zero-versus-nonzero cannot
     tell "the rule is broken" from "the check stopped addressing anything". Eight
     acceptance criteria were found rotted exactly that way this session.
  3. Every entry declaring `guidance: true` carries a `why`. "No check is possible" is a
     claim, and an unexplained one hides an unenforced rule behind a label.

Read-only: it imports nothing from the checks it validates and never executes them, so it
stays fast enough for the blocking pre-push tier.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "canonical" / "rules.yml"

#: A collect probe is bounded: an unresponsive one must fail the gate, not hang the push.
_COLLECT_TIMEOUT_SECS = 120


def _load_registry() -> tuple[list[dict], list[str]]:
    """Return (rules, errors). A registry that cannot be read is a gate failure."""
    if not REGISTRY.is_file():
        # Not relative_to(REPO_ROOT): the registry path is patchable, and a path outside
        # the repo made that raise ValueError -- so the gate CRASHED on the very input it
        # exists to report. An error path that cannot report its error is not a gate.
        try:
            shown: str | Path = REGISTRY.relative_to(REPO_ROOT)
        except ValueError:
            shown = REGISTRY
        return [], [f"registry missing at {shown}"]
    try:
        import yaml
    except ImportError:  # pragma: no cover - yaml is a hard dependency of the repo
        return [], ["PyYAML unavailable, cannot read the rule registry"]
    try:
        data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - any parse fault is a gate failure
        return [], [f"registry is unreadable: {type(exc).__name__}: {exc}"]
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        return [], ["registry declares no rules"]
    return rules, []


def _classification_errors(rules: list[dict]) -> list[str]:
    """A rule must be enforced or declared guidance, and guidance must say why."""
    errors: list[str] = []
    seen: set[str] = set()
    for index, rule in enumerate(rules):
        rid = str(rule.get("id") or f"<entry {index}>")
        if rid in seen:
            errors.append(f"{rid}: duplicate id -- an id must name exactly one rule")
        seen.add(rid)
        if not rule.get("statement"):
            errors.append(f"{rid}: no statement -- a rule with no text cannot be checked")
        enforced = rule.get("enforced_by") or []
        guidance = bool(rule.get("guidance"))
        if not enforced and not guidance:
            errors.append(
                f"{rid}: neither enforced_by nor guidance:true. Every rule is one or the"
                " other; an unclassified rule is prose asserting a rule, which is the"
                " state this registry exists to end."
            )
        if enforced and guidance:
            errors.append(
                f"{rid}: both enforced_by and guidance:true. If a check exists the rule is"
                " enforced; calling it guidance too hides which one the gate trusts."
            )
        if guidance and not str(rule.get("why") or "").strip():
            errors.append(
                f"{rid}: guidance:true with no `why`. 'No check is possible' is a claim,"
                " and an unexplained one hides an unenforced rule behind a label."
            )
    return errors


def _collectable(node_id: str) -> tuple[bool, str]:
    """True when pytest can collect exactly this node id.

    Collection, not execution: this gate asserts the check EXISTS and is addressable. A
    check that fails is the rule being broken, which is the check's job to report, not
    this gate's.
    """
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, "-m", "pytest", node_id, "--collect-only", "-q"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_COLLECT_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired:
        return False, f"collection timed out after {_COLLECT_TIMEOUT_SECS}s"
    if proc.returncode == 4:
        return (
            False,
            "pytest usage error (exit 4) -- the node id is malformed or the file is absent",
        )
    if proc.returncode == 5:
        return False, "collected nothing (exit 5) -- the named test does not exist"
    if proc.returncode != 0:
        tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-1:]
        return False, f"collection failed (exit {proc.returncode}): {tail[0] if tail else ''}"
    return True, ""


def _enforcement_errors(rules: list[dict]) -> list[str]:
    """Every enforced_by target must resolve to something runnable."""
    errors: list[str] = []
    for rule in rules:
        rid = str(rule.get("id") or "<unnamed>")
        for raw_target in rule.get("enforced_by") or []:
            target = str(raw_target).strip()
            if "::" in target or target.endswith(".py"):
                path = REPO_ROOT / target.split("::", 1)[0]
                if not path.is_file():
                    errors.append(f"{rid}: enforced_by names a missing file: {target}")
                    continue
                ok, why = _collectable(target)
                if not ok:
                    errors.append(f"{rid}: enforced_by is not runnable -- {target}: {why}")
            else:
                module_path = REPO_ROOT / (target.replace(".", "/") + ".py")
                if not module_path.is_file():
                    errors.append(f"{rid}: enforced_by names a missing gate module: {target}")
    return errors


def run() -> dict:
    """Return the gate result. status is 'pass' only when every rule is classified and real."""
    rules, errors = _load_registry()
    if errors:
        return {"status": "fail", "rule_count": 0, "errors": errors}

    errors = _classification_errors(rules) + _enforcement_errors(rules)
    enforced = sum(1 for r in rules if r.get("enforced_by"))
    guidance = sum(1 for r in rules if r.get("guidance"))
    return {
        "status": "fail" if errors else "pass",
        "rule_count": len(rules),
        "enforced": enforced,
        "guidance": guidance,
        "errors": errors,
    }


def main() -> int:
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "pass":
        print(
            "\nrule-registry: FAILED. Every rule in canonical/rules.yml must be enforced by"
            " a runnable check or declared guidance with a reason.",
            file=sys.stderr,
        )
        return 1
    print(
        f"\nrule-registry: OK - {result['rule_count']} rule(s):"
        f" {result['enforced']} enforced, {result['guidance']} declared guidance."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
