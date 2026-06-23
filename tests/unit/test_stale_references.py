"""Tests for WS 8c-3: Stale Reference Audit and Fix."""

from __future__ import annotations

import re
from pathlib import Path
from collections.abc import Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_ROOT = REPO_ROOT / "canonical"


def _iter_canonical_files() -> Iterator[Path]:
    for path in CANONICAL_ROOT.rglob("*"):
        if path.is_file():
            yield path


def _read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _collect_stale(pattern: str, exclude_pattern: str | None = None) -> list[tuple[Path, int, str]]:
    hits: list[tuple[Path, int, str]] = []
    regex = re.compile(pattern)
    exc_regex = re.compile(exclude_pattern) if exclude_pattern else None
    for path in _iter_canonical_files():
        content = _read_safe(path)
        for lineno, line in enumerate(content.splitlines(), 1):
            if regex.search(line):
                if exc_regex is None or not exc_regex.search(line):
                    hits.append((path, lineno, line.strip()))
    return hits


# ── Test: no quality:secure skill reference ───────────────────────────────────


def test_no_quality_secure_skill_reference():
    """quality:secure was renamed to quality:pr-security-scan in Slice 7."""
    hits = _collect_stale(r"quality:secure")
    assert hits == [], f"Found stale quality:secure references: {hits}"


def test_no_secure_skill_specifier_in_workflows():
    """Workflow skill: secure must be replaced with skill: pr-security-scan."""
    hits: list[tuple[Path, int, str]] = []
    for path in CANONICAL_ROOT.glob("workflows/*.yaml"):
        content = _read_safe(path)
        for lineno, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if re.match(r"skill:\s*secure\s*$", stripped):
                hits.append((path, lineno, stripped))
    assert hits == [], f"Found stale 'skill: secure' in workflows: {hits}"


# ── Test: no interfaces/adapters references ───────────────────────────────────


def test_no_interfaces_adapters_import():
    """interfaces/adapters was retired in Slice 4."""
    hits = _collect_stale(r"interfaces[/\\]adapters")
    assert hits == [], f"Found stale interfaces/adapters references: {hits}"


# ── Test: no hooks/run.py references ─────────────────────────────────────────


def test_no_hooks_run_py_reference():
    """hooks/run.py was deleted in Slice 3. ~/.claude/hooks/run.py is the installed target (OK)."""
    hits = _collect_stale(r"hooks/run\.py", exclude_pattern=r"~/")
    assert hits == [], f"Found stale hooks/run.py references: {hits}"


# ── Test: no wrong repo name ──────────────────────────────────────────────────


def test_no_builds_dream_studio_without_clean():
    """builds/dream-studio without -clean suffix references the wrong repo."""
    # Match builds/dream-studio NOT followed by -clean
    hits = _collect_stale(r"builds/dream-studio(?!-clean)")
    assert hits == [], f"Found stale builds/dream-studio (non-clean) references: {hits}"


# ── Test: no --set-active flag ────────────────────────────────────────────────


def test_no_set_active_flag():
    """--set-active was removed in Slice 8b."""
    hits = _collect_stale(r"--set-active")
    assert hits == [], f"Found stale --set-active flag references: {hits}"


# ── Test: no repo:skills/ without canonical/ prefix ──────────────────────────


def test_no_repo_skills_without_canonical_prefix():
    """Skills paths should use repo:canonical/skills/ not repo:skills/."""
    hits = _collect_stale(r"repo:skills/")
    assert hits == [], f"Found stale repo:skills/ (missing canonical/) references: {hits}"


# ── Test: audit function is callable and returns list ────────────────────────


def test_audit_function_returns_list_of_findings():
    """The audit scan should return a list (zero findings means passing)."""
    findings: list[tuple[Path, int, str]] = []
    # Patterns with optional per-pattern exclusions: (pattern, exclude_pattern | None)
    patterns = [
        (r"quality:secure", None),
        (r"interfaces[/\\]adapters", None),
        (r"hooks/run\.py", r"~/"),  # ~/.claude/hooks/run.py is the installed target (OK)
        (r"builds/dream-studio(?!-clean)", None),
        (r"--set-active", None),
        (r"repo:skills/", None),
    ]
    for pattern, exclude in patterns:
        findings.extend(_collect_stale(pattern, exclude_pattern=exclude))
    assert isinstance(findings, list)
    assert findings == [], f"Audit found {len(findings)} stale references: {findings[:5]}"


# ── Test: workflow skill specifiers are valid ─────────────────────────────────


def _load_valid_skill_ids() -> set[str]:
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        import yaml as _yaml

        packs_yaml = REPO_ROOT / "packs.yaml"
        data = _yaml.safe_load(packs_yaml.read_text(encoding="utf-8"))
        packs = data.get("packs", {})
        skills: set[str] = set()
        for pack_key, pack_cfg in packs.items():
            # pack keys themselves are valid skill identifiers in workflows
            skills.add(pack_key)
            if isinstance(pack_cfg, dict):
                modes = pack_cfg.get("modes", [])
                skills.update(modes)
                skill_name = pack_cfg.get("skill", "")
                if skill_name:
                    skills.add(skill_name)
        return skills
    except Exception:
        return set()


def test_workflow_skill_specifiers_are_valid():
    """Every skill: field in workflow YAMLs must match a mode or pack in packs.yaml."""
    valid = _load_valid_skill_ids()
    # Also allow workflow-specific orchestration directives
    allowed_extra = {
        "plan",
        "verify",
        "dashboard",
        "pr-security-scan",
        "review",
        "build",
        "think",
        "ship",
        "handoff",
        "recap",
        "explain",
        "debug",
        "audit",
        "coach",
    }
    valid = valid | allowed_extra

    invalid: list[tuple[Path, str, str]] = []
    skill_re = re.compile(r"^\s*skill:\s*(\S+)")
    for path in CANONICAL_ROOT.glob("workflows/*.yaml"):
        content = _read_safe(path)
        for line in content.splitlines():
            # Skip template expressions like skill: "{{params.foo}}"
            if "{{" in line:
                continue
            m = skill_re.match(line)
            if m:
                specifier = m.group(1).strip("\"'")
                if specifier not in valid:
                    invalid.append((path, specifier, line.strip()))

    assert invalid == [], f"Invalid skill specifiers in workflows: {invalid}"
