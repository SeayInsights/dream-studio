"""The enforce decision is a contract, and any implementation must satisfy it.

`on-edit-enforce` runs on EVERY Edit, Write, MultiEdit and Bash call, and it can
say no. A second implementation -- the Rust port, taken on because 57 of its
98 ms is Python interpreter start plus stdlib import and nothing else is left to
remove -- is only safe if it decides identically. A blocking hook that disagrees
denies real work, on a path with no error message to read.

So the decision is pinned here as a TABLE. Any implementation, in any language,
must produce the same verdict for every row.

EVERY ROW WAS DISCOVERED FROM THE IMPLEMENTATION, NOT ASSUMED. The first draft
of this file was written from what the functions sounded like they did and
failed 14 of its 24 cases: `classify_path` takes a project root and calls
`tests/**` "source" (not "test") and README.md "source" (not "doc");
`extract_write_targets` returns a *tuple*; `.planning` classifies as
"docstore_only". A contract written from the name of a function is not a
contract, and hand-copying one into a second language is how two
implementations drift while both look tested.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from runtime.lib import enforcement

PROJECT = tempfile.mkdtemp()


def _p(rel: str) -> str:
    return f"{PROJECT}/{rel}"


# --- the tier ladder --------------------------------------------------------

TIER_CASES = [
    ({}, "enforce", "unset stays on"),
    ({"DS_ENFORCE": "0"}, "off", "the documented form"),
    ({"DS_ENFORCE": "off"}, "off", "same control, named"),
    ({"DS_ENFORCE": "observe"}, "observe", "record, then allow"),
    ({"DS_ENFORCE": "warn"}, "warn", "surface, then allow"),
    ({"DS_ENFORCE": "yes"}, "enforce", "unrecognized fails safe"),
    ({"DS_ENFORCE_TIER": "observe"}, "observe", "deprecated var still honoured"),
    ({"DS_ENFORCE": "0", "DS_ENFORCE_TIER": "enforce"}, "off", "new var wins"),
]


@pytest.mark.parametrize("env,expect,why", TIER_CASES)
def test_tier_resolution_contract(env, expect, why, monkeypatch):
    for k in ("DS_ENFORCE", "DS_ENFORCE_TIER"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert enforcement.resolve_tier() == expect, why


# --- path classification ----------------------------------------------------
#
# Observed, not assumed. Note that "source" is the DEFAULT: anything that is not
# docs and not the docstore-only tree is treated as source, including tests and
# README.md. That is what decides which rule applies, so a port that narrows it
# would stop enforcing on files this one covers.

CLASSIFY_CASES = [
    ("core/config/paths.py", "source"),
    ("interfaces/cli/ds.py", "source"),
    ("tests/unit/test_x.py", "source"),
    ("README.md", "source"),
    ("notes.txt", "source"),
    ("docs/DATABASE.md", "doc"),
    (".planning/work-orders/x.md", "docstore_only"),
    (".planning/personal/notes.md", "docstore_only"),
]


@pytest.mark.parametrize("rel,expect", CLASSIFY_CASES)
def test_path_classification_contract(rel, expect):
    assert enforcement.classify_path(_p(rel), PROJECT) == expect


# --- boundary parsing -------------------------------------------------------
#
# boundary_globs reads a WORK ORDER DESCRIPTION, not a bare glob: it looks for a
# "Module boundary: a, b, c." clause. Passing anything else yields [], and [] is
# not "matches nothing" -- see the next test, which is the important one.

BOUNDARY_PARSE_CASES = [
    ("Module boundary: core, docs.", ["core", "docs"]),
    ("Module boundary: core/config/paths.py.", ["core/config/paths.py"]),
    ("no clause here at all", []),
    ("", []),
]


@pytest.mark.parametrize("desc,expect", BOUNDARY_PARSE_CASES)
def test_boundary_parsing_contract(desc, expect):
    assert enforcement.boundary_globs(desc) == expect


def test_an_undeclared_boundary_claims_every_file():
    """THE BEHAVIOUR BEHIND THE NOISE, pinned so a port reproduces it knowingly.

    path_in_boundary returns True when the glob list is empty -- deliberate, per
    its own docstring ("or no boundary is declared"). Measured on the live
    authority 2026-09-21: 56 work orders in progress, 28 of them declaring no
    parseable boundary, and therefore each one claiming every file in the repo.

    That is why a stop message can name two dozen work orders as "covering" a
    single edited file. Pinned rather than quietly fixed, because changing it is
    a decision about enforcement, not a refactor -- and a port that silently
    decided the other way would start denying edits this one allows.
    """
    assert enforcement.path_in_boundary(_p("anything/at/all.py"), PROJECT, []) is True


BOUNDARY_MATCH_CASES = [
    (["core"], "core/config/paths.py", True, "a declared subtree covers its files"),
    (["core"], "interfaces/cli/ds.py", False, "and nothing outside it"),
    (["core/config/paths.py"], "core/config/paths.py", True, "an exact file matches"),
    # FIXED 2026-09-21, and this row is how it stays fixed. enforcement.py used to
    # accept a DIRNAME match for any boundary containing a "/", so declaring one file
    # silently claimed its whole directory. Measured against one edited test file on
    # the live authority: 24 in-progress work orders claimed it, 15 of them ONLY
    # through that widening -- each having declared a single, different test file.
    # Removing it took that file's claimants from 24 to 9.
    #
    # A work order that owns a directory declares the directory.
    (
        ["core/config/paths.py"],
        "core/config/other.py",
        False,
        "a declared FILE claims that file, not its neighbours",
    ),
    (["core/config/paths.py"], "interfaces/cli/ds.py", False, "but not another directory"),
]


@pytest.mark.parametrize("globs,rel,expect,why", BOUNDARY_MATCH_CASES)
def test_boundary_matching_contract(globs, rel, expect, why):
    assert enforcement.path_in_boundary(_p(rel), PROJECT, globs) is expect, why


# --- write targets extracted from a Bash command ----------------------------
#
# Returns (targets, saw_redirect). The hook inspects Bash too, so a port that
# finds different targets lets edits through the door this exists to watch.

BASH_CASES = [
    ("echo hi > out.txt", ["out.txt"]),
    ("echo hi >> out.txt", ["out.txt"]),
    ("cat a.txt", []),
    ("ls -la", []),
]


@pytest.mark.parametrize("cmd,expect", BASH_CASES)
def test_bash_write_target_contract(cmd, expect):
    targets, _flag = enforcement.extract_write_targets(cmd)
    if expect:
        for e in expect:
            assert any(e in t for t in targets), f"{cmd!r}: expected {e}, got {targets}"
    else:
        assert not targets, f"{cmd!r}: expected none, got {targets}"


def test_the_contract_is_machine_readable():
    """A second implementation consumes these rows instead of re-deriving them.

    Set DS_ENFORCE_CONTRACT_OUT to a path and the table is written as JSON, so
    the Rust port's own tests read the same rows this file asserts rather than a
    translation someone typed twice.
    """
    contract = {
        "tiers": [{"env": e, "expect": x} for e, x, _ in TIER_CASES],
        "classify": [{"path": p, "expect": k} for p, k in CLASSIFY_CASES],
        "boundary_parse": [{"desc": d, "expect": e} for d, e in BOUNDARY_PARSE_CASES],
        "boundary_match": [
            {"globs": g, "path": p, "expect": e} for g, p, e, _ in BOUNDARY_MATCH_CASES
        ],
        "undeclared_boundary_matches_everything": True,
        "bash": [{"cmd": c, "expect": e} for c, e in BASH_CASES],
    }
    blob = json.dumps(contract, indent=2, sort_keys=True)
    assert json.loads(blob) == contract
    out = os.environ.get("DS_ENFORCE_CONTRACT_OUT")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(blob)
