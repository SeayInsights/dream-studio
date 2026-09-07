"""The normative-baseline ratchet must fail in BOTH directions.

An increase is the obvious failure: a new shouted rule that nothing classifies. A DECREASE
failing is the less obvious half and the more important one -- a ceiling left sitting above
reality drifts upward silently and stops meaning anything, which is how the pile grew the
first time. Both are asserted here.

The number this gate corrects: "2,172 normative statements" circulated as a backlog of
unwritten rules. It was a count of word occurrences. The same corpus yields ~191 shouted
statements and ~5,752 any-case ones, so a test here pins that the gate counts the SHOUTED
form only -- if it ever starts counting lowercase prose, the ceiling becomes unmeetable and
the ratchet gets switched off, which is worse than not having it.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.gates import normative_baseline as nb


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return tmp_path


def _seed(tmp_path: Path, lanes: dict[str, int]) -> Path:
    path = tmp_path / "canonical" / "normative_baseline.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"lanes": lanes}), encoding="utf-8")
    return path


def test_counts_only_the_shouted_form(tmp_path):
    tree = _tree(
        tmp_path,
        {
            "docs/a.md": (
                "The runner must be the sole writer and should never be bypassed.\n"
                "Callers always retry.\n"
                "You MUST NOT bypass the runner.\n"
            )
        },
    )
    # Three lowercase occurrences (must, never, always) and one shouted MUST NOT.
    assert nb.measure(tree)["docs"] == 1


def test_an_increase_fails_and_names_the_four_ways_out(tmp_path):
    tree = _tree(tmp_path, {"docs/a.md": "You MUST do this. You NEVER do that.\n"})
    result = nb.run(tree, _seed(tmp_path, {**{k: 0 for k in nb._LANES}, "docs": 1}))
    assert result["status"] == "fail"
    joined = " ".join(result["errors"])
    assert "canonical/rules.yml" in joined
    assert "eval" in joined
    assert "generated" in joined
    assert "deleted" in joined


def test_at_the_ceiling_passes(tmp_path):
    tree = _tree(tmp_path, {"docs/a.md": "You MUST do this.\n"})
    result = nb.run(tree, _seed(tmp_path, {**{k: 0 for k in nb._LANES}, "docs": 1}))
    assert result["status"] == "pass", result["errors"]


def test_a_decrease_also_fails_so_the_ceiling_cannot_drift(tmp_path):
    # The half that makes the ratchet monotonic. Deleting prose is exactly the behaviour we
    # want, and recording it is what stops the ceiling floating free of reality.
    tree = _tree(tmp_path, {"docs/a.md": "nothing normative here\n"})
    result = nb.run(tree, _seed(tmp_path, {**{k: 0 for k in nb._LANES}, "docs": 5}))
    assert result["status"] == "fail"
    assert "Lower the ceiling" in " ".join(result["errors"])


def test_an_unrecorded_lane_is_a_finding(tmp_path):
    tree = _tree(tmp_path, {"docs/a.md": "You MUST do this.\n"})
    partial = _seed(tmp_path, {k: 0 for k in nb._LANES if k != "docs"})
    result = nb.run(tree, partial)
    assert result["status"] == "fail"
    assert "no ceiling recorded" in " ".join(result["errors"])


def test_a_stale_lane_in_the_baseline_is_a_finding(tmp_path):
    tree = _tree(tmp_path, {"docs/a.md": "plain prose\n"})
    stale = _seed(tmp_path, {**{k: 0 for k in nb._LANES}, "lane_that_was_removed": 3})
    result = nb.run(tree, stale)
    assert result["status"] == "fail"
    assert "not a known lane" in " ".join(result["errors"])


def test_a_missing_baseline_fails_rather_than_passing_vacuously(tmp_path):
    tree = _tree(tmp_path, {"docs/a.md": "You MUST do this.\n"})
    result = nb.run(tree, tmp_path / "canonical" / "absent.json")
    assert result["status"] == "fail"
    assert "seed it" in " ".join(result["errors"])


def test_an_unreadable_baseline_fails_rather_than_passing_vacuously(tmp_path):
    tree = _tree(tmp_path, {"docs/a.md": "You MUST do this.\n"})
    broken = tmp_path / "canonical" / "normative_baseline.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("{not json", encoding="utf-8")
    result = nb.run(tree, broken)
    assert result["status"] == "fail"
    assert "unreadable" in " ".join(result["errors"])


def test_the_registry_is_not_counted_against_itself(tmp_path):
    # canonical/rules.yml STATES every rule it classifies. Counting it would mean writing a
    # rule raises the number that writing a rule exists to lower.
    tree = _tree(
        tmp_path,
        {
            "canonical/rules.yml": "statement: A payload key MUST reach its projection. NEVER drop it.\n",
            "canonical/workflows/w.yaml": "description: nothing shouted\n",
        },
    )
    assert nb.measure(tree)["canonical/workflows"] == 0


def test_update_writes_the_measured_counts(tmp_path):
    tree = _tree(tmp_path, {"docs/a.md": "You MUST do this. And you NEVER do that.\n"})
    path = tmp_path / "canonical" / "normative_baseline.json"
    result = nb.update(tree, path)
    assert result["lanes"]["docs"] == 2
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["lanes"]["docs"] == 2
    assert written["total"] == 2
    assert "_comment" in written, "the file must explain itself to whoever opens it next"
    # And the gate it feeds must then pass against the same tree.
    assert nb.run(tree, path)["status"] == "pass"


def test_lanes_are_grouped_by_enforcement_substrate():
    # The lane names carry the whole point: an increase in `code` wants a gate, an increase
    # in canonical/skills wants an EVAL because no static check can enforce a prompt. If the
    # lanes collapse into one number, the count stops telling anyone what to do about it.
    assert "canonical/skills" in nb._LANES
    assert "code" in nb._LANES
    assert "docs" in nb._LANES


def test_the_real_repository_is_at_its_ceiling():
    result = nb.run()
    assert result["status"] == "pass", result["errors"]
    assert result["total_measured"] > 100, "the scan found almost nothing -- lanes are wrong"
    assert result["total_measured"] < 500, (
        "the count jumped into the thousands, which means the pattern started matching"
        " lowercase prose -- an unmeetable ceiling gets switched off, which is worse than"
        " having none"
    )
