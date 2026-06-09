"""Regression test: PACK_SKILL_DIRS paths must resolve to existing directories."""

from pathlib import Path


def test_pack_skill_dirs_paths_resolve():
    """Each PACK_SKILL_DIRS path must resolve to an existing directory."""
    from control.skills.completion import PACK_SKILL_DIRS

    repo_root = Path(__file__).resolve().parent.parent.parent
    for pack, rel_path in PACK_SKILL_DIRS.items():
        full_path = repo_root / rel_path
        assert full_path.is_dir(), f"{pack} → {rel_path} does not exist"
