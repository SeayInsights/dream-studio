"""WO-DEAD-ON-ARRIVAL: block code that arrives with no caller.

Five verify findings across 2026-08-19/21 were the same shape — a mechanism written,
its wiring omitted, and the mechanism then described as the outcome. The detector
already existed and was ignored: `core/gates/leanness.py` runs
`vulture --min-confidence 80` on every push as an ADVISORY gate and printed
"dead symbols (vulture >=80%): 8" on ~26 consecutive pushes while those functions sat
unreachable at 60% confidence.

Naively lowering the threshold is wrong, and this suite pins why: at 60 vulture also
flags `currency_failure`, which IS called — through a lazy import inside a function
body. DS uses lazy imports deliberately (a module-level import freezes the reference
and silently defeats `patch(...)`), so a static call-graph walk cannot see them.

The two real cases in this file come from the repo, not from imagination:
`currency_evidence` (0 references when this gate was written) and `currency_failure`
(reachable only through a lazy import). A synthetic fixture would have proved the gate
runs; these prove it is right.
"""

from __future__ import annotations

import textwrap

import pytest

from core.gates.reachability import (
    EXEMPT_MARKER,
    SourceUnreadable,
    added_symbol_names,
    code_identifiers,
    is_production_python,
    module_level_public_symbols,
    reference_count,
    unreachable_symbols,
)


def _dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


# ── Task 1: a newly added public symbol with no reference is flagged ──────────


def test_a_new_unreferenced_public_function_is_flagged():
    """The core case, reconstructed from the real one: merge_readiness() shipped
    correct, tested, and with no production call site — "a gate that exists, is
    correct, and sits where it cannot stop the thing it was built to stop"."""
    defining = _dedent("""
        def merge_readiness(*, branch=None):
            return {"ready": True}
        """)
    other = _dedent("""
        def unrelated():
            return 1
        """)
    findings = unreachable_symbols(
        changed_sources={"core/gates/merge_readiness.py": defining},
        added_names={"merge_readiness"},
        search_sources={"core/gates/merge_readiness.py": defining, "interfaces/cli/x.py": other},
    )
    assert [f.name for f in findings] == ["merge_readiness"]
    assert findings[0].kind == "function"
    assert findings[0].file == "core/gates/merge_readiness.py"
    assert findings[0].exempt is False


def test_a_pre_existing_unreferenced_symbol_is_out_of_scope():
    """Diff-scoped on purpose. There are 387 pre-existing advisory leanness findings;
    a gate that blocks on all of them blocks every push and gets switched off."""
    defining = _dedent("""
        def ancient_and_unused():
            return 1
        """)
    findings = unreachable_symbols(
        changed_sources={"core/old.py": defining},
        added_names=set(),  # this change set added nothing
        search_sources={"core/old.py": defining},
    )
    assert findings == []


def test_a_referenced_new_function_is_not_flagged():
    defining = _dedent("""
        def wired_up():
            return 1
        """)
    caller = _dedent("""
        from core.thing import wired_up

        def surface():
            return wired_up()
        """)
    findings = unreachable_symbols(
        changed_sources={"core/thing.py": defining},
        added_names={"wired_up"},
        search_sources={"core/thing.py": defining, "interfaces/cli/s.py": caller},
    )
    assert findings == []


# ── Task 1 (the other half): the lazy-import idiom must not be punished ───────


def test_a_lazily_imported_callee_is_not_flagged():
    """The reason tightening vulture to 60% is not the fix. DS imports inside function
    bodies so `patch(...)` works; a module-level import freezes the reference and the
    patch silently does nothing. Static call-graph analysis cannot see through that."""
    defining = _dedent("""
        def currency_failure(project_id, *, conn, db_path=None):
            return None
        """)
    lazy_caller = _dedent("""
        def run_gate_check(name):
            from core.gates.brief_currency import currency_failure

            return currency_failure("p", conn=None)
        """)
    findings = unreachable_symbols(
        changed_sources={"core/gates/brief_currency.py": defining},
        added_names={"currency_failure"},
        search_sources={
            "core/gates/brief_currency.py": defining,
            "core/work_orders/close_gates.py": lazy_caller,
        },
    )
    assert findings == [], "a lazily-imported callee is reachable"


def test_the_real_lazy_import_case_from_this_repo():
    """Not a fixture — the actual repo. `currency_failure` is reached only through a
    lazy import in close_gates.run_gate_check, and `currency_evidence` next to it had
    zero references when this gate was written. One file, both answers."""
    from core.gates.reachability import _collect_search_sources

    sources = _collect_search_sources()
    target = "core/gates/brief_currency.py"
    assert target in sources, "the real module must be in the production corpus"

    lazy = reference_count("currency_failure", sources)
    assert lazy > 0, "currency_failure is called via a lazy import — it is reachable"


def test_a_string_reference_counts():
    """`__all__` entries, getattr-by-name, and dispatch-table keys are real ways DS
    reaches code. A facade re-export is not death."""
    defining = _dedent("""
        def exported():
            return 1
        """)
    facade = _dedent("""
        __all__ = ["exported"]
        """)
    findings = unreachable_symbols(
        changed_sources={"core/mod.py": defining},
        added_names={"exported"},
        search_sources={"core/mod.py": defining, "core/facade.py": facade},
    )
    assert findings == []


# ── The regression that matters most: prose is not a reference ────────────────


def test_a_docstring_mention_is_not_a_reference():
    """THE GATE DEFEATED ITSELF ON ITS FIRST RUN. Its own module docstring names
    `currency_evidence()` as an example of a dead symbol, and the line-based text
    search counted that sentence as a call site — so the gate reported the corpus
    clean while the symbol it cited sat unreferenced.

    A grep cannot tell a mention from a use. That substitution is the very thing this
    gate exists to stop, and it happened inside the gate.
    """
    defining = _dedent("""
        def orphan():
            return 1
        """)
    prose_only = _dedent('''
        """A module whose docstring discusses orphan() at length.

        See orphan for the canonical example of an unreachable symbol.
        """

        # orphan is also named in this comment
        def something_else():
            return 2
        ''')
    findings = unreachable_symbols(
        changed_sources={"core/mod.py": defining},
        added_names={"orphan"},
        search_sources={"core/mod.py": defining, "core/gates/doc.py": prose_only},
    )
    assert [f.name for f in findings] == [
        "orphan"
    ], "a docstring and a comment naming the symbol are documentation, not call sites"


def test_code_identifiers_separates_use_from_documentation():
    source = _dedent('''
        """module docstring mentioning ghost"""

        # comment mentioning ghost
        import os

        __all__ = ["listed"]

        def f():
            """inner docstring mentioning ghost"""
            return os.path.join(real_use, "ghost_in_a_string")
        ''')
    identifiers = code_identifiers(source)
    assert "real_use" in identifiers, "an ordinary Name reference is a use"
    assert "listed" in identifiers, "an __all__ string is a use"
    assert "join" in identifiers, "an attribute lookup is a use"
    assert "ghost" not in identifiers, "docstrings and comments are not uses"


def test_an_unparseable_file_falls_back_rather_than_blocking():
    """Over-counting yields a false negative; under-counting blocks a push over a file
    the gate merely failed to read, which is how a gate gets routed around."""
    broken = "def f(:\n    pass\n"
    count = reference_count("thing", {"core/broken.py": "thing()\n" + broken})
    assert count >= 1, "an unparseable file is text-searched rather than skipped"


# ── Task 2: private and test-only symbols are out of scope ────────────────────


def test_a_private_symbol_is_out_of_scope():
    """A helper used once inside its own module is normal. A gate that flags normal
    code gets routed around — the failure mode that made leanness advisory."""
    defining = _dedent("""
        def _private_helper():
            return 1


        def public_and_wired():
            return _private_helper()
        """)
    caller = _dedent("""
        from core.mod import public_and_wired

        def surface():
            return public_and_wired()
        """)
    findings = unreachable_symbols(
        changed_sources={"core/mod.py": defining},
        added_names={"_private_helper", "public_and_wired"},
        search_sources={"core/mod.py": defining, "interfaces/cli/s.py": caller},
    )
    assert findings == [], "underscore-private is out of scope; the public one is wired"


def test_a_public_symbol_reached_only_by_tests_is_flagged():
    """DELIBERATE DIVERGENCE FROM THIS WORK ORDER'S OWN TASK TEXT, and the task text
    was wrong.

    Task 2 as written said a helper referenced only by tests "is not dead on arrival
    (it may be a fixture seam)". That contradicts a standing operator rule (2026-06-29):
    anything test-only must be REMOVED — production code under core/, projections/,
    interfaces/, spool/, control/, runtime/ reachable only from `tests/` is dead and
    gets deleted, because test-only production code is dead weight that masquerades as
    a feature and lies about what the system does.

    So `tests/` is excluded from the reference corpus on purpose: a symbol whose only
    caller is a test is exactly the case this gate must not bless. The earlier name of
    this test claimed the opposite of what its body asserted, which hid the conflict
    instead of resolving it — caught by this work order's own verify.

    A genuine fixture seam is still expressible: mark it with the exemption marker and
    say so, which the gate prints on every run.
    """
    defining = _dedent("""
        def helper_only_tests_call():
            return 1
        """)
    findings = unreachable_symbols(
        changed_sources={"core/mod.py": defining},
        added_names={"helper_only_tests_call"},
        # A test file is NOT in the corpus — production roots only (PRODUCTION_ROOTS).
        search_sources={"core/mod.py": defining},
    )
    assert [f.name for f in findings] == ["helper_only_tests_call"]

    assert is_production_python("core/mod.py") is True
    assert (
        is_production_python("tests/unit/test_mod.py") is False
    ), "tests are not production, so they cannot make production code reachable"
    assert is_production_python("core/mod.pyi") is False
    assert is_production_python("docs/README.md") is False


def test_a_declared_fixture_seam_is_allowed_and_visible():
    """The escape hatch for the case task 2 was reaching for: a deliberate seam says so
    inline and the gate prints it on every run, so 'fixture seam' is an audited claim
    rather than a silent exception."""
    defining = _dedent(f"""
        # {EXEMPT_MARKER}: injection seam, driven only from tests by design
        def seam_for_tests():
            return 1
        """)
    findings = unreachable_symbols(
        changed_sources={"core/mod.py": defining},
        added_names={"seam_for_tests"},
        search_sources={"core/mod.py": defining},
    )
    assert len(findings) == 1
    assert findings[0].exempt is True
    assert "injection seam" in findings[0].exempt_reason


def test_a_decorated_definition_is_not_flagged():
    """A decorator IS the registration mechanism — a FastAPI route, a pytest fixture,
    a click command. "No Python caller" is the normal, correct state for them."""
    defining = _dedent("""
        import app


        @app.get("/health")
        def health():
            return {"ok": True}
        """)
    findings = unreachable_symbols(
        changed_sources={"projections/api/main.py": defining},
        added_names={"health"},
        search_sources={"projections/api/main.py": defining},
    )
    assert findings == []


def test_a_class_method_is_not_examined():
    """A method is reached through its class and an override has no direct caller by
    design. Walking into class bodies would produce noise, not findings."""
    defining = _dedent("""
        class Projection:
            def handle(self, event):
                return 0
        """)
    findings = unreachable_symbols(
        changed_sources={"core/p.py": defining},
        added_names={"handle", "Projection"},
        search_sources={"core/p.py": defining},
    )
    assert [f.name for f in findings] == ["Projection"], "the class, not its methods"


# ── Task 3: it fires on the real unwired case and passes once wired ───────────


def test_the_gate_fires_on_the_unwired_case_and_passes_once_wired():
    """Anything less proves the gate exists, not that it works — which is the very
    pattern it was built to catch.

    Reconstructs the actual defect: `core/gates/merge_readiness.py` defining
    `merge_readiness` and `record_merge_override` with no call site, then the same
    module after the `ds work-order merge-check` CLI wiring landed.
    """
    module = _dedent("""
        def merge_readiness(*, work_order_id=None, branch=None):
            return {"ready": True}


        def record_merge_override(*, work_order_id, state, reason):
            return None
        """)
    added = {"merge_readiness", "record_merge_override"}

    unwired = unreachable_symbols(
        changed_sources={"core/gates/merge_readiness.py": module},
        added_names=added,
        search_sources={"core/gates/merge_readiness.py": module},
    )
    assert sorted(f.name for f in unwired) == [
        "merge_readiness",
        "record_merge_override",
    ], "both functions shipped with no production call site and must be named"

    cli = _dedent("""
        def _work_order_merge_check(*, work_order_id, branch, override, pull_request):
            from core.gates.merge_readiness import merge_readiness, record_merge_override

            result = merge_readiness(work_order_id=work_order_id, branch=branch)
            if override:
                record_merge_override(
                    work_order_id=result.get("work_order_id"),
                    state=str(result.get("state")),
                    reason=override,
                )
            return 0 if result.get("ready") else 1
        """)
    wired = unreachable_symbols(
        changed_sources={"core/gates/merge_readiness.py": module},
        added_names=added,
        search_sources={
            "core/gates/merge_readiness.py": module,
            "interfaces/cli/commands/work_order_query.py": cli,
        },
    )
    assert wired == [], "once the CLI calls them, both are reachable"


def test_an_exemption_is_recorded_and_carries_its_reason():
    """An intentional definition-before-caller is allowed and VISIBLE: the gate prints
    every exemption on every run, because an exemption nobody can see is the same shape
    as the defect it exempts."""
    defining = _dedent(f"""
        # {EXEMPT_MARKER}: public API for external adapters, called from outside this repo
        def adapter_entry_point():
            return 1
        """)
    findings = unreachable_symbols(
        changed_sources={"core/api.py": defining},
        added_names={"adapter_entry_point"},
        search_sources={"core/api.py": defining},
    )
    assert len(findings) == 1
    assert findings[0].exempt is True
    assert "external adapters" in findings[0].exempt_reason
    assert findings[0].name == "adapter_entry_point"


def test_an_exemption_without_a_reason_still_says_so():
    defining = _dedent(f"""
        # {EXEMPT_MARKER}
        def bare():
            return 1
        """)
    findings = unreachable_symbols(
        changed_sources={"core/api.py": defining},
        added_names={"bare"},
        search_sources={"core/api.py": defining},
    )
    assert findings[0].exempt is True
    assert findings[0].exempt_reason == "(no reason given)"


# ── The added-name detector ───────────────────────────────────────────────────


def test_added_symbol_names_reads_the_diff():
    diff = _dedent("""
        diff --git a/core/x.py b/core/x.py
        --- a/core/x.py
        +++ b/core/x.py
        @@ -0,0 +1,6 @@
        +def brand_new():
        +    pass
        +
        +
        +class AlsoNew:
        +    pass
        -def removed():
         def untouched():
        """)
    assert added_symbol_names(diff) == {"brand_new", "AlsoNew"}


def test_an_async_definition_is_detected():
    diff = "+async def fetch_it():\n"
    assert added_symbol_names(diff) == {"fetch_it"}


def test_the_plus_plus_plus_header_is_not_a_definition():
    """`+++ b/def_something.py` starts with '+' and must not be parsed as a def."""
    assert added_symbol_names("+++ b/core/def_helpers.py\n") == set()


def test_a_syntax_error_in_a_changed_file_is_raised_not_swallowed():
    """A gate that silently skips what it cannot read reports clean on exactly the
    files most likely to be wrong."""
    with pytest.raises(SourceUnreadable) as exc:
        module_level_public_symbols("def f(:\n    pass\n", path="core/broken.py")
    assert "core/broken.py" in str(exc.value)


# ── Task 3 (the other half): the gate is actually WIRED, and blocking ─────────


def test_the_gate_is_registered_as_a_blocking_pre_push_entry():
    """A gate that exists and never runs is the defect it was built to catch. This
    assertion is the deterministic form of "did we remember to wire it" — the question
    an LLM grader was asked about five other mechanisms, after they shipped."""
    import yaml

    from core.gates.reachability import REPO_ROOT

    manifest = yaml.safe_load(
        (REPO_ROOT / "canonical" / "workflows" / "pre-push.yaml").read_text(encoding="utf-8")
    )
    gates = manifest["gates"] if isinstance(manifest, dict) else manifest
    entry = next((g for g in gates if g.get("id") == "reachability"), None)
    assert entry is not None, "the reachability gate is not registered in pre-push.yaml"
    assert entry["tier"] == "blocking", f"registered but not blocking: {entry.get('tier')}"
    assert entry["command"] == ["py", "-m", "core.gates.reachability"]
    assert "fail_hint" in entry, "a blocking gate must tell the operator what to do"


def test_the_projected_manifest_matches_canonical():
    """`.claude/workflows/pre-push.yaml` is a generated copy. The runner reads
    canonical, but a stale projection is the two-copies-one-stale shape that has bitten
    this repo repeatedly — so it is compared, not assumed."""
    from core.gates.reachability import REPO_ROOT

    canonical = REPO_ROOT / "canonical" / "workflows" / "pre-push.yaml"
    projected = REPO_ROOT / ".claude" / "workflows" / "pre-push.yaml"
    if not projected.is_file():
        pytest.skip(f"no projected manifest on this machine ({projected})")
    assert projected.read_bytes().replace(b"\r\n", b"\n") == canonical.read_bytes().replace(
        b"\r\n", b"\n"
    ), "the projected pre-push manifest is stale"


def test_an_untracked_new_file_is_not_invisible():
    """`git diff` NEVER reports an untracked file, so this gate's first dry run said
    "nothing to check" while two brand-new modules sat in the tree — the files most
    likely to contain a mechanism with no caller. Pinned at the seam that reads them."""
    import inspect

    from core.gates import reachability

    source = inspect.getsource(reachability.main)
    assert (
        "_untracked_production_python()" in source
    ), "main() must fold untracked production files into the added-symbol set"
    assert "ls-files" in inspect.getsource(reachability._untracked_production_python)


def test_a_symbol_called_only_from_its_own_module_is_reachable():
    """Pins the semantic the removed `defining_file` parameter pretended to control.

    That parameter was advertised in the signature, documented, and changed no answer —
    its `if path == defining_file: continue` sat at the end of the loop body, a no-op.
    An argument that alters nothing is the same dead-on-arrival shape this module blocks,
    one level down where the module cannot see it: it checks symbols, not parameters.
    Found by this work order's own verify, not by the gate and not by me.

    The decision it was groping at, now stated once and tested: a sibling function
    calling a symbol means the code runs, so the defining module counts.
    """
    module = _dedent("""
        def helper():
            return 1


        def entry_point():
            return helper()
        """)
    caller = _dedent("""
        from core.mod import entry_point

        def surface():
            return entry_point()
        """)
    findings = unreachable_symbols(
        changed_sources={"core/mod.py": module},
        added_names={"helper", "entry_point"},
        search_sources={"core/mod.py": module, "interfaces/cli/s.py": caller},
    )
    assert findings == [], "a same-module caller makes the symbol reachable"

    assert reference_count("helper", {"core/mod.py": module}) == 1
    assert reference_count("absent_everywhere", {"core/mod.py": module}) == 0


def test_the_module_states_the_rule_it_enforces():
    """Gap 343d15aa. The correction — test-only production code is dead and gets
    flagged, not blessed as a fixture seam — landed in these test names and bodies but
    NOT in the module's own PRODUCTION_ROOTS comment, which still asserted the
    superseded claim and contradicted itself mid-sentence.

    A comment left stating the opposite of the code is read as the specification by the
    next person, which is how the conflict would have come back. Deterministic to
    check, so checked rather than trusted.
    """
    import inspect

    from core.gates import reachability

    source = inspect.getsource(reachability)
    head = source[: source.index("PRODUCTION_ROOTS = (")]
    assert (
        "test-only must be REMOVED" in head
    ), "the module must state the rule it enforces, next to the constant that enforces it"
    assert "2026-06-29" in head, "cite the standing operator rule, not just the behaviour"
    assert (
        "may be a deliberate fixture seam" not in head
    ), "the superseded claim must not appear in the module at all — git history holds it"
