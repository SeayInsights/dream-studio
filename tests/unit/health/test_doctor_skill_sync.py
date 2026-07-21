"""B.1 — Skill-sync drift detection tests.

Exercises the helpers added to `core/health/doctor.py` that back the pre-push
skill-sync gate:

  * _compute_directory_hash       — stable, content-sensitive
  * _check_skill_freshness        — detects content drift vs canonical
  * _check_pack_mode_coverage     — flags packs.yaml modes missing from install
  * _check_routing_trigger_coverage — flags metadata triggers absent from CLAUDE.md
  * _check_enforcement_block_no_cli — A4/A5 regression guard
  * _check_skills_installed       — composite return shape stays backward-compatible

The tests use hermetic tmp_path fixtures — no reads of the operator's real
~/.claude install.
"""

from __future__ import annotations

from pathlib import Path

from core.health.doctor import (
    _check_enforcement_block_no_cli,
    _check_pack_mode_coverage,
    _check_routing_trigger_coverage,
    _check_skill_freshness,
    _check_skills_installed,
    _compute_directory_hash,
)

# ── _compute_directory_hash ───────────────────────────────────────────────────


def test_directory_hash_is_stable_for_same_content(tmp_path: Path) -> None:
    a = tmp_path / "a"
    a.mkdir()
    (a / "SKILL.md").write_text("alpha", encoding="utf-8")
    (a / "notes.md").write_text("hello", encoding="utf-8")
    b = tmp_path / "b"
    b.mkdir()
    (b / "SKILL.md").write_text("alpha", encoding="utf-8")
    (b / "notes.md").write_text("hello", encoding="utf-8")
    assert _compute_directory_hash(a) == _compute_directory_hash(b)


def test_directory_hash_detects_content_change(tmp_path: Path) -> None:
    d = tmp_path / "d"
    d.mkdir()
    (d / "SKILL.md").write_text("alpha", encoding="utf-8")
    before = _compute_directory_hash(d)
    (d / "SKILL.md").write_text("beta", encoding="utf-8")
    assert _compute_directory_hash(d) != before


def test_directory_hash_ignores_cache_dirs(tmp_path: Path) -> None:
    d = tmp_path / "d"
    d.mkdir()
    (d / "SKILL.md").write_text("alpha", encoding="utf-8")
    before = _compute_directory_hash(d)
    cache = d / "__pycache__"
    cache.mkdir()
    (cache / "x.pyc").write_bytes(b"\x00\x01\x02")
    hidden = d / ".pytest_cache"
    hidden.mkdir()
    (hidden / "junk").write_text("noise", encoding="utf-8")
    assert _compute_directory_hash(d) == before


def test_directory_hash_returns_empty_for_missing_path(tmp_path: Path) -> None:
    assert _compute_directory_hash(tmp_path / "does-not-exist") == ""


# ── _check_skill_freshness ────────────────────────────────────────────────────


def _make_skill(root: Path, name: str, content: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


def test_skill_freshness_clean(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical" / "skills"
    installed = tmp_path / "installed" / "skills"
    _make_skill(canonical, "ds-alpha", "v1")
    _make_skill(installed, "ds-alpha", "v1")
    assert _check_skill_freshness(canonical, installed, ["ds-alpha"]) == []


def test_skill_freshness_detects_stale(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical" / "skills"
    installed = tmp_path / "installed" / "skills"
    _make_skill(canonical, "ds-alpha", "v2-source")
    _make_skill(installed, "ds-alpha", "v1-installed")
    assert _check_skill_freshness(canonical, installed, ["ds-alpha"]) == ["ds-alpha"]


def test_skill_freshness_resolves_bare_pack_key(tmp_path: Path) -> None:
    """Canonical lives under bare key (`core`), install under prefixed id (`ds-core`)."""
    canonical = tmp_path / "canonical" / "skills"
    installed = tmp_path / "installed" / "skills"
    _make_skill(canonical, "core", "v1")
    _make_skill(installed, "ds-core", "v1")
    assert _check_skill_freshness(canonical, installed, ["ds-core"]) == []


def test_skill_freshness_ignores_synthesized_frontmatter(tmp_path: Path) -> None:
    """WO-DOCTOR-DRIFT: the installer prepends synthesized frontmatter to a routable
    pack's top-level SKILL.md, so a raw canonical-vs-installed hash always diverges —
    a permanent false 'stale'. The freshness check must apply the same synthesis to
    the canonical side, so a correctly-installed skill compares equal while genuine
    body drift still flags."""
    from integrations.compiler.claude_code import synthesize_skill_frontmatter

    # doctor derives canonical_root = <skills>/.. and packs = <skills>/../../packs.yaml
    (tmp_path / "packs.yaml").write_text(
        "packs:\n  foo:\n    skill: ds-foo\n    description: Foo pack for tests\n    modes: []\n",
        encoding="utf-8",
    )
    canonical = tmp_path / "canonical" / "skills"
    installed = tmp_path / "installed" / "skills"
    body = "# Foo\n\nCanonical body, no frontmatter.\n"
    _make_skill(canonical, "foo", body)  # canonical dir is the bare pack key

    frontmatter = synthesize_skill_frontmatter(
        "ds-foo", canonical_root=tmp_path / "canonical", packs_yaml_path=tmp_path / "packs.yaml"
    )
    assert frontmatter, "test precondition: ds-foo must be a routable pack that synthesizes"
    _make_skill(installed, "ds-foo", frontmatter + body)  # what the installer writes

    # Not stale: installed == canonical-with-synthesized-frontmatter.
    assert _check_skill_freshness(canonical, installed, ["ds-foo"]) == []

    # Genuine body drift is still caught.
    (installed / "ds-foo" / "SKILL.md").write_text(
        frontmatter + body + "\nDrifted extra line.\n", encoding="utf-8"
    )
    assert _check_skill_freshness(canonical, installed, ["ds-foo"]) == ["ds-foo"]


# ── _check_pack_mode_coverage ─────────────────────────────────────────────────


def test_pack_mode_coverage_clean(tmp_path: Path) -> None:
    packs = tmp_path / "packs.yaml"
    packs.write_text(
        "packs:\n  alpha:\n    skill: alpha\n    modes: [foo, bar]\n", encoding="utf-8"
    )
    installed = tmp_path / "skills"
    for mode in ("foo", "bar"):
        (installed / "ds-alpha" / "modes" / mode).mkdir(parents=True)
    assert _check_pack_mode_coverage(packs, installed) == []


def test_pack_mode_coverage_flags_missing(tmp_path: Path) -> None:
    packs = tmp_path / "packs.yaml"
    packs.write_text(
        "packs:\n  alpha:\n    skill: alpha\n    modes: [foo, bar, baz]\n",
        encoding="utf-8",
    )
    installed = tmp_path / "skills"
    (installed / "ds-alpha" / "modes" / "foo").mkdir(parents=True)
    assert sorted(_check_pack_mode_coverage(packs, installed)) == ["alpha:bar", "alpha:baz"]


def test_pack_mode_coverage_skill_path_aware(tmp_path: Path) -> None:
    """WO-DOCTOR-DRIFT: a pack with skill_path (website/fullstack) installs its modes
    nested under the owning pack (ds-domains/modes/<sub>/modes/<mode>), NOT under
    ds-<pack>/modes. The coverage check must resolve that from skill_path or it
    false-flags every such mode as missing."""
    packs = tmp_path / "packs.yaml"
    packs.write_text(
        "packs:\n"
        "  web:\n"
        "    skill: ds-web\n"
        "    skill_path: canonical/skills/domains/modes/web\n"
        "    modes: [discover, page]\n",
        encoding="utf-8",
    )
    installed = tmp_path / "skills"
    # Modes live under the skill_path-derived location, not ds-web/modes.
    for mode in ("discover", "page"):
        (installed / "ds-domains" / "modes" / "web" / "modes" / mode).mkdir(parents=True)
    # The naive ds-web/modes location does not exist at all.
    assert not (installed / "ds-web").exists()
    assert _check_pack_mode_coverage(packs, installed) == []

    # A genuinely-absent mode is still flagged.
    packs.write_text(
        "packs:\n"
        "  web:\n"
        "    skill: ds-web\n"
        "    skill_path: canonical/skills/domains/modes/web\n"
        "    modes: [discover, page, missing]\n",
        encoding="utf-8",
    )
    assert _check_pack_mode_coverage(packs, installed) == ["web:missing"]


# ── _check_routing_trigger_coverage ───────────────────────────────────────────


def _write_routing_block(claude_md: Path, body: str) -> None:
    claude_md.write_text(
        "# Header\n\n<!-- BEGIN AUTO-ROUTING -->\n" + body + "\n<!-- END AUTO-ROUTING -->\n",
        encoding="utf-8",
    )


def test_routing_trigger_coverage_clean(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical" / "skills"
    md_path = canonical / "alpha" / "modes" / "x" / "metadata.yml"
    md_path.parent.mkdir(parents=True)
    md_path.write_text("triggers: [foo, bar]\n", encoding="utf-8")
    claude_md = tmp_path / "CLAUDE.md"
    _write_routing_block(claude_md, "**x:** foo:, bar:")
    assert _check_routing_trigger_coverage(canonical, claude_md) == []


def test_routing_trigger_coverage_flags_unrouted(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical" / "skills"
    md_path = canonical / "alpha" / "modes" / "x" / "metadata.yml"
    md_path.parent.mkdir(parents=True)
    md_path.write_text("triggers: [foo, bar, missing]\n", encoding="utf-8")
    claude_md = tmp_path / "CLAUDE.md"
    _write_routing_block(claude_md, "**x:** foo:, bar:")
    assert _check_routing_trigger_coverage(canonical, claude_md) == ["missing"]


def test_routing_trigger_coverage_no_block(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical" / "skills"
    md_path = canonical / "alpha" / "modes" / "x" / "metadata.yml"
    md_path.parent.mkdir(parents=True)
    md_path.write_text("triggers: [foo]\n", encoding="utf-8")
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# No routing markers\n", encoding="utf-8")
    assert _check_routing_trigger_coverage(canonical, claude_md) == ["<no-routing-block>"]


def test_routing_trigger_coverage_missing_claude_md(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical" / "skills"
    canonical.mkdir(parents=True)
    assert _check_routing_trigger_coverage(canonical, tmp_path / "missing.md") == [
        "<missing-installed-CLAUDE.md>"
    ]


# ── _check_enforcement_block_no_cli ───────────────────────────────────────────


def test_enforcement_block_has_no_cli_references() -> None:
    """Source _ENFORCEMENT_BLOCK must not contain `py -m interfaces.cli.ds` (A4/A5 invariant)."""
    assert _check_enforcement_block_no_cli() == []


# ── _check_skills_installed composite shape ───────────────────────────────────


def test_check_skills_installed_returns_sync_fields_on_empty_path(tmp_path: Path) -> None:
    """Even when source_root is None, the new fields are present (empty)."""
    result = _check_skills_installed(tmp_path / "claude_dir", source_root=None)
    for field in ("stale", "pack_modes_missing", "triggers_unrouted", "enforcement_block_cli_refs"):
        assert field in result
        assert result[field] == []


def test_check_skills_installed_preserves_legacy_keys(tmp_path: Path) -> None:
    """Existing callers depending on total_expected/installed/missing keep working."""
    claude_dir = tmp_path / "claude_dir"
    (claude_dir / "skills" / "ds-bootstrap").mkdir(parents=True)
    (claude_dir / "skills" / "ds-bootstrap" / "SKILL.md").write_text("x", encoding="utf-8")
    result = _check_skills_installed(claude_dir, source_root=None)
    assert result["total_expected"] == 1
    assert result["installed"] == 1
    assert result["missing"] == []
