"""An installed app never writes workflow prompts into its own code."""

from __future__ import annotations

from core.config import paths
from control.execution.workflow.runner import workflow_context_dir


def test_an_installed_app_writes_workflow_prompts_under_the_home(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(paths, "is_source_checkout", lambda root=None: False)
    target = workflow_context_dir("wf-1")
    assert target == tmp_path / "home" / "planning" / "workflow" / "wf-1"
    assert paths.code_root() not in target.parents


def test_a_checkout_keeps_its_planning_directory(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    target = workflow_context_dir("wf-1")
    assert target.parts[-3:] == (".planning", "workflow", "wf-1")
