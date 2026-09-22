"""Every external-standard citation in canonical/ is registered and self-consistent.

Two audits of the skill corpus found citations that named a real standard and
attached a false claim to it -- "minimum 44x44 CSS pixels (WCAG 2.2 SC 2.5.8)"
when SC 2.5.8 is 24x24 at AA and 44x44 is SC 2.5.5 at AAA. Three of the four
WCAG criteria cited were wrong. The corrections are worth little on their own:
nothing stopped the fourth from being wrong next month. This is that something.

Two rules, both mechanical:

  1. A citation not in canonical/citations.yml fails. A new SC number, CWE or
     OWASP category cannot land without someone registering it, and registering
     it is where the primary source gets read.

  2. A line pairing a citation with a claim its registry entry forbids fails,
     unless the criterion that actually owns the claim is named on the same
     line. This is the rule that catches the historical bug directly, and the
     mutation tests at the bottom prove it still would.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL = REPO_ROOT / "canonical"
REGISTRY_PATH = CANONICAL / "citations.yml"

# Kept in sync with the registry by test_registry_has_no_dead_entries below.
CITATION_RE = re.compile(
    r"\bSC \d+\.\d+\.\d+\b"
    r"|\bA\d{2}:20\d{2}\b"
    # The `v` is OPTIONAL on purpose. Three citations read "OWASP ASVS 5.0 V5
    # Validation" -- version 5.0 with v4.0 chapter numbers, which is false rather
    # than merely stale -- and a pattern requiring the `v` never saw them. A
    # citation format this regex does not match is a citation this guard does not
    # check, which is indistinguishable from one that passes.
    r"|\bASVS v?\d+\.\d+(?:\.\d+)?\b"
    r"|\bCWE-\d+\b"
    r"|\bNIST SP \d{3}-\d+[A-Za-z]?\b"
    r"|\bRFC \d+\b"
    r"|\bPCI DSS(?: v?\d+(?:\.\d+)*)?\b"
    r"|\bISO \d+\b"
)

SCANNED_SUFFIXES = {".md", ".yml", ".yaml"}


def _registry() -> dict[str, dict]:
    raw = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {k: (v or {}) for k, v in raw["citations"].items()}


def _corpus() -> list[tuple[str, int, str]]:
    """(relative path, line number, line text) for every scanned line."""
    out = []
    for path in sorted(CANONICAL.rglob("*")):
        if path.suffix not in SCANNED_SUFFIXES or not path.is_file():
            continue
        if path == REGISTRY_PATH:
            continue  # the registry names every citation by definition
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), 1):
            out.append((rel, n, line))
    return out


def _citations_on(line: str) -> set[str]:
    return set(CITATION_RE.findall(line))


def _violations(line: str, registry: dict[str, dict]) -> list[str]:
    """Forbidden claim/citation pairings on a single line.

    A forbidden claim is allowed when the criterion that owns it is cited on the
    same line -- that is how a passage may legitimately contrast two criteria
    ("24x24 is the AA floor (SC 2.5.8); 44x44 is AAA (SC 2.5.5)") without the
    guard objecting.
    """
    found = _citations_on(line)
    problems = []
    for cite in found:
        entry = registry.get(cite) or {}
        forbidden = entry.get("must_not_claim") or []
        owner = entry.get("claim_owner")
        for claim in forbidden:
            # A REGEX, NOT A SUBSTRING. Seeded with the literal strings "44x44" and
            # "44 by 44", this check passed "SC 2.5.8 requires targets of at least
            # 44 CSS pixels square" -- the same false claim, reworded. A guard that
            # only catches the phrasing it was shown catches nothing but itself.
            # The forbidden thing is the wrong NUMBER near the citation.
            if not re.search(claim, line, re.IGNORECASE):
                continue
            if owner and owner in found:
                continue  # disambiguated on the same line
            problems.append(
                f"{cite} ({entry.get('title', '?')}) is paired with /{claim}/, "
                f"which belongs to {owner or 'another criterion'}"
            )
    return problems


# ── rule 1: nothing unregistered ────────────────────────────────────────────────


def test_every_citation_is_registered():
    registry = _registry()
    unknown: dict[str, list[str]] = {}
    for rel, n, line in _corpus():
        for cite in _citations_on(line):
            if cite not in registry:
                unknown.setdefault(cite, []).append(f"{rel}:{n}")

    assert not unknown, (
        "Unregistered standard citations. Read the PRIMARY source, record what it "
        "actually requires, and add it to canonical/citations.yml -- do not fill the "
        "entry in from memory:\n"
        + "\n".join(
            f"  {cite}  ({len(locs)}x, first at {locs[0]})"
            for cite, locs in sorted(unknown.items())
        )
    )


# ── rule 2: no citation carries a claim it does not own ─────────────────────────


def test_no_citation_carries_a_foreign_claim():
    registry = _registry()
    problems = []
    for rel, n, line in _corpus():
        for problem in _violations(line, registry):
            problems.append(f"  {rel}:{n}: {problem}")

    assert not problems, "Citations paired with claims they do not make:\n" + "\n".join(problems)


# ── the guard must catch the bug it was built for ───────────────────────────────


@pytest.mark.parametrize(
    "line,why",
    [
        (
            "- Touch targets: minimum 44x44 CSS pixels (WCAG 2.2 SC 2.5.8).",
            "the original defect: 44x44 attributed to SC 2.5.8, which is 24x24 at AA",
        ),
        (
            "tap target of 44 by 44 CSS pixels per WCAG 2.2 SC 2.5.8",
            "same defect spelled out in words rather than the NNxNN form",
        ),
        (
            "- [ ] Focus indicator has 3:1 contrast against adjacent colors (WCAG 2.2 SC 2.4.11)",
            "SC 2.4.11 is Focus Not Obscured and contains no contrast requirement",
        ),
        (
            "Focus indicator visible with 3:1 contrast (SC 2.4.7)",
            "SC 2.4.7 is visibility only; the 3:1 AA rule is SC 1.4.11",
        ),
        (
            "targets must be at least 24x24 CSS pixels (SC 2.5.5)",
            "the inverse error: the AA threshold attributed to the AAA criterion",
        ),
        # ── paraphrases ────────────────────────────────────────────────────────
        # An independent check proved the first of these slipped past the guard
        # when must_not_claim held the literal strings "44x44" and "44 by 44".
        # The claim is identical; only the spelling differs. A guard that catches
        # the phrasing it was seeded with catches nothing but itself.
        (
            "SC 2.5.8 requires targets of at least 44 CSS pixels square",
            "the same wrong number, worded so neither seeded literal appears",
        ),
        (
            "Per SC 2.5.8, make hit areas 44px on a side.",
            "44px, with no separator between the two dimensions at all",
        ),
        (
            "targets should be 44 pixels by 44 pixels (SC 2.5.8)",
            "spelled out at full length rather than as the compact 44x44",
        ),
        (
            "SC 2.4.11 wants the focus ring at a ratio of 4.5:1",
            "a contrast ratio that is not 3:1, on a criterion with no ratio at all",
        ),
    ],
)
def test_guard_catches_known_miscitations(line, why):
    """Mutation check. Each line is a real or symmetric form of a defect this
    guard exists to stop; a guard that passes these is not doing its job."""
    assert _violations(line, _registry()), f"guard failed to catch {why}: {line!r}"


@pytest.mark.parametrize(
    "line",
    [
        "- Touch targets: 24x24 CSS pixels is the AA floor (SC 2.5.8). 44x44 is AAA (SC 2.5.5).",
        "3:1 contrast against adjacent colors (SC 1.4.11 Non-text Contrast, AA)",
        "Focus is not entirely hidden by sticky headers (SC 2.4.11 Focus Not Obscured, AA)",
        "Pointer targets at least 44 by 44 CSS pixels (SC 2.5.5, AAA)",
    ],
)
def test_guard_allows_correct_and_contrasting_citations(line):
    """The guard must not fire on correct text, including a passage that names
    two criteria to contrast their thresholds -- otherwise the fix for the bug
    would itself be unshippable."""
    assert _violations(line, _registry()) == []


# ── registry hygiene ────────────────────────────────────────────────────────────


def test_registry_has_no_dead_entries():
    """A registered citation nothing cites is drift. Either the corpus dropped it
    (remove the entry) or the extraction regex stopped seeing it (fix the regex --
    a citation the regex misses is a citation this guard does not check)."""
    cited = set()
    for _, _, line in _corpus():
        cited |= _citations_on(line)
    dead = sorted(set(_registry()) - cited)
    assert not dead, (
        "Registered but never cited -- remove the entry, or fix CITATION_RE if it "
        "has stopped matching the form used in the corpus:\n  " + "\n  ".join(dead)
    )


def test_verified_entries_carry_a_primary_source():
    registry = _registry()
    bad = [
        cite
        for cite, entry in registry.items()
        if entry.get("verified") and not str(entry.get("source", "")).startswith("http")
    ]
    assert not bad, f"marked verified with no primary source URL: {bad}"


def test_claim_guards_are_wired_to_a_real_owner():
    """A must_not_claim with a claim_owner that is not itself registered would
    silently never disambiguate, turning a correct contrasting passage into a
    permanent failure."""
    registry = _registry()
    for cite, entry in registry.items():
        owner = entry.get("claim_owner")
        if entry.get("must_not_claim"):
            assert owner, f"{cite} forbids a claim but names no owner for it"
            assert owner in registry, f"{cite} names unregistered claim_owner {owner!r}"


def test_every_owasp_top10_category_has_an_analyst_seat():
    """pr-security-scan advertises an OWASP scan, so every category in the current
    edition needs a seat that names it -- either a dedicated analyst or a STRIDE
    analyst whose perspective declares it covers that category.

    This started as three orphans: A06 Insecure Design, A08 Software or Data
    Integrity Failures, and A10 Mishandling of Exceptional Conditions (new in
    2025). Advertising Top 10 coverage while scanning seven of ten is the kind of
    overclaim a citation makes easy and nobody notices.
    """
    registry = _registry()
    current = {
        cite: entry
        for cite, entry in registry.items()
        if str(entry.get("standard", "")).startswith("OWASP Top 10")
    }
    assert len(current) == 10, f"expected 10 Top 10 categories registered, found {len(current)}"

    analysts = CANONICAL / "skills/quality/modes/pr-security-scan/analysts"
    seats = "\n".join(p.read_text(encoding="utf-8") for p in sorted(analysts.glob("*.yml")))

    orphans = [
        f"{cite} {entry.get('title')}"
        for cite, entry in sorted(current.items())
        if cite not in seats
    ]
    assert not orphans, (
        "OWASP categories with no analyst seat naming them. Add a seat, or map the "
        "category onto an existing seat's perspective where it already covers the "
        "substance:\n  " + "\n  ".join(orphans)
    )


def test_registered_analysts_exist_on_disk():
    """A mode listing an analyst file that does not exist fails at dispatch time,
    in the middle of a security scan."""
    base = CANONICAL / "skills/quality/modes/pr-security-scan"
    modes = yaml.safe_load((base / "modes.yml").read_text(encoding="utf-8"))
    missing = []
    for mode, cfg in modes.items():
        for key in ("analysts", "quick_analysts"):
            for name in cfg.get(key) or []:
                if not (base / "analysts" / f"{name}.yml").is_file():
                    missing.append(f"{mode}.{key}: {name}")
    assert not missing, "modes.yml references analyst files that do not exist:\n  " + "\n  ".join(
        missing
    )


def test_no_frozen_popularity_counts_in_provenance():
    """A star count baked into a source header is provenance theatre.

    It reads as though someone checked the repository, it is never re-checked,
    and it only decays. This had already decayed before the guard existed:
    sdras/awesome-actions was cited as "21.7k stars" in one file and "~28k
    stars" in another -- same repository, two frozen numbers, neither true.

    Thresholds ("stars > 20", "<100 stars") and the ingest log's dated `stars:`
    field are fine: a threshold is a rule, and the log documents its own value
    as a count at time of analysis.
    """
    frozen = re.compile(r"\(\s*~?\d[\d,.]*k?\s+stars\s*\)|,\s*~?\d[\d,.]*k?\s+stars\b")
    allowed = {"ingest-log.yml", "eval-rubric.yml", "anti-slop-linter.md"}
    hits = []
    for rel, n, line in _corpus():
        if Path(rel).name in allowed:
            continue
        if frozen.search(line):
            hits.append(f"  {rel}:{n}: {line.strip()[:90]}")
    assert not hits, (
        "Frozen popularity counts in provenance. Name the source; do not freeze a "
        "number nobody will re-check:\n" + "\n".join(hits)
    )


def test_unverified_backlog_is_reported():
    """Not a failure -- an honest count. Inventorying a citation is not the same
    as checking it, and this keeps the difference visible instead of letting a
    registered-but-unread entry read as validated."""
    registry = _registry()
    unverified = sorted(c for c, e in registry.items() if not e.get("verified"))
    verified = len(registry) - len(unverified)
    print(
        f"\ncitation registry: {verified}/{len(registry)} verified against a primary source"
        f"\nunverified backlog ({len(unverified)}): {', '.join(unverified)}"
    )
    assert len(registry) > 0
