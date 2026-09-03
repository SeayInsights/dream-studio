"""A path a skill tells an agent to open must exist in the tree the agent stands in.

WO f1290b5c. Operator symptom: another Dream Studio install "said it couldn't do the
reviews because it didn't have some of the files needed". The review mode instructed the
reader to open ``core/orchestration.md`` -- which holds the reviewer prompt template and
the review loop -- and no install has ever had a ``core/`` directory. Projection renames
the pack directory (``canonical/skills/core`` -> ``ds-core``), so a reference written
canonical-relative resolves from ``canonical/skills/`` in THIS repo and from nowhere in a
deployed tree. Measured before the fix: 111 such references across 3 packs, none
resolving.

This gate walks ``dist/plugin/skills`` -- the DEPLOYED surface, the tree an agent actually
stands in -- and not ``canonical/``, because canonical is precisely where the wrong prefix
works by accident.

TWO DRAFTS FAILED BEFORE THIS ONE, in opposite directions, and both failures are why the
rule is written the way it is:

* Draft one matched a reference by BASENAME. It found the real breaks but also flagged 127
  references to the USER'S project (``.planning/plan.md``, ``CLAUDE.md``) and every generic
  ``README.md``/``SKILL.md`` -- a false-positive machine.
* Draft two demanded an exact trailing-SEGMENT match. That silenced the false positives and
  the true positives together: nothing shipped ends in ``("core", "git.md")``, because the
  pack is named ``ds-core``, so the very reference shape this gate exists to catch was
  classified as "not a module reference" and dropped. An independent mutation run
  reintroduced all four broken review references and the suite stayed green.

So the rule now models the rename explicitly rather than hoping a suffix match implies it,
and ``_locate`` is tested directly against a synthetic tree below -- the gate must be
falsifiable without depending on this repo happening to be broken.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_SKILLS = REPO_ROOT / "dist" / "plugin" / "skills"

#: A relative markdown path with at least one directory segment. Bare filenames are
#: excluded: they are overwhelmingly prose ("see CLAUDE.md") and carry no prefix to be
#: wrong, which is the defect class under test.
REFERENCE = re.compile(r"(?<![\w/.-])((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.md)(?![\w/-])")

#: Prefixes naming the user's project or this repo's own layout, not shipped skill content.
FOREIGN_PREFIXES = (
    ".planning/",
    ".sessions/",
    ".audit/",
    "./",
    "../",
    "docs/",
    "canonical/",
    "tests/",
    ".github/",
    "dist/",
    "runtime/",
    "http",
    ".claude/",
    "src/",
    "app/",
)

#: Projection prefixes every pack directory: canonical/skills/core -> ds-core.
PACK_PREFIX = "ds-"


def _ends_with_segments(candidate: Path, reference: str) -> bool:
    """True when *candidate*'s trailing path segments equal *reference*'s.

    Compared by SEGMENTS, not by string suffix: ``ds-core/git.md`` ends with the STRING
    ``"core/git.md"`` purely because projection renamed the pack by prefixing it, so a
    string test would report a broken reference as resolved.
    """
    cand, ref = candidate.parts, Path(reference).parts
    if len(cand) < len(ref):
        return False
    tail_start = len(cand) - len(ref)
    return cand[tail_start:] == ref


def _locate(reference: str, source: Path, skills_root: Path) -> Path | None:
    """Where *reference* actually lives, or None if it resolves or names nothing shipped.

    Returning None covers two very different cases on purpose -- the reference is correct,
    or it points outside the shipped tree entirely (the reader's own project) -- because
    neither is a defect. A returned path means the reference is a real shipped module
    written at a location no install has.
    """
    pack_root = skills_root / source.relative_to(skills_root).parts[0]
    if any((base / reference).exists() for base in (source.parent, pack_root, skills_root)):
        return None

    candidates: list[str] = [reference]
    # Canonical-repo-relative references carry the tree root: skills/core/git.md.
    tree_root = "skills/"
    root_len = len(tree_root)
    if reference.startswith(tree_root):
        candidates.append(reference[root_len:])

    for candidate in candidates:
        parts = Path(candidate).parts
        # THE RENAME. A head segment that is a pack directory under its projected name is
        # the whole reported defect: true from canonical/skills/, false in every install.
        renamed = skills_root / (PACK_PREFIX + parts[0]) / Path(*parts[1:])
        if len(parts) > 1 and renamed.is_file():
            return renamed
        direct = skills_root / candidate
        if direct.is_file():
            return direct

    # A tail that matches a shipped file: `references/craft-rules.md` cited from a nested
    # mode whose references/ directory sits two levels up.
    #
    # Prefer a match inside the referring pack. The verdict is the same either way -- the
    # reference resolves from none of the three sanctioned bases, so it IS broken -- but
    # the location this reports is read by whoever fixes it, and an unconstrained rglob
    # will happily name another pack's same-shaped file whose trailing segments coincide.
    # A report that misdirects the fix is a smaller version of the defect being reported.
    # Sorted, because rglob yields whatever os.scandir yields. Leaving the order to the
    # filesystem left both branches below undefined: which same-shaped file gets named
    # would vary across the three CI platforms, and the test meant to pin the preference
    # could pass by accident whenever the referring pack happened to be visited first.
    matches = sorted(p for p in skills_root.rglob("*.md") if _ends_with_segments(p, reference))
    in_pack = [p for p in matches if p.is_relative_to(pack_root)]
    if in_pack:
        return in_pack[0]
    return matches[0] if matches else None


def _broken_references(skills_root: Path) -> list[tuple[str, str, str]]:
    """Return (referring file, written path, where it actually lives) for each break."""
    broken: list[tuple[str, str, str]] = []
    for source in sorted(skills_root.rglob("*.md")):
        text = source.read_text(encoding="utf-8", errors="replace")
        for reference in sorted(set(REFERENCE.findall(text))):
            if reference.startswith(FOREIGN_PREFIXES):
                continue
            actual = _locate(reference, source, skills_root)
            if actual is None:
                continue
            broken.append(
                (
                    source.relative_to(skills_root).as_posix(),
                    reference,
                    actual.relative_to(skills_root).as_posix(),
                )
            )
    return broken


@pytest.fixture(scope="module")
def broken() -> list[tuple[str, str, str]]:
    if not SHIPPED_SKILLS.is_dir():
        pytest.skip("no built plugin tree to inspect")
    return _broken_references(SHIPPED_SKILLS)


def _describe(offenders: list[tuple[str, str, str]]) -> str:
    return "; ".join(f"{src} says {ref} (actually {actual})" for src, ref, actual in offenders)


# --------------------------------------------------------------------------------------
# The rule itself, over a synthetic tree. These cases do not depend on the state of this
# repo, so they keep working -- and keep being able to FAIL -- once the shipped tree is
# clean. Draft two passed every live assertion while being blind to the reported bug.
# --------------------------------------------------------------------------------------


@pytest.fixture
def synthetic(tmp_path: Path) -> Path:
    """A miniature shipped tree mirroring the real layouts these references appear in.

    The nested ``modes/website/modes/animate`` shape is not decoration. That is where the
    real ``references/animation-pitfalls.md`` break lived: the ``references/`` directory
    sits at the MODE-GROUP level, so the reference resolves neither from the referring
    file's own directory nor from the pack root. An earlier version of this fixture put
    the shared file at the pack root instead, where resolving from the pack root is
    correct -- so the test demanded a break the resolver was right not to report, and the
    fixture, not the resolver, was wrong.
    """
    root = tmp_path / "skills"
    (root / "ds-core" / "modes" / "review").mkdir(parents=True)
    (root / "ds-setup" / "modes" / "jit").mkdir(parents=True)
    (root / "ds-domains" / "modes" / "website" / "references").mkdir(parents=True)
    (root / "ds-domains" / "modes" / "website" / "modes" / "animate").mkdir(parents=True)
    (root / "ds-core" / "git.md").write_text("# git\n", encoding="utf-8")
    (root / "ds-core" / "modes" / "review" / "SKILL.md").write_text("# review\n", encoding="utf-8")
    (root / "ds-setup" / "modes" / "jit" / "SKILL.md").write_text("# jit\n", encoding="utf-8")
    (root / "ds-domains" / "modes" / "website" / "references" / "craft.md").write_text(
        "# craft\n", encoding="utf-8"
    )
    (root / "ds-domains" / "modes" / "website" / "modes" / "animate" / "SKILL.md").write_text(
        "# animate\n", encoding="utf-8"
    )
    # Two files with identical trailing segments in DIFFERENT packs, arranged so the
    # DECOY sorts FIRST. That ordering is the whole point: with the referring pack
    # sorting first instead, `matches[0]` is already correct and the same-pack preference
    # cannot be observed -- which is exactly how the previous version of this fixture
    # turned its own test into decoration. A distinct filename keeps it from colliding
    # with the website craft.md case above.
    (root / "ds-core" / "modes" / "deep" / "references").mkdir(parents=True)
    (root / "ds-setup" / "modes" / "deep" / "references").mkdir(parents=True)
    (root / "ds-setup" / "modes" / "deep" / "nested").mkdir()
    (root / "ds-core" / "modes" / "deep" / "references" / "shared.md").write_text(
        "# the decoy, in an earlier-sorting pack\n", encoding="utf-8"
    )
    (root / "ds-setup" / "modes" / "deep" / "references" / "shared.md").write_text(
        "# the referring pack's own copy\n", encoding="utf-8"
    )
    (root / "ds-setup" / "modes" / "deep" / "nested" / "SKILL.md").write_text(
        "# nested\n", encoding="utf-8"
    )
    return root


def test_resolver_flags_a_pack_relative_reference(synthetic: Path) -> None:
    """`core/git.md` from inside ds-core: the exact shape that was reported and missed.

    Draft two returned None here, which is why an independent run could reintroduce all
    four broken review references and watch the suite stay green.
    """
    source = synthetic / "ds-core" / "modes" / "review" / "SKILL.md"
    found = _locate("core/git.md", source, synthetic)
    assert found is not None, "a pack-relative reference must be flagged, not dropped"
    assert found == synthetic / "ds-core" / "git.md"


def test_resolver_flags_a_canonical_repo_relative_reference(synthetic: Path) -> None:
    """`skills/core/git.md` -- written relative to the canonical tree root."""
    source = synthetic / "ds-setup" / "modes" / "jit" / "SKILL.md"
    assert _locate("skills/core/git.md", source, synthetic) == synthetic / "ds-core" / "git.md"


def test_resolver_flags_a_reference_that_skips_intervening_directories(synthetic: Path) -> None:
    """`references/craft.md` cited from a nested mode, where it lives two levels up.

    The real break: ``modes/website/modes/animate/SKILL.md`` cited
    ``references/animation-pitfalls.md`` while the file sat in
    ``modes/website/references/`` -- reachable from neither the referring directory nor
    the pack root, so no install could open it.
    """
    website = synthetic / "ds-domains" / "modes" / "website"
    source = website / "modes" / "animate" / "SKILL.md"
    assert _locate("references/craft.md", source, synthetic) == website / "references" / "craft.md"


def test_resolver_accepts_a_reference_that_resolves_from_the_pack_root(synthetic: Path) -> None:
    """A pack-root-relative reference is fine, and must not be reported as a break.

    The counterpart to the case above, and the distinction the earlier fixture blurred:
    what makes a reference broken is resolving NOWHERE, not skipping directories.
    """
    source = synthetic / "ds-core" / "modes" / "review" / "SKILL.md"
    assert _locate("modes/review/SKILL.md", source, synthetic) is None


def test_resolver_reports_the_match_inside_the_referring_pack(synthetic: Path) -> None:
    """Two packs hold a file with the same trailing segments; report the referring one.

    The verdict is identical either way -- the reference resolves from none of the three
    sanctioned bases, so it is broken. But the location this reports is what whoever fixes
    it will open, and an unconstrained rglob names whichever same-shaped file it reaches
    first. A report that misdirects the fix is a smaller copy of the defect it reports.
    """
    source = synthetic / "ds-setup" / "modes" / "deep" / "nested" / "SKILL.md"
    found = _locate("references/shared.md", source, synthetic)
    expected = synthetic / "ds-setup" / "modes" / "deep" / "references" / "shared.md"
    decoy = synthetic / "ds-core" / "modes" / "deep" / "references" / "shared.md"

    # The decoy sorts first, so without the preference this returns the decoy. Asserted
    # explicitly: round 4 found the earlier version of this test passing with the
    # mechanism removed, because the fixture let matches[0] be right by accident.
    assert decoy < expected, "fixture must place the decoy ahead of the correct file"
    assert found == expected, f"expected the referring pack's own copy, got {found}"


def test_resolver_accepts_a_correct_relative_reference(synthetic: Path) -> None:
    """The fix's own shape must NOT be flagged, or the gate blocks its own remedy.

    Both forms the sweep produced: up to the pack root for a shared module, and up to a
    mode-group's own references/ directory.
    """
    source = synthetic / "ds-core" / "modes" / "review" / "SKILL.md"
    assert _locate("../../git.md", source, synthetic) is None

    animate = synthetic / "ds-domains" / "modes" / "website" / "modes" / "animate" / "SKILL.md"
    assert _locate("../../references/craft.md", animate, synthetic) is None


def test_resolver_ignores_a_reference_to_the_readers_own_project(synthetic: Path) -> None:
    """Nothing shipped answers to it, so it is not this gate's business.

    Draft one flagged 127 of these. They are the reason the rule cannot simply report
    every unresolvable path.
    """
    source = synthetic / "ds-core" / "modes" / "review" / "SKILL.md"
    assert _locate("some-project/notes.md", source, synthetic) is None


def test_resolver_does_not_mistake_a_string_suffix_for_a_segment_match(synthetic: Path) -> None:
    """`ds-core/git.md` ends with the string "core/git.md" -- that is not resolution.

    Pins the distinction the module docstring rests on. Nothing in the live tree exercises
    it once the tree is clean, so it is asserted directly here.
    """
    assert not _ends_with_segments(synthetic / "ds-core" / "git.md", "core/git.md")
    assert _ends_with_segments(synthetic / "ds-core" / "git.md", "ds-core/git.md")


# --------------------------------------------------------------------------------------
# The live shipped tree.
# --------------------------------------------------------------------------------------


def test_the_gate_has_something_to_examine() -> None:
    """Guard against a vacuous pass.

    If the regex stopped matching, or the shipped tree were empty, every assertion below
    would pass over an empty list. A check that reports clean because it examined nothing
    is the defect class this whole file is about.
    """
    assert SHIPPED_SKILLS.is_dir(), f"no shipped skills tree at {SHIPPED_SKILLS}"
    files = list(SHIPPED_SKILLS.rglob("*.md"))
    assert len(files) > 100, f"expected the full shipped skill tree, found {len(files)} files"
    referencing = sum(
        1 for f in files if REFERENCE.search(f.read_text(encoding="utf-8", errors="replace"))
    )
    assert referencing > 20, f"only {referencing} shipped files carry a module reference"


def test_review_mode_module_paths_resolve(broken: list[tuple[str, str, str]]) -> None:
    """The operator's reported case: the review mode's own imports."""
    offenders = [b for b in broken if "review" in b[0]]
    assert offenders == [], "the review mode points at files no install has: " + _describe(
        offenders
    )


def test_ds_core_module_paths_resolve(broken: list[tuple[str, str, str]]) -> None:
    """ds-core's modes referenced their own pack root through the pre-rename name."""
    offenders = [b for b in broken if b[0].startswith("ds-core")]
    assert offenders == [], "ds-core module references do not resolve: " + _describe(offenders)


def test_cross_pack_references_do_not_use_a_path(broken: list[tuple[str, str, str]]) -> None:
    """A cross-pack reference cannot be written as a path that is true in both trees.

    ``canonical/skills/core`` is ``ds-core`` once installed, so a cross-pack path is false
    in one tree or the other whichever way it is written. Those references name the owning
    pack in prose instead: true in both, and no false path to follow.
    """
    offenders = [b for b in broken if b[0].split("/")[0] != b[2].split("/")[0]]
    assert offenders == [], "cross-pack path references remain: " + _describe(offenders)


def test_no_shipped_skill_points_at_a_file_no_install_has(
    broken: list[tuple[str, str, str]],
) -> None:
    """The whole class, across every pack."""
    assert broken == [], (
        f"{len(broken)} shipped module reference(s) do not resolve in the deployed tree:\n"
        + "\n".join(f"  {src} says {ref} -- actually at {actual}" for src, ref, actual in broken)
    )
