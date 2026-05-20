"""Integrity guard for packs.yaml — prevents drift between registry and runtime."""

from __future__ import annotations
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKS_YAML = REPO_ROOT / "packs.yaml"
SKILLS_DIR = REPO_ROOT / "skills"
CANONICAL_SKILLS_DIR = REPO_ROOT / "canonical" / "skills"
PACKS_DIR = REPO_ROOT / "packs"
RUNTIME_HOOKS_DIR = REPO_ROOT / "runtime" / "hooks"


def _find_pack_skills_dir(
    pack_name: str, skill_alias: str = "", skill_path: str = ""
) -> Path | None:
    """Return the skills directory for a pack, checking skill_path, canonical/ then skills/."""
    if skill_path:
        candidate = REPO_ROOT / skill_path
        if candidate.exists():
            return candidate
    for base in (CANONICAL_SKILLS_DIR, SKILLS_DIR):
        candidate = base / pack_name
        if candidate.exists():
            return candidate
        if skill_alias:
            candidate = base / skill_alias
            if candidate.exists():
                return candidate
    return None


def _load_packs() -> dict:
    return yaml.safe_load(PACKS_YAML.read_text(encoding="utf-8"))


def test_packs_yaml_exists():
    assert PACKS_YAML.exists(), "packs.yaml not found at repo root"


def test_security_pack_exists():
    """Prevents Flag 3 recurrence — security pack must always be registered."""
    data = _load_packs()
    assert "security" in data.get(
        "packs", {}
    ), "security pack missing from packs.yaml — Flag 3 recurrence"


def test_mode_dirs_listed_in_packs_yaml():
    """Every directory in skills/{pack}/modes/ must appear in packs.yaml modes:."""
    data = _load_packs()
    packs = data.get("packs", {})
    errors: list[str] = []

    for pack_name, pack_config in packs.items():
        skill_alias = pack_config.get("skill", "")
        pack_dir = _find_pack_skills_dir(pack_name, skill_alias, pack_config.get("skill_path", ""))
        if pack_dir is None:
            continue
        modes_dir = pack_dir / "modes"
        if not modes_dir.exists():
            continue
        registered_modes = set(pack_config.get("modes") or [])
        for mode_dir in modes_dir.iterdir():
            if mode_dir.is_dir():
                if mode_dir.name not in registered_modes:
                    errors.append(
                        f"pack '{pack_name}': mode dir '{mode_dir.name}' "
                        f"not listed in packs.yaml modes:"
                    )

    assert not errors, "\n".join(errors)


def test_packs_yaml_modes_have_dirs():
    """Every mode listed in packs.yaml must have a directory in canonical/skills/ or skills/{pack}/modes/."""
    data = _load_packs()
    packs = data.get("packs", {})
    errors: list[str] = []

    for pack_name, pack_config in packs.items():
        modes = pack_config.get("modes") or []
        if not modes:
            continue
        skill_alias = pack_config.get("skill", "")
        pack_dir = _find_pack_skills_dir(pack_name, skill_alias, pack_config.get("skill_path", ""))
        if pack_dir is None:
            for mode in modes:
                errors.append(
                    f"pack '{pack_name}': no skills directory found in canonical/skills/ or skills/"
                )
            continue
        modes_dir = pack_dir / "modes"
        for mode in modes:
            if not (modes_dir / mode).exists():
                errors.append(
                    f"pack '{pack_name}': mode '{mode}' listed in packs.yaml "
                    f"but directory not found at {modes_dir / mode}"
                )

    assert not errors, "\n".join(errors)


def test_pack_dirs_exist():
    """Every pack in packs.yaml must have a directory in canonical/skills/, skills/, or packs/.
    Checks pack_name first, then the skill alias (e.g. meta uses skill: workflow).
    """
    data = _load_packs()
    packs = data.get("packs", {})
    errors: list[str] = []

    for pack_name, pack_config in packs.items():
        skill_alias = pack_config.get("skill", "")
        in_packs = (PACKS_DIR / pack_name).exists()
        found = (
            in_packs
            or _find_pack_skills_dir(pack_name, skill_alias, pack_config.get("skill_path", ""))
            is not None
        )
        if not found:
            errors.append(
                f"pack '{pack_name}': no directory found in canonical/skills/, skills/, or packs/ "
                f"(skill alias checked: '{skill_alias}')"
            )

    assert not errors, "\n".join(errors)


def test_hooks_listed_in_packs_yaml_exist_as_files():
    """Every hook listed in packs.yaml must have a .py handler in runtime/hooks/{pack}/."""
    data = _load_packs()
    packs = data.get("packs", {})
    errors: list[str] = []

    for pack_name, pack_config in packs.items():
        hooks = pack_config.get("hooks") or []
        if not hooks:
            continue
        hook_dir = RUNTIME_HOOKS_DIR / pack_name
        for hook_name in hooks:
            handler = hook_dir / f"{hook_name}.py"
            if not handler.exists():
                errors.append(
                    f"pack '{pack_name}': hook '{hook_name}' listed in packs.yaml "
                    f"but handler not found at {handler}"
                )

    assert not errors, "\n".join(errors)


def test_no_unlisted_handlers():
    """Every .py handler in runtime/hooks/{pack}/ must be listed in packs.yaml.
    Prevents inverse drift — fixes Flag 5 recurrence.
    """
    data = _load_packs()
    packs = data.get("packs", {})
    errors: list[str] = []

    if not RUNTIME_HOOKS_DIR.exists():
        return

    for pack_dir in RUNTIME_HOOKS_DIR.iterdir():
        if not pack_dir.is_dir():
            continue
        pack_name = pack_dir.name
        if pack_name not in packs:
            continue
        registered = set(packs[pack_name].get("hooks") or [])
        for handler_file in pack_dir.glob("*.py"):
            if handler_file.name == "__init__.py":
                continue
            handler_stem = handler_file.stem
            if handler_stem not in registered:
                errors.append(
                    f"pack '{pack_name}': handler '{handler_stem}.py' exists "
                    f"in runtime/hooks/ but is not listed in packs.yaml"
                )

    assert not errors, "\n".join(errors)
