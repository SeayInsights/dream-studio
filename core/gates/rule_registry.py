"""Gate: every registered rule is either enforced by a runnable check, or declared guidance.

Operator, on the substrate: it is "a lot of prose laid on top of each other as suggestions
with no rules, evals, or really any real test that doing anything they are supposed to".
Nothing distinguished a statement something enforces from one nothing does.

A figure of "2,172 normative statements" circulated here, including in this docstring, as
though it were a backlog of unwritten rules. It was a count of WORD OCCURRENCES under one
pattern, and most occurrences are ordinary English inside explanatory prose. Re-measured
2026-09-07 over the same corpus: 191 SHOUTED statements against 5,752 any-case. The shouted
count is now a per-lane ceiling in canonical/normative_baseline.json, enforced by the
normative-baseline gate; see that module for the lane breakdown and why the lane decides
which substrate can enforce a statement at all.

This gate does not attempt to enforce every sentence -- some are judgment no check can
settle. It enforces the property that makes the distinction real:

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
  4. A rule a check covers only PARTLY declares `enforced_by` plus `residual_risk` naming
     what the check cannot see. Filing such a rule as pure guidance understates what the
     substrate already does; filing it as fully enforced hides the gap. Both were happening.

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
                " For a rule a check covers only PARTLY, use enforced_by plus"
                " residual_risk -- that is the honest third state, and pretending the"
                " whole rule is guidance understates what is already checked."
            )
        if guidance and not str(rule.get("why") or "").strip():
            errors.append(
                f"{rid}: guidance:true with no `why`. 'No check is possible' is a claim,"
                " and an unexplained one hides an unenforced rule behind a label."
            )
        # PARTIAL ENFORCEMENT IS THE COMMON CASE, and the binary above could not say it.
        # Two rules sat as pure `guidance` while a real check already covered part of each:
        # no-fabricated-data is partly covered by the evidence-backed-output gate (a claim
        # must CITE something -- necessary, not sufficient), and
        # tests-run-by-a-different-agent is partly covered by recorded runner identity.
        # Filing those as unenforceable understated what the substrate does and made the
        # registry read as more helpless than it is. `residual_risk` names the uncovered
        # part so the gap stays visible WITHOUT discarding the coverage.
        residual = str(rule.get("residual_risk") or "").strip()
        if residual and not enforced:
            errors.append(
                f"{rid}: residual_risk with no enforced_by. Residual risk is what a check"
                " does NOT cover; with no check there is no residual, only the whole rule"
                " unenforced -- say guidance:true and why."
            )
        if residual and len(residual) < 60:
            errors.append(
                f"{rid}: residual_risk states too little ({residual!r}). Name the part the"
                " check cannot see, concretely enough that someone can later close it."
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


def _collectable_batch(node_ids: list[str]) -> tuple[bool, str]:
    """True when pytest can collect ALL of these node ids in one run.

    ONE SPAWN, NOT ONE PER ID. Measured 2026-09-08: 64 node ids meant 64 subprocess
    spawns and 213s for this gate alone, and its own test file -- which runs the gate
    several times -- took 355s and pushed the blocking pin-tests gate past its 600s
    timeout. A Windows subprocess spawn costs 3-12s, so the cost was spawn count rather
    than collection work. The registry grows by ratchet, so a per-id probe gets slower
    every time a rule is classified: a gate that punishes its own adoption eventually gets
    switched off, and it would take every rule with it.

    Returns (ok, detail). On failure the caller probes individually to name the offender,
    because "something in the registry is unrunnable" is not actionable.
    """
    if not node_ids:
        return True, ""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, "-m", "pytest", *node_ids, "--collect-only", "-q"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_COLLECT_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired:
        return False, f"batch collection timed out after {_COLLECT_TIMEOUT_SECS}s"
    if proc.returncode == 0:
        return True, ""
    return False, f"batch collection exited {proc.returncode}"


def _enforcement_errors(rules: list[dict]) -> list[str]:
    """Every enforced_by target must resolve to something runnable."""
    errors: list[str] = []

    # Gather the pytest node ids first and collect them in ONE run. Only if that fails is
    # each probed individually, to name the offender.
    pytest_targets: list[tuple[str, str]] = []
    for rule in rules:
        rid = str(rule.get("id") or "<unnamed>")
        for raw_target in rule.get("enforced_by") or []:
            target = str(raw_target).strip()
            if "::" in target or target.endswith(".py"):
                pytest_targets.append((rid, target))

    present = [(rid, t) for rid, t in pytest_targets if (REPO_ROOT / t.split("::", 1)[0]).is_file()]
    for rid, target in pytest_targets:
        if (rid, target) not in present:
            errors.append(f"{rid}: enforced_by names a missing file: {target}")

    batch_ok, batch_detail = _collectable_batch([t for _rid, t in present])
    if not batch_ok:
        for rid, target in present:
            ok, why = _collectable(target)
            if not ok:
                errors.append(f"{rid}: enforced_by is not runnable -- {target}: {why}")
        if not any("is not runnable" in e for e in errors):
            # The batch failed and no individual id did: the fault is in the run itself,
            # not in a rule. Reported rather than swallowed -- a gate that cannot complete
            # must not report clean.
            errors.append(
                f"the registry's checks could not be collected together ({batch_detail})"
                " and every id collected individually, so the fault is in the collection"
                " run rather than in any one rule"
            )

    for rule in rules:
        rid = str(rule.get("id") or "<unnamed>")
        for raw_target in rule.get("enforced_by") or []:
            target = str(raw_target).strip()
            if "::" in target or target.endswith(".py"):
                continue
            else:
                module_path = REPO_ROOT / (target.replace(".", "/") + ".py")
                if not module_path.is_file():
                    errors.append(f"{rid}: enforced_by names a missing gate module: {target}")
                    continue
                ok, why = _runnable_as_module(target)
                if not ok:
                    errors.append(f"{rid}: enforced_by is not runnable -- {target}: {why}")
    return errors


def _runnable_as_module(dotted: str) -> tuple[bool, str]:
    """True when `py -m <dotted>` would have an entry point to run.

    Existence of the file was the whole check before, which let a rule cite a gate that
    could not actually be invoked the way pre-push invokes it. Verified by import and an
    attribute lookup rather than by execution -- a gate that FAILS is the rule being
    broken, which is the gate's job to report, not this one's.
    """
    import importlib

    try:
        module = importlib.import_module(dotted)
    except Exception as exc:  # noqa: BLE001 - any import failure means not runnable
        return False, f"import failed: {type(exc).__name__}: {exc}"[:180]
    if not callable(getattr(module, "main", None)):
        return False, "no callable main() -- `py -m` would do nothing"
    return True, ""


def run() -> dict:
    """Return the gate result. status is 'pass' only when every rule is classified and real."""
    rules, errors = _load_registry()
    if errors:
        return {"status": "fail", "rule_count": 0, "errors": errors}

    errors = _classification_errors(rules) + _enforcement_errors(rules)
    enforced = sum(1 for r in rules if r.get("enforced_by"))
    guidance = sum(1 for r in rules if r.get("guidance"))
    partial = sum(
        1 for r in rules if r.get("enforced_by") and str(r.get("residual_risk") or "").strip()
    )
    return {
        "status": "fail" if errors else "pass",
        "rule_count": len(rules),
        "enforced": enforced,
        "guidance": guidance,
        "partially_enforced": partial,
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
        f" {result['enforced']} enforced ({result['partially_enforced']} partially,"
        f" residual stated), {result['guidance']} declared guidance."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
