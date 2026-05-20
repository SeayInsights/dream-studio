"""Health-check pure functions for the Dream Studio runtime.

Skills, workflows, and hooks should import these directly instead of
shelling out to `ds doctor`, `ds version`, `ds validate`, or `ds status`.
The CLI in `interfaces/cli/ds.py` is a thin wrapper that calls these and
prints the result.
"""
