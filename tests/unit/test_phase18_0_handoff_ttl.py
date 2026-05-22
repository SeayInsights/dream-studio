"""Tests for handoff TTL guards in on-prompt-validate.py (Phase 18.0, C2)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def state_dir(tmp_path):
    d = tmp_path / ".dream-studio" / "state"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def pending_file(state_dir):
    return state_dir / "pending-handoff.json"


def _write_handoff(pending_file: Path, age_seconds: float, status: str = "pending") -> None:
    triggered = int(time.time() - age_seconds)
    pending_file.write_text(
        json.dumps({"triggered_at": triggered, "status": status, "session_id": "sess-1"}),
        encoding="utf-8",
    )


class TestHandoffTTLGuards:
    def test_fresh_pending_file_is_injected(self, state_dir, pending_file):
        """A brand-new pending file (age < 60s) should trigger handoff injection."""
        import sys
        from unittest.mock import MagicMock

        _write_handoff(pending_file, age_seconds=5, status="pending")

        payload = {"prompt": "hello"}
        # Patch Path.home to return our tmp dir
        with patch("pathlib.Path.home", return_value=state_dir.parent.parent):
            import importlib

            spec = importlib.util.spec_from_file_location(
                "on_prompt_validate",
                Path(__file__).resolve().parents[2]
                / "runtime"
                / "hooks"
                / "meta"
                / "on-prompt-validate.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            captured = []
            with patch.object(sys, "stdout") as mock_stdout:
                mock_stdout.write = lambda s: captured.append(s)
                result = mod._check_pending_handoff(payload)

        assert result is True
        assert pending_file.is_file()  # updated to in_progress, not deleted

    def test_stale_file_is_deleted_on_read(self, state_dir, pending_file, tmp_path):
        """A file older than HANDOFF_STALE_TTL_S must be deleted and False returned."""
        _write_handoff(pending_file, age_seconds=400, status="in_progress")
        assert pending_file.is_file()

        import importlib

        with patch("pathlib.Path.home", return_value=state_dir.parent.parent):
            spec = importlib.util.spec_from_file_location(
                "on_prompt_validate_stale",
                Path(__file__).resolve().parents[2]
                / "runtime"
                / "hooks"
                / "meta"
                / "on-prompt-validate.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            result = mod._check_pending_handoff({"prompt": "hello"})

        assert result is False
        assert not pending_file.is_file(), "Stale pending file should have been deleted"

    def test_in_progress_past_injection_window_is_deleted(self, state_dir, pending_file):
        """An in_progress file older than HANDOFF_INJECTION_WINDOW_S must be deleted."""
        _write_handoff(pending_file, age_seconds=120, status="in_progress")
        assert pending_file.is_file()

        import importlib

        with patch("pathlib.Path.home", return_value=state_dir.parent.parent):
            spec = importlib.util.spec_from_file_location(
                "on_prompt_validate_inprogress",
                Path(__file__).resolve().parents[2]
                / "runtime"
                / "hooks"
                / "meta"
                / "on-prompt-validate.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            result = mod._check_pending_handoff({"prompt": "hello"})

        assert result is False
        assert not pending_file.is_file(), "Stale in_progress file should have been deleted"

    def test_stale_discard_writes_diagnostic(self, state_dir, pending_file):
        """Discarding a stale handoff must write a diagnostic log entry."""
        _write_handoff(pending_file, age_seconds=400, status="in_progress")

        import importlib
        import os

        diag_dir = state_dir.parent / "diagnostics"
        env_patch = {"DS_DIAGNOSTICS_DIR": str(diag_dir)}
        with patch("pathlib.Path.home", return_value=state_dir.parent.parent), patch.dict(
            os.environ, env_patch
        ):
            spec = importlib.util.spec_from_file_location(
                "on_prompt_validate_diag",
                Path(__file__).resolve().parents[2]
                / "runtime"
                / "hooks"
                / "meta"
                / "on-prompt-validate.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod._check_pending_handoff({"prompt": "hello"})

        diag_file = diag_dir / "stale-handoff.jsonl"
        assert diag_file.is_file(), "Diagnostic file should have been written"
        entry = json.loads(diag_file.read_text(encoding="utf-8").strip())
        assert entry["event"] == "stale_handoff_discarded"
        assert entry["age_seconds"] >= 399

    def test_ttl_constants_have_expected_values(self):
        """TTL constants must match the documented values."""
        import importlib

        spec = importlib.util.spec_from_file_location(
            "on_prompt_validate_consts",
            Path(__file__).resolve().parents[2]
            / "runtime"
            / "hooks"
            / "meta"
            / "on-prompt-validate.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.HANDOFF_STALE_TTL_S == 300
        assert mod.HANDOFF_INJECTION_WINDOW_S == 60
