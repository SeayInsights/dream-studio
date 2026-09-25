"""The apps pack split (PR #817) moved on-game-validate.py's hook file from
runtime/hooks/domains/ to runtime/hooks/apps/ and updated three of the (at
least) five call sites that separately name which packs own real hook
handler files, missing runtime_preflight.py's HOOK_PACKS and
setup_diagnostics.py's projection-completeness check -- neither had a test.

This computes the real set from the filesystem and checks every such site
against it, so the next pack split that relocates a hook fails loudly at
whichever site it misses, instead of silently regressing sync, uninstall,
the doctor freshness manifest, or the runtime preflight handler check.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_ROOT = REPO_ROOT / "runtime" / "hooks"


def _real_hook_pack_dirs() -> set[str]:
    """Subdirs of runtime/hooks/ that actually hold a handler .py file.

    Excludes native (Rust) helper dirs like enforce-native/enqueue-native,
    which hold no .py handlers and are not pack names.
    """
    return {
        entry.name for entry in HOOKS_ROOT.iterdir() if entry.is_dir() and any(entry.glob("*.py"))
    }


def test_setup_hooks_sync_covers_every_hook_owning_pack():
    from interfaces.cli.setup_hooks import SYNC_HOOK_PACKS

    real = _real_hook_pack_dirs()
    missing = real - set(SYNC_HOOK_PACKS)
    assert not missing, f"step_sync_hook_projection never copies: {missing}"


def test_setup_hooks_uninstall_tracks_pack_split_moves():
    """step_uninstall has never removed runtime/hooks/meta/'s projection --
    true since this module's first commit, and meta hooks never move between
    packs, so that gap is pre-existing and out of scope here. This guards
    only the part a pack split can actually break: a pack that a mode's hook
    moved OUT of must not linger, and one it moved INTO must be covered."""
    from interfaces.cli.setup_hooks import UNINSTALL_HOOK_PACKS

    assert "domains" not in UNINSTALL_HOOK_PACKS
    assert "apps" in UNINSTALL_HOOK_PACKS


def test_doctor_freshness_manifest_covers_every_hook_owning_pack():
    from core.health.doctor_shared import _PROJECTED_HOOK_SUBDIRS

    real = _real_hook_pack_dirs()
    missing = real - set(_PROJECTED_HOOK_SUBDIRS)
    assert not missing, f"doctor freshness manifest never tracks: {missing}"


def test_runtime_preflight_hook_packs_covers_every_hook_owning_pack():
    from interfaces.cli.runtime_preflight import HOOK_PACKS

    real = _real_hook_pack_dirs()
    missing = real - set(HOOK_PACKS)
    assert not missing, f"runtime preflight would report handlers under {missing} as missing"


def test_setup_diagnostics_expected_subdirs_covers_every_hook_owning_pack():
    import inspect

    from interfaces.cli import setup_diagnostics

    src = inspect.getsource(setup_diagnostics._projection_completeness_report)
    assert "SYNC_HOOK_PACKS" in src, (
        "expected_subdirs should reuse setup_hooks.SYNC_HOOK_PACKS rather than "
        "a second hardcoded pack tuple that can drift independently"
    )


def test_a_pack_with_no_hook_content_is_named_nowhere():
    """domains/ is now an empty leftover dir -- not a regression, but every
    site should agree it owns no handler files, so no test should expect it
    to be listed."""
    from core.health.doctor_shared import _PROJECTED_HOOK_SUBDIRS
    from interfaces.cli.runtime_preflight import HOOK_PACKS
    from interfaces.cli.setup_hooks import SYNC_HOOK_PACKS, UNINSTALL_HOOK_PACKS

    real = _real_hook_pack_dirs()
    assert "domains" not in real
    for name, packs in (
        ("SYNC_HOOK_PACKS", SYNC_HOOK_PACKS),
        ("UNINSTALL_HOOK_PACKS", UNINSTALL_HOOK_PACKS),
        ("_PROJECTED_HOOK_SUBDIRS", _PROJECTED_HOOK_SUBDIRS),
        ("HOOK_PACKS", HOOK_PACKS),
    ):
        assert "domains" not in packs, f"{name} still lists domains, which owns no hook file"
