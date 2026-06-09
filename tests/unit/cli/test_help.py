"""Verify that ds validate and ds doctor --help text cross-reference each other."""

from __future__ import annotations

import subprocess
import sys


def _help(subcmd: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "interfaces.cli.ds", subcmd, "--help"],
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr


def test_validate_help_references_doctor():
    out = _help("validate")
    assert "ds doctor" in out, f"'ds doctor' not found in `ds validate --help`:\n{out}"


def test_doctor_help_references_validate():
    out = _help("doctor")
    assert "ds validate" in out, f"'ds validate' not found in `ds doctor --help`:\n{out}"


def test_validate_help_mentions_db_plane():
    out = _help("validate")
    assert (
        "schema" in out.lower() or "migration" in out.lower()
    ), f"Expected schema/migration mention in `ds validate --help`:\n{out}"


def test_doctor_help_mentions_integration_plane():
    out = _help("doctor")
    assert (
        "skills" in out.lower() or "integration" in out.lower()
    ), f"Expected skills/integration mention in `ds doctor --help`:\n{out}"
