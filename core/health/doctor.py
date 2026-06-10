"""Doctor checks — composite health view used by `ds doctor`.

The pure read-only path is `run_doctor_checks(fix=False)`. The `--fix` path
remains driven from the CLI wrapper in `interfaces/cli/ds.py` because it
shells out to `ds integrate install`, `ds spool ingest`, and `ds update`
which are themselves CLI-bound; A2 will decompose those subprocess
re-invocations into direct calls.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from core.health.overhead import run_overhead_checks
from core.health.validate import run_validation
from core.installed_runtime import resolve_installed_runtime_paths

_CLI_REFERENCE_PATTERN = re.compile(r"py\s+-m\s+interfaces\.cli\.ds")
_ROUTING_BEGIN = "<!-- BEGIN AUTO-ROUTING -->"
_ROUTING_END = "<!-- END AUTO-ROUTING -->"


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


def _compute_directory_hash(path: Path) -> str:
    """SHA-256 over the relative paths and bytes of every regular file under ``path``.

    Hidden directories (``.git``, ``.pytest_cache``, ``__pycache__``) are skipped
    so caches and editor scratch files do not flip the hash.
    """
    if not path.is_dir():
        return ""
    digest = hashlib.sha256()
    for file_path in sorted(path.rglob("*")):
        if not file_path.is_file():
            continue
        if any(
            part.startswith(".") or part == "__pycache__"
            for part in file_path.relative_to(path).parts
        ):
            continue
        rel = file_path.relative_to(path).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\x00")
        try:
            # Normalize line endings so CRLF (Windows install) == LF (repo source).
            digest.update(file_path.read_bytes().replace(b"\r\n", b"\n"))
        except OSError:
            digest.update(b"<unreadable>")
        digest.update(b"\x01")
    return digest.hexdigest()


def _resolve_canonical_skill_dir(canonical_skills_dir: Path, skill_id: str) -> Path | None:
    """Find a skill's source directory.

    Some canonical packs live under their bare key (``canonical/skills/core``)
    while installed packs live under the ds-prefixed id (``ds-core``). Try both.
    """
    pack_key = skill_id.removeprefix("ds-")
    for candidate in (canonical_skills_dir / skill_id, canonical_skills_dir / pack_key):
        if candidate.is_dir():
            return candidate
    return None


def _check_skill_freshness(
    canonical_skills_dir: Path,
    installed_skills_dir: Path,
    expected_skill_ids: list[str],
) -> list[str]:
    """Return skill ids whose installed copy hashes differently from the canonical copy."""
    stale: list[str] = []
    for sid in expected_skill_ids:
        source_dir = _resolve_canonical_skill_dir(canonical_skills_dir, sid)
        installed_dir = installed_skills_dir / sid
        if source_dir is None or not installed_dir.is_dir():
            continue
        if _compute_directory_hash(source_dir) != _compute_directory_hash(installed_dir):
            stale.append(sid)
    return stale


def _check_pack_mode_coverage(
    packs_yaml_path: Path,
    installed_skills_dir: Path,
) -> list[str]:
    """Return ``"<pack>:<mode>"`` entries declared in packs.yaml but not installed."""
    try:
        import yaml as _yaml
    except ImportError:
        return []
    try:
        data = _yaml.safe_load(packs_yaml_path.read_text(encoding="utf-8")) or {}
    except OSError:
        return []
    missing: list[str] = []
    for pack_key, pack_cfg in (data.get("packs") or {}).items():
        if not isinstance(pack_cfg, dict):
            continue
        skill_id = pack_cfg.get("skill", pack_key)
        if not skill_id.startswith("ds-"):
            skill_id = f"ds-{skill_id}"
        modes_dir = installed_skills_dir / skill_id / "modes"
        for mode in pack_cfg.get("modes", []) or []:
            if not (modes_dir / mode).is_dir():
                missing.append(f"{pack_key}:{mode}")
    return missing


def _check_routing_trigger_coverage(
    canonical_skills_dir: Path,
    installed_claude_md: Path,
) -> list[str]:
    """Return triggers declared in metadata.yml files but absent from the installed routing block."""
    if not installed_claude_md.is_file():
        return ["<missing-installed-CLAUDE.md>"]
    try:
        content = installed_claude_md.read_text(encoding="utf-8")
    except OSError:
        return ["<unreadable-installed-CLAUDE.md>"]

    begin = content.find(_ROUTING_BEGIN)
    end = content.find(_ROUTING_END)
    if begin == -1 or end == -1:
        return ["<no-routing-block>"]
    routing_block = content[begin:end]

    try:
        import yaml as _yaml
    except ImportError:
        return []

    unrouted: list[str] = []
    seen: set[str] = set()
    for metadata_path in sorted(canonical_skills_dir.rglob("metadata.yml")):
        try:
            data = _yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
        except (OSError, Exception):
            continue
        for item in data.get("triggers", []) or []:
            trigger: str | None = None
            if isinstance(item, str):
                trigger = item.rstrip(":").strip()
            elif isinstance(item, dict):
                for key in item:
                    trigger = str(key).rstrip(":").strip()
                    break
            if not trigger or trigger in seen:
                continue
            seen.add(trigger)
            if f"{trigger}:" not in routing_block:
                unrouted.append(trigger)
    return unrouted


def _check_enforcement_block_no_cli() -> list[str]:
    """Regression guard for A4/A5: source _ENFORCEMENT_BLOCK must contain no CLI commands."""
    try:
        from integrations.compiler.claude_code import _ENFORCEMENT_BLOCK
    except Exception:
        return []
    return _CLI_REFERENCE_PATTERN.findall(_ENFORCEMENT_BLOCK)


def _check_skills_installed(claude_dir: Path, source_root: Path | None = None) -> dict[str, Any]:
    """Composite skill-install + skill-sync status.

    Returns the existing keys (``total_expected``, ``installed``, ``missing``) plus
    drift-detection fields used by the pre-push gate:

      * ``stale`` — installed skills whose contents differ from the canonical source
      * ``pack_modes_missing`` — ``<pack>:<mode>`` combos declared in packs.yaml but not installed
      * ``triggers_unrouted`` — metadata.yml triggers absent from the installed CLAUDE.md routing block
      * ``enforcement_block_cli_refs`` — CLI patterns found in the source enforcement block (A4/A5 regression guard)
    """
    expected = _get_expected_skill_ids(source_root) if source_root is not None else ["ds-bootstrap"]
    empty_sync_fields = {
        "stale": [],
        "pack_modes_missing": [],
        "triggers_unrouted": [],
        "enforcement_block_cli_refs": [],
    }
    try:
        skills_dir = claude_dir / "skills"
        installed = [sid for sid in expected if (skills_dir / sid / "SKILL.md").is_file()]
        missing = [sid for sid in expected if sid not in installed]
        result: dict[str, Any] = {
            "total_expected": len(expected),
            "installed": len(installed),
            "missing": missing,
            **empty_sync_fields,
        }
    except Exception:
        return {
            "total_expected": len(expected),
            "installed": 0,
            "missing": expected,
            **empty_sync_fields,
        }

    if source_root is None:
        return result

    canonical_skills_dir = source_root / "canonical" / "skills"
    packs_yaml_path = source_root / "packs.yaml"
    installed_claude_md = claude_dir / "CLAUDE.md"

    result["stale"] = _check_skill_freshness(canonical_skills_dir, skills_dir, expected)
    result["pack_modes_missing"] = _check_pack_mode_coverage(packs_yaml_path, skills_dir)
    result["triggers_unrouted"] = _check_routing_trigger_coverage(
        canonical_skills_dir, installed_claude_md
    )
    result["enforcement_block_cli_refs"] = _check_enforcement_block_no_cli()
    return result


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


def _check_handoff_spawner(source_root: Path) -> dict[str, Any]:
    """Verify the handoff-continuation spawner can load session_config.spawn_new_session."""
    import importlib.util

    session_config_path = source_root / "runtime" / "session_config.py"
    if not session_config_path.is_file():
        return {
            "status": "fail",
            "reason": "session_config.py not found",
            "spawn_importable": False,
        }
    try:
        spec = importlib.util.spec_from_file_location(
            "_ds_session_config_check", session_config_path
        )
        if spec is None or spec.loader is None:
            return {
                "status": "fail",
                "reason": "module spec unresolvable",
                "spawn_importable": False,
            }
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        if not hasattr(mod, "spawn_new_session"):
            return {
                "status": "fail",
                "reason": "spawn_new_session missing from session_config",
                "spawn_importable": False,
            }
        return {"status": "pass", "spawn_importable": True}
    except Exception as exc:
        return {"status": "fail", "reason": str(exc), "spawn_importable": False}


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


def _check_stale_dbs(dream_studio_home: Path) -> dict[str, Any]:
    """Scan ~/.dream-studio/ for .db files outside ~/.dream-studio/state/.

    These are unexpected and likely stale ghost files (e.g. empty authority.db
    created at the home root by a misconfigured resolver). Flags them with a
    clear delete recommendation so they don't cause false-negative task-done
    reads or other silent authority mismatches.
    """
    try:
        state_dir = dream_studio_home / "state"
        diagnostics_dir = dream_studio_home / "diagnostics"
        stale: list[str] = []
        for db_file in dream_studio_home.rglob("*.db"):
            try:
                db_file.relative_to(state_dir)
                continue
            except ValueError:
                pass
            try:
                db_file.relative_to(diagnostics_dir)
                continue
            except ValueError:
                pass
            stale.append(str(db_file))
        return {"stale_dbs": stale, "ok": len(stale) == 0}
    except Exception:
        return {"stale_dbs": [], "ok": True}


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
    handoff_spawner_info = _check_handoff_spawner(source_root)
    stale_dbs_info = _check_stale_dbs(paths.dream_studio_home)

    from core.config.schema_coherence import check_schema_coherence

    # Use the canonical live-DB path (same resolver as database.py).
    # paths.dream_studio_home is already resolved from the env/default chain.
    live_db = paths.dream_studio_home / "state" / "studio.db"
    schema_coherence_info = check_schema_coherence(source_root=source_root, live_db_path=live_db)
    overhead_info = run_overhead_checks(source_root=source_root, claude_dir=claude_dir)

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
            "schema_coherence": schema_coherence_info,
            "overhead": overhead_info,
            "handoff_spawner": handoff_spawner_info,
            "stale_dbs": stale_dbs_info,
        },
        "validation": validation,
    }
    if fix:
        result["fix_actions"] = fix_actions
    return result
