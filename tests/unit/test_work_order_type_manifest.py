"""The pack manifest loader for work-order types: what it reads, what it refuses, and when it runs.

Three questions, kept apart.

1. THE SCHEMA. ``packs.<pack>.contributes.work_order_types`` in packs.yaml. Every refusal names the
   file and the pack, and a manifest with one bad entry registers none of its entries.
2. THE CALL SITE. The registry reads the running checkout's manifest lazily, on first use, once,
   with no write at import, an explicit error if it is unreadable, and no dependence on the
   working directory or on which module was imported first.
3. SCOPING. Tests register types without leaving them behind; there is no public unregister.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from core.work_orders import type_manifest, type_registry
from core.work_orders.type_manifest import load_pack_work_order_types
from core.work_orders.type_registry import (
    CODE,
    DOCUMENT,
    PackManifestError,
    builtin_work_order_type_names,
    get_work_order_type,
    register_work_order_type,
    scoped_pack_manifest,
    scoped_registration,
    work_order_type_names,
    work_order_types_in_presentation_order,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

GOOD = """\
schema_version: 2
packs:
  legal:
    skill: legal
    modes: [review]
    contributes:
      work_order_types:
        - name: contract_review
          artifact_class: document
          description: Reviewing a contract or policy for completeness and accuracy
          exempt_from_verification: true
        - name: poster
          artifact_class: code
          ui_bearing: true
          description: A marketing poster that ships a surface
  finance:
    skill: finance
    modes: [close]
    contributes:
      work_order_types:
        - name: month_end_close
          artifact_class: data
          dashboard_truth_gated: true
          description: Closing the books for a month
"""


def _manifest(tmp_path: Path, text: str, name: str = "packs.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ── 1. the schema ─────────────────────────────────────────────────────────────


def test_a_manifest_registers_every_declared_type_with_its_facts(tmp_path):
    path = _manifest(tmp_path, GOOD)
    with scoped_registration():
        loaded = load_pack_work_order_types(packs_yaml_path=path)
        assert [t.name for t in loaded] == ["contract_review", "poster", "month_end_close"]
        review, poster, close = (get_work_order_type(n) for n in [t.name for t in loaded])
        assert review.artifact_class == DOCUMENT and review.exempt_from_verification is True
        assert poster.ui_bearing is True and poster.stales_design_brief is True
        assert close.dashboard_truth_gated is True and close.artifact_class == "data"
        assert review.declared_by == "legal" and close.declared_by == "finance"
        assert review.description.startswith("Reviewing a contract")
        # Pack types follow the built-ins, in manifest order.
        names = [t.name for t in work_order_types_in_presentation_order()]
        assert names[-3:] == ["contract_review", "poster", "month_end_close"]
        assert names[:10] == [
            "ui_component",
            "ui_page",
            "api_endpoint",
            "authentication",
            "saas_feature",
            "data_pipeline",
            "game_mechanic",
            "deployment",
            "infrastructure",
            "documentation",
        ]


def test_a_manifest_with_no_contributes_registers_nothing(tmp_path):
    path = _manifest(tmp_path, "schema_version: 2\npacks:\n  core:\n    modes: [think]\n")
    with scoped_registration():
        assert load_pack_work_order_types(packs_yaml_path=path) == ()
        assert work_order_type_names() == builtin_work_order_type_names()


def test_this_repositorys_own_manifest_declares_no_type():
    """The premise of the byte-identical AGENTS.md claim, checked rather than assumed."""
    with scoped_registration():
        assert load_pack_work_order_types(packs_yaml_path=REPO_ROOT / "packs.yaml") == ()


def _bad(entry: str, *, pack: str = "legal", extra: str = "") -> str:
    return (
        "schema_version: 2\npacks:\n"
        f"  {pack}:\n    skill: x\n    modes: [m]\n    contributes:\n{extra}"
        f"      work_order_types:\n{entry}"
    )


_OK_ENTRY = (
    "        - name: contract_review\n          artifact_class: document\n"
    "          description: A real sentence\n"
)


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        pytest.param(
            _bad(_OK_ENTRY + "          colour: red\n"),
            "unknown key(s) ['colour']",
            id="unknown-key-on-a-type",
        ),
        pytest.param(
            _bad("        - name: a_type\n          description: x\n"),
            "missing required key(s) ['artifact_class']",
            id="missing-artifact-class",
        ),
        pytest.param(
            _bad("        - name: a_type\n          artifact_class: document\n"),
            "missing required key(s) ['description']",
            id="missing-description",
        ),
        pytest.param(
            _bad(_OK_ENTRY.replace("document", "spreadsheet")),
            "unknown artifact class 'spreadsheet'",
            id="bad-class",
        ),
        pytest.param(
            _bad(_OK_ENTRY.replace("contract_review", "Contract-Review")),
            "must be lowercase",
            id="bad-name",
        ),
        pytest.param(
            _bad(_OK_ENTRY + "          ui_bearing: 'yes'\n"),
            "ui_bearing must be a bool",
            id="string-flag",
        ),
        pytest.param(
            _bad(_OK_ENTRY.replace("A real sentence", "has | a pipe")),
            "no '|'",
            id="pipe-in-description",
        ),
        pytest.param(
            _bad(_OK_ENTRY.replace("contract_review", "ui_page")),
            "'ui_page' is a built-in work-order type",
            id="built-in-collision",
        ),
        pytest.param(
            _bad(_OK_ENTRY + _OK_ENTRY),
            "'contract_review' is already declared by pack 'legal'",
            id="duplicate-in-one-pack",
        ),
        pytest.param(
            _bad("        - just a string\n"),
            "work_order_types[0] must be a mapping",
            id="entry-not-a-mapping",
        ),
        pytest.param(
            _bad(_OK_ENTRY, extra="      gates: [x]\n"),
            "unsupported key(s) ['gates']",
            id="contributes-gates-not-read-yet",
        ),
        pytest.param(
            _bad(_OK_ENTRY).replace("schema_version: 2", "schema_version: 1"),
            "needs schema_version 2 or later",
            id="old-schema",
        ),
        pytest.param(
            "schema_version: 2\npacks:\n  legal:\n    contributes:\n      work_order_types: nope\n",
            "'work_order_types' must be a list",
            id="not-a-list",
        ),
    ],
)
def test_a_bad_declaration_is_refused_naming_the_file_and_the_pack(tmp_path, text, needle):
    path = _manifest(tmp_path, text)
    with scoped_registration():
        before = work_order_type_names()
        with pytest.raises(PackManifestError) as exc:
            load_pack_work_order_types(packs_yaml_path=path)
        message = str(exc.value)
        assert needle in message, message
        assert str(path) in message, "the refusal names the file"
        assert "'legal'" in message or "pack" in message
        assert work_order_type_names() == before, "a refused manifest registers nothing"


def test_a_type_two_packs_both_declare_is_refused_naming_both(tmp_path):
    text = GOOD + (
        "  other:\n    skill: o\n    modes: [m]\n    contributes:\n      work_order_types:\n"
        "        - name: poster\n          artifact_class: code\n          description: again\n"
    )
    with scoped_registration():
        with pytest.raises(PackManifestError) as exc:
            load_pack_work_order_types(packs_yaml_path=_manifest(tmp_path, text))
    message = str(exc.value)
    assert "'poster' is already declared by pack 'legal'" in message
    assert "pack 'other'" in message


def test_a_manifest_with_one_bad_entry_registers_none_of_its_entries(tmp_path):
    """Atomic: the good entry that precedes the bad one is not left behind."""
    text = _bad(_OK_ENTRY + _OK_ENTRY.replace("contract_review", "second").replace("document", "x"))
    with scoped_registration():
        with pytest.raises(PackManifestError):
            load_pack_work_order_types(packs_yaml_path=_manifest(tmp_path, text))
        assert get_work_order_type("contract_review") is None


def test_a_name_registered_through_the_api_collides_with_a_manifest_that_declares_it(tmp_path):
    path = _manifest(tmp_path, GOOD)
    with scoped_registration():
        register_work_order_type("poster", artifact_class=CODE)
        with pytest.raises(PackManifestError, match="already registered"):
            load_pack_work_order_types(packs_yaml_path=path)
        assert get_work_order_type("contract_review") is None, "and nothing else was applied"


@pytest.mark.parametrize(
    ("content", "needle"),
    [
        pytest.param(None, "cannot read the pack manifest", id="missing-file"),
        pytest.param("packs: [unclosed", "not valid YAML", id="invalid-yaml"),
        pytest.param("- a\n- list\n", "must be a mapping at the top level", id="top-level-list"),
        pytest.param("packs: nope\n", "'packs' must be a mapping", id="packs-not-a-mapping"),
    ],
)
def test_an_unreadable_or_malformed_manifest_is_an_explicit_error(tmp_path, content, needle):
    path = tmp_path / "packs.yaml"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with scoped_registration():
        with pytest.raises(PackManifestError, match=needle):
            load_pack_work_order_types(packs_yaml_path=path)


def test_a_manifest_can_declare_a_type_the_api_would_refuse_only_through_the_same_checks(tmp_path):
    """The loader registers through the registry's own validation, not a second copy of it: a
    flag combination the API refuses is refused here too."""
    text = _bad(_OK_ENTRY + "          ui_bearing: true\n          stales_design_brief: false\n")
    with scoped_registration():
        with pytest.raises(PackManifestError, match="does not stale the design brief"):
            load_pack_work_order_types(packs_yaml_path=_manifest(tmp_path, text))


# ── 2. the call site ──────────────────────────────────────────────────────────


@pytest.fixture
def new_process(monkeypatch):
    """The registry as a freshly started process has it: built-ins only, manifest not read."""
    builtins = {
        n: t for n, t in type_registry._REGISTRY.items() if n in builtin_work_order_type_names()
    }
    monkeypatch.setattr(type_registry, "_REGISTRY", builtins)
    monkeypatch.setattr(type_registry, "_STATE", {"loaded": False, "loading": False})


def test_the_first_read_applies_the_running_manifest_and_a_second_changes_nothing(
    new_process, tmp_path, monkeypatch
):
    path = _manifest(tmp_path, GOOD)
    monkeypatch.setattr(type_manifest, "default_manifest_path", lambda: path)
    assert type_registry._STATE["loaded"] is False
    assert work_order_type_names()[-3:] == ("contract_review", "poster", "month_end_close")
    assert type_registry._STATE["loaded"] is True
    before = work_order_type_names()
    type_registry.ensure_loaded()
    type_registry.ensure_loaded()
    assert work_order_type_names() == before, "idempotent: no duplicate, no second read"


@pytest.mark.parametrize(
    "reader",
    [
        pytest.param(lambda: work_order_type_names(), id="names"),
        pytest.param(lambda: get_work_order_type("ui_page"), id="get"),
        pytest.param(lambda: type_registry.artifact_class_for("ui_page"), id="artifact-class"),
        pytest.param(lambda: type_registry.is_ui_bearing("ui_page"), id="ui-bearing"),
        pytest.param(lambda: type_registry.is_verification_exempt("ui_page"), id="exempt"),
        pytest.param(lambda: type_registry.is_dashboard_truth_gated("ui_page"), id="truth"),
        pytest.param(lambda: type_registry.design_brief_staling_types(), id="staling"),
        pytest.param(lambda: work_order_types_in_presentation_order(), id="presentation"),
        pytest.param(
            lambda: register_work_order_type("fresh_one", artifact_class=CODE), id="register"
        ),
    ],
)
def test_every_reader_loads_the_manifest_before_answering(
    new_process, tmp_path, monkeypatch, reader
):
    """Not only work_order_type_names: a consumer that read `get_work_order_type` first would
    otherwise see the built-ins alone and refuse a pack's type as undeclared."""
    path = _manifest(tmp_path, GOOD)
    monkeypatch.setattr(type_manifest, "default_manifest_path", lambda: path)
    reader()
    assert get_work_order_type("contract_review") is not None


def test_an_unreadable_running_manifest_is_an_explicit_error_on_every_read_until_fixed(
    new_process, tmp_path, monkeypatch
):
    missing = tmp_path / "nowhere" / "packs.yaml"
    monkeypatch.setattr(type_manifest, "default_manifest_path", lambda: missing)
    for _ in range(2):
        with pytest.raises(PackManifestError, match="cannot read the pack manifest"):
            work_order_type_names()
    assert type_registry._STATE["loaded"] is False, "a failed load is not remembered as done"
    _manifest(tmp_path, GOOD, name="fixed.yaml")
    monkeypatch.setattr(type_manifest, "default_manifest_path", lambda: tmp_path / "fixed.yaml")
    assert "contract_review" in work_order_type_names()


def test_a_manifest_that_fails_leaves_the_built_ins_exactly_as_they_were(
    new_process, tmp_path, monkeypatch
):
    bad = _manifest(tmp_path, GOOD + "  broken:\n    contributes:\n      gates: [x]\n")
    monkeypatch.setattr(type_manifest, "default_manifest_path", lambda: bad)
    with pytest.raises(PackManifestError):
        work_order_type_names()
    assert tuple(type_registry._REGISTRY) == builtin_work_order_type_names()


def test_the_default_manifest_is_the_code_roots_packs_yaml():
    """code_root(), not the working directory and not a path walked up from this module: the
    checkout in a checkout, site-packages in an installed app, whose wheel ships packs.yaml at
    the same relative path (pyproject shipped-root-data; test_wheel_runs_without_checkout)."""
    from core.config.paths import code_root

    assert type_manifest.default_manifest_path() == code_root() / "packs.yaml"
    assert type_manifest.default_manifest_path().is_file()


def _run_python(code: str, *, cwd: Path) -> str:
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_importing_the_registry_reads_no_manifest_and_the_first_read_does(tmp_path):
    """No write, and no file read, at import: loaded is False after import and True after a read."""
    out = _run_python(
        "import core.work_orders.type_registry as r;"
        "print(r._STATE['loaded'], len(r._REGISTRY));"
        "r.work_order_type_names();"
        "print(r._STATE['loaded'], len(r._REGISTRY))",
        cwd=tmp_path,
    )
    assert out.splitlines() == ["False 10", "True 10"]


def test_the_answer_does_not_depend_on_the_working_directory(tmp_path):
    """Run from a directory with no packs.yaml and no checkout in it: the manifest is found by
    code_root(), so the answer is the same as from the repository root."""
    code = "from core.work_orders.type_registry import work_order_type_names as n;print(len(n()))"
    assert _run_python(code, cwd=tmp_path) == _run_python(code, cwd=REPO_ROOT) == "10"


def test_concurrent_first_reads_all_succeed_and_load_once(new_process, tmp_path, monkeypatch):
    path = _manifest(tmp_path, GOOD)
    monkeypatch.setattr(type_manifest, "default_manifest_path", lambda: path)
    results: list[object] = []
    barrier = threading.Barrier(8)

    def read() -> None:
        barrier.wait()
        try:
            results.append(work_order_type_names())
        except BaseException as exc:  # noqa: BLE001 - the assertion below names it
            results.append(exc)

    threads = [threading.Thread(target=read) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 8 and all(r == results[0] for r in results), results
    assert results[0][-3:] == ("contract_review", "poster", "month_end_close")


# ── 3. scoping ────────────────────────────────────────────────────────────────


def test_scoped_registration_removes_what_the_block_registered_even_when_it_raises():
    before = work_order_type_names()
    with scoped_registration():
        register_work_order_type("scratch_type", artifact_class=DOCUMENT)
        assert "scratch_type" in work_order_type_names()
    assert work_order_type_names() == before
    with pytest.raises(RuntimeError, match="boom"):
        with scoped_registration():
            register_work_order_type("scratch_type", artifact_class=DOCUMENT)
            raise RuntimeError("boom")
    assert work_order_type_names() == before


def test_there_is_no_public_way_to_unregister():
    """The registry only grows at runtime; a test narrows the process with a scope, never with a
    delete. Nothing named for removal is public."""
    public = [n for n in dir(type_registry) if not n.startswith("_")]
    assert [
        n for n in public if "unregister" in n or n.startswith(("remove", "delete", "clear"))
    ] == []


def test_scoped_pack_manifest_replaces_the_running_manifest_for_the_block_only(tmp_path):
    path = _manifest(tmp_path, GOOD)
    before = work_order_type_names()
    state = dict(type_registry._STATE)
    with scoped_pack_manifest(path):
        assert work_order_type_names() == builtin_work_order_type_names() + (
            "contract_review",
            "poster",
            "month_end_close",
        )
    assert work_order_type_names() == before
    assert type_registry._STATE == state


def test_scoped_pack_manifest_restores_even_when_the_manifest_is_refused(tmp_path):
    path = _manifest(tmp_path, GOOD + "  bad:\n    contributes:\n      gates: [x]\n")
    before = work_order_type_names()
    with pytest.raises(PackManifestError):
        with scoped_pack_manifest(path):
            pass
    assert work_order_type_names() == before
