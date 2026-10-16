"""The enforcement hooks' remediation commands work outside a checkout.

Their deny and block messages said `py -m interfaces.cli.ds ...`, which only works with
a Dream Studio checkout as the working directory. From an installed app the operator
follows the message and gets `No module named interfaces`. They now name the `ds`
launcher.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCES = (
    "runtime/hooks/meta/on-edit-enforce.py",
    "runtime/hooks/meta/on-stop-enforce.py",
    "runtime/hooks/enforce-native/src/enforce.rs",
)


def test_no_enforcement_message_tells_the_operator_to_run_the_checkout_module():
    offenders = [
        f"{rel}:{n}"
        for rel in SOURCES
        for n, line in enumerate((REPO / rel).read_text(encoding="utf-8").splitlines(), 1)
        if "interfaces.cli.ds" in line
    ]
    assert offenders == [], offenders


def test_the_remediation_still_names_the_commands():
    text = (REPO / "runtime/hooks/meta/on-edit-enforce.py").read_text(encoding="utf-8")
    assert 'ds files write "<name>" --category planning' in text
    assert "ds work-order start" in text
