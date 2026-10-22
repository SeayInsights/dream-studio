"""`ds doctor` counts gate runs, not rows, and prints the window it counted over (#927).

It reported 218 docs-drift bypasses over a window it did not print; each row is one gate
execution, so one push retried five times was five bypasses. A run is a (gate, HEAD sha).
Rows from before the payload carried a sha are still counted, as unattributed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

from core.config.sqlite_bootstrap import bootstrap_database  # noqa: E402
from core.health.doctor_bypass import bypass_audit  # noqa: E402

# -- doctor: runs, not rows -----------------------------------------------------------------


def _bypass_row(
    db: Path,
    gate: str,
    *,
    head_sha: str | None = None,
    branch: str | None = None,
    age_days: float = 0.0,
    attribute: bool = True,
) -> None:
    """Seed one gate.bypassed row. ``attribute=False`` writes the OLD payload shape (no
    branch/head_sha/invocation keys at all), as the ledger already holds."""
    import sqlite3

    when = (datetime.now(UTC) - timedelta(days=age_days)).isoformat()
    payload: dict = {"gate": gate, "reason": "r"}
    if attribute:
        payload.update({"head_sha": head_sha, "branch": branch, "invocation": "direct"})
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_canonical_events"
        " (event_id, received_at, event_type, event_timestamp, schema_version,"
        "  trace, payload, severity, source)"
        " VALUES (?, ?, 'gate.bypassed', ?, '1', '{}', ?, 'warning', 'test')",
        (str(uuid.uuid4()), when, when, json.dumps(payload)),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def ledger(tmp_path: Path) -> Path:
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    return db


def test_doctor_reports_distinct_runs_beside_the_raw_count(ledger):
    gate = "docs_drift_reviewed_no_change"
    for _ in range(5):  # five retries of one push
        _bypass_row(ledger, gate, head_sha="a" * 40, branch="feat/x")
    for _ in range(2):
        _bypass_row(ledger, gate, head_sha="b" * 40, branch="feat/y")
    for _ in range(3):  # rows from before the payload carried a sha
        _bypass_row(ledger, gate, attribute=False)
    _bypass_row(ledger, "migration_risk", head_sha="a" * 40, branch="feat/x")

    report = bypass_audit(ledger)

    bucket = report["gate_bypasses"][gate]
    assert bucket["count"] == 10  # raw executions, unchanged key and meaning
    assert bucket["distinct_runs"] == 2  # (gate, head_sha): a... and b...
    assert bucket["unattributed"] == 3  # counted, reported as such, not dropped
    # The same sha under another gate is another run of THAT gate.
    other = report["gate_bypasses"]["migration_risk"]
    assert (other["count"], other["distinct_runs"], other["unattributed"]) == (1, 1, 0)
    assert report["total"] == 11  # raw, as before


def test_old_shape_rows_alone_are_all_unattributed_and_no_sha_is_invented(ledger):
    for _ in range(4):
        _bypass_row(ledger, "migration_risk", attribute=False)
    bucket = bypass_audit(ledger)["gate_bypasses"]["migration_risk"]
    assert (bucket["count"], bucket["distinct_runs"], bucket["unattributed"]) == (4, 0, 4)
    assert all(s["head_sha"] is None for s in bucket["samples"])


def test_a_null_or_empty_sha_is_unattributed_not_a_run(ledger):
    _bypass_row(ledger, "migration_risk", head_sha=None)
    _bypass_row(ledger, "migration_risk", head_sha="")
    _bypass_row(ledger, "migration_risk", head_sha="c" * 40)
    bucket = bypass_audit(ledger)["gate_bypasses"]["migration_risk"]
    assert (bucket["count"], bucket["distinct_runs"], bucket["unattributed"]) == (3, 1, 2)


def test_samples_carry_the_attribution(ledger):
    _bypass_row(ledger, "migration_risk", head_sha="d" * 40, branch="feat/z")
    sample = bypass_audit(ledger)["gate_bypasses"]["migration_risk"]["samples"][0]
    assert (sample["head_sha"], sample["branch"], sample["invocation"]) == (
        "d" * 40,
        "feat/z",
        "direct",
    )


def test_doctor_prints_the_real_window(ledger):
    _bypass_row(ledger, "migration_risk", head_sha="e" * 40, age_days=2)
    _bypass_row(ledger, "migration_risk", head_sha="f" * 40, age_days=10)  # outside 7 days

    week = bypass_audit(ledger)
    assert week["since_days"] == 7
    assert week["window"].startswith("last 7 days (since ")
    assert week["since"] in week["window"]
    assert week["gate_bypasses"]["migration_risk"]["count"] == 1

    day = bypass_audit(ledger, since_days=1)
    assert day["since_days"] == 1
    assert day["window"].startswith("last 1 day (since ")
    assert "migration_risk" not in day["gate_bypasses"]

    month = bypass_audit(ledger, since_days=30)
    assert month["window"].startswith("last 30 days (since ")
    assert month["gate_bypasses"]["migration_risk"]["count"] == 2
    assert month["gate_bypasses"]["migration_risk"]["distinct_runs"] == 2


def test_ds_doctor_surfaces_the_window_and_the_run_counts(ledger, tmp_path):
    """Through the real CLI: what an operator reads is the window and both counts."""
    import os

    for _ in range(3):
        _bypass_row(ledger, "migration_risk", head_sha="1" * 40, branch="feat/q")
    home = ledger.parent.parent
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DREAM_STUDIO", "DS_"))}
    env.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=str(REPO_ROOT),
        PYTHONIOENCODING="utf-8",
        DREAM_STUDIO_DB_PATH=str(ledger),
        CLAUDE_CONFIG_DIR=str(tmp_path / "claude"),
        HOME=str(tmp_path / "userhome"),
        USERPROFILE=str(tmp_path / "userhome"),
    )
    (tmp_path / "work").mkdir()
    proc = subprocess.run(
        [sys.executable, "-m", "interfaces.cli.ds", "--home", str(home), "doctor"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=tmp_path / "work",
        env=env,
        timeout=900,
    )
    assert proc.returncode in (0, 1), proc.stderr[-2000:]
    report = json.JSONDecoder().raw_decode(proc.stdout, proc.stdout.index("{"))[0]
    audit = report["checks"]["bypass_audit"]
    assert audit["window"].startswith("last 7 days (since ")
    bucket = audit["gate_bypasses"]["migration_risk"]
    assert (bucket["count"], bucket["distinct_runs"], bucket["unattributed"]) == (3, 1, 0)
