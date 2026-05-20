"""Skill registry queries — derived from packs.yaml and per-mode config.yml."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_SKILL_FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def _load_packs(source_root: Path) -> dict[str, Any]:
    packs_path = source_root / "packs.yaml"
    if not packs_path.is_file():
        return {}
    try:
        import yaml as _yaml

        data = _yaml.safe_load(packs_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def list_skills(
    *,
    pack_filter: str | None = None,
    source_root: Path,
    dream_studio_home: Path | None = None,  # noqa: ARG001 — kept for handler symmetry
) -> dict[str, Any]:
    """Return the list of all skills (pack:mode) with model preference and duration."""

    packs_data = _load_packs(source_root)
    packs = packs_data.get("packs", {})

    skills: list[dict[str, Any]] = []
    for pack_name, pack_info in packs.items():
        if pack_filter and pack_name != pack_filter:
            continue
        for mode_name in pack_info.get("modes", []):
            _skill_path_key = pack_info.get("skill_path")
            if _skill_path_key:
                skill_md = source_root / _skill_path_key / "modes" / mode_name / "SKILL.md"
            else:
                skill_md = (
                    source_root
                    / "canonical"
                    / "skills"
                    / pack_name
                    / "modes"
                    / mode_name
                    / "SKILL.md"
                )
            config_yml = skill_md.parent / "config.yml"

            model_preference: str | None = None
            estimated_duration = None

            if config_yml.is_file():
                try:
                    import yaml as _yaml

                    config_data = _yaml.safe_load(config_yml.read_text(encoding="utf-8"))
                    if isinstance(config_data, dict):
                        model_preference = config_data.get("model_tier")
                except Exception:
                    pass

            if skill_md.is_file():
                try:
                    import yaml as _yaml

                    text = skill_md.read_text(encoding="utf-8-sig")
                    fm_match = _SKILL_FM_RE.match(text)
                    if fm_match:
                        fm_data = _yaml.safe_load(fm_match.group(1))
                        if isinstance(fm_data, dict):
                            ds_section = fm_data.get("dream_studio", {})
                            if isinstance(ds_section, dict):
                                estimated_duration = ds_section.get("estimated_duration")
                except Exception:
                    pass

            skills.append(
                {
                    "specifier": f"{pack_name}:{mode_name}",
                    "model_preference": model_preference or "sonnet",
                    "estimated_duration": estimated_duration,
                }
            )

    return {"ok": True, "skills": skills}
