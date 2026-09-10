"""The Custodian's detector, and the two fail-opens it shipped with.

The gate reports a row written into a projection that no canonical event can reconstruct.
Measured on the live authority: 493 of 949 work orders and 1706 of 3286 tasks have no
creation event, and `pre_rebuild` truncates each projection's declared targets before
replaying -- so a rebuild deletes 52% of both, and a rebuild is the recovery tool.

BOTH FAIL-OPENS WERE IN THE FILE LISTING, not in the detection, which is the part nobody
looks at. `locale-decode` caught the first on this gate's own first chain run: without
`encoding=`, child output decodes with the platform codec, one unmapped byte raises inside
subprocess's reader thread, `run` returns returncode=0 with stdout=None, and the gate
examines ZERO files and reports every write site clean. The second was the empty listing
itself -- an absent git, a non-repo, a failed call -- all of which read as "no Python files
here". A gate written to catch compared-nothing-reported-clean contained it twice.
"""

from __future__ import annotations

import subprocess

import pytest

from core.gates import event_backed_write as ebw


def _repo(tmp_path, files: dict[str, str]):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, timeout=120)
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, timeout=120)
    return tmp_path


# ── the two fail-opens ──────────────────────────────────────────────────────


def test_an_unreadable_listing_raises_rather_than_examining_nothing(monkeypatch, tmp_path):
    """THE SHAPE `locale-decode` CAUGHT. `subprocess.run` can return success with
    stdout=None when the decoder raises in its reader thread. Examining zero files must not
    render as finding zero offenders."""

    class _Silent:
        returncode = 0
        stdout = None

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Silent())
    with pytest.raises(RuntimeError, match="examined nothing"):
        ebw._tracked_python(tmp_path)


def test_an_empty_listing_raises(tmp_path):
    """A directory that is not a git repo lists nothing. That is not compliance."""
    with pytest.raises(RuntimeError, match="listed no Python files"):
        ebw._tracked_python(tmp_path)


def test_the_listing_pins_its_decoding(tmp_path):
    """And the positive control: a real repo with a real file DOES list it, so the raises
    above are not simply "this function always raises"."""
    repo = _repo(tmp_path, {"a.py": "x = 1\n"})
    listed = ebw._tracked_python(repo)
    assert [p.name for p in listed] == ["a.py"], listed


# ── the target tables are derived from the projections ──────────────────────


def test_the_target_tables_come_from_the_projections_themselves():
    """A HARDCODED LIST WOULD HAVE COVERED THE TWO TABLES THE DEFECT WAS FOUND IN and
    silently exempted the rest -- the same subset-of-what-it-writes shape as WO b56cca8a,
    where `ds update` checked drift only under `skills/` and five gates went missing.

    So this asserts the set is DERIVED and non-trivial, not that it equals a list typed
    here: a list typed here would be the second source the derivation exists to avoid.
    """
    targets = ebw.projection_targets()

    assert len(targets) >= 4, targets
    # Every table names at least one projection that declares it, which is what makes it
    # the set `pre_rebuild` truncates.
    for table, projections in targets.items():
        assert projections, table
        assert table.startswith("business_"), table

    # And it really is read from the declarations, not from this gate.
    from core.projections.task_projection import TaskProjection

    for declared in TaskProjection.target_tables:
        assert declared in targets, declared


# ── detection, both directions ──────────────────────────────────────────────


# The import is part of the fixture because it is part of the real shape: the gate reads
# provenance, so a bare `write_event(...)` in a file that never imported it is not an
# emission — it is a NameError waiting to happen. A fixture without the import would be a
# stand-in with a different contract than production, which is the very defect class this
# gate's own work order was about.
WITH_EVENT = """
from spool.writer import write_event


def create_thing(conn):
    write_event(envelope)
    conn.execute("INSERT INTO business_tasks (task_id) VALUES (?)", ("x",))
"""

WITHOUT_EVENT = """
def sneak_thing(conn):
    conn.execute("INSERT INTO business_tasks (task_id) VALUES (?)", ("x",))
"""

DECLARED = """
def scratch_thing(conn):
    # event-backed-write: a disposable scratch authority that is torn down and never rebuilt
    conn.execute("INSERT INTO business_tasks (task_id) VALUES (?)", ("x",))
"""

BARE_MARKER = """
def lazy_thing(conn):
    # event-backed-write: nope
    conn.execute("INSERT INTO business_tasks (task_id) VALUES (?)", ("x",))
"""


def test_a_write_with_no_event_is_reported_and_one_with_an_event_is_not(tmp_path):
    repo = _repo(tmp_path, {"good.py": WITH_EVENT, "bad.py": WITHOUT_EVENT})
    report = ebw.offenders(repo)

    assert report["examined"] == 2, report
    flagged = {item["file"] for item in report["offenders"]}
    assert flagged == {"bad.py"}, flagged


def test_a_declared_reason_exempts_and_a_bare_marker_does_not(tmp_path):
    """The exemption contract, same 20-character bar as `security-scan` and `--why`. A
    marker that costs nothing to write becomes the norm, so a shrug is not a declaration."""
    repo = _repo(tmp_path, {"declared.py": DECLARED, "lazy.py": BARE_MARKER})
    report = ebw.offenders(repo)

    flagged = {item["file"] for item in report["offenders"]}
    assert flagged == {"lazy.py"}, flagged


def test_tests_are_out_of_scope(tmp_path):
    """A fixture building rows directly is what a fixture IS -- the whole-tree measurement
    was 211 of 214 write sites, almost entirely fixtures. Including them would have made the
    gate a wall on day one."""
    repo = _repo(tmp_path, {"tests/test_x.py": WITHOUT_EVENT, "prod.py": WITHOUT_EVENT})
    report = ebw.offenders(repo)

    flagged = {item["file"] for item in report["offenders"]}
    assert flagged == {"prod.py"}, flagged


def test_the_report_states_what_it_examined_even_when_clean(tmp_path):
    """A clean run that prints nothing is indistinguishable from one that measured nothing,
    which is this gate's own subject applied to its own output."""
    repo = _repo(tmp_path, {"good.py": WITH_EVENT})
    rendered = ebw._render(ebw.offenders(repo))

    assert "1 production write site(s) examined" in rendered, rendered
    assert "OK" in rendered


# ── emission reached through a helper, not spelled in the function ──────────
#
# WO 17466550 collapsed two copied emission blocks in verify_gaps.py into one shared
# `_emit_creation`. The literal-text check this gate used then flagged BOTH callers,
# including the one that was already correct, because neither contained the string any
# more. A gate that scores the correct refactor as the defect pushes people to paste the
# block a third time — which is the condition that created the original bug.

VIA_HELPER = """
from spool.writer import write_event


def _emit(payload):
    write_event(payload)


def create_thing(conn):
    _emit({"a": 1})
    conn.execute("INSERT INTO business_tasks (task_id) VALUES (?)", ("x",))
"""

VIA_HELPER_CHAIN = """
from spool.writer import write_event


def _emit(payload):
    write_event(payload)


def _emit_creation(payload):
    _emit(payload)


def create_thing(conn):
    _emit_creation({"a": 1})
    conn.execute("INSERT INTO business_tasks (task_id) VALUES (?)", ("x",))
"""

HELPER_THAT_DOES_NOT_EMIT = """
def _log(payload):
    print(payload)


def create_thing(conn):
    _log({"a": 1})
    conn.execute("INSERT INTO business_tasks (task_id) VALUES (?)", ("x",))
"""


def test_a_write_emitting_through_a_helper_is_not_reported(tmp_path):
    """The refactor the old text match punished."""
    repo = _repo(tmp_path, {"helper.py": VIA_HELPER})
    report = ebw.offenders(repo)

    assert report["offenders"] == [], report["offenders"]
    assert report["examined"] >= 1, "must have actually examined the write site"


def test_the_helper_chain_is_followed_to_a_fixed_point(tmp_path):
    """A helper calling a helper still counts, or the rule only survives one refactor."""
    repo = _repo(tmp_path, {"chain.py": VIA_HELPER_CHAIN})

    assert ebw.offenders(repo)["offenders"] == []


UNRELATED_RECEIVER = """
class TelemetryLogger:
    def write_event(self, msg):
        self._buf.append(msg)


def create_thing(conn, logger):
    conn.execute("INSERT INTO business_work_orders (work_order_id) VALUES (?)", ("x",))
    logger.write_event("inserted")
"""

MODULE_ALIAS_RECEIVER = """
import spool.writer as _spool_writer


def create_thing(conn):
    _spool_writer.write_event({"a": 1})
    conn.execute("INSERT INTO business_work_orders (work_order_id) VALUES (?)", ("x",))
"""

# The three constructions an independent reviewer EXECUTED against the first receiver
# fix, each of which slipped through a name-only allowlist as a genuine emission while
# doing a raw INSERT and emitting nothing. The names are ordinary ones in this
# codebase's vocabulary, so the collision is likely rather than contrived.
SHADOWED_BY_PARAM_WRITER = """
import spool.writer as _spool_writer


def create_thing(conn, writer):
    conn.execute("INSERT INTO business_work_orders (work_order_id) VALUES (?)", ("x",))
    writer.write_event("inserted")
"""

SHADOWED_BY_PARAM_SPOOL = """
import spool.writer as _spool_writer


def create_thing(conn, spool):
    conn.execute("INSERT INTO business_work_orders (work_order_id) VALUES (?)", ("x",))
    spool.write_event("inserted")
"""

SHADOWED_BY_LOCAL = """
import spool.writer as _spool_writer


def create_thing(conn):
    _spool_writer = FakeWriter()
    conn.execute("INSERT INTO business_work_orders (work_order_id) VALUES (?)", ("x",))
    _spool_writer.write_event("inserted")
"""

NO_IMPORT_AT_ALL = """
def create_thing(conn):
    conn.execute("INSERT INTO business_work_orders (work_order_id) VALUES (?)", ("x",))
    write_event("inserted")
"""


# A second round of execution-verified false negatives from the same reviewer. The first
# three are shadow forms an enumerated check could not see; the fourth needs no name
# collision at all, which is what makes it the worst of them.
SHADOWED_AT_MODULE_LEVEL = """
import spool.writer as _spool_writer

_spool_writer = None


def create_thing(conn):
    conn.execute("INSERT INTO business_tasks (task_id) VALUES (?)", ("x",))
    _spool_writer.write_event("inserted")
"""

SHADOWED_BY_FOR_TARGET = """
import spool.writer as _spool_writer


def create_thing(conn, things):
    for _spool_writer in things:
        pass
    conn.execute("INSERT INTO business_tasks (task_id) VALUES (?)", ("x",))
    _spool_writer.write_event("inserted")
"""

SHADOWED_BY_WITH_AS = """
import spool.writer as _spool_writer


def create_thing(conn, ctx):
    with ctx as _spool_writer:
        conn.execute("INSERT INTO business_tasks (task_id) VALUES (?)", ("x",))
        _spool_writer.write_event("inserted")
"""

DEAD_NESTED_HELPER = """
import spool.writer as _spool_writer


def create_thing(conn):
    def _never_called():
        _spool_writer.write_event({"a": 1})

    conn.execute("INSERT INTO business_tasks (task_id) VALUES (?)", ("x",))
"""

DEAD_LAMBDA = """
import spool.writer as _spool_writer


def create_thing(conn):
    _unused = lambda: _spool_writer.write_event({"a": 1})  # noqa: E731
    conn.execute("INSERT INTO business_tasks (task_id) VALUES (?)", ("x",))
"""

LIVE_NESTED_HELPER = """
import spool.writer as _spool_writer


def create_thing(conn):
    def _emit():
        _spool_writer.write_event({"a": 1})

    _emit()
    conn.execute("INSERT INTO business_tasks (task_id) VALUES (?)", ("x",))
"""


@pytest.mark.parametrize(
    "name,source",
    [
        ("param named writer", SHADOWED_BY_PARAM_WRITER),
        ("param named spool", SHADOWED_BY_PARAM_SPOOL),
        ("local named _spool_writer", SHADOWED_BY_LOCAL),
        ("no import at all", NO_IMPORT_AT_ALL),
        ("rebound at module level", SHADOWED_AT_MODULE_LEVEL),
        ("rebound by a for target", SHADOWED_BY_FOR_TARGET),
        ("rebound by a with-as", SHADOWED_BY_WITH_AS),
        ("dead nested helper", DEAD_NESTED_HELPER),
        ("dead lambda", DEAD_LAMBDA),
    ],
)
def test_a_receiver_that_is_not_the_imported_writer_is_still_reported(tmp_path, name, source):
    """Provenance, not spelling. Each of these emits nothing and must be reported.

    A name-only allowlist passed all of the first three. The direction of that error is
    the unsafe one — the gate blessing a row no replay can rebuild — which is the single
    mistake this gate must not make, and it would have made it while reading as fixed.
    """
    repo = _repo(tmp_path, {"x.py": source})
    flagged = [item["function"] for item in ebw.offenders(repo)["offenders"]]

    assert "create_thing" in flagged, f"{name}: emits nothing but was not reported ({flagged})"


def test_a_nested_helper_that_is_actually_called_still_counts(tmp_path):
    """The other direction, or the nested fix is just "nesting is never an emission".

    Excluding nested scopes must not mean a real closure stops counting. `_emit` is
    defined inside `create_thing` AND invoked, so the outer function reaches an emission
    — through the call graph, which is the thing that actually answers the question, not
    through lexical nesting, which does not.
    """
    repo = _repo(tmp_path, {"live.py": LIVE_NESTED_HELPER})

    assert ebw.offenders(repo)["offenders"] == []


def test_an_unrelated_object_named_write_event_does_not_count_as_an_emission(tmp_path):
    """The false negative an independent reviewer constructed against this gate.

    `logger.write_event(...)` on a telemetry object is not the spool writer. Counting it
    would have the gate bless a row no replay can rebuild — the single error this gate
    exists to prevent, committed by the gate itself. The text match this replaced had the
    same hole.
    """
    repo = _repo(tmp_path, {"telemetry.py": UNRELATED_RECEIVER})
    flagged = [item["function"] for item in ebw.offenders(repo)["offenders"]]

    assert "create_thing" in flagged, (
        "a write whose only 'emission' is an unrelated object's method must still be "
        f"reported; got {flagged}"
    )


def test_the_real_module_alias_receiver_does_count(tmp_path):
    """The other direction: the spelling production actually uses must be recognised.

    Guards against fixing the false negative by making the check so strict that the real
    call site stops counting — which would flag the entire tree.
    """
    repo = _repo(tmp_path, {"real.py": MODULE_ALIAS_RECEIVER})

    assert ebw.offenders(repo)["offenders"] == []


def test_calling_a_helper_that_does_not_emit_is_still_reported(tmp_path):
    """Show it going red: resolution must not become 'any function call counts'.

    Without this, the previous two tests would pass against a check that treats every
    call as an emission — which would silence the gate entirely while reading as a fix.
    """
    repo = _repo(tmp_path, {"quiet.py": HELPER_THAT_DOES_NOT_EMIT})
    flagged = [item["function"] for item in ebw.offenders(repo)["offenders"]]

    assert "create_thing" in flagged, (
        "a function whose only call is a non-emitting helper must still be reported; "
        f"got {flagged}"
    )
