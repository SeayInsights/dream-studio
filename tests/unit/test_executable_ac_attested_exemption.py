"""WO 254674de — attested design-only WOs are exempt from the executable_ac force requirement.

A design-only work order (deliverable is an operator-local docstore artifact — a spec, an ADR,
a capability map) has no code to executably check. An operator attestation (ds work-order
attest) is the human certification for such work; when present, executable_ac passes without
force. Un-attested zero-check WOs still require a check or force (the no-false-done guard for
code WOs is preserved).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders import close_gates


def _seed_zero_check_wo(db: Path) -> sqlite3.Connection:
    """A WO with one task whose acceptance criteria carries NO executable check."""
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id,project_id,milestone_id,title,description,status,"
        " work_order_type,created_at,updated_at)"
        " VALUES ('wo-d','p','m','WO','d','in_progress','documentation','2026-08-05','2026-08-05')"
    )
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id,work_order_id,project_id,title,description,status,acceptance_criteria,"
        " created_at,updated_at)"
        " VALUES ('t','wo-d','p','T','d','complete','ATTEST: docstore artifact exists',"
        " '2026-08-05','2026-08-05')"
    )
    conn.commit()
    return conn


def test_attested_design_wo_exempt_from_force(tmp_path: Path):
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    conn = _seed_zero_check_wo(db)
    try:
        # Without an attestation: a zero-check WO must still fail (require a check or force).
        failures = close_gates._run_ac_gate(conn, work_order_id="wo-d", db_path=db)
        assert failures, "zero-check WO with no attestation must not pass executable_ac"
        assert "executable_ac" in failures[0]

        # Record a passing operator attestation, exactly as `ds work-order attest` does.
        from core.work_orders.artifacts import set_wo_artifact

        set_wo_artifact(
            "wo-d",
            "review_verdict",
            json.dumps({"passed": True, "certification_basis": "operator_attested"}),
            db_path=db,
        )

        # With the attestation: executable_ac now passes without force.
        assert close_gates._run_ac_gate(conn, work_order_id="wo-d", db_path=db) == []

        # A NON-operator verdict (e.g. an ordinary review) does NOT grant the exemption.
        set_wo_artifact(
            "wo-d",
            "review_verdict",
            json.dumps({"passed": True, "certification_basis": "git_diff"}),
            db_path=db,
        )
        assert close_gates._run_ac_gate(
            conn, work_order_id="wo-d", db_path=db
        ), "only an operator attestation grants the exemption, not any passing verdict"
    finally:
        conn.close()
