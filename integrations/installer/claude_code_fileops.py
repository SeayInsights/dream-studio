"""FileOp collection helpers for the Claude Code installer — hook/skill sync
and settings.json interpolation.

WO-GF-CONTROL-INSTALL-split: see claude_code.py facade docstring.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from integrations.installer.base import FileOp

from .claude_code_shared import _compute_file_hash_chunked, _python_cmd


def _interpolate_statusline_cmd(hooks_dir: Path) -> str:
    """Return the resolved statusLine command string with {hooks_dir} and {python_cmd} substituted."""
    template = '{python_cmd} "{hooks_dir}/statusline.py"'
    return template.replace("{hooks_dir}", str(hooks_dir)).replace("{python_cmd}", _python_cmd())


def _interpolate_hooks_dir(hooks: list[dict[str, Any]], hooks_dir: Path) -> list[dict[str, Any]]:
    """Replace {hooks_dir} and {python_cmd} placeholders in hook command strings."""
    import copy as _copy

    hooks_dir_str = str(hooks_dir).replace("\\", "/")
    python_cmd = _python_cmd()
    result = []
    for entry in hooks:
        entry = _copy.deepcopy(entry)
        for h in entry.get("hooks", []):
            if isinstance(h, dict):
                cmd = h.get("command", "")
                if "{hooks_dir}" in cmd:
                    cmd = cmd.replace("{hooks_dir}", hooks_dir_str)
                if "{python_cmd}" in cmd:
                    cmd = cmd.replace("{python_cmd}", python_cmd)
                h["command"] = cmd
        result.append(entry)
    return result


def _collect_hook_file_ops(
    source_root: Path,
    hooks_dir: Path,
    repo_root: Path,
    backup_base: Path,
) -> list[FileOp]:
    """Return FileOps for hook scripts, all handler packs, and the two sidecars.

    Two sidecars are written on every install (WO-RT self-containment):
    - .plugin-root   → hooks_dir  (handler-file path resolution)
    - .ds-source-root → repo_root (Python lib import fallback for core.*, spool.*, etc.)

    This keeps handler-file resolution and lib-import resolution on separate paths.
    A repo edit only takes effect after re-running install (re-projection).
    """
    from integrations.manifest import compute_hash as _compute_hash

    ops: list[FileOp] = []

    # Core hook scripts and their __init__.py companions
    hook_files: list[tuple[Path, Path]] = [
        (source_root / "emitters" / "claude_code" / "run.py", hooks_dir / "run.py"),
        (source_root / "runtime" / "dispatch" / "hooks.py", hooks_dir / "dispatch" / "hooks.py"),
        (
            source_root / "runtime" / "dispatch" / "__init__.py",
            hooks_dir / "dispatch" / "__init__.py",
        ),
        (
            source_root / "control" / "execution" / "dispatch_tracking.py",
            hooks_dir / "control" / "execution" / "dispatch_tracking.py",
        ),
        (source_root / "control" / "__init__.py", hooks_dir / "control" / "__init__.py"),
        (
            source_root / "control" / "execution" / "__init__.py",
            hooks_dir / "control" / "execution" / "__init__.py",
        ),
        (
            source_root / "runtime" / "hooks" / "meta" / "__init__.py",
            hooks_dir / "runtime" / "hooks" / "meta" / "__init__.py",
        ),
        # session_config.py — shared utility for session continuation
        (
            source_root / "runtime" / "session_config.py",
            hooks_dir / "runtime" / "session_config.py",
        ),
        # runtime package __init__ chain — required for runtime.lib.* imports
        # by direct-entry hooks (on-edit-enforce, on-stop-enforce)
        (source_root / "runtime" / "__init__.py", hooks_dir / "runtime" / "__init__.py"),
    ]

    # runtime/lib — shared hook libraries; direct-entry hooks resolve
    # runtime.lib relative to the plugin root, so the installed tree must
    # carry them (with .ds-source-root as the repo-import fallback).
    lib_src_dir = source_root / "runtime" / "lib"
    if lib_src_dir.is_dir():
        for lib_file in sorted(lib_src_dir.rglob("*.py")):
            if "__pycache__" in lib_file.parts:
                continue
            hook_files.append(
                (lib_file, hooks_dir / "runtime" / "lib" / lib_file.relative_to(lib_src_dir))
            )

    for src, tgt in hook_files:
        if not src.is_file():
            continue
        file_hash = _compute_file_hash_chunked(src)
        try:
            content: str | None = src.read_text(encoding="utf-8")
            src_path: Path | None = None
        except (UnicodeDecodeError, ValueError):
            content = None
            src_path = src
        ops.append(
            FileOp(
                target=tgt,
                op="create",
                backup_required=tgt.exists(),
                source_hash=file_hash,
                source_content=content,
                source_path=src_path,
                reason=f"Install hook script {src.name} to hooks/",
                safety_notes="Additive hook install — part of sidecar resolution chain.",
                backup_path=backup_base if tgt.exists() else None,
            )
        )

    # Handler packs — all .py files (except __init__.py) for every active pack
    # WO-RT: project ALL packs so every handler path resolves inside the installed runtime.
    # Previously only meta/ was projected; quality/, domains/, core/, security/ were missing.
    for pack in ("meta", "quality", "domains", "core", "security"):
        pack_src_dir = source_root / "runtime" / "hooks" / pack
        pack_tgt_dir = hooks_dir / "runtime" / "hooks" / pack
        if not pack_src_dir.is_dir():
            continue
        for handler in sorted(pack_src_dir.glob("*.py")):
            if handler.name == "__init__.py":
                continue
            tgt = pack_tgt_dir / handler.name
            file_hash = _compute_file_hash_chunked(handler)
            handler_content = handler.read_text(encoding="utf-8")
            ops.append(
                FileOp(
                    target=tgt,
                    op="create",
                    backup_required=tgt.exists(),
                    source_hash=file_hash,
                    source_content=handler_content,
                    reason=f"Install {pack} hook handler {handler.name}",
                    safety_notes="Handler for hook event dispatch.",
                    backup_path=backup_base if tgt.exists() else None,
                )
            )

    # .plugin-root — points at the INSTALLED hooks dir (not the repo working tree).
    # WO-RT: changed from str(repo_root) to str(hooks_dir) so _get_plugin_root()
    # in run.py and dispatch/hooks.py resolves handler paths inside the installed
    # runtime. Re-run install after moving the repo or the installed hooks dir.
    sidecar_content = str(hooks_dir) + "\n"
    sidecar_tgt = hooks_dir / ".plugin-root"
    ops.append(
        FileOp(
            target=sidecar_tgt,
            op="create",
            backup_required=False,
            source_hash=_compute_hash(sidecar_content),
            source_content=sidecar_content,
            reason="Write .plugin-root sidecar pointing at the installed hooks dir",
            safety_notes="Overwritten on every install. Re-run install if hooks dir moves.",
        )
    )

    # .ds-source-root — points at the repo working tree for Python lib imports.
    # Handler scripts import from core.*, spool.*, canonical.* etc. which live
    # in the repo. This sidecar lets run.py / dispatch/hooks.py append the repo
    # to sys.path as a secondary entry (after the installed hooks dir), keeping
    # lib resolution separate from handler-file resolution.
    source_root_content = str(repo_root) + "\n"
    source_root_tgt = hooks_dir / ".ds-source-root"
    ops.append(
        FileOp(
            target=source_root_tgt,
            op="create",
            backup_required=False,
            source_hash=_compute_hash(source_root_content),
            source_content=source_root_content,
            reason="Write .ds-source-root sidecar so handlers can import core/* from repo",
            safety_notes="Overwritten on every install. Re-run install if repo moves.",
        )
    )

    # statusline.py — cross-platform status line (replaces statusline-command.sh bash wrapper)
    statusline_src = repo_root / "canonical" / "adapters" / "claude" / "statusline.py"
    if statusline_src.is_file():
        statusline_tgt = hooks_dir / "statusline.py"
        file_hash = _compute_file_hash_chunked(statusline_src)
        statusline_content = statusline_src.read_text(encoding="utf-8")
        ops.append(
            FileOp(
                target=statusline_tgt,
                op="create",
                backup_required=statusline_tgt.exists(),
                source_hash=file_hash,
                source_content=statusline_content,
                reason="Install cross-platform Python status line script",
                safety_notes="Replaces statusline-command.sh bash wrapper. Existing ~/.claude/statusline-command.sh is left in place.",
                backup_path=backup_base if statusline_tgt.exists() else None,
            )
        )

    return ops


def _collect_skill_dir_ops(
    skill_dir: Path,
    target_dir: Path,
    skill_id: str,
    backup_base: Path,
) -> list[FileOp]:
    """Return one FileOp per file in skill_dir, preserving subdirectory structure."""
    from integrations.compiler.claude_code import synthesize_skill_frontmatter

    ops: list[FileOp] = []
    for file_path in sorted(skill_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(skill_dir)
        target = target_dir / rel
        file_hash = _compute_file_hash_chunked(file_path)
        try:
            source_content: str | None = file_path.read_text(encoding="utf-8")
            source_path: Path | None = None
        except (UnicodeDecodeError, ValueError):
            source_content = None
            source_path = file_path
        # WO-AUTOACT-A: prepend synthesized description frontmatter to the
        # top-level SKILL.md so Claude Code's native skill auto-invoker has a
        # when-to-use description + trigger anchors to match. Canonical SKILL.md
        # ships frontmatter-less (single source = packs.yaml + metadata.yml);
        # mode SKILL.md files are left untouched (only the pack skill auto-invokes).
        if (
            source_content is not None
            and rel.as_posix() == "SKILL.md"
            and not source_content.lstrip().startswith("---")
        ):
            _fm = synthesize_skill_frontmatter(skill_id)
            if _fm:
                source_content = _fm + source_content
                # Re-hash the prepended content so change-detection rewrites an
                # already-installed SKILL.md (whose stored hash is the canonical,
                # frontmatter-less file) instead of skipping it (WO-AUTOACT-A-FIX).
                file_hash = hashlib.sha256(source_content.encode("utf-8")).hexdigest()
        ops.append(
            FileOp(
                target=target,
                op="create",
                backup_required=target.exists(),
                source_hash=file_hash,
                source_content=source_content,
                source_path=source_path,
                reason=f"Sync {skill_id}/{rel} to Claude Code skills",
                safety_notes="Full skill directory sync — additive only.",
                backup_path=backup_base if target.exists() else None,
            )
        )
    return ops
