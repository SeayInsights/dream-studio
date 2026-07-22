"""Doctor skill-sync checks — canonical-vs-installed skill drift detection.

Split out of doctor.py (WO-GF-CORE-HEALTH-SKILLS): the skill-freshness,
pack-mode-coverage, routing-trigger-coverage, and enforcement-block checks
composed by ``_check_skills_installed`` for the pre-push drift gate.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .doctor_shared import _ROUTING_BEGIN, _ROUTING_END, _CLI_REFERENCE_PATTERN


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


def _compute_directory_hash(
    path: Path,
    *,
    transform: Callable[[str, bytes], bytes] | None = None,
) -> str:
    """SHA-256 over the relative paths and bytes of every regular file under ``path``.

    Hidden directories (``.git``, ``.pytest_cache``, ``__pycache__``) are skipped
    so caches and editor scratch files do not flip the hash.

    ``transform`` (when given) is applied to each file's already-CRLF-normalized
    bytes, keyed by its POSIX relative path, before hashing. The skill-freshness
    check uses it to mirror the installer's top-level ``SKILL.md`` frontmatter
    synthesis so a correctly-installed skill is not reported as drifted.
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
            data = file_path.read_bytes().replace(b"\r\n", b"\n")
        except OSError:
            digest.update(b"<unreadable>")
            digest.update(b"\x01")
            continue
        if transform is not None:
            data = transform(rel, data)
        digest.update(data)
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


def _synthesized_skill_transform(
    skill_id: str,
    canonical_root: Path,
    packs_yaml_path: Path,
) -> Callable[[str, bytes], bytes]:
    """Per-file transform mirroring the installer's top-level SKILL.md synthesis.

    The installer (``integrations.installer.claude_code._collect_skill_dir_ops``)
    prepends ``synthesize_skill_frontmatter(skill_id)`` to a routable pack's
    top-level ``SKILL.md`` (only that file, and only when it has no ``---`` block).
    A raw canonical-vs-installed hash therefore always diverges for those skills —
    a permanent false "stale". Applying the same synthesis to the canonical side
    before hashing makes a correctly-installed skill compare equal, while genuine
    body drift, orphan files, or a stale synthesized description still diverge.
    """

    def _transform(rel_posix: str, data: bytes) -> bytes:
        if rel_posix != "SKILL.md":
            return data
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return data
        # The installer only synthesizes when the canonical file is frontmatter-less.
        if text.lstrip().startswith("---"):
            return data
        try:
            from integrations.compiler.claude_code import synthesize_skill_frontmatter

            frontmatter = synthesize_skill_frontmatter(
                skill_id,
                canonical_root=canonical_root,
                packs_yaml_path=packs_yaml_path,
            )
        except Exception:
            return data
        if not frontmatter:
            return data
        return (frontmatter + text).encode("utf-8")

    return _transform


def _check_skill_freshness(
    canonical_skills_dir: Path,
    installed_skills_dir: Path,
    expected_skill_ids: list[str],
) -> list[str]:
    """Return skill ids whose installed copy differs from the expected install.

    "Expected install" is the canonical source with the installer's top-level
    SKILL.md frontmatter synthesis applied (see ``_synthesized_skill_transform``),
    NOT the raw canonical bytes — otherwise every routable pack reads as stale
    because the installer prepends synthesized frontmatter the canonical file lacks.
    """
    canonical_root = canonical_skills_dir.parent
    packs_yaml_path = canonical_skills_dir.parent.parent / "packs.yaml"
    stale: list[str] = []
    for sid in expected_skill_ids:
        source_dir = _resolve_canonical_skill_dir(canonical_skills_dir, sid)
        installed_dir = installed_skills_dir / sid
        if source_dir is None or not installed_dir.is_dir():
            continue
        expected_hash = _compute_directory_hash(
            source_dir,
            transform=_synthesized_skill_transform(sid, canonical_root, packs_yaml_path),
        )
        if expected_hash != _compute_directory_hash(installed_dir):
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
        modes_dir = _installed_modes_dir(installed_skills_dir, skill_id, pack_cfg.get("skill_path"))
        for mode in pack_cfg.get("modes", []) or []:
            if not (modes_dir / mode).is_dir():
                missing.append(f"{pack_key}:{mode}")
    return missing


def _installed_modes_dir(
    installed_skills_dir: Path,
    skill_id: str,
    skill_path: str | None,
) -> Path:
    """Resolve where a pack's modes are installed, honoring packs.yaml ``skill_path``.

    Most packs install at ``<skills>/ds-<pack>/modes``. Packs that declare a
    ``skill_path`` (e.g. website/fullstack → ``canonical/skills/domains/modes/website``)
    are NOT installed as their own top-level skill; their modes live nested under the
    owning pack's install tree (``<skills>/ds-domains/modes/website/modes``). Resolving
    that from the skill_path is what keeps website:*/fullstack:* from reading as missing.
    """
    if skill_path:
        rel = skill_path.replace("\\", "/")
        marker = "canonical/skills/"
        if marker in rel:
            rel = rel.split(marker, 1)[1]
        parts = [p for p in rel.strip("/").split("/") if p]
        if parts:
            parts[0] = parts[0] if parts[0].startswith("ds-") else f"ds-{parts[0]}"
            return installed_skills_dir.joinpath(*parts, "modes")
    return installed_skills_dir / skill_id / "modes"


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
