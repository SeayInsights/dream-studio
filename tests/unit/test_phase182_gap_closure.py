"""Tests for Phase 18.2 gap closure + popup refactor.

Three fixes:
  Fix 1 (pre-existing): unblock_work_order() emits work_order.unblocked
  Fix 2 (pre-existing): Design brief mutations emit canonical events
  Fix 3 (this WO): _repo_stack_evidence() removed from /details critical path

Both Fix 1 and Fix 2 were already present in current code — the audit's findings
were based on a stale inventory. These tests verify the current state is correct.
Fix 3 removes the 40-120s filesystem walk from the popup load path.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]


# ── Fix 1: unblock_work_order emits canonical event ──────────────────────


class TestFix1UnblockWorkOrder:
    def test_unblock_emits_canonical_event(self):
        """unblock_work_order() must contain work_order.unblocked emit call."""
        source = (REPO_ROOT / "core/work_orders/mutations.py").read_text(encoding="utf-8")
        assert (
            "work_order.unblocked" in source
        ), "unblock_work_order() must emit work_order.unblocked canonical event"

    def test_unblock_uses_spool_writer(self):
        """unblock_work_order() must use spool.writer for event emission."""
        source = (REPO_ROOT / "core/work_orders/mutations.py").read_text(encoding="utf-8")
        fn_start = source.find("def unblock_work_order(")
        fn_end = source.find("\ndef ", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        assert (
            "spool.writer" in fn_body or "_spool_writer" in fn_body
        ), "unblock_work_order() must use spool writer for event emission"
        assert "work_order.unblocked" in fn_body


# ── Fix 2: Design brief mutations emit canonical events ───────────────────


_BRIEF_DML = re.compile(
    r"(INSERT\s+(OR\s+\w+\s+)?INTO|UPDATE|DELETE\s+FROM|REPLACE\s+INTO)\s+business_design_briefs",
    re.IGNORECASE,
)


def direct_brief_writes(source: str) -> list[str]:
    """Every string literal in ``source`` that is INSERT/UPDATE/DELETE against
    business_design_briefs.

    Whole module, every literal (plain, implicitly concatenated, the constant parts of an
    f-string, a SQL held in a variable first): the old guard sliced the public functions'
    text, so a direct UPDATE added to a helper passed it.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _BRIEF_DML.search(node.value):
                found.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            text = "".join(
                v.value
                for v in node.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)
            )
            if _BRIEF_DML.search(text):
                found.append(text)
    return found


class TestFix2DesignBriefEmits:
    """The mutations never write business_design_briefs themselves: DesignBriefProjection
    is the sole writer. What each function emits, and that the effect lands, is asserted
    by running them (tests/unit/test_design_brief_sync.py); this class holds the static
    guards that cannot be a behaviour test."""

    def test_design_brief_events_in_registry(self):
        """All design_brief.* event types must be registered."""
        source = (REPO_ROOT / "config/event_type_registry_entries_business.py").read_text(
            encoding="utf-8"
        )
        for event_type in ("design_brief.created", "design_brief.updated", "design_brief.locked"):
            assert event_type in source, (
                f"Event type {event_type!r} must be registered in "
                "config/event_type_registry_entries_business.py"
            )

    def test_the_mutations_module_has_no_direct_write_anywhere(self):
        source = (REPO_ROOT / "core/design_briefs/mutations.py").read_text(encoding="utf-8")
        assert direct_brief_writes(source) == [], (
            "core/design_briefs/mutations.py must not INSERT/UPDATE/DELETE "
            "business_design_briefs anywhere: DesignBriefProjection applies every change "
            "from the canonical event."
        )

    @pytest.mark.parametrize(
        "snippet",
        [
            'conn.execute("UPDATE business_design_briefs SET status = 1")',
            'conn.execute("insert into business_design_briefs (a) values (1)")',
            'conn.execute("INSERT OR IGNORE INTO business_design_briefs (a) VALUES (1)")',
            'conn.execute("DELETE FROM business_design_briefs")',
            'conn.execute("UPDATE business_design_briefs " "SET status = 1")',
            'sql = "UPDATE business_design_briefs SET x = 1"; conn.execute(sql)',
            'conn.execute(f"UPDATE business_design_briefs SET {field} = ?")',
            "def helper(conn):\n    conn.execute('UPDATE business_design_briefs SET x = 1')",
        ],
    )
    def test_the_guard_sees_a_direct_write_wherever_it_hides(self, snippet):
        assert direct_brief_writes(snippet), snippet

    def test_the_guard_ignores_reads(self):
        read = 'conn.execute("SELECT status FROM business_design_briefs WHERE brief_id = ?")'
        assert direct_brief_writes(read) == []


# ── Fix 3: _repo_stack_evidence not on critical path ─────────────────────


class TestFix3RepoStackEvidenceRefactor:
    def _get_handler_source(self):
        # project_intelligence.py was split; handlers live in project_detail.py,
        # _repo_stack_evidence lives in projections/api/lib/stack_helpers.py.
        # WO-GF-API-ROUTES split project_detail.py further: get_project_health now
        # lives in project_detail_health.py and get_project_details in
        # project_detail_details.py (the only two handlers this class inspects).
        health_source = (REPO_ROOT / "projections/api/routes/project_detail_health.py").read_text(
            encoding="utf-8"
        )
        details_source = (REPO_ROOT / "projections/api/routes/project_detail_details.py").read_text(
            encoding="utf-8"
        )
        stack_source = (REPO_ROOT / "projections/api/lib/stack_helpers.py").read_text(
            encoding="utf-8"
        )
        # Sentinel "@router." boundary: get_project_details is the last handler in
        # this concatenation (no route-decorated sibling follows it here), so
        # without this the fn_start/fn_end slicing below would bleed into
        # stack_helpers.py's own body (which legitimately defines
        # _repo_stack_evidence and calls rglob) and produce false failures.
        return health_source + "\n" + details_source + "\n@router.\n" + stack_source

    def test_repo_stack_evidence_not_called_from_details_handler(self):
        """GET /details must not call _repo_stack_evidence() — filesystem walk removed."""
        source = self._get_handler_source()
        # Find get_project_details function
        fn_start = source.find("async def get_project_details(")
        fn_end = source.find("\n@router.", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        assert "_repo_stack_evidence(" not in fn_body, (
            "get_project_details() must not call _repo_stack_evidence(). "
            "Filesystem walk removed from popup critical path. "
            "Stack data reads from business_projects.stack_json (L3) instead."
        )

    def test_repo_stack_evidence_function_still_exists(self):
        """_repo_stack_evidence() function must NOT be deleted — kept for future opt-in use."""
        source = self._get_handler_source()
        assert "def _repo_stack_evidence(" in source, (
            "_repo_stack_evidence() function must not be deleted. "
            "It is retained for future on-demand scan endpoint (separate WO)."
        )

    def test_details_response_has_deferred_repo_scan(self):
        """GET /details response must include repo_scan with classification='deferred'."""
        source = self._get_handler_source()
        fn_start = source.find("async def get_project_details(")
        fn_end = source.find("\n@router.", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        # Verify the deferred stub is in the response
        assert (
            '"classification": "deferred"' in fn_body or "'classification': 'deferred'" in fn_body
        ), (
            "get_project_details() must include a deferred stub for repo_scan with "
            "classification='deferred' to clearly signal the data is not on the critical path."
        )

    def test_module_runtime_fit_uses_l3_stack_evidence(self):
        """_module_runtime_fit() must use L3 stack_evidence, not filesystem scan result."""
        source = self._get_handler_source()
        fn_start = source.find("async def get_project_details(")
        fn_end = source.find("\n@router.", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        # The _module_runtime_fit call must use health_payload project stack evidence
        assert (
            "stack_evidence" in fn_body
        ), "_module_runtime_fit() must use L3 stack_evidence from health_payload (business_projects)"

    def test_no_rglob_on_details_critical_path(self):
        """rglob must not be on the /details critical path (only inside _repo_stack_evidence itself)."""
        source = self._get_handler_source()
        fn_start = source.find("async def get_project_details(")
        fn_end = source.find("\n@router.", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        assert "rglob" not in fn_body, (
            "rglob must not appear in get_project_details() handler body. "
            "Filesystem walk must not be on the popup critical path."
        )

    def test_health_endpoint_never_called_repo_stack_evidence(self):
        """GET /health should also not call _repo_stack_evidence()."""
        source = self._get_handler_source()
        fn_start = source.find("async def get_project_health(")
        fn_end = source.find("\n@router.", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        assert "_repo_stack_evidence(" not in fn_body, (
            "get_project_health() must not call _repo_stack_evidence(). "
            "Health endpoint should be fast for all projects."
        )

    def test_stack_json_still_read_from_l3(self):
        """Details handler must still surface framework data from business_projects.stack_json."""
        source = self._get_handler_source()
        fn_start = source.find("async def get_project_details(")
        fn_end = source.find("\n@router.", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        # registry_stack field must be present in the response
        assert (
            "registry_stack" in fn_body or "stack_evidence" in fn_body
        ), "get_project_details() must surface stack data from L3 (business_projects)"


# ── Compliance: no filesystem walks in dashboard handlers ─────────────────


class TestDashboardFilesystemCompliance:
    def test_no_rglob_in_handler_functions(self):
        """No dashboard handler function body should contain rglob calls."""
        # project_intelligence.py was split; combine all route files for the scan.
        # WO-GF-API-ROUTES split project_detail.py further into a thin facade
        # (zero @router. bodies) + 4 handler siblings — include the siblings so
        # this scan still covers their handler bodies (facade alone would
        # silently pass with no coverage).
        route_files = [
            REPO_ROOT / "projections/api/routes/project_list.py",
            REPO_ROOT / "projections/api/routes/project_detail.py",
            REPO_ROOT / "projections/api/routes/project_detail_health.py",
            REPO_ROOT / "projections/api/routes/project_detail_details.py",
            REPO_ROOT / "projections/api/routes/project_detail_history_runs.py",
            REPO_ROOT / "projections/api/routes/project_detail_activity.py",
            REPO_ROOT / "projections/api/routes/project_artifacts.py",
            REPO_ROOT / "projections/api/routes/project_security.py",
        ]
        source = "\n".join(f.read_text(encoding="utf-8") for f in route_files)
        # All router handlers (async def routes)
        lines = source.splitlines()
        in_handler = False
        handler_name = ""
        violations = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("@router."):
                in_handler = True
            elif in_handler and stripped.startswith("async def ") or stripped.startswith("def "):
                if in_handler:
                    handler_name = (
                        stripped.split("(")[0].replace("async def ", "").replace("def ", "")
                    )
            elif in_handler and "rglob" in stripped:
                # Only flag if we're inside a router handler, not inside _repo_stack_evidence itself
                if handler_name and handler_name not in ("_repo_stack_evidence",):
                    violations.append(f"Line {i+1} in {handler_name}: {stripped[:80]}")
            elif stripped.startswith("@router.") or (
                stripped.startswith("def ") and not in_handler
            ):
                in_handler = False
                handler_name = ""

        assert not violations, "rglob found in handler function bodies:\n" + "\n".join(violations)
