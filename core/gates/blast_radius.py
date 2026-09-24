"""Blast-radius merge gate (WO-BLAST-RADIUS-GATE).

pr-smoke runs a fixed subset of tests; the full suite that catches stale tests
and contract violations runs only post-merge and blocks nothing. That gap let
main go red for 11 consecutive merges (#347 stale shared-intelligence tests,
#353 handoff signature caller, #354 token_projection ownership violation).

This module closes the gap at merge time. From the diff it:

  1. computes the IMPACT SET — the dependent pytest nodes that must run before
     merge (a changed test runs itself; a changed source module pulls in every
     test that imports/references it), plus the impacted contract domains
     (reusing contract_registry.change_impact_report); and
  2. runs NOTHING-LEFT-HANGING detectors for the blast-radius-bigger-than-fix
     case — stale tests, broken callers, and authority/ownership violations that
     the fix's own change set leaves behind (see hanging_detectors.py).

`compute_impact_set` is pure and deterministic (no DB, no network) so the gate
can run identically in pre-push and in the pr-smoke matrix.

TEXT MATCHING IS BLIND TO SEVERAL IMPORT SHAPES, so a third selector walks an
AST-built import graph and adds their dependents (see ``_build_import_graph`` /
``_ancestor_hops``):

  - ``from pkg import mod`` splits a changed module's dotted path across two tokens
    -- ``pkg`` then ``mod``, joined by the word ``import`` -- and the literal
    substring ``pkg.mod`` the regex rule needs never appears. A change to
    ``core/gates/pre_push.py`` did not select ``tests/unit/gates/
    test_pre_push_outcome_event.py``, which does exactly
    ``from core.gates import pre_push``; pr-smoke stayed green on all three
    platforms with that test broken.
  - a FACADE -- a package ``__init__.py`` that does ``from .impl import helper`` --
    re-exports a name without its wrapped module's dotted path ever appearing in a
    test that imports the package instead of the module. Measured to put main red
    twice before this.
  - a CONFTEST FIXTURE -- a conftest.py that imports a module and exposes it as a
    fixture (tests/conftest.py's own autouse ``guard_real_homedir`` does this) --
    reaches a consuming test through pytest's collection machinery, not an import
    statement, so no AST edge connects them either. Handled by directory scope
    rather than by resolving fixture names (see ``_conftest_scope_tests``).

These are relationships an AST sees and a regex cannot, so they are resolved by
walking the graph rather than by adding more patterns.

KNOWN OPEN GAP, NOT FIXED HERE: a module-level ``__getattr__`` doing a runtime
``importlib.import_module(name)`` (PEP 562 lazy re-export -- see
``core/work_orders/start.py``, whose ``_require_db``/``read_work_order_brief``/
``write_work_order_context`` are re-exported this way, deliberately, so a test's
``patch()`` sees the live sibling rather than a frozen first-import snapshot)
produces NO graph edge at all: the target module is a runtime string, not an
``ast.Import``/``ast.ImportFrom`` node. Measured on this repository:
``core.work_orders.start`` has static edges to ``.start_main`` and ``.start_shared``
only; ``.start_brief`` and ``.start_context`` -- both re-exported dynamically -- have
none, from that facade. Tests that patch them by their sibling-module dotted string
(``patch("core.work_orders.start_brief...")``) still get selected through the
pre-existing text-matching rule, which is why this has not been the source of a
measured red main the way the other two were; a test that reaches them ONLY through
``core.work_orders.start`` with no literal sibling-module string anywhere in it would
not be selected by either rule. Resolving a runtime ``importlib.import_module(name)``
call in general requires dataflow analysis this module does not do; flagged rather
than special-cased for one file.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import networkx as nx

REPO_ROOT = Path(__file__).resolve().parents[2]

BLAST_RADIUS_GATE_SCHEMA = "dream_studio.blast_radius_gate.v1"


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip()


def _is_test_file(path: str) -> bool:
    p = _normalize(path)
    return p.startswith("tests/") and p.endswith(".py") and Path(p).name.startswith("test_")


def _module_tokens(source_path: str) -> set[str]:
    """Dotted module path(s) a source file is importable as.

    ``core/foo/bar.py`` → ``{"core.foo.bar"}``.
    ``core/foo/__init__.py`` → ``{"core.foo.__init__", "core.foo"}``.
    """
    p = _normalize(source_path)
    if not p.endswith(".py"):
        return set()
    mod = p[:-3].replace("/", ".")
    tokens = {mod}
    if mod.endswith(".__init__"):
        tokens.add(mod[: -len(".__init__")])
    return tokens


def _iter_test_files(repo_root: Path) -> Iterable[Path]:
    tests_dir = repo_root / "tests"
    if not tests_dir.is_dir():
        return
    yield from tests_dir.rglob("test_*.py")


#: Directories that can never hold an importable module: VCS/build internals, not
#: application or test code. Skipped so none of them can become a spurious graph node.
_IMPORT_GRAPH_SKIP_DIRS = frozenset(
    {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv"}
)

#: Hops the import-graph closure SELECTS on before it stops counting a test as
#: dependent. The search itself is always unbounded (see ``_ancestor_hops``); this
#: only draws the line between "selected" and "truncated, and counted".
#:
#: MEASURED ON THIS REPOSITORY, 695 test files total, and the numbers argue against
#: any finite bound ever being "enough": core/gates/pre_push.py went from 9 tests
#: (text matching) to 332 (48%) unbounded; core/work_orders/task_status.py from 4 to
#: 425 (61%); core/work_orders/start_brief.py -- picked because its own facade,
#: core/work_orders/start.py, re-exports it through a PEP-562 ``__getattr__`` this
#: graph cannot see at all (a separate, open gap -- see the module docstring) -- has
#: real test ancestors at EVERY hop count from 1 to 21, not clustered near the front:
#: 3 tests at hop 1, 3 at hop 2, 8 at hop 3, 2 at hop 4, climbing back up to 63 at hop
#: 8 and 51 at hop 13. A first version of this bound claimed "a full hop of margin
#: past both measured failure modes" -- wrong: it was measured against two
#: hand-built scenarios, not the repository's real chains, several of which sit at
#: exactly hop 3 already. There is no bound that leaves real margin here; past a few
#: hops this repo's import graph is close to fully connected, so raising the number
#: only moves where the truncation happens, never removes it.
#:
#: SO THE BOUND STOPS THE SELECTION FROM BALLOONING (protecting the pr-smoke job's
#: cost -- 127 files already measured at 12m05s against a 25-minute budget) AND THE
#: TRUNCATION IS COUNTED, NOT ASSUMED AWAY: every ``compute_impact_set`` result
#: reports ``import_graph_truncated_test_count``, the number of real test ancestors
#: this bound cut off, and both CLI entry points print it when it is nonzero. A
#: silent bound is the defect (a human trusting "the closure caught it" with no way
#: to tell); a bound that admits what it dropped is the fix.
IMPORT_GRAPH_MAX_DEPTH: int | None = 3

#: Cache value: (tree fingerprint at build time, module index, import graph). The
#: fingerprint is what makes reuse safe -- see ``_tree_fingerprint`` and
#: ``_cached_import_graph``.
_IMPORT_GRAPH_CACHE: dict[str, tuple[tuple, dict[str, str], nx.DiGraph]] = {}


def _file_to_module(rel_path: str) -> str:
    """The single dotted name a file answers to as an import target.

    ``core/foo/bar.py`` -> ``core.foo.bar``. ``core/foo/__init__.py`` -> ``core.foo``:
    the package's own file is what ``import core.foo`` and ``from core.foo import x``
    both name, so it is indexed under the bare package name, not ``core.foo.__init__``
    (nothing ever imports that).
    """
    mod = rel_path[:-3].replace("/", ".")
    if mod.endswith(".__init__"):
        mod = mod[: -len(".__init__")]
    return mod


def _relative_base(module: str, rel_path: str, level: int) -> str | None:
    """The package a relative import's leading dots resolve against, or None if the
    dots climb past the repository root.

    Level 1 is the importing module's OWN package: itself, for a package's
    ``__init__.py`` (the file that answers for the package), or its parent, for an
    ordinary module -- Python resolves a relative import against the *package*, and
    only ``__init__.py`` is one. Each further dot climbs one more parent.
    """
    is_pkg = rel_path == "__init__.py" or rel_path.endswith("/__init__.py")
    base = module if is_pkg else (module.rsplit(".", 1)[0] if "." in module else "")
    for _ in range(level - 1):
        if not base:
            return None
        base = base.rsplit(".", 1)[0] if "." in base else ""
    return base


def _imported_targets(node: ast.AST, *, module: str, rel_path: str, known: set[str]) -> set[str]:
    """Repo modules a single import statement depends on, resolved to dotted names.

    ``import a.b.c`` names its target directly. ``from a.b import c`` is ambiguous
    from the statement alone: ``c`` is a submodule (``a.b.c``) when that file exists
    in this repository, and otherwise a name ``a.b`` defines or re-exports -- a
    function, a class, or (the facade case) another module's symbol threaded through
    an ``__init__.py`` -- in which case the dependency is on ``a.b`` itself. ``known``
    (every module this repository defines, from ``_build_module_index``) is what
    tells the two apart. Relative imports are resolved to an absolute dotted base
    first (``_relative_base``) so the same rule then applies to both.
    """
    targets: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            targets.add(alias.name)
        return targets
    if not isinstance(node, ast.ImportFrom):
        return targets

    if node.level:
        base = _relative_base(module, rel_path, node.level)
        if base is None:
            return targets
        if node.module:
            base = f"{base}.{node.module}" if base else node.module
    else:
        base = node.module or ""
    if not base:
        return targets

    for alias in node.names:
        name = alias.name
        if name == "*":
            # A star import pulls in the whole module; there is no name to resolve
            # against `known`, so the dependency is on the module itself.
            targets.add(base)
            continue
        candidate = f"{base}.{name}"
        targets.add(candidate if candidate in known else base)
    return targets


def _iter_repo_python_files(repo_root: Path) -> Iterable[Path]:
    """Every .py file the import graph can consider, VCS/build internals excluded.

    Shared by the module index, the graph build, and the cache fingerprint below --
    the same walk was being repeated with the same skip-list; one definition is one
    place for that list to be right.
    """
    for path in repo_root.rglob("*.py"):
        if any(part in _IMPORT_GRAPH_SKIP_DIRS for part in path.parts):
            continue
        yield path


def _build_module_index(repo_root: Path) -> dict[str, str]:
    """Every importable module this repository defines, mapped to its file."""
    index: dict[str, str] = {}
    for path in _iter_repo_python_files(repo_root):
        rel = _normalize(str(path.relative_to(repo_root)))
        index[_file_to_module(rel)] = rel
    return index


def _tree_fingerprint(repo_root: Path) -> tuple[tuple[str, int, int], ...]:
    """A cheap stand-in for "has anything in this tree changed since the graph was
    built", so the cache below can detect a stale answer instead of assuming there
    isn't one.

    ``compute_impact_set``'s own docstring promises it is pure and deterministic; a
    cache keyed on repo root ALONE breaks that promise for any caller that builds
    the graph, the checkout changes on disk, and it builds again in the same
    process -- the second call would silently return the first call's answer.
    Stats every file rather than re-reading and re-parsing it (the cost the cache
    exists to avoid): path, mtime, and size are what changes when a file is edited,
    added, or removed, and comparing them costs a directory walk, not 1696 AST
    parses.
    """
    stamps: list[tuple[str, int, int]] = []
    for path in _iter_repo_python_files(repo_root):
        try:
            st = path.stat()
        except OSError:
            continue
        rel = _normalize(str(path.relative_to(repo_root)))
        stamps.append((rel, st.st_mtime_ns, st.st_size))
    return tuple(sorted(stamps))


def _build_import_graph(repo_root: Path) -> tuple[dict[str, str], nx.DiGraph]:
    """(module -> file, directed graph of module -> the repo modules it imports).

    Built with ``ast`` rather than by importing anything: the same purity
    ``compute_impact_set`` already promises (no DB, no network, no executing the
    tree being scanned) applies here, and a file that fails to parse is skipped
    rather than aborting the whole graph -- one bad file must not blind the gate to
    every other change.

    NOT BUILT ON TOP OF THE TWO EXISTING AST/GRAPH TOOLS IN THIS REPOSITORY, checked
    and rejected rather than overlooked:

    - ``core/graph/query_traversal.py`` (``build_graph`` / ``get_dependents``) IS a
      cached, depth-bounded dependents query over an ``nx.DiGraph`` -- exactly this
      shape -- but its graph comes from the ``pi_components``/``pi_dependencies``
      tables in studio.db (``core/graph/query_shared.py``), pre-indexed by a separate
      job and cached with a 5-minute TTL keyed on that index's own timestamp, not on
      the current git tree. Building on it would mean either giving
      ``compute_impact_set`` a hard DB dependency it does not otherwise have, or
      trusting a graph that can be stale relative to the diff being gated -- the
      exact defect class ``_cached_import_graph``'s fingerprint above exists to rule
      out for THIS graph. networkx itself (the traversal library, not this module) is
      shared -- see ``_ancestor_hops``.
    - ``core/org_intelligence/ingestor.py`` (``RepoParser._parse_file``) also walks
      ``ast.Import``/``ast.ImportFrom`` nodes, but resolves each ``ImportFrom`` to
      bare ``node.module`` with no disambiguation between a submodule and a
      re-exported member (``from core.gates import pre_push`` records the edge as
      ``core.gates``, never ``core.gates.pre_push``) and drops relative imports
      whose ``node.module`` is ``None`` entirely (``from . import x``). Both are
      exactly the gaps this module exists to close (see the module docstring), so
      reusing it here would silently reintroduce them. It is also deliberately
      decoupled from ``core.gates`` ("avoids importing main runtime internals", its
      own docstring) for the org-intelligence tool's cross-repo portability, a
      boundary this module has no reason to cross for a one-repository gate.
    """
    module_index = _build_module_index(repo_root)
    known = set(module_index)
    graph: nx.DiGraph = nx.DiGraph()
    graph.add_nodes_from(known)
    for module, rel in module_index.items():
        try:
            tree = ast.parse((repo_root / rel).read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for target in _imported_targets(node, module=module, rel_path=rel, known=known):
                if target in known and target != module:
                    graph.add_edge(module, target)
    return module_index, graph


def _cached_import_graph(repo_root: Path) -> tuple[dict[str, str], nx.DiGraph]:
    """Built once per resolved repo root and tree state, then reused.

    Every real caller (pre_push, impact_tests_gate, and the CI steps that invoke
    them) is a fresh process making exactly one ``compute_impact_set`` call. The case
    this cache is FOR is this repository's own test suite, which calls
    ``compute_impact_set`` against ``REPO_ROOT`` many times in one pytest session
    (the PR replays in test_impact_tests_gate.py) -- without it, each of those calls
    re-walks and re-parses the whole tree.

    The fingerprint check is what makes this safe rather than merely usually-safe: a
    stale cache is silently WRONG, not just slow, so a resolved-root key alone was
    the wrong contract to sign given ``compute_impact_set``'s own "pure and
    deterministic" claim. Recomputing the fingerprint costs one directory walk with a
    ``stat`` per file (no read, no parse), so a cache hit still means skipping the
    expensive part -- 1696 files parsed -- not skipping the walk that proves it is
    still safe to.
    """
    root = Path(repo_root)
    key = str(root.resolve())
    fingerprint = _tree_fingerprint(root)
    cached = _IMPORT_GRAPH_CACHE.get(key)
    if cached is None or cached[0] != fingerprint:
        cached = (fingerprint, *_build_import_graph(root))
        _IMPORT_GRAPH_CACHE[key] = cached
    return cached[1], cached[2]


def _ancestor_hops(changed: set[str], graph: nx.DiGraph) -> dict[str, int]:
    """Hop-distance from the nearest module in ``changed`` to every module whose
    forward-import chain reaches it -- UNBOUNDED.

    Traversal over the already-built, in-memory graph is cheap regardless of depth
    (milliseconds, measured on this repository's ~3600-edge graph even for the
    most-connected modules in it), so nothing is saved by bounding the SEARCH.
    Bounding the search is also how a truncation goes silent: a cutoff BFS simply
    never visits what lies past it, so there is nothing left to report having
    dropped. Computing the full distance map instead is what lets
    ``compute_impact_set`` draw the ``IMPORT_GRAPH_MAX_DEPTH`` line itself AND count
    exactly what fell on the far side of it.

    Ancestors of ``changed`` in the import graph are descendants of ``changed`` in
    the REVERSED graph (``.reverse(copy=False)`` is an O(E) view, not a copy).
    """
    if not changed:
        return {}
    reverse = graph.reverse(copy=False)
    hops: dict[str, int] = {}
    for module in changed:
        if module not in reverse:
            continue
        for node, dist in nx.single_source_shortest_path_length(reverse, module).items():
            if node in changed:
                continue
            if node not in hops or dist < hops[node]:
                hops[node] = dist
    return hops


def _is_conftest_file(rel_path: str) -> bool:
    return Path(_normalize(rel_path)).name == "conftest.py"


def _conftest_scope_tests(repo_root: Path, conftest_rel_path: str) -> set[str]:
    """Every test file pytest hands this conftest.py's fixtures to.

    FIXTURE INJECTION IS A DEPENDENCY EDGE THE AST GRAPH CANNOT SEE. A conftest.py
    can import a module and expose it through a fixture -- tests/conftest.py's own
    autouse ``guard_real_homedir`` fixture does exactly this -- and a test consuming
    that fixture writes no import statement naming the module at all; pytest wires
    them together by fixture name at collection time, not by anything ``ast`` can
    see. Modeling that precisely would mean resolving which fixture a test actually
    requests, name by name. Instead this is conservative but correct: pytest already
    scopes a conftest.py's fixtures to every test AT OR BELOW its own directory
    (never siblings, never a parent's directory), so that directory scope is used
    directly -- every test in it is selected, whether or not it uses the fixture
    the changed import feeds.
    """
    conftest_dir = (repo_root / conftest_rel_path).parent
    return {_normalize(str(p.relative_to(repo_root))) for p in conftest_dir.rglob("test_*.py")}


def compute_impact_set(
    changed_files: Iterable[str],
    *,
    repo_root: Path | str = REPO_ROOT,
) -> dict[str, Any]:
    """Map changed files to the dependent test set and impacted contract domains.

    Returns a dict::

        {
          "changed_files": [...normalized...],
          "dependent_tests": [...pytest file paths, sorted...],
          "impacted_contract_domains": [...domain_id...],
          "module_tokens": [...dotted modules the source changes expose...],
          "import_graph_truncated_test_count": N,  # real ancestors past the depth bound
        }

    Selection rules:
      - a changed test file selects itself;
      - a changed ``.py`` source file selects every ``tests/**/test_*.py`` whose
        text references its dotted module path (word-boundary match, so
        ``core.foo.bar`` does not match ``core.foo.barbaz`` but does match
        ``core.foo.bar.do_thing`` and ``from core.foo.bar import ...``);
      - a changed hook (a ``.py`` whose stem is hyphenated, so it has no importable
        module path) also selects every test whose text names its file stem
        (``on-token-log``), which is how tests load hooks;
      - a changed file under ``canonical/skills/<pack>/`` selects every test whose text
        names that pack as a string literal (``"ds-project"``), because tests about packs
        build their paths from parts rather than writing them out;
      - any other changed file selects every test whose text names its
        repo-relative path (``canonical/rules.yml``), the same way;
      - ADDITIVELY, a changed ``.py`` source module also selects every test that
        imports it through the repository's import graph -- directly, through
        ``from pkg import mod``, through a facade ``__init__.py``, or through a
        chain of any of those up to ``IMPORT_GRAPH_MAX_DEPTH`` hops -- which the
        text rule above cannot see (see the module docstring). A real ancestor
        PAST that bound is not silently dropped: it is counted in
        ``import_graph_truncated_test_count``;
      - and a changed module reached ONLY through a conftest.py -- a fixture the
        conftest builds by importing the module, with no import statement in the
        test that uses the fixture -- selects every test in that conftest's
        directory scope (see ``_conftest_scope_tests``).
    """
    root = Path(repo_root)
    changed = sorted({_normalize(f) for f in changed_files if f})

    dependent: set[str] = set()
    module_tokens: set[str] = set()
    #: Pack names, matched as string literals rather than as words. Kept apart from
    #: module_tokens because those are matched with a trailing word boundary, which a
    #: closing quote can never satisfy.
    quoted_tokens: set[str] = set()
    for f in changed:
        if _is_test_file(f):
            dependent.add(f)
        elif f.endswith(".py"):
            module_tokens.update(_module_tokens(f))
            # A HOOK IS NOT IMPORTABLE, SO ITS MODULE TOKEN MATCHES NOTHING. runtime/hooks/
            # meta/on-token-log.py yields `runtime.hooks.meta.on-token-log`, a dotted path
            # no test can write. Tests load hooks by file stem -- handler("on-token-log"),
            # 32 files do -- so the stem is the token that reaches them. Replayed on #738,
            # which moved that hook's status to stderr: its own integration test read
            # stdout, was not selected, and main went red on exactly that test.
            stem = f.rsplit("/", 1)[-1][: -len(".py")]
            if "-" in stem:
                module_tokens.add(stem)
            # AND THE PATH ITSELF, for the tests that read source as text rather than
            # importing it: gate guards, AST walkers, drift checks. They name the file the
            # only way they can -- `interfaces/cli/commands/work_order_dispatch.py` -- and
            # a dotted module token never matches that. Both other branches below already
            # add the path; this one stopped at the module, on the assumption that a test
            # depending on a source file imports it.
            module_tokens.add(f)
        elif f.startswith("canonical/skills/") and len(f.split("/")) > 2:
            # A SKILL FILE SELECTS THE TESTS THAT NAME ITS PACK. Tests about packs build
            # their paths from parts -- REPO_ROOT / "canonical" / "skills" / "ds-project"
            # -- or name the pack alone, so the repo-relative path never appears and the
            # data-file rule below reaches none of them. Eight tests went red on main
            # across two dissolutions for this reason.
            #
            # The pack name is added QUOTED, because a test naming a pack writes a string
            # literal. Measured over 683 test files: bare `core` appears in 522 of them
            # and `"core"` in 89, while `"website"` selects 8. The bare form would make a
            # one-pack edit select the whole suite.
            quoted_tokens.add(f.split("/")[2])
            # The path still counts, for the tests that do write it out.
            module_tokens.add(f)
        else:
            # A DATA FILE IS A DEPENDENCY TOO. Replayed on the change that edited
            # canonical/rules.yml and broke two tests naming that path three times, this
            # set held neither of them: only .py changes produced tokens, so a test that
            # reads a registry, a manifest or a pack file was unreachable through the file
            # it reads. The token is the repo-relative path, matched exactly as a module
            # name is. (A test that builds the path from parts is not reached this way;
            # that limit is real and is the reason the sweep tests also always run.)
            module_tokens.add(f)

    if module_tokens or quoted_tokens:
        patterns = [re.compile(re.escape(tok) + r"\b") for tok in module_tokens]
        # No trailing \b for these: the token ends in a quote, and a boundary between a
        # quote and whatever follows it is not one the engine will ever find.
        patterns += [re.compile(f"[\"']{re.escape(tok)}[\"']") for tok in quoted_tokens]
        for test_path in _iter_test_files(root):
            rel = _normalize(str(test_path.relative_to(root)))
            if rel in dependent:
                continue
            try:
                text = test_path.read_text(encoding="utf-8")
            except OSError:
                continue
            if any(pat.search(text) for pat in patterns):
                dependent.add(rel)

    # IMPORT-GRAPH CLOSURE -- see the module docstring for the shapes text matching
    # above cannot see (`from pkg import mod`, a facade `__init__.py`, and a
    # conftest.py fixture). `module_tokens` already holds every dotted module a
    # changed .py source file exposes (test files are excluded from it above), so no
    # second pass over `changed` is needed to find the graph's starting set. Gated on
    # `module_tokens` so a non-.py-only or empty change set never pays for the
    # whole-repo AST walk.
    truncated_test_count = 0
    #: conftest.py files reached by this change, whose test-directory SCOPE (not
    #: just the conftest file itself) must be unioned in below -- both a changed
    #: conftest.py directly and one found while walking the import-graph ancestors.
    conftest_hits = {f for f in changed if _is_conftest_file(f)}
    if module_tokens:
        module_index, import_graph = _cached_import_graph(root)
        known_changed = module_tokens & set(module_index)
        if known_changed:
            for ancestor, hops in _ancestor_hops(known_changed, import_graph).items():
                rel = module_index[ancestor]
                is_conftest = _is_conftest_file(rel)
                if _is_test_file(rel):
                    target = dependent
                elif is_conftest:
                    target = conftest_hits
                else:
                    continue
                # ONE enforcement point for "is this ancestor within the depth
                # bound, and must its exclusion be counted" -- a second, separately
                # maintained copy of this decision is exactly what let the
                # conftest branch silently drop past-bound ancestors from both
                # selection and the count while the test-file branch counted them.
                if IMPORT_GRAPH_MAX_DEPTH is None or hops <= IMPORT_GRAPH_MAX_DEPTH:
                    target.add(rel)
                elif is_conftest:
                    # A truncated conftest ancestor can gate its entire directory
                    # scope (_conftest_scope_tests), not just itself -- counting a
                    # flat 1 here undercounts by however many test files that
                    # directory holds, exactly as badly as not counting at all.
                    # This walk is filesystem-only, not import-graph depth, so it
                    # is safe to run even though the conftest itself was excluded.
                    truncated_test_count += max(1, len(_conftest_scope_tests(root, rel)))
                else:
                    truncated_test_count += 1
    for rel in conftest_hits:
        dependent.update(_conftest_scope_tests(root, rel))

    impacted_domains: list[str] = []
    try:
        from core.shared_intelligence.contract_registry import change_impact_report

        report = change_impact_report(changed)
        impacted_domains = [d["domain_id"] for d in report["domains"] if d["impacted"]]
    except Exception:
        impacted_domains = []

    return {
        "changed_files": changed,
        "dependent_tests": sorted(dependent),
        "impacted_contract_domains": impacted_domains,
        "module_tokens": sorted(module_tokens),
        "import_graph_truncated_test_count": truncated_test_count,
    }


def evaluate(
    diff_text: str,
    changed_files: Iterable[str],
    *,
    repo_root: Path | str = REPO_ROOT,
) -> dict[str, Any]:
    """Run the merge-time blast-radius gate. Pure — no git, no exit.

    Returns a report dict with ``status`` ``"pass"``/``"fail"``. Status is
    ``"fail"`` when any nothing-left-hanging detector fires; the impact set is
    always included so the matrix step can run the dependent tests.
    """
    from core.gates.hanging_detectors import run_all_detectors

    findings = run_all_detectors(diff_text, repo_root=repo_root)
    impact = compute_impact_set(changed_files, repo_root=repo_root)
    return {
        "schema": BLAST_RADIUS_GATE_SCHEMA,
        "status": "fail" if findings else "pass",
        "blocking_finding_count": len(findings),
        "findings": findings,
        "impact_set": impact,
    }


def _git(args: list[str], repo_root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def _resolve_diff_and_changed(repo_root: Path, base_ref: str | None) -> tuple[str, list[str]]:
    """Resolve the unified diff text and changed-file list against the base ref."""
    if base_ref:
        rng = f"{base_ref}...HEAD"
        diff_text = _git(["diff", rng], repo_root)
        names = _git(["diff", "--name-only", rng], repo_root)
        if diff_text or names:
            return diff_text, [ln.strip() for ln in names.splitlines() if ln.strip()]
    # Fallback: staged + working-tree changes.
    diff_text = _git(["diff", "HEAD"], repo_root)
    names = _git(["diff", "--name-only", "HEAD"], repo_root)
    return diff_text, [ln.strip() for ln in names.splitlines() if ln.strip()]


def main() -> int:
    base_ref = os.environ.get("DREAM_STUDIO_BASE_REF")
    github_base = os.environ.get("GITHUB_BASE_REF")
    if github_base and not base_ref:
        base_ref = f"origin/{github_base}"
    if not base_ref:
        base_ref = "origin/main"

    diff_text, changed = _resolve_diff_and_changed(REPO_ROOT, base_ref)
    report = evaluate(diff_text, changed, repo_root=REPO_ROOT)
    print(json.dumps(report, indent=2, sort_keys=True))
    truncated = report["impact_set"].get("import_graph_truncated_test_count", 0)
    if truncated:
        # LOUD ON PURPOSE. IMPORT_GRAPH_MAX_DEPTH cuts off real ancestors past a
        # finite hop count (see the constant's docstring -- this repo has real
        # chains 21 hops deep); a human or CI reading only "PASS" has no way to know
        # the closure was truncated rather than exhaustive. This does not fail the
        # gate -- the bound exists precisely to keep the run affordable -- it makes
        # the trade-off visible every time it is paid.
        print()
        print("=" * 70)
        print(
            f"IMPORT-GRAPH CLOSURE TRUNCATED: {truncated} real dependent test file(s) "
            f"sit beyond IMPORT_GRAPH_MAX_DEPTH={IMPORT_GRAPH_MAX_DEPTH} hops and were "
            "NOT selected."
        )
        print("This is a known, counted trade-off, not a failure -- see")
        print("IMPORT_GRAPH_MAX_DEPTH's docstring in core/gates/blast_radius.py.")
        print("=" * 70)
    if report["status"] != "pass":
        print()
        print("=" * 70)
        print("BLAST-RADIUS GATE: nothing-left-hanging detector(s) fired")
        print("=" * 70)
        for finding in report["findings"]:
            print(f"  [{finding['detector']}] {finding['message']}")
        print()
        print("These break main post-merge (the pr-smoke subset misses them).")
        print("Fix the dangling reference/ownership, or delete the dead test.")
        print("=" * 70)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
