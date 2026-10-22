"""Every field scan_coverage reads for a decision is the documented type, or the scan is unknown.

WHY (#895 follow-up). scan-meta.json is written by an agent following prose and read back
by code, so any field can hold anything. `_word()` turned a non-string into "" and the
decision then proceeded as if the field were absent: `run.status: ["completed"]`,
`source: ["github-actions"]` with no run, `outcome: ["not_scanned"]` beside a step that ran
all read `complete`. A wrong-typed field is a claim the record makes and the code cannot
read, so the scan is `unknown`, never `complete`.

The matrix: for each field a decision reads (run, run.status, run.conclusion, source,
outcome, planned_steps, steps, and each field of a steps entry), each JSON type (str, list,
dict, int, float, bool, null). `null` means "no value": it is the same as the field being
absent, and an absent optional field changes nothing; an absent required one is unknown.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ETL = Path(__file__).resolve().parents[2] / "templates" / "security" / "etl"
sys.path.insert(0, str(ETL))
import scan_coverage  # noqa: E402

PLANNED = ("semgrep", "bandit")
READ = {"semgrep", "bandit"}

#: One of each JSON type that is NOT the documented one for a text field.
NOT_TEXT = {
    "list": ["x"],
    "dict": {"x": 1},
    "int": 7,
    "float": 1.5,
    "bool": True,
}


def baseline() -> dict:
    """A github-actions scan that reads complete."""
    return {
        "source": "github-actions",
        "planned_steps": ["semgrep", "bandit"],
        "run": {"run_id": "1", "status": "completed", "conclusion": "success"},
        "steps": [
            {"step": "semgrep", "status": "ran", "tool": "semgrep"},
            {"step": "bandit", "status": "ran", "tool": "bandit"},
        ],
    }


def coverage_of(meta: dict) -> str:
    return scan_coverage.assess(meta, PLANNED, READ)["coverage"]


def test_the_baseline_reads_complete() -> None:
    assert coverage_of(baseline()) == "complete"


# -- optional text fields: wrong type is unknown, null is absent ----------------------------------------


def _set(meta: dict, path: str, value: object) -> dict:
    out = copy.deepcopy(meta)
    target = out
    *parents, leaf = path.split(".")
    for part in parents:
        target = target[part]
    target[leaf] = value
    return out


@pytest.mark.parametrize("kind", NOT_TEXT)
@pytest.mark.parametrize("path", ["run.status", "source", "outcome"])
def test_a_wrong_typed_optional_text_field_is_unknown(path: str, kind: str) -> None:
    report = scan_coverage.assess(_set(baseline(), path, NOT_TEXT[kind]), PLANNED, READ)
    assert report["coverage"] == "unknown", (path, kind)
    assert any(f"`{path}`" in x and "not text" in x for x in report["limitations"]), report


@pytest.mark.parametrize("path", ["run.status", "source", "outcome"])
def test_null_for_an_optional_text_field_is_the_same_as_absent(path: str) -> None:
    assert coverage_of(_set(baseline(), path, None)) == "complete"


@pytest.mark.parametrize("path", ["run.status", "source", "outcome"])
def test_text_for_an_optional_text_field_is_fine(path: str) -> None:
    value = {"run.status": "completed", "source": "github-actions", "outcome": "scanned"}[path]
    assert coverage_of(_set(baseline(), path, value)) == "complete"


# -- the hostile combinations the verifier found ------------------------------------------------------------


def test_a_run_status_that_is_a_list_beside_a_success_conclusion_is_not_complete() -> None:
    assert coverage_of(_set(baseline(), "run.status", ["in_progress"])) == "unknown"


def test_a_source_that_is_a_list_with_no_run_is_not_complete() -> None:
    meta = baseline()
    del meta["run"]
    meta["source"] = ["github-actions"]
    assert coverage_of(meta) == "unknown"


def test_an_outcome_that_is_a_list_beside_a_step_that_ran_is_not_complete() -> None:
    assert coverage_of(_set(baseline(), "outcome", ["not_scanned"])) == "unknown"


def test_a_wrong_typed_field_does_not_hide_a_partial_it_cannot_outrank() -> None:
    """Known gaps outrank the unreadable: a failed run with a junk field stays partial."""
    meta = _set(baseline(), "run.conclusion", "failure")
    meta = _set(meta, "source", ["x"])
    assert coverage_of(meta) == "partial"


# -- run and its conclusion ---------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [*NOT_TEXT.values(), None, "x", ""])
def test_a_run_that_is_not_an_object_is_unknown(value: object) -> None:
    assert coverage_of(_set(baseline(), "run", value)) == "unknown"


@pytest.mark.parametrize("value", [*NOT_TEXT.values(), None, ""])
def test_a_conclusion_that_is_not_text_is_unknown(value: object) -> None:
    report = scan_coverage.assess(_set(baseline(), "run.conclusion", value), PLANNED, READ)
    assert report["coverage"] == "unknown"
    assert any("conclusion" in x for x in report["limitations"])


# -- planned_steps ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["dict", "int", "float", "bool"])
def test_planned_steps_that_is_not_a_list_is_unknown(kind: str) -> None:
    report = scan_coverage.assess(_set(baseline(), "planned_steps", NOT_TEXT[kind]), PLANNED, READ)
    assert report["coverage"] == "unknown"
    assert any("`planned_steps`" in x for x in report["limitations"])


def test_planned_steps_given_as_one_string_is_unknown() -> None:
    assert coverage_of(_set(baseline(), "planned_steps", "semgrep")) == "unknown"


def test_null_planned_steps_is_absent() -> None:
    assert coverage_of(_set(baseline(), "planned_steps", None)) == "complete"


@pytest.mark.parametrize("item", [None, 3, 1.5, True, ["semgrep"], {"step": "semgrep"}])
def test_a_planned_step_that_is_not_text_is_unknown(item: object) -> None:
    meta = _set(baseline(), "planned_steps", ["semgrep", item])
    report = scan_coverage.assess(meta, PLANNED, READ)
    assert report["coverage"] == "unknown"
    assert any("`planned_steps`" in x for x in report["limitations"])


# -- steps and each field of an entry -------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["ran", *NOT_TEXT.values(), None])
def test_steps_that_is_not_a_list_is_unknown(value: object) -> None:
    if isinstance(value, list):
        pytest.skip("a list is the documented type")
    assert coverage_of(_set(baseline(), "steps", value)) == "unknown"


@pytest.mark.parametrize("entry", ["ran", ["a"], 7, 1.5, True, None])
def test_a_steps_entry_that_is_not_an_object_makes_the_record_unknown(entry: object) -> None:
    meta = baseline()
    meta["steps"].append(entry)  # beside two valid entries: a junk entry must not be ignored
    report = scan_coverage.assess(meta, PLANNED, READ)
    assert report["coverage"] == "unknown"
    assert any("not an object" in x for x in report["limitations"])


@pytest.mark.parametrize("field", ["step", "status", "tool"])
@pytest.mark.parametrize("kind", [*NOT_TEXT, "none"])
def test_a_wrong_typed_field_of_a_step_makes_it_unusable(field: str, kind: str) -> None:
    meta = baseline()
    meta["steps"][1][field] = None if kind == "none" else NOT_TEXT[kind]
    assert coverage_of(meta) == "unknown", (field, kind)


@pytest.mark.parametrize("kind", [*NOT_TEXT, "none"])
def test_a_wrong_typed_reason_is_only_prose_and_never_decides(kind: str) -> None:
    meta = baseline()
    meta["steps"][1] = {
        "step": "bandit",
        "status": "skipped",
        "tool": "bandit",
        "reason": None if kind == "none" else NOT_TEXT[kind],
    }
    report = scan_coverage.assess(meta, PLANNED, {"semgrep"})
    assert report["coverage"] == "partial"  # skipped is a known gap whatever the reason says
    assert all(isinstance(x, str) and x.isprintable() for x in report["limitations"])


def test_the_whole_matrix_never_raises_and_only_the_baseline_shape_is_complete() -> None:
    """Every field, every type, every position: never an exception, and `complete` only when
    the field either holds the documented type or is null/absent where it is optional."""
    values = [None, "x", "", ["x"], {"x": 1}, 7, 1.5, True, False]
    paths = [
        "run",
        "run.status",
        "run.conclusion",
        "source",
        "outcome",
        "planned_steps",
        "steps",
        "steps.0.step",
        "steps.1.status",
        "steps.1.tool",
    ]
    for path in paths:
        for value in values:
            meta = baseline()
            target: object = meta
            *parents, leaf = path.split(".")
            for part in parents:
                target = target[int(part)] if isinstance(target, list) else target[part]
            if isinstance(target, list):
                target[int(leaf)] = value
            else:
                target[leaf] = value
            report = scan_coverage.assess(meta, PLANNED, READ)  # must not raise
            if report["coverage"] == "complete":
                # the only complete outcomes: an optional field that is null or text, a list
                # of text for planned_steps, or a non-blank tool name
                ok = {
                    "run.status": value is None or isinstance(value, str),
                    "source": value is None or isinstance(value, str),
                    "outcome": value is None or isinstance(value, str),
                    "planned_steps": value is None or value == ["x"],
                    "steps.1.tool": isinstance(value, str) and bool(value.strip()),
                }
                assert ok.get(path, False), (path, value)
