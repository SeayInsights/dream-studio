"""Every test file a gate manifest names must exist.

Three times in one day a manifest pointed at a file an earlier cull had deleted:

  canonical/workflows/pre-push.yaml   4 dead entries in `pin-tests`, so pytest
                                      errored on a missing path and the gate
                                      failed before running anything
  .github/workflows/ci.yml            test_gate_fixture_resurrection.py in the
                                      focused smoke list, deleted in 3b2dc373
  canonical/review_lanes.yml          four lanes naming detector modules that
                                      had been removed on purpose

The shape is always the same: a cull removes the thing and leaves the reference,
and nothing reads the reference until a push is already blocked by it. The cost
is not the broken gate -- it is that the gate fails for a reason unrelated to the
change being pushed, so whoever hits it learns nothing about their own work.

This is deliberately cheap and structural: it resolves paths, runs no tests, and
checks BOTH manifests, because fixing one at a time is what let this recur.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_PUSH = REPO_ROOT / "canonical" / "workflows" / "pre-push.yaml"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _named_test_paths(text: str) -> list[str]:
    """Every tests/... path token in a blob of manifest text."""
    out = []
    for token in text.replace(",", " ").split():
        token = token.strip("\"'")
        if token.startswith("tests/") and token.endswith(".py"):
            out.append(token)
    return out


def test_pre_push_manifest_names_only_files_that_exist():
    gates = yaml.safe_load(PRE_PUSH.read_text(encoding="utf-8"))["gates"]
    missing = []
    for gate in gates:
        for token in gate.get("command") or []:
            token = str(token)
            if token.startswith("tests/") and token.endswith(".py"):
                if not (REPO_ROOT / token).is_file():
                    missing.append(f"{gate['id']}: {token}")
    assert not missing, (
        "pre-push gates name test files that do not exist, so the gate fails before it"
        " runs anything:\n  " + "\n  ".join(missing)
    )


def test_ci_workflow_names_only_files_that_exist():
    missing = [
        token
        for token in _named_test_paths(CI.read_text(encoding="utf-8"))
        if not (REPO_ROOT / token).is_file()
    ]
    assert not missing, (
        "ci.yml names test files that do not exist, so the step fails on a missing path"
        " rather than on the change being tested:\n  " + "\n  ".join(sorted(set(missing)))
    )


def test_every_pre_push_gate_command_resolves():
    """A gate naming a module nobody wrote is the same defect one layer up, and it
    is how four review lanes shipped claiming detectors that did not exist."""
    import importlib

    gates = yaml.safe_load(PRE_PUSH.read_text(encoding="utf-8"))["gates"]
    broken = []
    for gate in gates:
        command = [str(c) for c in (gate.get("command") or [])]
        if "-m" in command:
            module = command[command.index("-m") + 1]
            try:
                importlib.import_module(module)
            except Exception as exc:  # noqa: BLE001 - any import failure is the finding
                broken.append(f"{gate['id']}: {module} ({type(exc).__name__})")
        elif len(command) > 1 and command[1].endswith(".py"):
            if not (REPO_ROOT / command[1]).is_file():
                broken.append(f"{gate['id']}: {command[1]} (missing file)")
    assert not broken, "pre-push gates whose command does not resolve:\n  " + "\n  ".join(broken)
