"""Build a synthesized Claude Code plugin artifact from the canonical sources.

WO 90a13043 / WO-REL-PACKAGING follow-up. A github-source marketplace install resolves a
plugin's components (``skills/``, ``agents/``, ``.mcp.json``) relative to the plugin root and
copies files verbatim — it cannot run Dream Studio's install-time frontmatter synthesis. The
canonical skills ship frontmatter-less (single source = ``packs.yaml`` + ``metadata.yml``), so
they are not directly loadable as plugin skills.

This module assembles a self-contained, loadable plugin root by reusing the installer's own
skill-directory synthesis (``_collect_skill_dir_ops`` → ``synthesize_skill_frontmatter``). The
skill set is the **routable pack set** (``skill_ids()`` from ``packs.yaml``) — the authoritative
user-facing surface. ``ds-bootstrap`` is intentionally excluded: it is a passive system
component, not a user-invocable skill (``synthesize_skill_frontmatter`` returns ``None`` for it).

The output layout (plugin root):

    <out>/
      .claude-plugin/plugin.json   # build_plugin_manifest()
      skills/<skill-id>/SKILL.md    # synthesized frontmatter + canonical body (+ mode files)
      agents/<agent>.md
      .mcp.json
"""

from __future__ import annotations

from pathlib import Path

from integrations.marketplace.plugin_manifest import build_plugin_manifest, skill_ids

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parent.parent.parent


def skill_source_dirs(
    *, canonical_root: Path | None = None, packs_yaml_path: Path | None = None
) -> dict[str, Path]:
    """Map each routable skill id to its canonical source directory.

    A pack's source is its ``skill_path`` (e.g. ``ds-website`` →
    ``canonical/skills/domains/modes/website``) when declared, else
    ``canonical/skills/<pack-key>``. Only routable packs (the ``skill_ids()`` set) are mapped.
    """
    import yaml

    repo_root = canonical_root.parent if canonical_root else _REPO_ROOT
    canonical_root = canonical_root or (_REPO_ROOT / "canonical")
    packs = packs_yaml_path or (repo_root / "packs.yaml")
    data = yaml.safe_load(packs.read_text(encoding="utf-8")) or {}
    routable = set(skill_ids(packs))
    out: dict[str, Path] = {}
    for key, cfg in (data.get("packs") or {}).items():
        if not isinstance(cfg, dict):
            continue
        sid = cfg.get("skill", key)
        if not sid.startswith("ds-"):
            sid = f"ds-{sid}"
        if sid not in routable:
            continue
        skill_path = cfg.get("skill_path")
        src = (repo_root / skill_path) if skill_path else (canonical_root / "skills" / key)
        out[sid] = src
    return out


def _normalize_pack_frontmatter(skill_id: str, skill_md: Path) -> None:
    """Ensure the built top SKILL.md carries the synthesized PACK frontmatter (``name: <id>``).

    Most pack SKILL.md files ship frontmatter-less (``_collect_skill_dir_ops`` already prepended
    the synthesized block). But the website/fullstack packs live under ``domains/modes/*`` and
    ship MODE-level frontmatter (``skill_id: ds-domains, mode: …``); as standalone plugin skills
    they need pack frontmatter. Replace any leading frontmatter block that isn't already this
    skill's pack frontmatter with the synthesized one.
    """
    from integrations.compiler.claude_code import synthesize_skill_frontmatter

    text = skill_md.read_text(encoding="utf-8")
    has_frontmatter = text.lstrip().startswith("---")
    leading_block = text.split("---", 2)[1] if has_frontmatter else ""
    if f"name: {skill_id}" in leading_block:
        return  # already the correct pack frontmatter
    fm = synthesize_skill_frontmatter(skill_id)
    if not fm:
        return  # non-routable (e.g. ds-bootstrap) — never reached for the routable set
    if has_frontmatter:
        # Strip the existing (mode-level) frontmatter block: everything through the 2nd '---'.
        parts = text.split("---", 2)
        body = parts[2].lstrip("\n") if len(parts) == 3 else text
    else:
        body = text
    skill_md.write_text(fm + body, encoding="utf-8")


def build_plugin_dist(
    out_dir: Path,
    *,
    canonical_root: Path | None = None,
    repo_root: Path | None = None,
) -> list[Path]:
    """Assemble the synthesized plugin root under *out_dir*. Returns the written paths.

    Idempotent: *out_dir* is fully rebuilt from the canonical sources each call.
    """
    import json
    import shutil

    from integrations.installer.claude_code_fileops import _collect_skill_dir_ops

    repo_root = repo_root or _REPO_ROOT
    canonical_root = canonical_root or (repo_root / "canonical")
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def _materialize(op) -> None:
        op.target.parent.mkdir(parents=True, exist_ok=True)
        if op.source_content is not None:
            op.target.write_text(op.source_content, encoding="utf-8")
        elif op.source_path is not None:
            shutil.copyfile(op.source_path, op.target)
        written.append(op.target)

    # 1. Skills — the routable pack set, with synthesized frontmatter on each top SKILL.md.
    sources = skill_source_dirs(
        canonical_root=canonical_root, packs_yaml_path=repo_root / "packs.yaml"
    )
    for skill_id, skill_dir in sorted(sources.items()):
        if not (skill_dir / "SKILL.md").is_file():
            continue
        target_dir = out_dir / "skills" / skill_id
        for op in _collect_skill_dir_ops(skill_dir, target_dir, skill_id, out_dir / ".backups"):
            _materialize(op)
        _normalize_pack_frontmatter(skill_id, target_dir / "SKILL.md")

    # 2. Agents — copy every canonical agent card verbatim.
    agents_src = canonical_root / "agents"
    if agents_src.is_dir():
        for agent_md in sorted(agents_src.glob("*.md")):
            target = out_dir / "agents" / agent_md.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(agent_md, target)
            written.append(target)

    # 3. .mcp.json — copy the repo-root MCP server map.
    mcp_src = repo_root / ".mcp.json"
    if mcp_src.is_file():
        target = out_dir / ".mcp.json"
        shutil.copyfile(mcp_src, target)
        written.append(target)

    # 4. Plugin manifest at the plugin root.
    manifest_dir = out_dir / ".claude-plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "plugin.json"
    manifest_path.write_text(
        json.dumps(build_plugin_manifest(repo_root / "packs.yaml"), indent=2) + "\n",
        encoding="utf-8",
    )
    written.append(manifest_path)

    return written
