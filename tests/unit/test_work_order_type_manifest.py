"""The pack manifest loader for work-order types: what it reads, what it refuses, and when it runs.

Five questions, kept apart.

1. THE SCHEMA. ``packs.<pack>.contributes.work_order_types`` in packs.yaml. Every refusal names the
   file and the pack, and a manifest with one bad entry registers none of its entries.
2. GOVERNANCE. A manifest is the pack's own statement about itself, so it can never LOWER how work
   is reviewed: an exemption needs the operator, the flags that switch governance are never
   defaulted, and a name core writes cannot be taken.
3. HOSTILE INPUT. The manifest is untrusted data: bounded, no aliases, no repr() of what it
   contains in a message, and every failure to read it is a PackManifestError naming the file.
4. THE CALL SITE. The registry reads the running checkout's manifest lazily, on first use, once,
   with no write at import, an explicit error if it is unreadable, and no dependence on the
   working directory or on which module was imported first.
5. SCOPING. Tests register types without leaving them behind; there is no public unregister.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from core.work_orders import type_manifest, type_registry
from core.work_orders.type_manifest import (
    governance_profile,
    load_pack_work_order_types,
    read_pack_trust,
)
from core.work_orders.type_registry import (
    CODE,
    DOCUMENT,
    RESERVED_WORK_ORDER_TYPES,
    PackManifestError,
    builtin_work_order_type_names,
    get_work_order_type,
    manifest_changed_since_load,
    register_work_order_type,
    scoped_pack_manifest,
    scoped_registration,
    work_order_type_names,
    work_order_types_in_presentation_order,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The operator allows the legal pack to declare an exemption.
TRUST = frozenset({"legal"})

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
          ui_bearing: false
          exempt_from_verification: true
        - name: poster
          artifact_class: code
          ui_bearing: true
          exempt_from_verification: false
          description: A marketing poster that ships a surface
  finance:
    skill: finance
    modes: [close]
    contributes:
      work_order_types:
        - name: month_end_close
          artifact_class: data
          ui_bearing: false
          exempt_from_verification: false
          dashboard_truth_gated: true
          description: Closing the books for a month
"""


def _manifest(tmp_path: Path, text: str | bytes, name: str = "packs.yaml") -> Path:
    path = tmp_path / name
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def _load(path: Path, **kwargs):
    kwargs.setdefault("trusted", TRUST)
    return load_pack_work_order_types(packs_yaml_path=path, **kwargs)


# ── 1. the schema ─────────────────────────────────────────────────────────────


def test_a_manifest_registers_every_declared_type_with_its_facts(tmp_path):
    path = _manifest(tmp_path, GOOD)
    with scoped_registration():
        loaded = _load(path)
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
        assert _load(path) == ()
        assert work_order_type_names() == builtin_work_order_type_names()


def test_this_repositorys_own_manifest_declares_no_type():
    """The premise of the byte-identical AGENTS.md claim, checked rather than assumed."""
    with scoped_registration():
        assert _load(REPO_ROOT / "packs.yaml") == ()


def _bad(entry: str, *, pack: str = "legal", extra: str = "") -> str:
    return (
        "schema_version: 2\npacks:\n"
        f"  {pack}:\n    skill: x\n    modes: [m]\n    contributes:\n{extra}"
        f"      work_order_types:\n{entry}"
    )


_OK_ENTRY = (
    "        - name: contract_review\n          artifact_class: document\n"
    "          description: A real sentence\n"
    "          ui_bearing: false\n          exempt_from_verification: false\n"
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
            _bad(
                "        - name: a_type\n          description: x\n          ui_bearing: false\n"
                "          exempt_from_verification: false\n"
            ),
            "missing required key(s) ['artifact_class']",
            id="missing-artifact-class",
        ),
        pytest.param(
            _bad(
                "        - name: a_type\n          artifact_class: document\n"
                "          ui_bearing: false\n          exempt_from_verification: false\n"
            ),
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
            _bad(_OK_ENTRY.replace("ui_bearing: false", "ui_bearing: 'yes'")),
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
            _load(path)
        message = str(exc.value)
        assert needle in message, message
        assert str(path) in message, "the refusal names the file"
        assert "'legal'" in message or "pack" in message
        assert work_order_type_names() == before, "a refused manifest registers nothing"


def test_a_type_two_packs_both_declare_is_refused_naming_both(tmp_path):
    text = GOOD + (
        "  other:\n    skill: o\n    modes: [m]\n    contributes:\n      work_order_types:\n"
        "        - name: poster\n          artifact_class: code\n          description: again\n"
        "          ui_bearing: false\n          exempt_from_verification: false\n"
    )
    with scoped_registration():
        with pytest.raises(PackManifestError) as exc:
            _load(_manifest(tmp_path, text))
    message = str(exc.value)
    assert "'poster' is already declared by pack 'legal'" in message
    assert "pack 'other'" in message


def test_a_manifest_with_one_bad_entry_registers_none_of_its_entries(tmp_path):
    """Atomic: the good entry that precedes the bad one is not left behind."""
    text = _bad(_OK_ENTRY + _OK_ENTRY.replace("contract_review", "second").replace("document", "x"))
    with scoped_registration():
        with pytest.raises(PackManifestError):
            _load(_manifest(tmp_path, text))
        assert get_work_order_type("contract_review") is None


def test_a_name_registered_through_the_api_collides_with_a_manifest_that_declares_it(tmp_path):
    path = _manifest(tmp_path, GOOD)
    with scoped_registration():
        register_work_order_type("poster", artifact_class=CODE)
        with pytest.raises(PackManifestError, match="already registered"):
            _load(path)
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
            _load(path)


def test_the_loader_registers_through_the_same_checks_the_api_applies(tmp_path):
    """A flag combination the API refuses is refused here too: one copy of the rules."""
    text = _bad(
        _OK_ENTRY.replace("ui_bearing: false", "ui_bearing: true")
        + "          stales_design_brief: false\n"
    )
    with scoped_registration():
        with pytest.raises(PackManifestError, match="does not stale the design brief"):
            _load(_manifest(tmp_path, text))


def test_a_non_ascii_description_survives_the_round_trip(tmp_path):
    """The manifest is UTF-8, whatever the platform's locale codec is."""
    text = _bad(_OK_ENTRY.replace("A real sentence", "Révision d'un contrat \u2014 clause 3"))
    path = _manifest(tmp_path, text.encode("utf-8"))
    with scoped_registration():
        (declared,) = _load(path)
        assert declared.description == "Révision d'un contrat \u2014 clause 3"


# ── 2. governance ─────────────────────────────────────────────────────────────


def _exempt(pack: str = "legal", name: str = "contract_review", cls: str = "code") -> str:
    return _bad(
        _OK_ENTRY.replace("contract_review", name)
        .replace("document", cls)
        .replace("exempt_from_verification: false", "exempt_from_verification: true"),
        pack=pack,
    )


def test_a_manifest_cannot_exempt_its_own_work_from_independent_review(tmp_path):
    """The attack: declare a code-class type exempt and close code with no independent review.
    Refused unless the operator has allowed that pack by name, outside the manifest."""
    path = _manifest(tmp_path, _exempt())
    with scoped_registration():
        with pytest.raises(PackManifestError) as exc:
            load_pack_work_order_types(packs_yaml_path=path, trusted=frozenset())
        message = str(exc.value)
        assert "exempt_from_verification: true" in message
        assert "no independent review" in message and "'legal'" in message
        assert type_manifest.TRUST_NAME in message, "the message says where the operator allows it"
        assert get_work_order_type("contract_review") is None
        assert _load(path)[0].exempt_from_verification is True, "the allowed pack may"


def test_the_allowance_is_per_pack_not_per_manifest(tmp_path):
    path = _manifest(tmp_path, _exempt(pack="mallory"))
    with scoped_registration():
        with pytest.raises(PackManifestError, match="'mallory'"):
            _load(path)  # TRUST allows 'legal' only


def test_a_pack_cannot_allow_itself(tmp_path):
    """The allowance lives in the operator's home, not in anything a manifest can say: no key
    on the pack or under contributes grants it."""
    for placement in (
        "    exempt_from_verification: [legal]\n",
        "    trusted: true\n",
        "    allow_exempt: [legal]\n",
    ):
        text = _exempt().replace("    skill: x\n", "    skill: x\n" + placement)
        with scoped_registration():
            with pytest.raises(PackManifestError, match="exempt_from_verification: true"):
                load_pack_work_order_types(
                    packs_yaml_path=_manifest(tmp_path, text), trusted=frozenset()
                )
    text = _exempt().replace("    contributes:\n", "    contributes:\n      trust: [legal]\n")
    with scoped_registration():
        with pytest.raises(PackManifestError, match="unsupported key"):
            load_pack_work_order_types(
                packs_yaml_path=_manifest(tmp_path, text), trusted=frozenset()
            )


def test_the_operators_trust_file_is_what_allows_an_exemption(tmp_path):
    path = _manifest(tmp_path, _exempt())
    trust = _manifest(tmp_path, "exempt_from_verification: [legal]\n", name="pack-trust.yaml")
    assert read_pack_trust(trust) == frozenset({"legal"})
    with scoped_registration():
        (declared,) = load_pack_work_order_types(packs_yaml_path=path, trust_path=trust)
        assert declared.exempt_from_verification is True
    absent = tmp_path / "no-such-trust.yaml"
    assert read_pack_trust(absent) == frozenset()
    with scoped_registration():
        with pytest.raises(PackManifestError, match="exempt_from_verification: true"):
            load_pack_work_order_types(packs_yaml_path=path, trust_path=absent)


@pytest.mark.parametrize(
    ("content", "needle"),
    [
        pytest.param("- a\n", "must be a mapping", id="list"),
        pytest.param("everything: [legal]\n", "unknown key", id="unknown-key"),
        pytest.param("exempt_from_verification: legal\n", "must be a list", id="not-a-list"),
        pytest.param("exempt_from_verification: [1]\n", "must be a list", id="not-strings"),
        pytest.param("a: &x [1]\nb: *x\n", "anchor or alias", id="alias"),
    ],
)
def test_a_malformed_trust_file_is_an_error_naming_it_not_an_empty_allowance(
    tmp_path, content, needle
):
    trust = _manifest(tmp_path, content, name="pack-trust.yaml")
    with pytest.raises(PackManifestError, match=needle) as exc:
        read_pack_trust(trust)
    assert str(trust) in str(exc.value)


def test_a_manifest_that_asks_for_no_exemption_loads_whatever_the_trust_file_holds(tmp_path):
    """The trust file is read only when something needs it."""
    path = _manifest(tmp_path, _bad(_OK_ENTRY))
    broken = _manifest(tmp_path, "- not a mapping\n", name="pack-trust.yaml")
    with scoped_registration():
        (declared,) = load_pack_work_order_types(packs_yaml_path=path, trust_path=broken)
        assert declared.exempt_from_verification is False


@pytest.mark.parametrize("omitted", ["ui_bearing", "exempt_from_verification"])
def test_the_flags_that_switch_governance_have_no_default(tmp_path, omitted):
    """A pack that ships a page cannot skip the milestone design audit by saying nothing, and
    one cannot be exempt by omission either: the author must say which, and own the answer."""
    entry = "".join(
        line + "\n" for line in _OK_ENTRY.splitlines() if not line.strip().startswith(omitted)
    )
    with scoped_registration():
        with pytest.raises(PackManifestError) as exc:
            _load(_manifest(tmp_path, _bad(entry)))
    assert f"['{omitted}']" in str(exc.value) and "never defaulted" in str(exc.value)


@pytest.mark.parametrize("name", sorted(RESERVED_WORK_ORDER_TYPES))
def test_a_name_core_writes_cannot_be_declared(tmp_path, name):
    """The hijack: core files `cleanup` itself (and live authorities hold the other three), so a
    pack declaring one as an exempt document type would retroactively change how those existing
    work orders are reviewed. Refused even for a pack the operator trusts."""
    path = _manifest(tmp_path, _exempt(name=name, cls="document"))
    with scoped_registration():
        with pytest.raises(PackManifestError) as exc:
            _load(path)
        message = str(exc.value)
        assert f"{name!r} is reserved" in message and "existing work orders" in message
        assert get_work_order_type(name) is None


@pytest.mark.parametrize("name", sorted(RESERVED_WORK_ORDER_TYPES))
def test_a_reserved_name_is_refused_by_the_api_too(name):
    with scoped_registration():
        with pytest.raises(ValueError, match="is reserved"):
            register_work_order_type(name, artifact_class=DOCUMENT, exempt_from_verification=True)


def test_reserved_names_are_not_built_in_and_each_says_why():
    assert not set(RESERVED_WORK_ORDER_TYPES) & set(builtin_work_order_type_names())
    assert all(len(reason) > 20 for reason in RESERVED_WORK_ORDER_TYPES.values())


def test_the_shipped_manifest_passes_every_governance_rule_and_its_profile_is_pinned():
    """Every type the repository's own packs.yaml declares loads with NO operator allowance (so
    none is exempt), and its governance profile is recorded here, so adding a type to the
    shipped manifest is a reviewed change to this table. It declares none today."""
    with scoped_registration():
        declared = load_pack_work_order_types(
            packs_yaml_path=REPO_ROOT / "packs.yaml", trusted=frozenset()
        )
        profiles = {t.name: governance_profile(t) for t in declared}
    shipped_profiles: dict[str, dict] = {}
    assert profiles == shipped_profiles, (
        "the shipped manifest declares a type this test does not list; add its governance"
        f" profile here: {profiles}"
    )


def test_governance_profile_shows_what_a_class_costs_in_review(tmp_path):
    with scoped_registration():
        _load(_manifest(tmp_path, GOOD))
        review = governance_profile(get_work_order_type("contract_review"))
        poster = governance_profile(get_work_order_type("poster"))
    assert review["review_rules"] < poster["review_rules"], "a document is reviewed more lightly"
    assert review["independent_review_at_close"] is False
    assert poster["independent_review_at_close"] is True and poster["ui_bearing"] is True
    assert poster["declared_by"] == "legal"


# ── 3. hostile input ──────────────────────────────────────────────────────────

_BOMB = (
    "schema_version: 2\n"
    "x0: &a0 [lol, lol, lol, lol, lol, lol, lol, lol, lol]\n"
    + "".join(
        f"x{i}: &a{i} [*a{i - 1}, *a{i - 1}, *a{i - 1}, *a{i - 1}, *a{i - 1}, *a{i - 1}]\n"
        for i in range(1, 9)
    )
    + "packs:\n  p:\n    contributes:\n      work_order_types:\n"
    "        - name: t\n          artifact_class: *a8\n          description: d\n"
    "          ui_bearing: false\n          exempt_from_verification: false\n"
)


def test_an_alias_bomb_is_refused_cheaply_and_the_message_stays_small(tmp_path):
    """Eight levels of aliasing expanded to a ~300 MB error message in 4 s, and one more level
    exhausted memory. Anchors and aliases are refused before anything is composed."""
    path = _manifest(tmp_path, _BOMB)
    assert len(_BOMB) < 2000
    started = time.perf_counter()
    with scoped_registration():
        with pytest.raises(PackManifestError) as exc:
            _load(path)
    assert time.perf_counter() - started < 1.0
    assert "anchor or alias" in str(exc.value) and len(str(exc.value)) < 500


def test_an_anchor_with_no_alias_is_refused_too(tmp_path):
    with scoped_registration():
        with pytest.raises(PackManifestError, match="anchor or alias"):
            _load(_manifest(tmp_path, "schema_version: 2\nx: &a 1\npacks: {}\n"))


def test_an_oversized_manifest_is_refused_before_it_is_read(tmp_path):
    big = _manifest(tmp_path, "# " + "x" * (type_manifest.MAX_MANIFEST_BYTES + 1) + "\n")
    with scoped_registration():
        with pytest.raises(PackManifestError) as exc:
            _load(big)
    assert str(big) in str(exc.value) and "limit" in str(exc.value)


def test_twenty_thousand_declared_types_cost_nothing_because_the_file_is_bounded(tmp_path):
    entry = _OK_ENTRY.replace("contract_review", "t{n}")
    body = "".join(entry.replace("{n}", f"{n:05d}".replace("0", "a")) for n in range(20000))
    path = _manifest(tmp_path, _bad(body))
    started = time.perf_counter()
    with scoped_registration():
        with pytest.raises(PackManifestError):
            _load(path)
    assert time.perf_counter() - started < 2.0


def test_more_than_the_declared_type_limit_is_refused(tmp_path):
    entry = (
        "        - {name: tNAME, artifact_class: code, description: d,"
        " ui_bearing: false, exempt_from_verification: false}\n"
    )
    names = ["t" + "".join(chr(97 + (n // 26**k) % 26) for k in range(4)) for n in range(201)]
    body = "".join(entry.replace("tNAME", name) for name in names)
    path = _manifest(tmp_path, _bad(body))
    assert len(path.read_bytes()) < type_manifest.MAX_MANIFEST_BYTES
    with scoped_registration():
        with pytest.raises(PackManifestError, match="more than 200"):
            _load(path)


def test_deep_nesting_is_refused_not_a_recursion_error(tmp_path):
    """5000 nested flow sequences blew the composer's stack with a raw RecursionError."""
    path = _manifest(tmp_path, "packs: " + "[" * 5000 + "]" * 5000 + "\n")
    with scoped_registration():
        with pytest.raises(PackManifestError) as exc:
            _load(path)
    assert str(path) in str(exc.value) and "nests deeper" in str(exc.value)


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("schema_version: 2\n# caf\xe9\n".encode("cp1252"), id="cp1252"),
        pytest.param("packs: {}\n".encode("utf-16"), id="utf-16"),
        pytest.param(b"\xff\xfe\x00\x00", id="garbage"),
    ],
)
def test_a_manifest_that_is_not_utf8_is_refused_naming_the_file(tmp_path, raw):
    path = _manifest(tmp_path, raw)
    with scoped_registration():
        with pytest.raises(PackManifestError) as exc:
            _load(path)
    assert str(path) in str(exc.value) and "UTF-8" in str(exc.value)


@pytest.mark.parametrize(
    "tag",
    [
        "!!python/object/apply:os.getcwd []",
        "!!python/name:os.system",
        "!!python/object:os.PathLike",
    ],
)
def test_yaml_that_names_a_python_object_is_refused(tmp_path, tag):
    """The manifest is parsed with the safe loader. A mutant using unsafe_load would execute this."""
    path = _manifest(tmp_path, f"schema_version: 2\nx: {tag}\npacks: {{}}\n")
    with scoped_registration():
        with pytest.raises(PackManifestError) as exc:
            _load(path)
    assert str(path) in str(exc.value) and "not valid YAML" in str(exc.value)


def test_a_memory_error_while_parsing_is_a_manifest_error_naming_the_file(tmp_path, monkeypatch):
    import yaml

    def boom(*args, **kwargs):
        raise MemoryError("out of memory")

    monkeypatch.setattr(yaml, "load", boom)
    path = _manifest(tmp_path, "packs: {}\n")
    with pytest.raises(PackManifestError) as exc:
        _load(path)
    assert str(path) in str(exc.value) and "MemoryError" in str(exc.value)


def test_no_message_quotes_a_hostile_value_whole(tmp_path):
    """Every message the loader or the registry builds from manifest data is bounded: a huge
    string, a huge key list, a huge nested structure each cost a short message."""
    huge = "z" * 100000
    cases = [
        _bad(_OK_ENTRY.replace("document", huge)),
        _bad(_OK_ENTRY.replace("contract_review", huge)),
        _bad(_OK_ENTRY.replace("A real sentence", huge)),
        _bad(
            _OK_ENTRY.replace("ui_bearing: false", f"ui_bearing: [{', '.join(['[1,2]'] * 5000)}]")
        ),
        _bad(_OK_ENTRY + "".join(f"          k{n}: 1\n" for n in range(5000))),
        _bad(_OK_ENTRY.replace("contract_review", "x\n    y: z").replace("- name:", "- ")),
    ]
    for n, text in enumerate(cases):
        path = _manifest(tmp_path, text, name=f"m{n}.yaml")
        if path.stat().st_size > type_manifest.MAX_MANIFEST_BYTES:
            continue
        with scoped_registration():
            with pytest.raises(PackManifestError) as exc:
                _load(path)
        assert len(str(exc.value)) < 1500, (n, len(str(exc.value)))


def test_quote_names_a_structure_by_type_and_never_renders_it():
    from core.work_orders.type_registry import quote

    nested: list = []
    for _ in range(200):
        nested = [nested, nested]
    assert quote(nested) == "<list>" and quote({"a": 1}) == "<dict>"
    assert quote("a" * 1000).endswith("...") and len(quote("a" * 1000)) < 60
    assert quote(None) == "None" and quote(3) == "3"


# ── 4. the call site ──────────────────────────────────────────────────────────


@pytest.fixture
def new_process(monkeypatch, tmp_path):
    """The registry as a freshly started process has it: built-ins only, manifest not read, and
    an operator who has allowed the legal pack (the trust file lives in the home, not here)."""
    builtins = {
        n: t for n, t in type_registry._REGISTRY.items() if n in builtin_work_order_type_names()
    }
    monkeypatch.setattr(type_registry, "_REGISTRY", builtins)
    monkeypatch.setattr(type_registry, "_STATE", {"loaded": False, "loading": False})
    trust = _manifest(tmp_path, "exempt_from_verification: [legal]\n", name="pack-trust.yaml")
    monkeypatch.setattr(type_manifest, "default_trust_path", lambda: trust)


def _running_manifest(monkeypatch, path: Path) -> None:
    monkeypatch.setattr(type_manifest, "default_manifest_path", lambda: path)


def test_the_first_read_applies_the_running_manifest_and_a_second_changes_nothing(
    new_process, tmp_path, monkeypatch
):
    _running_manifest(monkeypatch, _manifest(tmp_path, GOOD))
    assert type_registry._STATE["loaded"] is False
    assert work_order_type_names()[-3:] == ("contract_review", "poster", "month_end_close")
    assert type_registry._STATE["loaded"] is True
    before = work_order_type_names()
    type_registry.ensure_loaded()
    type_registry.ensure_loaded()
    assert work_order_type_names() == before, "idempotent: no duplicate, no second read"


def _reader_names():
    return [
        "work_order_type_names",
        "get_work_order_type",
        "artifact_class_for",
        "is_ui_bearing",
        "is_verification_exempt",
        "is_dashboard_truth_gated",
        "design_brief_staling_types",
        "work_order_types_in_presentation_order",
        "register_work_order_type",
        "scoped_registration",
    ]


@pytest.mark.parametrize("reader", _reader_names())
def test_each_public_reader_loads_the_manifest_before_it_answers(
    new_process, tmp_path, monkeypatch, reader
):
    """The reader is called FIRST, in a fresh process state with a manifest present, and the
    check reads the registry's own table: asking through `get_work_order_type` (which loads the
    manifest itself) would let a reader that forgot to load pass."""
    _running_manifest(monkeypatch, _manifest(tmp_path, GOOD))
    assert "contract_review" not in type_registry._REGISTRY
    if reader == "register_work_order_type":
        register_work_order_type("fresh_one", artifact_class=CODE)
    elif reader == "scoped_registration":
        with scoped_registration():
            assert "contract_review" in type_registry._REGISTRY
    elif reader in ("get_work_order_type", "artifact_class_for", "is_ui_bearing"):
        getattr(type_registry, reader)("ui_page")
    elif reader in ("is_verification_exempt", "is_dashboard_truth_gated"):
        getattr(type_registry, reader)("documentation")
    else:
        getattr(type_registry, reader)()
    assert "contract_review" in type_registry._REGISTRY, f"{reader} did not load the manifest"


def test_the_readers_that_must_not_load_do_not(new_process, tmp_path, monkeypatch):
    """The built-in subset is fixed and answers without reading any file."""
    _running_manifest(monkeypatch, tmp_path / "does-not-exist.yaml")
    assert type_registry.builtin_work_order_type_names()[0] == "api_endpoint"
    assert type_registry.builtin_work_order_types()[0].name == "ui_component"
    assert type_registry._STATE["loaded"] is False


def test_an_unreadable_running_manifest_is_an_explicit_error_on_every_read_until_fixed(
    new_process, tmp_path, monkeypatch
):
    _running_manifest(monkeypatch, tmp_path / "nowhere" / "packs.yaml")
    for _ in range(2):
        with pytest.raises(PackManifestError, match="cannot read the pack manifest"):
            work_order_type_names()
    assert type_registry._STATE["loaded"] is False, "a failed load is not remembered as done"
    _running_manifest(monkeypatch, _manifest(tmp_path, GOOD, name="fixed.yaml"))
    assert "contract_review" in work_order_type_names()


def test_a_manifest_that_fails_leaves_the_built_ins_exactly_as_they_were(
    new_process, tmp_path, monkeypatch
):
    _running_manifest(
        monkeypatch, _manifest(tmp_path, GOOD + "  broken:\n    contributes:\n      gates: [x]\n")
    )
    with pytest.raises(PackManifestError):
        work_order_type_names()
    assert tuple(type_registry._REGISTRY) == builtin_work_order_type_names()


def test_the_running_manifest_cannot_exempt_itself_either(new_process, tmp_path, monkeypatch):
    """The same governance applies on the path every process takes, not only through the loader."""
    monkeypatch.setattr(type_manifest, "default_trust_path", lambda: tmp_path / "none.yaml")
    _running_manifest(monkeypatch, _manifest(tmp_path, GOOD))
    with pytest.raises(PackManifestError, match="exempt_from_verification: true"):
        work_order_type_names()


def test_the_default_manifest_is_the_code_roots_packs_yaml():
    """code_root(), not the working directory and not a path walked up from this module: the
    checkout in a checkout, site-packages in an installed app, whose wheel ships packs.yaml at
    the same relative path (pyproject shipped-root-data; test_wheel_runs_without_checkout)."""
    from core.config.paths import code_root

    assert type_manifest.default_manifest_path() == code_root() / "packs.yaml"
    assert type_manifest.default_manifest_path().is_file()


def test_the_default_trust_file_is_in_the_home_not_in_the_code_root(monkeypatch, tmp_path):
    """Outside every pack: the home is the operator's, the code root is what packs ship into."""
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path))
    assert type_manifest.default_trust_path() == tmp_path / "pack-trust.yaml"
    from core.config.paths import code_root

    assert code_root() not in type_manifest.default_trust_path().parents


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
    _running_manifest(monkeypatch, _manifest(tmp_path, GOOD))
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


# ── a manifest edited after a process loaded it ───────────────────────────────


def test_a_process_notices_that_its_manifest_changed_after_it_loaded(
    new_process, tmp_path, monkeypatch
):
    """The manifest is read once per process; a long-lived one keeps serving what it loaded.
    The check is a stat, not a read, so it is cheap to ask on every request."""
    path = _manifest(tmp_path, GOOD)
    _running_manifest(monkeypatch, path)
    assert manifest_changed_since_load() is None, "nothing loaded yet, nothing to compare"
    work_order_type_names()
    assert manifest_changed_since_load() is None
    path.write_text(GOOD + "# edited\n", encoding="utf-8")
    os.utime(path, (time.time() + 60, time.time() + 60))
    warning = manifest_changed_since_load()
    assert warning and str(path) in warning and "restart" in warning
    assert "\n" not in warning, "one line"
    path.unlink()
    assert "changed on disk" in manifest_changed_since_load()


def test_a_scope_does_not_leave_a_fingerprint_behind(tmp_path):
    before = manifest_changed_since_load()
    with scoped_pack_manifest(_manifest(tmp_path, GOOD), trusted=TRUST):
        pass
    assert manifest_changed_since_load() == before


# ── 5. scoping ────────────────────────────────────────────────────────────────


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
    with scoped_pack_manifest(path, trusted=TRUST):
        assert work_order_type_names() == builtin_work_order_type_names() + (
            "contract_review",
            "poster",
            "month_end_close",
        )
    assert work_order_type_names() == before
    assert type_registry._STATE == state


def test_scoped_pack_manifest_restores_the_loaded_flag_of_a_process_that_had_not_loaded(
    new_process, tmp_path
):
    """The restore of `_STATE` is only visible from a process that had not loaded yet: in one
    that had, the scope sets loaded=True over loaded=True."""
    assert type_registry._STATE["loaded"] is False
    with scoped_pack_manifest(_manifest(tmp_path, GOOD), trusted=TRUST):
        assert type_registry._STATE["loaded"] is True
    assert type_registry._STATE == {"loaded": False, "loading": False}


def test_scoped_pack_manifest_restores_even_when_the_manifest_is_refused(tmp_path):
    path = _manifest(tmp_path, GOOD + "  bad:\n    contributes:\n      gates: [x]\n")
    before = work_order_type_names()
    with pytest.raises(PackManifestError):
        with scoped_pack_manifest(path, trusted=TRUST):
            pass
    assert work_order_type_names() == before


def test_a_scope_never_reads_the_operators_trust_file(tmp_path, monkeypatch):
    """A test's outcome must not depend on whose machine it runs on."""
    trust = _manifest(tmp_path, "exempt_from_verification: [legal]\n", name="pack-trust.yaml")
    monkeypatch.setattr(type_manifest, "default_trust_path", lambda: trust)
    path = _manifest(tmp_path, _exempt())
    with pytest.raises(PackManifestError, match="exempt_from_verification: true"):
        with scoped_pack_manifest(path):
            pass


def test_two_scopes_on_two_threads_cannot_interleave_and_leave_a_type_behind():
    """Two interleaved scopes in two threads left a type registered for good: the second thread
    is refused while the first is inside, and the registry is whole afterwards."""
    before = work_order_type_names()
    inside, release = threading.Event(), threading.Event()
    errors: list[BaseException] = []

    def first() -> None:
        with scoped_registration():
            register_work_order_type("aa_type", artifact_class=CODE)
            inside.set()
            release.wait(10)

    def second() -> None:
        inside.wait(10)
        try:
            with scoped_registration():
                register_work_order_type("bb_type", artifact_class=CODE)
        except RuntimeError as exc:
            errors.append(exc)
        finally:
            release.set()

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 1 and "another thread" in str(errors[0])
    assert work_order_type_names() == before, "neither thread's type survived"


def test_a_scope_inside_a_scope_on_one_thread_is_fine():
    before = work_order_type_names()
    with scoped_registration():
        register_work_order_type("outer_type", artifact_class=CODE)
        with scoped_registration():
            register_work_order_type("inner_type", artifact_class=CODE)
        assert get_work_order_type("outer_type") and get_work_order_type("inner_type") is None
    assert work_order_type_names() == before
