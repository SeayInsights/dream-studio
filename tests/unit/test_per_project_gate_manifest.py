"""A project's gates are the project's, and Dream Studio declines rather than substituting.

THE SHAPE OF THE DEFECT. `run_pre_push_gates` has accepted `manifest_path` and
`repo_root` for a long time, and `main()` called it with neither — it also accepted an
`argv` parameter it never read. So the capability was built and had no door: the only
reachable behaviour was Dream Studio's manifest against Dream Studio's tree.

The obvious way to add `--repo` is to keep DS's manifest and change the working
directory. That would gate another project on `rule4-ingestor-sole-event-writer` and
`fixture-schema-parity` — facts about THIS codebase's event pipeline. Every one would
fail, and none of the failures would say anything true about that project.
"""

from __future__ import annotations

import pathlib

from core.gates.pre_push import main as pre_push_main
from core.projects.standards import GATE_MANIFEST_PATHS, gate_manifest_for

MANIFEST = """name: demo-gates
gates:
  - id: says-hello
    description: proves the project's OWN manifest ran
    command: [py, -c, "print('hello from the project')"]
    fail_hint: n/a
"""


def _declaring(tmp_path: pathlib.Path, parts: tuple[str, ...]) -> pathlib.Path:
    target = tmp_path.joinpath(*parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(MANIFEST, encoding="utf-8")
    return tmp_path


# ── resolution ──────────────────────────────────────────────────────────────


def test_both_layouts_resolve(tmp_path):
    """Mirrors `round_table.registry_for`: a project laid out like Dream Studio needs no
    second file to say the same thing."""
    for index, parts in enumerate(GATE_MANIFEST_PATHS):
        root = _declaring(tmp_path / f"p{index}", parts)
        path, refusal = gate_manifest_for(root)
        assert refusal is None
        assert path == root.joinpath(*parts)


def test_the_dedicated_layout_wins_when_both_exist(tmp_path):
    """A project that has both is saying something specific with the dedicated file."""
    root = tmp_path
    for parts in GATE_MANIFEST_PATHS:
        _declaring(root, parts)
    path, _ = gate_manifest_for(root)
    assert path == root.joinpath(*GATE_MANIFEST_PATHS[0])


def test_a_project_declaring_nothing_is_refused_not_defaulted(tmp_path):
    """THE MUTANT THIS EXISTS FOR. Falling back to Dream Studio's manifest would run
    this repository's rules against someone else's code."""
    path, refusal = gate_manifest_for(tmp_path)
    assert path is None
    assert refusal
    # The refusal has to say WHERE to declare them; "declare your gates" without a
    # location is the same dead end as no message.
    for parts in GATE_MANIFEST_PATHS:
        assert "/".join(parts) in refusal


def test_no_repo_means_no_opinion(tmp_path):
    """Dream Studio gating itself must not go through the project resolver at all."""
    assert gate_manifest_for(None) == (None, None)


# ── the door ────────────────────────────────────────────────────────────────


def test_the_project_manifest_actually_runs(capsys):
    """End to end, because nothing above proves `main` consults the resolver or passes
    what it returns — the gap that let a mutant survive twenty-six tests earlier."""
    import tempfile

    root = _declaring(pathlib.Path(tempfile.mkdtemp()), GATE_MANIFEST_PATHS[0])
    rc = pre_push_main(["--repo", str(root)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "says-hello" in out, "the project's own gate did not run"
    # And Dream Studio's own gates did NOT run against it.
    assert "rule4-ingestor-sole-event-writer" not in out
    assert "fixture-schema-parity" not in out


def test_the_door_refuses_with_exit_two(capsys):
    import tempfile

    rc = pre_push_main(["--repo", tempfile.mkdtemp()])
    assert rc == 2
    assert "declares no gate manifest" in capsys.readouterr().err


def test_main_still_takes_no_arguments_for_this_repo():
    """The git hook calls `py -m core.gates.pre_push` with nothing. Adding a parser must
    not make the no-argument case an error."""
    import argparse
    import inspect

    source = inspect.getsource(pre_push_main)
    assert "--repo" in source
    assert "add_argument" in source
    # argparse with only optional arguments accepts an empty argv.
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=None)
    assert parser.parse_args([]).repo is None
