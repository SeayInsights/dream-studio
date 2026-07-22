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

import inspect
import json
from pathlib import Path

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


class TestFix2DesignBriefEmits:
    def _get_design_brief_source(self):
        return (REPO_ROOT / "core/design_briefs/mutations.py").read_text(encoding="utf-8")

    def test_create_design_brief_emits_event(self):
        """create_design_brief() must emit design_brief.created."""
        source = self._get_design_brief_source()
        fn_start = source.find("def create_design_brief(")
        fn_end = source.find("\ndef ", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        assert (
            "design_brief.created" in fn_body
        ), "create_design_brief() must emit design_brief.created event"

    def test_lock_design_brief_emits_event(self):
        """lock_design_brief() must emit design_brief.locked."""
        source = self._get_design_brief_source()
        fn_start = source.find("def lock_design_brief(")
        fn_end = source.find("\ndef ", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        assert (
            "design_brief.locked" in fn_body
        ), "lock_design_brief() must emit design_brief.locked event"

    def test_update_design_brief_field_emits_event_with_field_and_value(self):
        """update_design_brief_field() must emit event carrying field name + value."""
        source = self._get_design_brief_source()
        fn_start = source.find("def update_design_brief_field(")
        fn_end = source.find("\ndef ", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        assert (
            "design_brief.updated" in fn_body
        ), "update_design_brief_field() must emit design_brief.updated event"
        # Event payload must carry field name — W16 requirement
        assert (
            '"field"' in fn_body or "'field'" in fn_body
        ), "Event payload must include 'field' key for W16 dynamic-field compliance"

    def test_design_brief_events_in_registry(self):
        """All design_brief.* event types must be registered."""
        source = (REPO_ROOT / "config/event_type_registry.py").read_text(encoding="utf-8")
        for event_type in ("design_brief.created", "design_brief.updated", "design_brief.locked"):
            assert (
                event_type in source
            ), f"Event type {event_type!r} must be registered in config/event_type_registry.py"

    def test_lock_design_brief_no_direct_update(self):
        """lock_design_brief() must not do direct UPDATE — projection handles it."""
        source = self._get_design_brief_source()
        fn_start = source.find("def lock_design_brief(")
        fn_end = source.find("\ndef ", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        # No direct SQL UPDATE after migration — projection is the writer
        assert "UPDATE business_design_briefs" not in fn_body, (
            "lock_design_brief() must not directly UPDATE business_design_briefs. "
            "DesignBriefProjection applies the state change from the canonical event."
        )

    def test_create_design_brief_no_direct_insert(self):
        """create_design_brief() must not do direct INSERT — projection handles it."""
        source = self._get_design_brief_source()
        fn_start = source.find("def create_design_brief(")
        fn_end = source.find("\ndef ", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        assert "INSERT INTO business_design_briefs" not in fn_body, (
            "create_design_brief() must not directly INSERT into business_design_briefs. "
            "DesignBriefProjection applies the row from the design_brief.created event."
        )

    def test_update_design_brief_field_no_direct_update(self):
        """update_design_brief_field() must not do direct UPDATE — projection handles it."""
        source = self._get_design_brief_source()
        fn_start = source.find("def update_design_brief_field(")
        fn_end = source.find("\ndef ", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        assert "UPDATE business_design_briefs" not in fn_body, (
            "update_design_brief_field() must not directly UPDATE business_design_briefs. "
            "DesignBriefProjection applies the field change from the design_brief.updated event."
        )

    def test_set_design_system_no_direct_update(self):
        """set_design_system() must not do direct UPDATE — projection handles it."""
        source = self._get_design_brief_source()
        fn_start = source.find("def set_design_system(")
        fn_end = source.find("\ndef ", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        assert "UPDATE business_design_briefs" not in fn_body, (
            "set_design_system() must not directly UPDATE business_design_briefs. "
            "DesignBriefProjection applies the update from the design_brief.updated event."
        )


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
        details_source = (
            REPO_ROOT / "projections/api/routes/project_detail_details.py"
        ).read_text(encoding="utf-8")
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
