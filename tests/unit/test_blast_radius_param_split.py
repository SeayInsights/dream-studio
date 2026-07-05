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
