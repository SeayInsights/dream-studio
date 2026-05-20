"""Doctor checks — composite health view used by `ds doctor`.

The pure read-only path is `run_doctor_checks(fix=False)`. The `--fix` path
remains driven from the CLI wrapper in `interfaces/cli/ds.py` because it
shells out to `ds integrate install`, `ds spool ingest`, and `ds update`
which are themselves CLI-bound; A2 will decompose those subprocess
re-invocations into direct calls.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from core.health.validate import run_validation
from core.installed_runtime import resolve_installed_runtime_paths


def _check_dispatcher_hooks(claude_dir: Path) -> bool:
    import json

    _DISPATCHER_MARKERS = (
        "hooks\\dispatch\\hooks.py",
        "hooks/dispatch/hooks.py",
        "runtime/dispatch/hooks",
        "'dispatch'/'hooks.py'",
    )
    try:
        settings_path = claude_dir / "settings.json"
        if not settings_path.is_file():
            return False
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        hooks_section = data.get("hooks", {})
        event_entries = hooks_section.get("UserPromptSubmit", [])
        for entry in event_entries:
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                if any(m in cmd for m in _DISPATCHER_MARKERS):
                    return True
        return False
    except Exception:
        return False


def _get_expected_skill_ids(source_root: Path) -> list[str]:
    skills_dir = source_root / "canonical" / "skills"
    if not skills_dir.is_dir():
        return ["ds-bootstrap"]
    ids = [
        (d.name if d.name.startswith("ds-") else f"ds-{d.name}")
        for d in sorted(skills_dir.iterdir())
        if d.is_dir() and (d / "SKILL.md").is_file()
    ]
    return ids or ["ds-bootstrap"]


def _check_skills_installed(claude_dir: Path, source_root: Path | None = None) -> dict[str, Any]:
    expected = _get_expected_skill_ids(source_root) if source_root is not None else ["ds-bootstrap"]
    try:
        skills_dir = claude_dir / "skills"
        installed = [sid for sid in expected if (skills_dir / sid / "SKILL.md").is_file()]
        missing = [sid for sid in expected if sid not in installed]
        return {"total_expected": len(expected), "installed": len(installed), "missing": missing}
    except Exception:
        return {"total_expected": len(expected), "installed": 0, "missing": expected}


def _check_agents_installed(claude_dir: Path, source_root: Path) -> dict[str, Any]:
    try:
        agents_src = source_root / "canonical" / "agents"
        expected = (
            [p.stem for p in agents_src.glob("*.md") if p.name != "README.md"]
            if agents_src.is_dir()
            else []
        )
        agents_dir = claude_dir / "agents"
        installed = [name for name in expected if (agents_dir / f"{name}.md").is_file()]
        missing = [name for name in expected if name not in installed]
        return {"total_expected": len(expected), "installed": len(installed), "missing": missing}
    except Exception:
        return {"total_expected": 0, "installed": 0, "missing": []}


def _check_failed_events(dream_studio_home: Path) -> dict[str, int]:
    try:
        failed_dir = dream_studio_home / "events" / "failed"
        if not failed_dir.is_dir():
            return {"count": 0}
        count = sum(1 for p in failed_dir.iterdir() if p.is_file() and p.suffix == ".json")
        return {"count": count}
    except Exception:
        return {"count": 0}


def _check_version_current(source_root: Path, dream_studio_home: Path) -> dict[str, Any]:
    try:
        repo_file = source_root / "VERSION"
        installed_file = dream_studio_home / "state" / "installed-version"
        repo_ver = repo_file.read_text(encoding="utf-8").strip() if repo_file.is_file() else None
        installed_ver = (
            installed_file.read_text(encoding="utf-8").strip() if installed_file.is_file() else None
        )
        current = repo_ver is not None and repo_ver == installed_ver
        return {"repo": repo_ver, "installed": installed_ver, "current": current}
    except Exception:
        return {"repo": None, "installed": None, "current": False}


def run_doctor_checks(
    *,
    source_root: Path,
    dream_studio_home: Path | None = None,
    fix: bool = False,
) -> dict[str, Any]:
    """Composite doctor status. fix=True triggers self-healing side effects."""

    validation = run_validation(source_root=source_root, dream_studio_home=dream_studio_home)
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    claude_dir = Path.home() / ".claude"

    dispatcher_ok = _check_dispatcher_hooks(claude_dir)
    skills_info = _check_skills_installed(claude_dir, source_root=source_root)
    agents_info = _check_agents_installed(claude_dir, source_root)
    failed_info = _check_failed_events(paths.dream_studio_home)
    version_info = _check_version_current(source_root, paths.dream_studio_home)

    core_pass = validation["ready"]
    critical_fail = (
        not dispatcher_ok
        or skills_info["missing"]
        or failed_info["count"] >= 6
        or not version_info["current"]
    )
    has_warnings = 0 < failed_info["count"] < 6

    if critical_fail:
        overall = "fail"
    elif not core_pass:
        overall = "attention_required"
    elif has_warnings:
        overall = "warn"
    else:
        overall = "pass"

    fix_actions: list[str] = []
    if fix:
        if not dispatcher_ok or skills_info["missing"] or agents_info["missing"]:
            try:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "interfaces.cli.ds",
                        "integrate",
                        "install",
                        "claude_code",
                        "--execute",
                    ],
                    check=False,
                )
                fix_actions.append("install: ran integrate install claude_code --execute")
            except Exception as exc:
                fix_actions.append(f"install: failed — {exc}")
        if failed_info["count"] > 0:
            try:
                spool_events_root = paths.dream_studio_home / "events"
                failed_dir = spool_events_root / "failed"
                spool_dir = spool_events_root / "spool"
                spool_dir.mkdir(parents=True, exist_ok=True)
                requeued = 0
                for event_file in list(failed_dir.glob("*.json")):
                    try:
                        os.replace(str(event_file), str(spool_dir / event_file.name))
                        requeued += 1
                    except OSError:
                        pass
                fix_actions.append(f"requeue: moved {requeued} failed event(s) back to spool/")
            except Exception as exc:
                fix_actions.append(f"requeue: failed — {exc}")
            try:
                subprocess.run(
                    [sys.executable, "-m", "interfaces.cli.ds", "spool", "ingest"],
                    check=False,
                )
                fix_actions.append("spool ingest: ran spool ingest to process requeued events")
            except Exception as exc:
                fix_actions.append(f"spool ingest: failed — {exc}")
        if not version_info["current"]:
            try:
                subprocess.run(
                    [sys.executable, "-m", "interfaces.cli.ds", "update"],
                    check=False,
                )
                fix_actions.append("update: ran ds update")
            except Exception as exc:
                fix_actions.append(f"update: failed — {exc}")

    result: dict[str, Any] = {
        "model_name": "dream_studio_doctor_status",
        "derived_view": True,
        "primary_authority": False,
        "status": overall,
        "checks": {
            "sqlite_exists": validation["sqlite_exists"],
            "schema_version_known": validation["schema_version"] is not None,
            "module_profiles_valid": not validation["module_profile_errors"],
            "doctor_runs_read_only": True,
            "dispatcher_hooks_installed": dispatcher_ok,
            "skills_installed": skills_info,
            "agents_installed": agents_info,
            "failed_events": failed_info,
            "version_current": version_info,
        },
        "validation": validation,
    }
    if fix:
        result["fix_actions"] = fix_actions
    return result
