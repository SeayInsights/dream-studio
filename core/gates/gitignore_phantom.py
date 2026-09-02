"""A committed file must not reference a path git will not ship.

WO-GITIGNORE-PHANTOM. Green locally and on every gate, broken on a fresh checkout for
everyone else -- which is exactly the "dream studio should work out of the box for every
user" failure mode.

OBSERVED TWICE, both times caught by a human remembering to look.

1. WO-GF-WO-LIFECYCLE T1: nine ``verify_*.py`` split siblings were untracked because
   ``.gitignore`` line 159 is ``verify_*.py``. The committed facade imported them, so a
   fresh checkout raised ModuleNotFoundError.

2. 2026-08-27, WO-MULTIROOT-REVIEW task 5: the review-rules profile was authored at
   ``.dream-studio/review-rules.md``, and ``.gitignore`` line 4 is ``**/.dream-studio/``.
   A committed test asserted that file exists. It would have passed locally and failed in
   CI, and Dream Studio would have shipped without its own layer map -- silently falling
   back to the bare SDLC baseline.

WHY A GATE RATHER THAN A HABIT: git already knows the answer. ``git ls-files`` and
``git check-ignore`` are exact, not heuristic. A fact that can be computed should not live
in an operator's memory.

WHAT THIS DELIBERATELY DOES NOT CATCH (the false negatives of matching read/exists shapes
rather than every path-looking string):

* A path built at runtime from parts -- ``root / name / "file.md"`` with a variable
  component. Only literal strings are resolvable without executing the code.
* A path referenced only from a non-Python file (YAML, JSON, Markdown).
* A path a module WRITES and later reads in the same process. Write targets are excluded
  on purpose: a writer naming its output is not a phantom reference, and flagging those
  would bury the real findings in noise.

Those are accepted so the gate has no false positives, because a blocking gate that cries
wolf gets bypassed and then protects nothing.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Attribute calls that READ or TEST a path. A literal reaching one of these is being
# relied upon to exist at runtime.
_READ_ATTRS = frozenset(
    {
        "read_text",
        "read_bytes",
        "is_file",
        "is_dir",
        "exists",
        "iterdir",
        "glob",
        "rglob",
        "open",
        "stat",
        "resolve",
        "samefile",
    }
)

# Attribute calls that WRITE or CREATE. A literal reaching one of these is an output
# target, not a dependency, and must not be flagged.
_WRITE_ATTRS = frozenset(
    {
        "write_text",
        "write_bytes",
        "mkdir",
        "touch",
        "unlink",
        "rmdir",
        "rename",
        "replace",
        "symlink_to",
        "chmod",
    }
)


@dataclass
class Finding:
    """One referenced path that git will not ship."""

    referencing_file: str
    line: int
    referenced_path: str
    ignore_rule: str

    def render(self) -> str:
        return (
            f"  {self.referencing_file}:{self.line}\n"
            f"    references  {self.referenced_path}\n"
            f"    but git will not ship it: {self.ignore_rule}"
        )


def _git(args: list[str], *, repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def is_tracked(path: Path, *, repo_root: Path) -> bool:
    """Does git track this path? Exact -- not a guess about which paths matter."""
    rel = path.relative_to(repo_root).as_posix()
    return _git(["ls-files", "--error-unmatch", rel], repo_root=repo_root).returncode == 0


def ignore_rule(path: Path, *, repo_root: Path) -> str | None:
    """The .gitignore rule excluding this path, or None if nothing excludes it.

    ``check-ignore -v`` prints ``<source>:<line>:<pattern>\\t<path>``, so the operator gets
    the file and line to edit rather than "it is ignored somehow".
    """
    rel = path.relative_to(repo_root).as_posix()
    result = _git(["check-ignore", "-v", rel], repo_root=repo_root)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    first = result.stdout.strip().splitlines()[0]
    return first.split("\t")[0].strip() or None


def _string_literals_in_call(node: ast.Call) -> list[tuple[str, int]]:
    """Every string literal reachable from a call's own expression, with line numbers.

    Walks the call rather than only its args, because the literal is usually in the
    receiver: ``Path("x/y.md").read_text()`` puts it inside ``func.value``.
    """
    found: list[tuple[str, int]] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            found.append((child.value, getattr(child, "lineno", node.lineno)))
    return found


def _literals_asserted_absent(tree: ast.AST) -> set[tuple[str, int]]:
    """``(literal, lineno)`` pairs this source asserts are NOT there.

    Covers ``assert "x" not in y``, ``assert "x" != y`` and ``assert not <anything
    mentioning "x">``. A source that asserts absence does not depend on presence, so it
    cannot break on a fresh checkout for the reason this gate exists -- and asserting
    absence is exactly how a zero-disk rule gets tested, so collecting those literals made
    the gate refuse the tests enforcing the rule it supports.

    Deliberately narrow, in two ways. A literal is exempt only when a NEGATED assertion
    mentions it -- ``assert Path("x").is_file()`` and ``assert "x" in y`` still count,
    because those do break on a clean clone. And the exemption is keyed by LINE, so
    asserting a path absent in one test does not excuse depending on it in another; a
    set of bare strings did exactly that, which is a hole in a blocking gate.
    """
    absent: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        for inner in ast.walk(node):
            negated = isinstance(inner, ast.UnaryOp) and isinstance(inner.op, ast.Not)
            if isinstance(inner, ast.Compare):
                negated = any(isinstance(op, (ast.NotIn, ast.NotEq, ast.IsNot)) for op in inner.ops)
            if not negated:
                continue
            for child in ast.walk(inner):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    absent.add((child.value, getattr(child, "lineno", node.lineno)))
    return absent


def referenced_literals(source: str) -> list[tuple[str, int]]:
    """Path-like string literals this source RELIES ON existing.

    Collected from read/exists/test call shapes and from assert statements. Literals whose
    nearest enclosing call is a write is excluded -- see the module docstring on why write
    targets are not phantom references.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr in _WRITE_ATTRS:
                continue
            if attr in _READ_ATTRS:
                out.extend(_string_literals_in_call(node))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "open":
                out.extend(_string_literals_in_call(node))
        elif isinstance(node, ast.Assert):
            # AN ASSERTION OF ABSENCE IS THE OPPOSITE OF A DEPENDENCY.
            #
            # Every string literal under an `assert` was collected as "this source relies
            # on the path existing", which is backwards for `assert ".planning" not in
            # str(p)` -- that asserts the path is NOT used, and it is exactly how you test
            # a zero-disk rule. The gate failed the push for the tests that enforce the
            # rule the gate exists to support. Found by it firing on
            # tests/unit/test_workflow_runner.py's zero-disk tests, which pass on a fresh
            # checkout precisely because the path is absent.
            #
            # Narrow on purpose: only literals inside a negated comparison are skipped.
            # `assert Path(".planning/x").is_file()` and `assert "x" in y` still count,
            # which are the shapes that really do break on a clean clone.
            for child in ast.walk(node):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    out.append((child.value, getattr(child, "lineno", node.lineno)))

    # DEDUPE. `assert Path(x).is_file()` matches both the read-call shape and the assert
    # shape, so the same literal was reported twice. One defect should print once, or the
    # count in the failure message lies about how much is wrong.
    out = list(dict.fromkeys(out))

    # AND DROP WHAT IS ASSERTED ABSENT. Applied here rather than inside the Assert branch
    # because `assert not Path(".planning/x").exists()` is collected by the READ-CALL
    # branch, which cannot see the enclosing assert -- filtering in one branch missed it.
    # KEYED BY OCCURRENCE, NOT BY STRING. The first cut returned a set of strings, so one
    # `assert "x" not in y` anywhere in a file exempted every REAL dependency on "x"
    # elsewhere in that same file -- a hole punched straight through a blocking gate by
    # the change meant to reduce its false positives. Measured: a file asserting absence
    # in one test and calling `open(".planning/x.md")` in another reported clean.
    # (value, lineno) scopes the exemption to the assertion that earned it.
    absent = _literals_asserted_absent(tree)
    out = [(text, line) for text, line in out if (text, line) not in absent]

    # Only things that could plausibly be a repo-relative path.
    return [
        (text, line)
        for text, line in out
        if ("/" in text or "\\" in text or text.startswith("."))
        and len(text) > 3
        and "\n" not in text
        and not text.startswith(("http://", "https://", "git@"))
    ]


def changed_files(base_ref: str = "main", *, repo_root: Path) -> list[str]:
    """Python files added or modified against ``base_ref``."""
    result = _git(["diff", "--name-only", f"{base_ref}...HEAD"], repo_root=repo_root)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip().endswith(".py")]


def find_phantom_references(
    files: list[str] | None = None,
    *,
    repo_root: Path | None = None,
    base_ref: str = "main",
) -> list[Finding]:
    """Findings for every changed file referencing a path git will not ship."""
    # RESOLVE THE ROOT. A relative repo_root (Path(".")) made every candidate skip:
    # `candidate` is absolute after .resolve(), so `candidate.relative_to(root)` raised
    # ValueError and the loop `continue`d past every literal. The fixture tests passed
    # regardless because they pass an absolute tmp_path — so the gate reported OK on the
    # very case it was built for, and only a run against the REAL repo exposed it.
    root = (repo_root or REPO_ROOT).resolve()
    targets = files if files is not None else changed_files(base_ref, repo_root=root)

    findings: list[Finding] = []
    for rel_name in targets:
        source_path = root / rel_name
        try:
            source = source_path.read_text(encoding="utf-8")
        except OSError:
            continue

        for literal, line in referenced_literals(source):
            candidate = (root / literal).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                continue  # outside the repo; not ours to police
            if not candidate.exists():
                continue  # not a real path, or created at runtime
            if is_tracked(candidate, repo_root=root):
                continue
            rule = ignore_rule(candidate, repo_root=root)
            if rule is None:
                continue  # untracked but shippable — a `git add` away, not a phantom
            findings.append(
                Finding(
                    referencing_file=rel_name,
                    line=line,
                    referenced_path=literal,
                    ignore_rule=rule,
                )
            )
    return findings


def main() -> int:
    findings = find_phantom_references()
    if not findings:
        print("gitignore-phantom: OK — no changed file references a path git will not ship")
        return 0

    print("gitignore-phantom: FAIL — a committed file references a path git will not ship:")
    for finding in findings:
        print(finding.render())
    print(
        "\n  This passes locally, where the file is on disk, and breaks on a fresh\n"
        "  checkout for everyone else. Either `git add` the path (and remove the\n"
        "  .gitignore rule excluding it), or stop depending on it.\n"
        "  Note: git cannot re-include a file whose PARENT DIRECTORY is excluded —\n"
        "  if the rule names a directory, the file has to move."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
