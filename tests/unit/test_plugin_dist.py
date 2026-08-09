"""WO 90a13043: the synthesized plugin artifact is loadable and matches the authoritative
routable skill surface.

The canonical skills ship frontmatter-less, so a raw github-source install can't load them.
build_plugin_dist assembles a real plugin root (synthesized frontmatter + agents + .mcp.json +
manifest) that the marketplace git-subdir source resolves. The skill set is the packs.yaml
ROUTABLE set (the user-facing surface); ds-bootstrap — a passive, non-invocable system
component — is intentionally excluded.
"""

from __future__ import annotations

import json
from pathlib import Path

from integrations.marketplace.plugin_dist import build_plugin_dist, skill_source_dirs
from integrations.marketplace.plugin_manifest import (
    PLUGIN_COMPONENTS,
    skill_ids,
    validate_marketplace_manifest,
    validate_plugin_manifest_component_delivery,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_built_plugin_matches_routable_surface_and_is_loadable(tmp_path: Path):
    out = tmp_path / "plugin"
    build_plugin_dist(out, repo_root=REPO_ROOT)

    # Skill set == the authoritative routable pack surface (packs.yaml), no more, no less.
    built_skills = {p.name for p in (out / "skills").iterdir() if p.is_dir()}
    assert built_skills == set(
        skill_ids()
    ), f"built skills must equal the routable surface; diff={built_skills ^ set(skill_ids())}"

    # ds-bootstrap is a non-routable system component — never shipped as a plugin skill.
    assert "ds-bootstrap" not in built_skills

    # Every skill is loadable: its top SKILL.md carries synthesized YAML frontmatter.
    for skill in built_skills:
        text = (out / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        assert text.lstrip().startswith("---"), f"{skill}/SKILL.md missing frontmatter"
        assert f"name: {skill}" in text, f"{skill}/SKILL.md frontmatter missing its name"

    # Every declared component is delivered at the built plugin root.
    manifest = json.loads((out / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    problems = validate_plugin_manifest_component_delivery(manifest, out)
    assert problems == [], f"undelivered components: {problems}"

    # Agents + MCP payload present.
    assert list((out / "agents").glob("*.md")), "no agent cards materialized"
    assert (out / ".mcp.json").is_file()


def test_bootstrap_is_the_only_routable_exclusion():
    """ds-bootstrap is the sole installed-canonical skill excluded from the routable surface,
    and it declares itself non-invocable — the documented reason it is excluded."""
    source_map = skill_source_dirs()
    assert "ds-bootstrap" not in source_map, "ds-bootstrap must not be a routable plugin skill"
    bootstrap = (REPO_ROOT / "canonical" / "skills" / "ds-bootstrap" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "not user-invocable" in bootstrap.lower()


def test_marketplace_source_is_git_subdir():
    """The committed marketplace resolves the plugin from the synthesized dist/plugin subdir."""
    marketplace = json.loads(
        (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    assert validate_marketplace_manifest(marketplace) == []
    src = marketplace["plugins"][0]["source"]
    assert src["source"] == "git-subdir" and src["path"] == "dist/plugin"


def test_declared_components_are_the_deliverable_set():
    """commands is not declared — Dream Studio ships no top-level commands (skills replace them)."""
    assert "commands" not in PLUGIN_COMPONENTS
    assert set(PLUGIN_COMPONENTS) == {"agents", "skills", ".mcp.json"}


def test_installer_projection_vs_routable_surface_contract():
    """Compare the installer's real directory-scan projection to the routable surface, so a
    new/removed canonical/skills/<dir> is DETECTED (not silently ignored — the T2 gap).

    The two differ only by documented exceptions:
    - dir-scan-only = {ds-bootstrap} — a passive system component, excluded from the surface.
    - routable-only = {ds-website, ds-fullstack} — packs whose sources live under
      canonical/skills/domains/modes/* (not top-level dirs), delivered as standalone skills.
    Any other difference means a canonical/skills change that must be reflected in packs.yaml.
    """
    from integrations.installer.claude_code_installer import _skill_id_from_dir_name

    skills_dir = REPO_ROOT / "canonical" / "skills"
    dir_scan = {
        _skill_id_from_dir_name(d.name)
        for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file()
    }
    routable = set(skill_ids())
    assert dir_scan - routable == {
        "ds-bootstrap"
    }, f"unexpected installed-but-unroutable skill dirs: {dir_scan - routable - {'ds-bootstrap'}}"
    assert routable - dir_scan == {
        "ds-website",
        "ds-fullstack",
    }, f"unexpected routable skills without a top-level dir: {routable - dir_scan}"


def test_build_excludes_bytecode_and_cruft(tmp_path: Path):
    """The synthesized artifact must never carry machine-local/non-reproducible cruft
    (compiled bytecode, caches, OS files) — canonical skill dirs may contain __pycache__."""
    out = tmp_path / "plugin"
    build_plugin_dist(out, repo_root=REPO_ROOT)
    cruft = [
        p.relative_to(out).as_posix()
        for p in out.rglob("*")
        if p.suffix in {".pyc", ".pyo"} or "__pycache__" in p.parts or p.name == ".DS_Store"
    ]
    assert cruft == [], f"synthesized plugin must exclude cruft, found: {cruft}"


def test_pre_push_manifest_includes_dist_freshness_gate():
    """WO-PREPUSH-DIST-FRESH: the committed-dist freshness guard must run in a BLOCKING pre-push
    gate, not only in the full ubuntu suite. #610 edited canonical skills without re-projecting
    dist/plugin; the freshness test lived only in full-ci, so both the pre-push gate and the
    pr-smoke matrix went green while main's full-ci went red. This asserts the guard now fails
    BEFORE merge (pre-push tier)."""
    import yaml

    manifest = yaml.safe_load(
        (REPO_ROOT / "canonical" / "workflows" / "pre-push.yaml").read_text(encoding="utf-8")
    )
    running_gates = [
        g
        for g in manifest["gates"]
        if g.get("tier") == "blocking"
        and any("test_plugin_dist.py" in str(part) for part in g.get("command", []))
    ]
    assert running_gates, (
        "no BLOCKING pre-push gate runs tests/unit/test_plugin_dist.py — a canonical skill edit "
        "that isn't re-projected into dist/plugin would pass pre-push and only fail full-ci"
    )


def test_pr_smoke_runs_dist_freshness():
    """The pr-smoke matrix (merge-authorization) must also run the dist freshness test, so a stale
    dist/plugin fails on all three platforms at PR time rather than post-merge in full-ci."""
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert (
        "tests/unit/test_plugin_dist.py" in ci
    ), "pr-smoke focused smoke tests must include tests/unit/test_plugin_dist.py"


def test_committed_dist_plugin_is_fresh(tmp_path: Path):
    """The tracked dist/plugin artifact (what the marketplace git-subdir source serves) must
    equal a fresh build — else a canonical edit ships a stale public plugin. Compares text via
    read_text (newline-normalized) so it is CRLF/LF-agnostic across platforms."""
    committed = REPO_ROOT / "dist" / "plugin"
    assert committed.is_dir(), "dist/plugin must be committed (marketplace git-subdir payload)"

    fresh = tmp_path / "plugin"
    build_plugin_dist(fresh, repo_root=REPO_ROOT)

    def _rel_files(root: Path) -> set[str]:
        return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}

    fresh_files, committed_files = _rel_files(fresh), _rel_files(committed)
    assert (
        fresh_files == committed_files
    ), f"dist/plugin is stale — rebuild it. diff={fresh_files ^ committed_files}"
    for rel in sorted(fresh_files):
        c_bytes, f_bytes = (committed / rel).read_bytes(), (fresh / rel).read_bytes()
        if c_bytes == f_bytes:
            continue
        # Text files may differ only by checkout line-ending normalization — compare decoded,
        # newline-agnostic. Binary files (that already failed the byte check) are genuinely stale.
        try:
            c_text = c_bytes.decode("utf-8").replace("\r\n", "\n")
            f_text = f_bytes.decode("utf-8").replace("\r\n", "\n")
        except UnicodeDecodeError:
            raise AssertionError(f"dist/plugin/{rel} is stale (binary mismatch) — rebuild it")
        assert c_text == f_text, f"dist/plugin/{rel} is stale — rebuild it"
