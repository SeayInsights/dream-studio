"""What a review grades against: an SDLC baseline, extensible per project and per folder.

WO-MULTIROOT-REVIEW tasks 5-6. Two operator rulings, one mechanism.

RULING 1 (precedence). "the point should be that the rules live in dream studio by default
and a user can add their own per project or not but we will always vet work against what is
internal unless extra rules, scope, or other pieces needed for eval are added by the end
user" -- and then "they should be able to replace per project or folder if they choose as
well but out of the box it works with ours and until otherwise stated that will remain."

    folder profile  >  project profile  >  Dream Studio baseline

Nothing declared means the baseline, always. Per-FOLDER granularity exists because of
multi-root: six repositories under one project may not want one rulebook.

RULING 2 (what the baseline says). "the point of our rules is that they apply industry
standards for SDLC and that is what should traverse across roots." The prompt had this
exactly inverted. Its eight rules were:

    (1) three-store architecture      DS-specific
    (2) LAYER-MAP Rule 1              DS-specific
    (3) LAYER-MAP Rule 2              DS-specific
    (4) LAYER-MAP Rule 3              DS-specific
    (5) LAYER-MAP Rule 4              DS-specific  (spool/ingestor.py by name)
    (6) TEST COVERAGE                 universal
    (7) MIGRATION HYGIENE             DS-specific  (released_version, a DS doc by name)
    (8) DEAD TABLE RESURRECTION       DS-specific

Seven of eight described one project's concrete file layout. That is not a ruleset that
was too DS-specific -- it is a ruleset MISSING the standards it existed to enforce, which
is why grading Fulcrum against it produced nonsense. DS's layer map is one project's
EXPRESSION of layering discipline, not the standard itself.

So the baseline states the standards, and DS's layer map ships as a PROFILE -- the first
customer of the extension point, not a special case in the code. If the mechanism cannot
carry Dream Studio's own rules, it cannot carry anyone's.

NOT GRADED AS CODE WHEN IT IS NOT CODE. Operator: "End users will use claude for anything
and everything not just SDLC." A baseline rule that cannot apply to the work in hand is
not a violation; task 8 selects by work-order type, and this module keeps the standards
separable so that selection has something to select.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# The profile filename, looked for in a project root and in each folder/root.
#
# NOT under .dream-studio/: .gitignore excludes `**/.dream-studio/` as "local/private
# runtime state (never committed)", so a profile there could never ship. Dream Studio's
# own layer map is a profile, so an unshippable location would have silently dropped DS
# to the bare SDLC baseline -- while the test asserting the file exists passed locally
# and failed in CI. Git cannot re-include a file under an excluded directory, so a
# negation pattern was not available either.
#
# A single dotfile at the root: discoverable like .editorconfig, no directory to create,
# per-folder by construction.
PROFILE_NAME = ".ds-review-rules.md"

MODE_ADD = "add"
MODE_REPLACE = "replace"
MODE_DEFAULT = "default"

_MODE_RE = re.compile(r"^\s*mode\s*:\s*(add|replace)\s*$", re.IGNORECASE | re.MULTILINE)
_RULE_RE = re.compile(r"^\s*-\s+(.+?)\s*$", re.MULTILINE)


# Industry-standard SDLC practice. These traverse every root and every project because
# they describe properties of the work, not the shape of one repository.
#
# Each is phrased so it can be checked against a diff without knowing the project's file
# layout -- the test for whether a rule belongs here is: could this be applied to a repo
# nobody on this team has ever seen?
SDLC_BASELINE: tuple[str, ...] = (
    "TEST COVERAGE FOR CHANGED BEHAVIOUR: behaviour added or changed without a test that "
    "would fail if it regressed; existing tests deleted without replacement. A test that "
    "cannot fail is not coverage.",
    "INPUT AND SECRET HANDLING: untrusted input reaching a query, a shell, a filesystem "
    "path, or a deserializer without validation; credentials, tokens, or keys committed, "
    "logged, or embedded in source.",
    "ERROR HANDLING HONESTY: a failure swallowed so the caller cannot tell it happened; a "
    "success reported for work that did not occur; an absent result presented as a clean "
    "one. Absence of evidence must not read as evidence of absence.",
    "LAYERING AND DEPENDENCY DISCIPLINE: a module reaching across a declared boundary, a "
    "dependency cycle introduced, or a lower layer importing a higher one. The boundaries "
    "themselves are project-specific; having and respecting them is not.",
    "CHANGE CONTROL AND REVIEWABILITY: a change whose intent cannot be determined from "
    "the diff and its message; unrelated changes bundled such that one cannot be reverted "
    "without the other; generated artifacts edited by hand instead of regenerated.",
    "NO DEAD CODE: code added with no caller, no route, and no test reaching it; a "
    "mechanism that cannot be invoked by the surface it was built for.",
    "DATA SAFETY: a write that can destroy existing content without a backup or a "
    "protected region; a destructive operation with no preview and no confirmation; a "
    "schema change with no migration path.",
    "CONCURRENCY AND RESOURCE SAFETY: shared state mutated without synchronisation; a "
    "file, socket, or connection opened without a guaranteed close; unbounded growth in "
    "a loop or a cache.",
)


@dataclass
class RuleSet:
    """The rules one review will grade against, and where each came from."""

    rules: list[str] = field(default_factory=list)
    mode: str = MODE_DEFAULT
    sources: list[str] = field(default_factory=list)
    profiles: list[Path] = field(default_factory=list)

    @property
    def provenance(self) -> str:
        """One line naming what this review is grading against, and why.

        A reviewer that cannot say which rulebook it used is not auditable -- and the
        operator's complaint was precisely that reviews graded against the wrong one.
        """
        if self.mode == MODE_DEFAULT:
            return (
                f"Dream Studio SDLC baseline ({len(self.rules)} standards); no project or "
                "folder profile declared"
            )
        if self.mode == MODE_REPLACE:
            where = ", ".join(str(p) for p in self.profiles)
            return (
                f"REPLACED the Dream Studio baseline with {len(self.rules)} rule(s) from "
                f"{where}"
            )
        added = ", ".join(str(p) for p in self.profiles)
        base = len(SDLC_BASELINE)
        return (
            f"Dream Studio SDLC baseline ({base} standards) PLUS "
            f"{len(self.rules) - base} rule(s) added by {added}"
        )


def profile_path(root: Path) -> Path:
    """Where a profile lives for a given project root or folder."""
    return Path(root) / PROFILE_NAME


def parse_profile(text: str) -> tuple[str, list[str]]:
    """Return ``(mode, rules)`` parsed from a profile document.

    The format is markdown so it can be read by the person it constrains, and so it can
    be dropped straight into a grader prompt:

        mode: add

        - RULE NAME: what counts as a violation.
        - ANOTHER RULE: ...

    ``mode`` defaults to ``add`` when unstated. That default is deliberate: a profile
    written without reading this docstring should EXTEND the baseline, never silently
    discard it. Discarding the industry-standard baseline has to be an explicit act.
    """
    mode_match = _MODE_RE.search(text)
    mode = mode_match.group(1).lower() if mode_match else MODE_ADD
    rules = [m.group(1).strip() for m in _RULE_RE.finditer(text)]
    rules = [r for r in rules if r and not r.lower().startswith("mode:")]
    return mode, rules


def load_profile(root: Path) -> tuple[str, list[str], Path] | None:
    """Read the profile at ``root``, or None when there is none (or it is unreadable).

    An unreadable or ruleless profile returns None rather than an empty ruleset: a
    typo in a profile must not silently disarm the review. The caller falls back to the
    baseline, which is the safe direction.
    """
    path = profile_path(root)
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    mode, rules = parse_profile(text)
    if not rules:
        return None
    return mode, rules, path


def resolve_review_rules(
    *,
    project_root: Path | None = None,
    folders: list[Path] | None = None,
) -> RuleSet:
    """Resolve the ruleset for a review, applying folder > project > baseline.

    ``folders`` are the roots a multi-root project resolved to. A folder profile wins
    over the project's because it is nearer the code: with six repositories under one
    project, the repository that declares its own rules meant it.

    A REPLACE at any level stops the lower levels being applied -- that is what replace
    means. An ADD accumulates, project first then folders, so a folder can extend what
    its project already required.
    """
    layers: list[tuple[str, list[str], Path]] = []

    if project_root is not None:
        loaded = load_profile(project_root)
        if loaded:
            layers.append(loaded)

    for folder in folders or []:
        if project_root is not None and Path(folder) == Path(project_root):
            continue  # already read as the project layer; do not double-apply
        loaded = load_profile(folder)
        if loaded:
            layers.append(loaded)

    # A replace anywhere in the stack discards the baseline. The LAST replace wins,
    # since folders are nearer the code than the project is.
    replaces = [layer for layer in layers if layer[0] == MODE_REPLACE]
    if replaces:
        mode, rules, path = replaces[-1]
        # Adds declared NEARER than the winning replace still apply on top of it.
        nearer_start = layers.index(replaces[-1]) + 1
        later_adds = [layer for layer in layers[nearer_start:] if layer[0] == MODE_ADD]
        combined = list(rules)
        profiles = [path]
        for _m, extra, extra_path in later_adds:
            combined.extend(extra)
            profiles.append(extra_path)
        return RuleSet(
            rules=combined,
            mode=MODE_REPLACE,
            sources=[str(p) for p in profiles],
            profiles=profiles,
        )

    if not layers:
        return RuleSet(
            rules=list(SDLC_BASELINE),
            mode=MODE_DEFAULT,
            sources=["Dream Studio SDLC baseline"],
            profiles=[],
        )

    combined = list(SDLC_BASELINE)
    profiles: list[Path] = []
    for _mode, rules, path in layers:
        combined.extend(rules)
        profiles.append(path)
    return RuleSet(
        rules=combined,
        mode=MODE_ADD,
        sources=["Dream Studio SDLC baseline"] + [str(p) for p in profiles],
        profiles=profiles,
    )


def render_rules_block(ruleset: RuleSet) -> str:
    """Render a ruleset as the numbered block a grader prompt consumes."""
    lines = [f"({i}) {rule}" for i, rule in enumerate(ruleset.rules, 1)]
    return "\n".join(lines)
