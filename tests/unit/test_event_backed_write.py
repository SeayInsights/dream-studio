"""The event-backed-write detector the lane declared and nobody wrote.

`a-write-no-event-can-reconstruct` named `py -m core.gates.event_backed_write`.
The module did not exist, while five sites in prove.py already carried its
`# event-backed-write:` exemption comments and a test docstring reasoned about
"what event-backed-write reports". The convention was written against; the
detector never was.

These tests run against SYNTHETIC trees rather than the real repository. A
detector that currently reports zero on its own tree is indistinguishable from
one that reports zero on everything, and "it found nothing" is the one result
that proves nothing about a scanner.
"""

from __future__ import annotations

import textwrap

import pytest

from core.gates import event_backed_write as gate


def _tree(root, projection_table="business_things", **files):
    """A minimal tree with one projection declaring a target table."""
    proj = root / "core" / "projections"
    proj.mkdir(parents=True)
    (proj / "thing_projection.py").write_text(
        textwrap.dedent(f"""
            _TABLE = "{projection_table}"


            class ThingProjection:
                name = "thing"
                target_tables = [_TABLE]
            """),
        encoding="utf-8",
    )
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body), encoding="utf-8")
    return root


def test_derives_target_tables_from_the_projection(tmp_path):
    """Not a hardcoded list. Hardcoding the tables a defect was first found in
    exempts every other table the projection truncates, which is the same
    subset-of-what-it-writes shape this gate exists to catch."""
    _tree(tmp_path, projection_table="business_widgets")
    result = gate.run(tmp_path)
    assert result["tables"] == ["business_widgets"]


def test_write_with_no_event_is_a_finding(tmp_path):
    _tree(
        tmp_path,
        **{"core/w.py": """
                def save_thing(conn, tid):
                    conn.execute(
                        "INSERT INTO business_things (id) VALUES (?)", (tid,)
                    )
            """},
    )
    result = gate.run(tmp_path)
    assert result["status"] == "found"
    assert len(result["findings"]) == 1
    f = result["findings"][0]
    assert f["function"] == "save_thing"
    assert f["table"] == "business_things"
    assert f["file"] == "core/w.py"


def test_insert_or_replace_is_also_a_write(tmp_path):
    """INSERT OR REPLACE materialises a row exactly as INSERT does, and a rebuild
    drops it exactly the same way."""
    _tree(
        tmp_path,
        **{"core/w.py": """
                def save_thing(conn, tid):
                    conn.execute("INSERT OR REPLACE INTO business_things (id) VALUES (?)", (tid,))
            """},
    )
    assert gate.run(tmp_path)["status"] == "found"


def test_write_beside_an_emit_is_clean(tmp_path):
    _tree(
        tmp_path,
        **{"core/w.py": """
                def save_thing(conn, tid):
                    conn.execute("INSERT INTO business_things (id) VALUES (?)", (tid,))
                    write_event({"type": "thing.created", "id": tid})
            """},
    )
    assert gate.run(tmp_path)["status"] == "clean"


def test_a_declared_site_is_exempt(tmp_path):
    """A deliberately disposable row may stay, but it must say so. prove.py's
    scratch authority is the real instance: emitting there would write the
    operator's live spool."""
    _tree(
        tmp_path,
        **{"core/w.py": """
                def save_thing(conn, tid):
                    # event-backed-write: scratch authority, torn down after the run
                    conn.execute("INSERT INTO business_things (id) VALUES (?)", (tid,))
            """},
    )
    assert gate.run(tmp_path)["status"] == "clean"


def test_a_marker_in_another_function_does_not_exempt_this_one(tmp_path):
    """The exemption is per write site. A file-level marker would silently clear
    every future write added to that file."""
    _tree(
        tmp_path,
        **{"core/w.py": """
                def declared(conn, tid):
                    # event-backed-write: scratch authority
                    conn.execute("INSERT INTO business_things (id) VALUES (?)", (tid,))


                def undeclared(conn, tid):
                    conn.execute("INSERT INTO business_things (id) VALUES (?)", (tid,))
            """},
    )
    result = gate.run(tmp_path)
    assert result["status"] == "found"
    assert [f["function"] for f in result["findings"]] == ["undeclared"]


def test_tests_are_out_of_scope(tmp_path):
    """A fixture building rows directly is what a fixture IS. Including tests
    measured 214 sites against 4 real ones -- a wall, not a gate."""
    _tree(
        tmp_path,
        **{"tests/unit/test_x.py": """
                def test_something(conn):
                    conn.execute("INSERT INTO business_things (id) VALUES (1)")
            """},
    )
    assert gate.run(tmp_path)["status"] == "clean"


def test_a_write_to_an_unprojected_table_is_not_this_lane(tmp_path):
    """Only tables a projection truncates can be dropped by a rebuild. Reporting
    ordinary tables would make the finding meaningless."""
    _tree(
        tmp_path,
        **{"core/w.py": """
                def save_other(conn):
                    conn.execute("INSERT INTO some_other_table (id) VALUES (1)")
            """},
    )
    assert gate.run(tmp_path)["status"] == "clean"


def test_no_resolvable_projection_is_unknown_not_clean(tmp_path):
    """The load-bearing case. A scan that found no tables searched for nothing,
    and reporting that as clean is the compared-nothing-reported-clean shape every
    review lane exists to refuse."""
    (tmp_path / "core").mkdir()
    result = gate.run(tmp_path)
    assert result["status"] == "unknown"
    assert result["status"] != "clean"


def test_unknown_exits_zero_but_does_not_print_ok(tmp_path, capsys):
    (tmp_path / "core").mkdir()
    rc = gate.main(["--repo-root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "UNKNOWN" in out
    assert "OK" not in out


def test_finding_exits_nonzero(tmp_path, capsys):
    """The convener reads returncode: 0 is clean. A detector that found something
    and exited 0 would have its finding silently discarded."""
    _tree(
        tmp_path,
        **{"core/w.py": """
                def save_thing(conn, tid):
                    conn.execute("INSERT INTO business_things (id) VALUES (?)", (tid,))
            """},
    )
    assert gate.main(["--repo-root", str(tmp_path)]) == 1


def test_accepts_repo_root(tmp_path):
    _tree(tmp_path)
    assert gate.main(["--repo-root", str(tmp_path)]) == 0


@pytest.mark.parametrize(
    "table",
    [
        "business_clients",
        "business_design_briefs",
        "business_milestones",
        "business_projects",
        "business_tasks",
        "business_work_orders",
    ],
)
def test_real_tree_derives_every_projection_table(table):
    """Against the actual repository: all six projections must be found. If a
    projection stops resolving, the scan narrows silently and the tables it no
    longer covers go unwatched -- a regression that would otherwise look like
    the gate simply passing."""
    assert table in gate.run()["tables"]
