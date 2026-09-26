"""E19 — Skill output contract evals, at scale.

`docs/contracts/skill-contract.md` requires every active skill to declare an
"output contract". A 2026-09-26 inventory pass found 104 skill files, of which
only 4 (via `tests/evals/test_skill_contract_evals.py`) had ANY behavioral
output-contract test; the rest were untested. That inventory grouped the
skills with a real, checkable backing capability by WHICH capability they
share, since several unrelated-looking skills call the exact same function --
testing that function once, thoroughly, against real fixtures covers all of
them, rather than writing near-duplicate tests per skill.

This file follows PR #762's precedent (`instruction_commands`'s "resolve real
things, don't pattern-match prose"): every test here imports and calls the
REAL function or shells the REAL script/CLI command a skill names, against a
REAL fixture, and asserts on what actually comes back -- never a lexical check
that the skill's prose merely mentions an output section.

  detect_stack cluster — control.analysis.stacks.detector_core.detect_stack(),
  which 6 skills' audit modes call directly and dispatch on:
    fullstack:backend/audit    — .web_framework
    fullstack:frontend/audit   — .frontend_framework
    code-health:architecture/audit — .architecture_framework / .monorepo_type
    code-health:testing/audit  — .test_framework
    quality:types-deps/audit   — (stack-general; see its own SKILL.md)
    release:ops/audit          — .has_dockerfile / .has_docker_compose / .has_k8s_manifest / .is_service
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from control.analysis.stacks.detector_core import detect_stack
from core.files import store
from interfaces.cli.ds_files import cmd_files_read, cmd_files_write


def _write(path: Path, name: str, content: str) -> None:
    (path / name).write_text(content, encoding="utf-8")


# ── detect_stack cluster ─────────────────────────────────────────────────────


def test_detect_stack_web_framework_from_requirements_txt(tmp_path: Path) -> None:
    """fullstack:backend/audit dispatches on detect_stack().web_framework --
    verified against the exact SKILL.md wording ("Detect API framework from
    detect_stack().web_framework signal")."""
    _write(tmp_path, "requirements.txt", "fastapi==0.110.0\nuvicorn==0.27.0\n")
    result = detect_stack(tmp_path)
    assert result.web_framework == "fastapi"
    assert result.adapter == "python"


def test_detect_stack_web_framework_from_pyproject_poetry(tmp_path: Path) -> None:
    """The same signal, via the OTHER dependency-declaration path the detector
    reads (pyproject.toml/poetry) -- a skill relying on this signal must see
    it regardless of which dependency file the target project actually uses."""
    _write(
        tmp_path,
        "pyproject.toml",
        '[tool.poetry.dependencies]\npython = "^3.12"\nflask = "^3.0"\n',
    )
    result = detect_stack(tmp_path)
    assert result.web_framework == "flask"


def test_detect_stack_frontend_framework_from_package_json(tmp_path: Path) -> None:
    """fullstack:frontend/audit dispatches on detect_stack().frontend_framework."""
    _write(
        tmp_path,
        "package.json",
        '{"name": "x", "dependencies": {"react": "^18.0.0", "react-dom": "^18.0.0"}}',
    )
    result = detect_stack(tmp_path)
    assert result.frontend_framework == "react"
    assert result.adapter == "node"


def test_detect_stack_architecture_framework_from_nestjs(tmp_path: Path) -> None:
    """code-health:architecture/audit reads .architecture_framework for
    NestJS-specific calibration."""
    _write(tmp_path, "package.json", '{"name": "x", "dependencies": {"@nestjs/core": "^10.0.0"}}')
    result = detect_stack(tmp_path)
    assert result.architecture_framework == "nestjs"


def test_detect_stack_monorepo_type_from_npm_workspaces(tmp_path: Path) -> None:
    """code-health:architecture/audit also reads .monorepo_type -- a distinct
    field from architecture_framework, and both are real, independently
    triggerable signals, not the same detection collapsed into one name."""
    _write(tmp_path, "package.json", '{"name": "x", "workspaces": ["packages/*"]}')
    result = detect_stack(tmp_path)
    assert result.monorepo_type == "npm-workspaces"


def test_detect_stack_test_framework_from_pytest_ini(tmp_path: Path) -> None:
    """code-health:testing/audit dispatches its coverage-parser choice on
    .test_framework."""
    _write(tmp_path, "pytest.ini", "[pytest]\n")
    _write(tmp_path, "requirements.txt", "pytest==8.0.0\n")
    result = detect_stack(tmp_path)
    assert result.test_framework == "pytest"


def test_detect_stack_ops_signals_from_dockerfile(tmp_path: Path) -> None:
    """release:ops/audit's SKILL.md conditions ops-012/ops-013 findings on
    .has_dockerfile/.has_docker_compose/.has_k8s_manifest/.is_service."""
    _write(tmp_path, "Dockerfile", 'FROM python:3.12-slim\nCMD ["python", "app.py"]\n')
    _write(tmp_path, "docker-compose.yml", "services:\n  web:\n    build: .\n")
    result = detect_stack(tmp_path)
    assert result.has_dockerfile is True
    assert result.has_docker_compose is True


def test_detect_stack_returns_none_signals_for_an_empty_project(tmp_path: Path) -> None:
    """Every field this cluster's skills dispatch on must default to None/False
    for a project with no matching signal -- a skill reading a stale or
    over-eager default would misfire on every project that ISN'T its target
    stack, which is a much larger failure surface than the true-positive case
    every other test here checks."""
    result = detect_stack(tmp_path)
    assert result.web_framework is None
    assert result.frontend_framework is None
    assert result.architecture_framework is None
    assert result.monorepo_type is None
    assert result.test_framework is None
    assert result.has_dockerfile is False
    assert result.has_docker_compose is False


# ── ds_files write/read cluster ──────────────────────────────────────────────
#
# The underlying mechanism (core.files.store + ds files write/read) already has
# its own dedicated test file (tests/unit/test_ds_files_write_read.py) covering
# roundtrip, stdin input, and the "planning" category generically with bare
# filenames. What that file does NOT cover -- and what these three skills'
# specific output claims depend on -- is that the HIERARCHICAL name shapes
# those skills actually use (a "specs/<topic>/spec.md" path, an "ADR-NNNN-*"
# path, a bare artifact name like "direction-lock.json") round-trip correctly,
# not just a flat filename.


@pytest.fixture
def files_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "files.db"
    monkeypatch.setattr(store, "files_db_path", lambda: db)
    return db


def _write_args(name: str, content: str | None = None, category: str = "planning"):
    return argparse.Namespace(
        name=name,
        content=content,
        category=category,
        project_id=None,
        content_type=None,
        work_order_id=None,
    )


def _read_args(name: str, version: int | None = None):
    return argparse.Namespace(name=name, project_id=None, version=version)


def test_core_think_writes_a_nested_spec_path(files_db: Path, capsys) -> None:
    """core:think's SKILL.md: `ds files write "specs/<topic>/spec.md"` --
    verifies the docstore treats a slash-bearing logical name as a real,
    distinct, round-trippable key, not a filesystem path it tries to create."""
    name = "specs/auth-redesign/spec.md"
    assert cmd_files_write(_write_args(name, content="# Auth Redesign\n")) == 0
    capsys.readouterr()
    assert cmd_files_read(_read_args(name)) == 0
    assert capsys.readouterr().out == "# Auth Redesign\n"
    assert store.read_file_by_name(name)["category"] == "planning"


def test_core_think_writes_an_adr_path(files_db: Path, capsys) -> None:
    """core:think's other declared output: `ds files write "adr/ADR-NNNN-*.md"`."""
    name = "adr/ADR-0012-use-postgres.md"
    assert cmd_files_write(_write_args(name, content="# ADR-0012\n\nStatus: Accepted\n")) == 0
    capsys.readouterr()
    assert cmd_files_read(_read_args(name)) == 0
    assert capsys.readouterr().out == "# ADR-0012\n\nStatus: Accepted\n"


def test_website_direction_writes_direction_lock_json(files_db: Path, capsys) -> None:
    """website:direction's declared output: `ds files write "direction-lock.json"`."""
    payload = '{"palette": "warm-neutral", "locked_at": "2026-09-26"}'
    assert cmd_files_write(_write_args("direction-lock.json", content=payload)) == 0
    capsys.readouterr()
    assert cmd_files_read(_read_args("direction-lock.json")) == 0
    assert capsys.readouterr().out == payload


def test_fullstack_writes_and_reads_api_contract_json(files_db: Path, capsys) -> None:
    """fullstack (root skill)'s declared output: `ds files read/write
    "api-contract.json"` -- the shared contract the backend/frontend audit
    modes both read to stay in sync."""
    payload = '{"endpoints": [{"path": "/users", "method": "GET"}]}'
    assert cmd_files_write(_write_args("api-contract.json", content=payload)) == 0
    capsys.readouterr()
    assert cmd_files_read(_read_args("api-contract.json")) == 0
    assert capsys.readouterr().out == payload


# ── website:brand's generate-tokens.py ───────────────────────────────────────
#
# A standalone script (not an importable function), invoked as a subprocess by
# design -- its own docstring is the contract: `py scripts/generate-tokens.py
# brand-input.json [--output-dir DIR]`, writing brand-tokens.json (W3C DTCG)
# and brand.css. Zero existing behavioral tests before this.

WEBSITE_SCRIPTS = Path("canonical/skills/website/scripts")


def test_website_brand_generate_tokens_writes_dtcg_json_and_css(tmp_path: Path) -> None:
    import subprocess
    import sys as _sys

    brand_input = tmp_path / "brand-input.json"
    brand_input.write_text(
        '{"colors": {"primary": "#2563eb", "secondary": "#7c3aed"},'
        ' "fonts": {"heading": "Inter", "body": "Inter"}, "spacing_base": 8}',
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            _sys.executable,
            str(WEBSITE_SCRIPTS / "generate-tokens.py"),
            str(brand_input),
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr

    tokens_path = tmp_path / "brand-tokens.json"
    css_path = tmp_path / "brand.css"
    assert tokens_path.is_file()
    assert css_path.is_file()

    import json as _json

    tokens = _json.loads(tokens_path.read_text(encoding="utf-8"))
    assert set(tokens.keys()) >= {"$schema", "primitive", "semantic", "component"}
    css = css_path.read_text(encoding="utf-8")
    assert "--color-" in css, "the primary/secondary colors must produce real CSS custom properties"
