"""WO-BLAST-PARAM-SPLIT: the changed_signature_caller detector must not
false-positive on annotation-only changes.

_param_names split the parameter string on raw commas, so a comma inside a
bracketed annotation (Union[A, B], Dict[K, V], tuple[A, B]) fabricated a phantom
param. Modernizing Union[A, B] -> A | B removed that comma, changed the naive
param count, and fired a spurious "signature changed" block — which stopped the
PEP 604 modernization (WO 6d978483) at PR #470. The fix splits params on
top-level commas only, so an annotation rewrite yields identical param names.
"""

from __future__ import annotations

from pathlib import Path

from core.gates.hanging_detectors import (
    _param_names,
    detect_changed_signature_callers,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestParamNamesBracketAware:
    def test_union_with_inner_comma_is_one_param(self):
        assert _param_names("self, relation_type: Union[RelationType, str]") == ("relation_type",)

    def test_pep604_union_is_same_as_typing_union(self):
        old = _param_names("self, relation_type: Union[RelationType, str]")
        new = _param_names("self, relation_type: RelationType | str")
        assert old == new == ("relation_type",)

    def test_nested_brackets_and_defaults(self):
        assert _param_names("a: Dict[str, int], b: tuple[int, ...] = ()") == ("a", "b")

    def test_genuine_two_params_still_two(self):
        assert _param_names("a: int, b: str") == ("a", "b")


class TestDetectorNoFalsePositive:
    def test_annotation_only_union_change_not_flagged(self, tmp_path: Path) -> None:
        """The exact PR #470 case: Union[A, B] -> A | B on a signature whose caller
        is outside the diff must NOT be flagged (the annotation is semantically
        identical; the parameter list is unchanged)."""
        repo = tmp_path
        _write(
            repo / "tests" / "unit" / "test_relationship_catalog.py",
            "def test_specs():\n    cat.has_specs('x')\n    cat.get_specs('y')\n",
        )
        diff = (
            "diff --git a/core/ontology/relationships.py b/core/ontology/relationships.py\n"
            "--- a/core/ontology/relationships.py\n"
            "+++ b/core/ontology/relationships.py\n"
            "@@ -10,2 +10,2 @@\n"
            "-    def has_specs(self, relation_type: Union[RelationType, str]) -> bool:\n"
            "-    def get_specs(self, relation_type: Union[RelationType, str]) -> tuple:\n"
            "+    def has_specs(self, relation_type: RelationType | str) -> bool:\n"
            "+    def get_specs(self, relation_type: RelationType | str) -> tuple:\n"
        )
        findings = detect_changed_signature_callers(diff, repo_root=repo)
        assert findings == [], f"annotation-only change must not flag callers; got {findings}"

    def test_genuine_param_addition_still_flagged(self, tmp_path: Path) -> None:
        """Negative control: a real parameter addition to a function whose caller
        is outside the diff must STILL be flagged (the fix does not over-suppress)."""
        repo = tmp_path
        _write(
            repo / "tests" / "unit" / "test_caller.py",
            "def test_it():\n    do_work('a')\n",
        )
        diff = (
            "diff --git a/core/thing.py b/core/thing.py\n"
            "--- a/core/thing.py\n"
            "+++ b/core/thing.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-def do_work(name: str):\n"
            "+def do_work(name: str, extra: Dict[str, int] = None):\n"
        )
        findings = detect_changed_signature_callers(diff, repo_root=repo)
        flagged = {f["path"] for f in findings}
        assert (
            "tests/unit/test_caller.py" in flagged
        ), f"genuine param addition must still flag the caller; got {flagged}"


class TestAmbiguousSymbolNames:
    """An ambiguous name needs its module named before it counts as a reference.

    Measured on PR #707: 720 findings, 348 for `main` and 334 for `run`, in packs.yaml,
    canonical/rules.yml, .github/workflows/*.yml and examples/ -- none of them a caller of
    the changed `core.gates.untested_fallback.main`. All three platforms failed on a PR that
    broke nothing.

    A FIRST ATTEMPT AT THIS WAS WRONG AND THE EXISTING TESTS CAUGHT IT. Exempting
    "compatible widening" -- a parameter added with a default breaks no caller -- would have
    let #353 through, because #353 WAS that shape: `_write_handoff_packet_to_db(session_id,
    cwd)` gained `handoff_path=None`, and the break was a test asserting the old call shape
    through `assert_called_once_with`. A compatible signature still breaks a mock assertion.
    The defect is ambiguity, not arity.
    """

    def test_an_ambiguous_bare_name_is_not_a_reference(self, tmp_path: Path) -> None:
        repo = tmp_path
        # `main` defined in two modules makes the name ambiguous.
        _write(repo / "core" / "one.py", "def main():\n    return 1\n")
        _write(repo / "core" / "two.py", "def main():\n    return 2\n")
        # A bare mention, the shape that produced 682 of the 720 findings.
        _write(repo / "elsewhere.py", "def go():\n    main()\n")

        diff = (
            "diff --git a/core/one.py b/core/one.py\n"
            "--- a/core/one.py\n"
            "+++ b/core/one.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-def main():\n"
            "+def main(argv=None):\n"
        )
        flagged = {f["path"] for f in detect_changed_signature_callers(diff, repo_root=repo)}
        assert "elsewhere.py" not in flagged, flagged

    def test_an_ambiguous_name_IS_a_reference_when_the_module_is_named(
        self, tmp_path: Path
    ) -> None:
        """The other direction. Without this, the fix would be indistinguishable from
        switching the detector off for every common name."""
        repo = tmp_path
        _write(repo / "core" / "one.py", "def main():\n    return 1\n")
        _write(repo / "core" / "two.py", "def main():\n    return 2\n")
        _write(repo / "elsewhere.py", "import core.one\n\ndef go():\n    core.one.main()\n")

        diff = (
            "diff --git a/core/one.py b/core/one.py\n"
            "--- a/core/one.py\n"
            "+++ b/core/one.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-def main():\n"
            "+def main(argv=None):\n"
        )
        flagged = {f["path"] for f in detect_changed_signature_callers(diff, repo_root=repo)}
        assert "elsewhere.py" in flagged, flagged

    def test_a_unique_name_keeps_bare_matching(self, tmp_path: Path) -> None:
        """THE #353 PROPERTY, asserted here as well as in the regression test.

        `_write_handoff_packet_to_db` is defined once in the repo, so it never reaches the
        ambiguity branch and a bare reference to it still flags. If this narrowing had
        applied to unique names, the regression this detector exists for would stop being
        caught -- and the mock-assertion break it represents is invisible to any
        signature-compatibility reasoning.
        """
        repo = tmp_path
        _write(repo / "core" / "monitor.py", "def _write_packet(session_id, cwd):\n    pass\n")
        _write(
            repo / "tests" / "test_it.py",
            "def test_x():\n    with patch('core.monitor._write_packet') as m:\n"
            "        m.assert_called_once_with('s', 'c')\n",
        )

        diff = (
            "diff --git a/core/monitor.py b/core/monitor.py\n"
            "--- a/core/monitor.py\n"
            "+++ b/core/monitor.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-def _write_packet(session_id, cwd):\n"
            "+def _write_packet(session_id, cwd, handoff_path=None):\n"
        )
        flagged = {f["path"] for f in detect_changed_signature_callers(diff, repo_root=repo)}
        assert "tests/test_it.py" in flagged, (
            "a unique name must keep bare matching -- this is the #353 shape, and a"
            " compatible signature still breaks assert_called_once_with"
        )
