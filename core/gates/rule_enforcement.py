"""A rule that claims enforcement must name an enforcer that exists.

`canonical/rules.yml` is the register that separates the statements something enforces
from the ones nothing does. Its own header says why it was written: the substrate was
"a lot of prose laid on top of each other as suggestions with no rules, evals, or really
any real test that doing anything they are supposed to". Every rule carries an
`enforced_by` list naming the modules and pytest nodes that hold it up.

Those names were checked by `core/gates/rule_registry.py`, and that gate was culled in
`67ba10e` in the same sweep that removed several of the enforcers it would have been
checking. So the register kept asserting enforcement for gates that no longer existed,
and the one thing that could have noticed went with them.

MEASURED WHEN THIS WAS WRITTEN: 21 of 102 `enforced_by` references across 7 of 34 rules
named a module or a test file that is not in the tree. A register of enforcement claims
that nobody verifies is the failure it was built to prevent, one level up.

THE DECLARATION IS THE OTHER HALF. Five of those seven lost their enforcement because the
gate holding them up was deliberately removed as repo bookkeeping. Deleting the rules
would lose the statements; leaving them claiming enforcement would keep lying. So a rule
may instead declare `unenforced:` with a reason, which this gate accepts and COUNTS --
the register's whole purpose is to make the unenforced pile visible, and a pile nobody
can see is the state it was written to end.

Same contract as `admission.py`'s `--why` and the security-scan exemption: enforce, or
declare in writing why you cannot. One repo, one shape for "I cannot enforce this".
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "canonical" / "rules.yml"

#: Minimum characters for a declared reason. Mirrors `admission._MIN_WHY` deliberately:
#: an author who has met one has met them all, and a reason shorter than this is a shrug.
MIN_REASON = 20

_CODE_SUFFIXES = (".py", ".md", ".yml", ".yaml", ".json", ".toml", ".txt")


def _resolve(reference: str) -> str | None:
    """None when the reference resolves; otherwise why it does not."""
    ref = str(reference).strip()
    if not ref:
        return "empty reference"

    if "::" in ref:  # a pytest node id
        file_part = ref.split("::", 1)[0]
        if not (REPO_ROOT / file_part).is_file():
            return "no such test file"
        return None

    if "/" in ref or ref.endswith(_CODE_SUFFIXES):  # a path
        return None if (REPO_ROOT / ref).exists() else "no such path"

    if "." in ref:  # a dotted module
        target = REPO_ROOT.joinpath(*ref.split("."))
        if target.with_suffix(".py").is_file() or (target / "__init__.py").is_file():
            return None
        return "no such module"

    return "unrecognised reference"


def audit(registry_path: Path | None = None) -> dict[str, Any]:
    """Every rule whose enforcement claim does not hold, plus the declared ones."""
    import yaml

    path = registry_path or REGISTRY
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = data.get("rules") if isinstance(data, dict) else data

    broken: list[dict[str, Any]] = []
    declared: list[dict[str, Any]] = []
    guidance: list[dict[str, Any]] = []
    checked = 0

    for rule in rules or []:
        rule_id = rule.get("id", "<no id>")
        reason = str(rule.get("unenforced") or "").strip()
        references = list(rule.get("enforced_by") or [])
        guidance_why = str(rule.get("why") or "").strip()

        # GUIDANCE IS NOT A REGRESSION. `unenforced` records that something used to hold a
        # rule up and a named commit removed it, so that list is a debt that should shrink.
        # `guidance` records that no static check can settle the statement at all -- an
        # instruction to the model, answerable only by an eval. Filing the second under the
        # first inflates the regression count with rules nothing ever enforced, and the
        # reason can never name a commit because none exists.
        if rule.get("guidance") is True:
            if reason or references:
                broken.append(
                    {
                        "rule": rule_id,
                        "reference": "(guidance declaration)",
                        "why": "declares guidance AND unenforced/enforced_by; pick one",
                    }
                )
            elif len(guidance_why) < MIN_REASON:
                broken.append(
                    {
                        "rule": rule_id,
                        "reference": "(guidance declaration)",
                        "why": f"why is {len(guidance_why)} characters, {MIN_REASON} required",
                    }
                )
            else:
                guidance.append({"rule": rule_id, "why": guidance_why})
            continue

        if reason:
            # A DECLARATION IS NOT A BYPASS. It must say something, and it must not sit
            # beside a claim of enforcement -- a rule cannot be both held up and not.
            if len(reason) < MIN_REASON:
                broken.append(
                    {
                        "rule": rule_id,
                        "reference": "(unenforced declaration)",
                        "why": f"reason is {len(reason)} characters, {MIN_REASON} required",
                    }
                )
            elif references:
                broken.append(
                    {
                        "rule": rule_id,
                        "reference": "(unenforced declaration)",
                        "why": "declares unenforced AND lists enforced_by; pick one",
                    }
                )
            else:
                declared.append({"rule": rule_id, "reason": reason})
            continue

        if not references:
            broken.append(
                {
                    "rule": rule_id,
                    "reference": "(none)",
                    "why": "no enforced_by, no unenforced declaration, no guidance",
                }
            )
            continue

        for reference in references:
            checked += 1
            why = _resolve(reference)
            if why:
                broken.append({"rule": rule_id, "reference": reference, "why": why})

    return {
        "rules": len(rules or []),
        "references_checked": checked,
        "broken": broken,
        "declared": declared,
        "guidance": guidance,
    }


def main() -> int:
    report = audit()
    declared = report["declared"]

    if report["broken"]:
        print("[rule-enforcement] FAIL - a rule claims an enforcer that is not there")
        print()
        by_rule: dict[str, list[dict[str, Any]]] = {}
        for item in report["broken"]:
            by_rule.setdefault(item["rule"], []).append(item)
        for rule_id, items in by_rule.items():
            print(f"  {rule_id}")
            for item in items:
                print(f"      {item['why']:28s} {item['reference']}")
        print()
        print("  Point the rule at the enforcer that survived, or declare which it is:")
        print(f"    unenforced: <at least {MIN_REASON} chars> - an enforcer existed and a")
        print("                named commit removed it; this pile is a debt that shrinks.")
        print("    guidance: true")
        print(f"    why: <at least {MIN_REASON} chars> - no static check can settle this at")
        print("                all; it is an instruction to the model, answerable by an eval.")
        print("  Exactly one, and remove its enforced_by. A rule cannot be both held up and not.")
        return 1

    print(
        f"[rule-enforcement] OK - {report['references_checked']} enforcement reference(s) "
        f"across {report['rules']} rule(s) all resolve"
    )
    # THE UNENFORCED PILE IS PRINTED EVERY RUN, PASS OR FAIL. The register exists to make
    # it visible; a declaration that only shows up in a failure is a pile nobody sees.
    if declared:
        print(f"\n  {len(declared)} rule(s) UNENFORCED (an enforcer was removed):")
        for item in declared:
            print(f"    {item['rule']}")
            print(f"        {item['reason'][:150]}")
    # PRINTED APART, because the two counts mean different things. The pile above is a
    # debt and should shrink; the one below is a classification and will not, since no
    # static check can settle a statement about how the model should behave.
    if report["guidance"]:
        print(f"\n  {len(report['guidance'])} rule(s) GUIDANCE (no check can settle it):")
        for item in report["guidance"]:
            print(f"    {item['rule']}")
            print(f"        {item['why'][:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
