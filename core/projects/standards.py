"""What a project says about how it is verified, declared in its own tree.

WHY THIS EXISTS. `_run_one_test_check` runs a bare TEST-CHECK target as
``sys.executable -m pytest <target>`` in the work order's target repo. For a repo that
does not run pytest that is guaranteed wrong, and the failure it produces is worse than
useless -- measured on a scratch JS project carrying a real `src/foo.test.js`:

    TEST-CHECK could not run: pytest USAGE ERROR - the node id is wrong or the file
    does not exist here (exit 4)
    ERROR: not found: .../src/foo.test.js

**The file exists.** The check reports a defect in the criterion, and the actual fault is
that Dream Studio ran a tool the project does not use. A reviewer reading that verdict
learns something false about the work.

WHERE THE DECLARATION LIVES, AND WHY NOT THE DATABASE. `round_table.registry_for` already
set the precedent for this exact question and stated the reason: "another project
reviewing itself should be asked ITS questions, not this repo's, so the registry travels
with the tree rather than with the convener." A standards profile is the same kind of
fact. It belongs to the project, changes when the project's tooling changes, and should
be reviewable in the pull request that changes it -- which a row in Dream Studio's
authority would not be.

    <project>/.dream-studio/standards.yml

    test: npm test                          # shorthand: the suite command
    # or
    test:
      command: npm test                     # the suite
      with_target: npm test -- {target}     # how to run ONE test, if that is possible

ENFORCE OR DECLARE, APPLIED TO TARGETING. Dream Studio cannot guess how an arbitrary
runner takes a single test: `npm test` needs `--` before it, `go test` takes a package
rather than a file, and `cargo test` takes a filter. So a project that declares a runner
and no `with_target` gets a REFUSAL for a bare target, naming `cmd:` as the remedy --
never a guess, and never a silent fall back to pytest. Declaring `with_target` is the
project saying "here is how", and then it is used verbatim.

A project that declares nothing is unchanged: pytest, exactly as before.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: Where a project declares itself. One place, so a project cannot half-declare in two.
STANDARDS_PATH = (".dream-studio", "standards.yml")

#: Runners this repo's own default already is. A project that declares one of these is
#: saying "pytest", so the existing node-id path is correct for it and nothing changes.
_PYTEST_RUNNERS = ("pytest", "py.test")


def standards_path(repo_root: Path | None) -> Path | None:
    """The profile file for a tree, whether or not it exists."""
    if repo_root is None:
        return None
    return Path(repo_root).joinpath(*STANDARDS_PATH)


def standards_for(repo_root: Path | None) -> dict[str, Any]:
    """A project's declared standards, or ``{}`` when it declares none.

    Unreadable or malformed YAML returns ``{}`` rather than raising. A profile is an
    optimisation on top of a working default; a syntax error in it should not make a
    project unverifiable, and the caller's behaviour without a profile is the same
    behaviour every project had before profiles existed.
    """
    path = standards_path(repo_root)
    if path is None or not path.is_file():
        return {}
    try:
        import yaml

        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def declared_test_profile(repo_root: Path | None) -> dict[str, str]:
    """``{command, with_target}`` for this project's tests; ``{}`` when undeclared.

    Accepts the shorthand (``test: npm test``) and the mapping form. Both collapse to the
    same shape here so no caller has to know which spelling a project used.
    """
    # NOT test_profile(): pytest collects any module-level callable whose name starts
    # with test_, so that spelling turned this helper into a broken test case in every
    # file that imported it -- caught on the first run here.
    declared = standards_for(repo_root).get("test")
    if isinstance(declared, str):
        command = declared.strip()
        return {"command": command} if command else {}
    if isinstance(declared, dict):
        out: dict[str, str] = {}
        command = str(declared.get("command") or "").strip()
        if command:
            out["command"] = command
        with_target = str(declared.get("with_target") or "").strip()
        if with_target:
            out["with_target"] = with_target
        return out
    return {}


#: Where a project declares the gates its own pushes must pass.
#:
#: `.dream-studio/pre-push.yaml` IS NOT A NEW NAME. It is the convention
#: `interfaces/cli/ds_workflow.PROJECT_GATE_MANIFEST` already established for
#: `ds workflow run pre-push --repo-root`, and this file first shipped inventing a second
#: one (`gates.yaml`) without finding it. Two names for one fact is the defect this
#: repository keeps finding in other forms: a project writing one of them would have been
#: gated by one door and refused by the other, with nothing saying why.
#:
#: The second entry is the Dream-Studio-shaped layout this repo itself uses, so a project
#: laid out like DS needs no extra file to say the same thing -- the two-layout idea
#: mirrors `round_table.registry_for`, which states the reason.
GATE_MANIFEST_PATHS = (
    (".dream-studio", "pre-push.yaml"),
    ("canonical", "workflows", "pre-push.yaml"),
)


def gate_manifest_for(repo_root: Path | None) -> tuple[Path | None, str | None]:
    """The gate manifest for a tree: ``(path, refusal)``.

    **DREAM STUDIO'S OWN GATES ARE NOT A DEFAULT FOR SOMEBODY ELSE'S REPOSITORY.**
    `run_pre_push_gates` already accepted `manifest_path` and `repo_root`, and `main()`
    passed neither -- so the only reachable behaviour was DS's manifest against DS's
    tree. The obvious way to add `--repo` would be to keep DS's manifest and change the
    working directory, which would gate another project on rules like
    `rule4-ingestor-sole-event-writer` and `fixture-schema-parity`: facts about this
    codebase's event pipeline, not about whether that project works. Every one of them
    would fail, and the failure would say nothing true about the project.

    So a tree that declares no manifest is REFUSED, not defaulted. The refusal names
    both places it looked, because "declare your gates" without saying where is the
    same dead end as no message at all.
    """
    if repo_root is None:
        return None, None
    root = Path(repo_root)
    for parts in GATE_MANIFEST_PATHS:
        candidate = root.joinpath(*parts)
        if candidate.is_file():
            return candidate, None
    looked = " or ".join("/".join(p) for p in GATE_MANIFEST_PATHS)
    # `ds workflow run pre-push --repo-root <dir> --manifest <file>` is the older door on
    # the same capability and takes an explicit manifest; naming it here means an operator
    # who hits this refusal is not left thinking the only option is to create a file.
    return None, (
        f"{root} declares no gate manifest, and Dream Studio's own gates are not a"
        f" default for another repository -- they encode this codebase's rules, so"
        f" running them there would fail for reasons about Dream Studio. Declare the"
        f" project's gates in {looked}, or name one with"
        " `ds workflow run pre-push --repo-root <dir> --manifest <file>`."
    )


def is_pytest(command: str) -> bool:
    """True when a declared command is the runner Dream Studio already defaults to.

    Compared on the first token so `pytest platform/tests -q` counts, and matched against
    a leading interpreter too, because `python -m pytest` is the same runner spelled the
    long way.
    """
    tokens = command.split()
    for token in tokens[:3]:
        name = token.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
        if name.endswith(".exe"):
            name = name[:-4]
        if name in _PYTEST_RUNNERS:
            return True
    return False


def targeted_command(repo_root: Path | None, target: str) -> tuple[str | None, str | None]:
    """How to run ONE test in this project: ``(command, refusal)``.

    ``(None, None)``  -- the project declares nothing, or declares pytest. The caller's
                         existing pytest path is correct; nothing changes.
    ``(command, None)`` -- the project declared ``with_target``; run this verbatim.
    ``(None, reason)``  -- the project declared a non-pytest runner and no way to target
                         one test. REFUSE, naming the remedy. Falling back to pytest here
                         is the bug this module exists for: it runs a tool the project
                         does not use and then reports the criterion as wrong.
    """
    profile = declared_test_profile(repo_root)
    command = profile.get("command")
    if not command or is_pytest(command):
        return None, None

    with_target = profile.get("with_target")
    if with_target:
        return with_target.replace("{target}", target), None

    return None, (
        f"this project declares `test: {command}` and no `with_target`, so Dream Studio"
        f" cannot run one test by name here -- `{command}` and pytest take a target"
        " differently and guessing would run the wrong thing. Write the check as"
        " `TEST-CHECK: cmd: <command>`, or add a `with_target` line to"
        f" {'/'.join(STANDARDS_PATH)}."
    )
