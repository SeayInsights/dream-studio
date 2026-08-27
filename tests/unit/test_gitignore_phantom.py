"""WO-GITIGNORE-PHANTOM: a committed file must not reference a path git will not ship.

Both historical instances are reproduced as fixtures below, because a gate that cannot
catch the cases that motivated it is decoration:

1. WO-GF-WO-LIFECYCLE T1 — nine ``verify_*.py`` split siblings untracked under
   ``.gitignore`` rule ``verify_*.py``; the committed facade imported them, so a fresh
   checkout raised ModuleNotFoundError.
2. WO-MULTIROOT-REVIEW task 5 — the review-rules profile authored under
   ``.dream-studio/``, which ``.gitignore`` excludes; a committed test asserted the file
   exists, which passed locally and would have failed in CI while DS silently shipped
   without its own layer map.

Both were found by a human remembering to look. Git already knows the answer
(``git ls-files``, ``git check-ignore`` — exact, not heuristic), so this belongs in a gate.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core.gates.gitignore_phantom import (
    find_phantom_references,
    ignore_rule,
    is_tracked,
    referenced_literals,
)

NL = chr(10)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, encoding="utf-8"
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repo — the gate consults git, so a fake would prove nothing."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-q", "-m", "seed")
    return root


# -- The property ---------------------------------------------------------------


def test_an_ignored_referenced_path_fails_the_gate(repo):
    """The load-bearing case. A file reads a path that exists on disk and that git will
    never ship, so the reference works here and nowhere else."""
    (repo / ".gitignore").write_text("secret-config/\n", encoding="utf-8")
    (repo / "secret-config").mkdir()
    (repo / "secret-config" / "rules.md").write_text("- a rule\n", encoding="utf-8")
    (repo / "reader.py").write_text(
        "from pathlib import Path\n"
        'RULES = Path("secret-config/rules.md").read_text(encoding="utf-8")\n',
        encoding="utf-8",
    )

    findings = find_phantom_references(["reader.py"], repo_root=repo)

    assert len(findings) == 1, f"expected the ignored reference to be caught: {findings}"
    assert findings[0].referenced_path == "secret-config/rules.md"
    assert findings[0].referencing_file == "reader.py"
    assert findings[0].line == 2


def test_the_dream_studio_profile_case_is_caught(repo):
    """Instance 2, reproduced. `.dream-studio/` is excluded as private runtime state, and
    a committed test asserted a profile inside it exists."""
    (repo / ".gitignore").write_text("**/.dream-studio/\n", encoding="utf-8")
    (repo / ".dream-studio").mkdir()
    (repo / ".dream-studio" / "review-rules.md").write_text("mode: add\n", encoding="utf-8")
    (repo / "test_profile.py").write_text(
        "from pathlib import Path\n"
        "def test_profile_exists():\n"
        '    assert Path(".dream-studio/review-rules.md").is_file()\n',
        encoding="utf-8",
    )

    findings = find_phantom_references(["test_profile.py"], repo_root=repo)

    assert findings, "the profile case that motivated this gate must be caught"
    assert ".dream-studio/review-rules.md" in findings[0].referenced_path


def test_a_tracked_path_is_not_flagged(repo):
    """The overwhelmingly common case must stay silent, or the gate gets bypassed."""
    (repo / "data").mkdir()
    (repo / "data" / "shipped.md").write_text("real\n", encoding="utf-8")
    _git(repo, "add", "data/shipped.md")
    (repo / "reader.py").write_text(
        'from pathlib import Path\nPath("data/shipped.md").read_text()\n', encoding="utf-8"
    )

    assert find_phantom_references(["reader.py"], repo_root=repo) == []


def test_an_untracked_but_shippable_path_is_not_flagged(repo):
    """Untracked is not the defect — UNSHIPPABLE is. A file nothing excludes is one
    `git add` away, and flagging it would make the gate a nag about staging order."""
    (repo / "data").mkdir()
    (repo / "data" / "new.md").write_text("not added yet\n", encoding="utf-8")
    (repo / "reader.py").write_text(
        'from pathlib import Path\nPath("data/new.md").read_text()\n', encoding="utf-8"
    )

    assert find_phantom_references(["reader.py"], repo_root=repo) == []


def test_a_write_target_is_not_flagged(repo):
    """A writer naming its own output is not a phantom reference. Flagging these would
    bury the real findings — every diagnostics path and cache file would light up."""
    (repo / ".gitignore").write_text("out/\n", encoding="utf-8")
    (repo / "out").mkdir()
    (repo / "out" / "report.txt").write_text("generated\n", encoding="utf-8")
    (repo / "writer.py").write_text(
        "from pathlib import Path\n"
        'Path("out/report.txt").write_text("fresh")\n'
        'Path("out").mkdir(exist_ok=True)\n',
        encoding="utf-8",
    )

    assert find_phantom_references(["writer.py"], repo_root=repo) == []


def test_a_nonexistent_literal_is_not_flagged(repo):
    """A path that does not exist is not evidence of anything — it may be built at
    runtime, or belong to another machine. Only a real on-disk file git refuses to ship
    is a phantom."""
    (repo / "reader.py").write_text(
        'from pathlib import Path\nPath("nope/missing.md").read_text()\n', encoding="utf-8"
    )
    assert find_phantom_references(["reader.py"], repo_root=repo) == []


def test_a_url_is_not_treated_as_a_path(repo):
    """Slashes are not paths."""
    (repo / "reader.py").write_text(
        'import urllib.request\nurllib.request.urlopen("https://example.com/x/y")\n',
        encoding="utf-8",
    )
    assert find_phantom_references(["reader.py"], repo_root=repo) == []


# -- The message has to be actionable ------------------------------------------


def test_the_failure_names_the_ignore_rule(repo):
    """ "Path not shipped" is unactionable without the rule. `check-ignore -v` gives the
    source file and line, so the operator knows exactly what to edit."""
    (repo / ".gitignore").write_text("# c\nbuild-cache/\n", encoding="utf-8")
    (repo / "build-cache").mkdir()
    (repo / "build-cache" / "x.md").write_text("x\n", encoding="utf-8")
    (repo / "reader.py").write_text(
        'from pathlib import Path\nPath("build-cache/x.md").read_text()\n', encoding="utf-8"
    )

    finding = find_phantom_references(["reader.py"], repo_root=repo)[0]

    assert ".gitignore" in finding.ignore_rule
    assert "2" in finding.ignore_rule, f"the rule's LINE must be named: {finding.ignore_rule}"
    rendered = finding.render()
    assert "reader.py:2" in rendered
    assert "build-cache/x.md" in rendered


def test_the_git_helpers_answer_exactly(repo):
    """The gate's two facts come from git, not from pattern-matching guesses. If these
    ever became heuristics the gate would start lying in both directions."""
    (repo / ".gitignore").write_text("ignored.md\n", encoding="utf-8")
    (repo / "ignored.md").write_text("x\n", encoding="utf-8")
    (repo / "tracked.md").write_text("y\n", encoding="utf-8")
    _git(repo, "add", "tracked.md")

    assert is_tracked(repo / "tracked.md", repo_root=repo) is True
    assert is_tracked(repo / "ignored.md", repo_root=repo) is False
    assert ignore_rule(repo / "ignored.md", repo_root=repo) is not None
    assert ignore_rule(repo / "tracked.md", repo_root=repo) is None


# -- Literal extraction --------------------------------------------------------


def test_literals_are_found_in_the_receiver_not_only_the_args():
    """`Path("x/y.md").read_text()` puts the literal in the call's RECEIVER. Scanning only
    args would find nothing and the gate would silently pass everything."""
    found = referenced_literals('from pathlib import Path\nPath("a/b.md").read_text()\n')
    assert ("a/b.md", 2) in found


def test_an_assert_on_a_path_counts_as_a_reference():
    """The profile case was an assertion, not a read: `assert Path(p).is_file()`. A test
    asserting a file exists depends on it as surely as code reading it."""
    found = referenced_literals(
        'from pathlib import Path\ndef t():\n    assert Path(".x/prof.md").is_file()\n'
    )
    assert any(text == ".x/prof.md" for text, _ in found)


def test_syntactically_broken_source_does_not_crash_the_gate():
    """A gate that dies on a half-written file blocks every push until the file parses.
    Returning nothing is right: an unparseable file has no verifiable references."""
    assert referenced_literals("def broken(:\n") == []


def test_one_defect_is_reported_once(repo):
    """`assert Path(x).is_file()` matches BOTH the read-call shape and the assert shape,
    so the same literal was collected twice.

    Found by running the gate against the real repo, where tonight's profile case printed
    identically twice. A duplicated finding makes the failure message overstate how much
    is actually wrong.
    """
    (repo / ".gitignore").write_text("priv/" + NL, encoding="utf-8")
    (repo / "priv").mkdir()
    (repo / "priv" / "cfg.md").write_text("x" + NL, encoding="utf-8")
    (repo / "t.py").write_text(
        "from pathlib import Path"
        + NL
        + "def test_it():"
        + NL
        + '    assert Path("priv/cfg.md").is_file()'
        + NL,
        encoding="utf-8",
    )

    findings = find_phantom_references(["t.py"], repo_root=repo)
    assert len(findings) == 1, f"one defect must print once, got {len(findings)}: {findings}"


def test_a_relative_repo_root_still_finds_the_defect(tmp_path, monkeypatch):
    """THE BUG EVERY FIXTURE HERE WAS BLIND TO.

    ``candidate`` is absolute after ``.resolve()``, so ``candidate.relative_to(root)``
    raised ValueError whenever ``root`` was relative -- and the loop ``continue``d past
    EVERY literal. The gate reported "OK" on the exact case it was built to catch.

    Every fixture above passes an absolute ``tmp_path``, so all twelve of them passed
    against the broken code. Only running it against the real repo with
    ``repo_root=Path(".")`` exposed it. That is why the gate is now exercised both ways.
    """
    root = tmp_path / "r"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(root), capture_output=True)
    (root / ".gitignore").write_text("hidden/" + NL, encoding="utf-8")
    (root / "hidden").mkdir()
    (root / "hidden" / "f.md").write_text("x" + NL, encoding="utf-8")
    (root / "r.py").write_text(
        "from pathlib import Path" + NL + 'Path("hidden/f.md").read_text()' + NL,
        encoding="utf-8",
    )

    monkeypatch.chdir(root)
    findings = find_phantom_references(["r.py"], repo_root=Path("."))
    assert findings, "a relative repo_root must not silently skip every candidate"
    assert findings[0].referenced_path == "hidden/f.md"


def test_the_gate_is_in_the_pre_push_set():
    """A gate nobody runs is not a gate.

    Reads the manifest the pre-push runner actually loads, not a hardcoded path: a test
    that inspects a different file from the one the runner reads can pass while the gate
    never fires. The drain proved the failure mode -- written, called "repeatable", and
    reachable only from its own tests.
    """
    import yaml

    from core.gates.pre_push import DEFAULT_MANIFEST

    manifest = yaml.safe_load(Path(DEFAULT_MANIFEST).read_text(encoding="utf-8"))
    entries = {g["id"]: g for g in (manifest.get("gates") or [])}

    assert (
        "gitignore-phantom" in entries
    ), f"the gate is not registered in {DEFAULT_MANIFEST}; registered: {sorted(entries)}"
    entry = entries["gitignore-phantom"]
    assert entry["tier"] == "blocking", "a shippability defect must block, not advise"
    assert entry["command"] == ["py", "-m", "core.gates.gitignore_phantom"], entry["command"]
    assert entry.get("fail_hint"), "a blocking gate must say how to resolve it"
    # The hint has to name the trap that makes this hard to fix by hand.
    assert "PARENT DIRECTORY" in entry["fail_hint"], (
        "git cannot re-include a file under an excluded directory -- an author who does "
        "not know that will try a negation pattern and be baffled when it does nothing"
    )
