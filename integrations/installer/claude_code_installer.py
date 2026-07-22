"""ClaudeCodeInstaller — plan/install orchestration for the Claude Code
integration installer.

WO-GF-CONTROL-INSTALL-split: see claude_code.py facade docstring.
"""

from __future__ import annotations

import json
import platform
import stat
from pathlib import Path
from typing import Any, Literal

from integrations.compiler.claude_code import compile_pack
from integrations.installer.base import FileOp, FileOpPlan, InstallerBase, RefusalError
from integrations.installer.file_ops import atomic_copy, atomic_write, backup_before_write
from integrations.manifest import (
    build_manifest,
    compute_hash,
    get_ds_home,
    read_manifest,
    write_manifest,
)
from integrations.targets.claude_code.settings_merge import (
    dedup_hooks_by_normalized_command,
    load_settings,
    merge_settings,
    purge_all_hook_registrations,
    purge_legacy_hooks,
    purge_read_posttooluse_matcher,
    settings_to_json,
)

from .claude_code_fileops import (
    _collect_hook_file_ops,
    _collect_skill_dir_ops,
    _interpolate_hooks_dir,
    _interpolate_statusline_cmd,
)
from .claude_code_launcher import _first_run_guide, _get_ds_version, _write_global_launcher
from .claude_code_shared import _REPO_ROOT


def _post_install_validate(config_root: Path, settings_path: Path) -> dict[str, Any]:
    """Lightweight post-install validation — checks installed artifacts directly."""
    skills_dir = config_root / "skills"
    skills_found = (
        [d.name for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").is_file()]
        if skills_dir.is_dir()
        else []
    )
    agents_dir = config_root / "agents"
    agents_found = [f.stem for f in agents_dir.glob("*.md")] if agents_dir.is_dir() else []
    dispatcher_ok = False
    if settings_path.is_file():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            for entry in data.get("hooks", {}).get("UserPromptSubmit", []):
                for h in entry.get("hooks", []):
                    cmd = h.get("command", "")
                    if (
                        "dispatch/hooks.py" in cmd
                        or "dispatch\\hooks.py" in cmd
                        or "runtime/dispatch/hooks" in cmd
                        or "'dispatch'/'hooks.py'" in cmd
                    ):
                        dispatcher_ok = True
                        break
        except Exception:
            pass
    return {
        "skills_found": len(skills_found),
        "agents_found": len(agents_found),
        "dispatcher_hooks_ok": dispatcher_ok,
        "pass": len(skills_found) > 0 and dispatcher_ok,
    }


def _skill_id_from_dir_name(dirname: str) -> str:
    """Convert canonical/skills/ directory name to Claude Code skill_id."""
    return dirname if dirname.startswith("ds-") else f"ds-{dirname}"


class ClaudeCodeInstaller(InstallerBase):
    def __init__(
        self,
        config_root: Path,
        scope: str,
        *,
        canonical_root: Path | None = None,
        ds_home: Path | None = None,
        git_repo_root: Path | None = None,
        skip_hook_install: bool = False,
    ):
        self.config_root = config_root
        self.scope = scope
        self.canonical_root = canonical_root
        self.ds_home = ds_home
        self.git_repo_root = git_repo_root
        self.skip_hook_install = skip_hook_install

    def _get_source_root(self) -> Path:
        """Resolve source root (repo root) for VERSION and canonical/ lookups."""
        if self.canonical_root is not None:
            return self.canonical_root.parent
        return _REPO_ROOT

    def plan(self) -> FileOpPlan:
        pack = compile_pack(self.canonical_root)
        ops: list[FileOp] = []
        ds_home = get_ds_home(self.ds_home)
        backup_base = ds_home / "backups" / "claude_code"
        canonical_root = (
            self.canonical_root if self.canonical_root is not None else (_REPO_ROOT / "canonical")
        )

        # 1. Full skill directory sync — every file under canonical/skills/<pack>/
        skills_src_dir = canonical_root / "skills"
        if skills_src_dir.is_dir():
            for skill_dir in sorted(skills_src_dir.iterdir()):
                if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").is_file():
                    continue
                skill_id = _skill_id_from_dir_name(skill_dir.name)
                target_dir = self.config_root / "skills" / skill_id
                ops.extend(_collect_skill_dir_ops(skill_dir, target_dir, skill_id, backup_base))

        # 2. CLAUDE.md — create (enforcement block + adapter projection)
        claude_md_content = pack["files"].get("CLAUDE.md")
        if claude_md_content is not None:
            claude_target = self.config_root / "CLAUDE.md"
            ops.append(
                FileOp(
                    target=claude_target,
                    op="create",
                    backup_required=claude_target.exists(),
                    source_hash=compute_hash(claude_md_content),
                    source_content=claude_md_content,
                    reason="Install Dream Studio enforcement block into CLAUDE.md projection",
                    safety_notes=(
                        "Overwrites CLAUDE.md with enforcement block prepended to adapter projection. "
                        "Existing file is backed up before write."
                    ),
                    backup_path=backup_base if claude_target.exists() else None,
                )
            )

        # 2b. AGENTS.md — create (routing table target of CLAUDE.md's @AGENTS.md
        # import; without it the installed routing surface has no trigger keywords)
        agents_md_content = pack["files"].get("AGENTS.md")
        if agents_md_content:
            agents_target = self.config_root / "AGENTS.md"
            ops.append(
                FileOp(
                    target=agents_target,
                    op="create",
                    backup_required=agents_target.exists(),
                    source_hash=compute_hash(agents_md_content),
                    source_content=agents_md_content,
                    reason="Install generated AGENTS.md (resolves CLAUDE.md @AGENTS.md import)",
                    safety_notes=(
                        "Generated projection — overwritten on every install. "
                        "Existing file is backed up before write."
                    ),
                    backup_path=backup_base if agents_target.exists() else None,
                )
            )

        # 3. settings.json — merge_json (with {hooks_dir} interpolation + legacy purge)
        hooks_dir = self.config_root / "hooks"
        interpolated_hooks = _interpolate_hooks_dir(pack["settings_hooks"], hooks_dir)
        settings_target = self.config_root / "settings.json"
        existing_settings = load_settings(settings_target)
        merged, skip_reasons = merge_settings(existing_settings, interpolated_hooks)
        merged, _purged = purge_legacy_hooks(merged)
        merged = dedup_hooks_by_normalized_command(merged)
        merged = purge_read_posttooluse_matcher(merged)
        if self.scope == "project":
            # Project-scope settings must not register hook events — the user-global
            # ~/.claude/settings.json is the single dispatch surface.  Registering hooks
            # in both settings files causes every event to fire twice.
            merged = purge_all_hook_registrations(merged)
        # Always write the Python statusLine command to migrate from old bash wrapper
        merged["statusLine"] = {
            "type": "command",
            "command": _interpolate_statusline_cmd(hooks_dir),
        }
        merged_content = settings_to_json(merged)
        reason = (
            "Remove hook registrations from project-scope settings (single dispatch surface: user-global)"
            if self.scope == "project"
            else "Append DS spool emitter hooks (UserPromptSubmit, Stop, PostCompact, PostToolUse)"
        )
        ops.append(
            FileOp(
                target=settings_target,
                op="merge_json",
                backup_required=True,
                source_hash=compute_hash(merged_content),
                source_content=merged_content,
                reason=reason,
                safety_notes=(
                    "Additive only — never removes existing hooks. " f"Skipped: {skip_reasons}"
                    if skip_reasons
                    else "Additive only."
                ),
                backup_path=backup_base,
            )
        )

        # 4. settings.local.json — always skip
        local_target = self.config_root / "settings.local.json"
        ops.append(
            FileOp(
                target=local_target,
                op="skip",
                backup_required=False,
                source_hash="",
                reason="private/local config — never touched by DS installer",
                safety_notes="settings.local.json is operator-local and excluded from all DS operations.",
            )
        )

        # 5. Agent profiles — install canonical/agents/**/*.md to config_root/agents/
        agents_src_dir = canonical_root / "agents"
        if agents_src_dir.is_dir():
            for agent_file in sorted(agents_src_dir.rglob("*.md")):
                if agent_file.name == "README.md":
                    continue
                rel = agent_file.relative_to(agents_src_dir)
                content = agent_file.read_text(encoding="utf-8")
                target = self.config_root / "agents" / rel
                ops.append(
                    FileOp(
                        target=target,
                        op="create",
                        backup_required=target.exists(),
                        source_hash=compute_hash(content),
                        source_content=content,
                        reason=f"Install {agent_file.stem} agent profile for Claude Code",
                        safety_notes="Creates parent directories as needed.",
                        backup_path=backup_base if target.exists() else None,
                    )
                )

        # 6a. Workflow YAMLs — install canonical/workflows/*.yaml to config_root/workflows/
        workflows_src_dir = canonical_root / "workflows"
        if workflows_src_dir.is_dir():
            for wf_file in sorted(workflows_src_dir.glob("*.yaml")):
                content = wf_file.read_text(encoding="utf-8")
                target = self.config_root / "workflows" / wf_file.name
                ops.append(
                    FileOp(
                        target=target,
                        op="create",
                        backup_required=target.exists(),
                        source_hash=compute_hash(content),
                        source_content=content,
                        reason=f"Install {wf_file.name} workflow YAML",
                        safety_notes="Additive only — never deletes existing workflows.",
                        backup_path=backup_base if target.exists() else None,
                    )
                )

        # 6b. Workflow contract — copy docs/contracts/workflow-contract.md into ds-workflow skill
        source_root = self._get_source_root()
        contract_src = source_root / "docs" / "contracts" / "workflow-contract.md"
        if contract_src.is_file():
            content = contract_src.read_text(encoding="utf-8")
            contract_target = (
                self.config_root
                / "skills"
                / "ds-workflow"
                / "docs"
                / "contracts"
                / "workflow-contract.md"
            )
            ops.append(
                FileOp(
                    target=contract_target,
                    op="create",
                    backup_required=contract_target.exists(),
                    source_hash=compute_hash(content),
                    source_content=content,
                    reason="Install workflow contract into ds-workflow skill for schema validation",
                    safety_notes="Referenced by ds-workflow SKILL.md for runner validation.",
                    backup_path=backup_base if contract_target.exists() else None,
                )
            )

        # 7. Hook files — copy hook scripts, meta handlers, and .plugin-root sidecar
        source_root = self._get_source_root()
        ops.extend(_collect_hook_file_ops(source_root, hooks_dir, source_root, backup_base))

        # 7b. Git pre-push hook — install to <git_repo_root>/.git/hooks/pre-push (B.3).
        # Opt-in: only when git_repo_root is explicitly provided. The CLI sets this
        # to cwd when running `ds integrate install`; tests leave it None so the
        # operator's real .git/hooks/ is never touched.
        # Skipped when skip_hook_install=True (set via config.json skip_hook_install key).
        git_hook_src = source_root / "hooks" / "git" / "pre-push"
        git_hooks_dir = (self.git_repo_root / ".git" / "hooks") if self.git_repo_root else None
        if (
            not self.skip_hook_install
            and git_hook_src.is_file()
            and git_hooks_dir is not None
            and git_hooks_dir.is_dir()
        ):
            hook_content = git_hook_src.read_text(encoding="utf-8")
            git_hook_target = git_hooks_dir / "pre-push"
            ops.append(
                FileOp(
                    target=git_hook_target,
                    op="create",
                    backup_required=git_hook_target.exists(),
                    source_hash=compute_hash(hook_content),
                    source_content=hook_content,
                    reason="Install Dream Studio pre-push gate (B.3)",
                    safety_notes=(
                        "Runs canonical/workflows/pre-push.yaml gates before every push. "
                        "Bypass in emergencies with `git push --no-verify`. "
                        "Existing pre-push hook is backed up before overwrite."
                    ),
                    backup_path=backup_base if git_hook_target.exists() else None,
                )
            )

        # 8. installed-version — write version marker (must be last)
        source_root = self._get_source_root()
        version_file = source_root / "VERSION"
        if version_file.is_file():
            repo_version = version_file.read_text(encoding="utf-8").strip()
            version_target = ds_home / "state" / "installed-version"
            ops.append(
                FileOp(
                    target=version_target,
                    op="create",
                    backup_required=False,
                    source_hash=compute_hash(repo_version + "\n"),
                    source_content=repo_version + "\n",
                    reason="Write installed-version marker after successful install",
                    safety_notes="Tracks which source version is currently installed in this home.",
                )
            )

        return FileOpPlan(ops=ops, tool="claude_code", scope=self.scope)

    def install(self, mode: Literal["dry_run", "execute"]) -> dict[str, Any]:
        if mode not in ("dry_run", "execute"):
            raise RefusalError(
                f"install() requires mode='dry_run' or mode='execute'; got {mode!r}. "
                "Use --dry-run to simulate or --execute to write files."
            )

        file_plan = self.plan()
        plan_summary = file_plan.summary()

        if mode == "dry_run":
            return {
                "mode": "dry_run",
                "tool": "claude_code",
                "scope": self.scope,
                "config_root": str(self.config_root),
                "files_written": [],
                "plan": plan_summary,
                "ok": True,
            }

        # execute mode
        ds_home = get_ds_home(self.ds_home)
        backup_dir = ds_home / "backups" / "claude_code"
        files_written: list[dict[str, Any]] = []
        manifest_files: list[dict[str, Any]] = []
        agents_installed: list[str] = []
        hooks_installed: list[str] = []

        # Load existing manifest for incremental hash comparison
        existing_manifest = read_manifest("claude_code", self.ds_home)
        manifest_hash_map: dict[str, str] = {}
        if existing_manifest:
            for entry in existing_manifest.get("files", []):
                p, h = entry.get("path", ""), entry.get("content_hash", "")
                if h and entry.get("operation") not in ("skip",):
                    manifest_hash_map[p] = h

        # Per-category install counters
        skills_packs: set[str] = set()
        skills_files_copied = 0
        skills_files_updated = 0
        skills_files_unchanged = 0
        workflows_copied = 0
        workflows_updated = 0
        workflows_unchanged = 0
        hook_files_installed: list[str] = []

        for op in file_plan.ops:
            if op.op == "skip":
                continue

            target_str = str(op.target)
            is_unchanged = bool(
                manifest_hash_map.get(target_str) == op.source_hash and op.source_hash
            )

            # Categorize op
            parts = list(Path(op.target).parts)
            in_skills = "skills" in parts
            in_workflows = "workflows" in parts and not in_skills
            in_agents = "agents" in parts
            in_hooks = "hooks" in parts and not in_skills

            if in_skills:
                skill_idx = parts.index("skills")
                if skill_idx + 1 < len(parts):
                    skills_packs.add(parts[skill_idx + 1])
                if is_unchanged:
                    skills_files_unchanged += 1
                elif op.target.exists():
                    skills_files_updated += 1
                else:
                    skills_files_copied += 1
            elif in_workflows:
                if is_unchanged:
                    workflows_unchanged += 1
                elif op.target.exists():
                    workflows_updated += 1
                else:
                    workflows_copied += 1
            elif in_agents:
                agents_installed.append(Path(op.target).stem)
            elif in_hooks:
                hook_files_installed.append(Path(op.target).name)
            elif Path(op.target).name == "settings.json":
                hooks_installed.append("settings.json")

            if is_unchanged:
                manifest_files.append(
                    {
                        "path": target_str,
                        "operation": "unchanged",
                        "content_hash": op.source_hash,
                        "backup_path": None,
                    }
                )
                continue

            backup_path: Path | None = None
            if op.backup_required and op.target.exists():
                backup_path = backup_before_write(op.target, backup_dir)

            if op.source_content is not None:
                atomic_write(op.target, op.source_content)
            elif op.source_path is not None:
                atomic_copy(op.source_path, op.target)

            files_written.append(
                {
                    "path": target_str,
                    "op": op.op,
                    "backup_path": str(backup_path) if backup_path else None,
                }
            )
            manifest_files.append(
                {
                    "path": target_str,
                    "operation": op.op,
                    "content_hash": op.source_hash,
                    "backup_path": str(backup_path) if backup_path else None,
                }
            )

        manifest = build_manifest(
            tool="claude_code",
            scope=self.scope,
            ds_version=_get_ds_version(),
            files=manifest_files,
        )
        write_manifest("claude_code", manifest, self.ds_home)

        # B.3: ensure the git pre-push hook is executable on Unix-like systems.
        # FileOp's atomic_write does not preserve the +x bit and Windows ignores it.
        git_hook_installed = False
        if self.skip_hook_install:
            print(
                "\nPre-push hook installation skipped"
                " (config: skip_hook_install=true).\n"
                "To install it, remove skip_hook_install from config.json"
                " and re-run ds integrate install."
            )
        elif self.git_repo_root is not None:
            git_hook_path = self.git_repo_root / ".git" / "hooks" / "pre-push"
            if git_hook_path.is_file():
                if platform.system() != "Windows":
                    try:
                        git_hook_path.chmod(
                            git_hook_path.stat().st_mode
                            | stat.S_IEXEC
                            | stat.S_IXGRP
                            | stat.S_IXOTH
                        )
                    except OSError:
                        pass
                git_hook_installed = True
                print(
                    "\nPre-push hook installed to .git/hooks/pre-push\n"
                    "  Checks: formatting (black), lint baseline, skill-sync,"
                    " eval suite, atlas-leak, docs-drift\n"
                    "  To bypass once:    git push --no-verify\n"
                    "  To disable always: set skip_hook_install=true in"
                    " ~/.dream-studio/config.json, then re-run ds integrate install\n"
                    "  Docs: docs/contributing/pre-push-hook.md"
                )

        # Post-install validation (inline lightweight check)
        validation = _post_install_validate(self.config_root, self.config_root / "settings.json")

        # Write global launcher scripts
        launcher_output = _write_global_launcher(ds_home=ds_home)

        # Print PATH instructions
        print(launcher_output["path_instructions"])

        # Print first-run guide if no active projects exist
        first_run_guide = _first_run_guide(ds_home=ds_home)
        if first_run_guide:
            print(first_run_guide)

        # Print harvest pointer
        print(
            "\nOptional: Personalize Dream Studio from your session history.\n"
            "Run: ds memory ingest-sessions\n"
            "(You will be asked for consent before anything is stored.)"
        )

        return {
            "mode": "execute",
            "tool": "claude_code",
            "scope": self.scope,
            "config_root": str(self.config_root),
            "files_written": files_written,
            "skills": {
                "packs_synced": len(skills_packs),
                "files_copied": skills_files_copied,
                "files_updated": skills_files_updated,
                "files_unchanged": skills_files_unchanged,
            },
            "workflows": {
                "copied": workflows_copied,
                "updated": workflows_updated,
                "unchanged": workflows_unchanged,
            },
            "agents_installed": agents_installed,
            "hooks_installed": hooks_installed,
            "hook_files_installed": hook_files_installed,
            "git_hook_installed": git_hook_installed,
            "launcher": launcher_output,
            "plan": plan_summary,
            "validation": validation,
            "ok": True,
        }
