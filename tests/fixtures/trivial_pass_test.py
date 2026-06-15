"""Trivial always-passing test used as a TEST-CHECK fixture target.

This file exists solely so TEST-CHECK entries in acceptance_criteria can point
to a deterministically passing pytest node without risk of recursion.

DO NOT add real test logic here — it must remain unconditionally green.
"""


def test_trivial_always_passes() -> None:
    """Passes unconditionally. Used by TEST-CHECK fixture nodes in AC runner tests."""
    assert True
