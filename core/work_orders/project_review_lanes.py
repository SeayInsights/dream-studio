"""A project's own round-table seats, additive to Dream Studio's own bench.

SAME RULING AS `review_rules.py`, APPLIED TO LANES INSTEAD OF PROSE RULES. That module
already settled the shape for "a project extends a Dream Studio canonical registry with
its own": a project-root marker file, `mode: add` layering on top of Dream Studio's own
by default, `mode: replace` available for a project that wants total control. This
module is the same ruling over `canonical/review_lanes.yml`'s richer schema (question,
signature, precedent, measurement, model, exactly-one-of detector/eval/judgment)
instead of `.ds-review-rules.md`'s prose bullets -- the two markers exist side by side
because one schema cannot honestly carry the other's content.

THIS MODULE ONLY PARSES AND VALIDATES. It does not merge (that is
`core.gates.round_table._lanes()`'s job, since only that function has Dream Studio's
own lane list in hand to merge against and to check for id collisions across both
sources) and it does not compile a seat into a dispatchable agent (that is
`integrations.compiler.reviewers`'s job). Keeping this module to load-and-validate
means there is exactly one place a project's marker file is read and checked, reused by
both of those.

V1 SCOPE, DELIBERATELY NARROW:

- JUDGMENT LANES ONLY. `_run_detector`'s subprocess always spawns with
  `cwd=REPO_ROOT` (Dream Studio's own tree) and `_detector_runnable`'s check imports
  the module in-process against Dream Studio's own `sys.path` -- neither is
  project-tree-aware, so a project's own `detector:`/`eval:` command would silently
  run against the wrong tree or fail to import for a reason that has nothing to do
  with whether the check itself is broken. Making those project-tree-aware is a
  separate, larger design question; until then this module refuses both keys outright
  rather than accepting a lane it cannot honestly run.

- NEW SEATS ONLY, never a second lane on one of Dream Studio's own seats. Dream
  Studio's 9 currently-compiled seats each already ship a static, generator-checked
  `canonical/agents/review-*.md`; cleanly extending one with a project's own lane
  would mean recompiling and overwriting a file the `generated-artifacts` gate owns.
  A project's own seat gets its own new reviewer instead, compiled separately (see
  `integrations.compiler.reviewers`) and never touching Dream Studio's own tree.

- PROJECT ROOT ONLY, no per-folder granularity yet. `review_rules.py` earned
  per-folder profiles from a real multi-root ruling; nothing has asked for that here
  yet, and adding it speculatively would be exactly the premature generality this
  repo's own culture warns against.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.gates.review_lane_registry import SEATS, validate_lanes

#: The marker filename, at a project's root. Same family as review_rules.py's
#: PROFILE_NAME (".ds-review-rules.md") -- a single dotfile, discoverable like
#: .editorconfig, no directory to create. Also NOT under .dream-studio/, for the exact
#: reason review_rules.py's own PROFILE_NAME comment gives: .gitignore excludes
#: `**/.dream-studio/` everywhere, so a marker meant to be committed and shared with a
#: team could never ship from there.
MARKER_NAME = ".ds-review-lanes.yml"

MODE_ADD = "add"
MODE_REPLACE = "replace"
_VALID_MODES = (MODE_ADD, MODE_REPLACE)

#: The two enforcement keys this version refuses on a project lane. See the module
#: docstring's V1 SCOPE section for why.
_UNSUPPORTED_ENFORCEMENT_KEYS = ("detector", "eval")


def marker_path(repo_root: Path) -> Path:
    return Path(repo_root) / MARKER_NAME


def load_and_validate(
    repo_root: Path, *, reserved_seats: frozenset[str] = SEATS
) -> tuple[str, list[dict[str, Any]]] | None:
    """The project's own mode and lane list, or None if it declared no marker at all.

    None means "nothing to layer in" -- the caller's own bench stands unchanged, the
    same as if this module did not exist.

    A PRESENT-BUT-INVALID marker raises ValueError naming every problem found, never
    returning a partial or empty result. `core.gates.round_table._lanes()` refuses to
    let a present-but-broken *registry* silently read as "nothing here" (its own
    comments call that "the compared-nothing-reported-clean shape every lane here
    exists to refuse") -- a project's marker deserves the identical honesty. An
    operator who wrote this file to get MORE scrutiny and mistyped a field must see a
    loud failure naming the typo, not a silent downgrade to Dream Studio's bare bench
    as if they had written nothing.

    `reserved_seats` defaults to Dream Studio's own real closed set
    (`core.gates.review_lane_registry.SEATS`); overridable for tests that want to
    check collision behavior without depending on the full 26-name list.
    """
    path = marker_path(repo_root)
    if not path.is_file():
        return None

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"{path} could not be read ({exc})") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"{path} is not parseable YAML ({exc})") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"{path} must be a mapping with `mode:` and `lanes:` keys, not"
            f" {type(data).__name__}"
        )

    mode = str(data.get("mode", MODE_ADD)).strip().lower()
    if mode not in _VALID_MODES:
        raise ValueError(f"{path}: `mode` must be one of {_VALID_MODES}, not {data.get('mode')!r}")

    raw_lanes = data.get("lanes")
    if not isinstance(raw_lanes, list) or not raw_lanes:
        raise ValueError(
            f"{path} declares no `lanes:` list. A marker with nothing in it is not a"
            " reason to write one -- delete the file instead of shipping an empty opt-in."
        )
    lanes = [lane for lane in raw_lanes if isinstance(lane, dict)]

    errors = list(validate_lanes(lanes, closed_seats=None))
    for lane in lanes:
        lane_id = lane.get("id", "?")
        seat = str(lane.get("seat") or "").strip()
        if seat in reserved_seats:
            errors.append(
                f"{lane_id}: seat {seat!r} collides with one of Dream Studio's own"
                f" {len(reserved_seats)} reserved seat names. A project's own seat needs"
                " its own name -- Dream Studio may seat one of its reserved names later,"
                " and adopting it first would collide silently with no warning at the"
                " point that actually happens."
            )
        for kind in _UNSUPPORTED_ENFORCEMENT_KEYS:
            if kind in lane:
                errors.append(
                    f"{lane_id}: declares `{kind}:` -- project lanes are judgment-only in"
                    " this version. A project's own detector/eval command would run"
                    " against Dream Studio's own tree and Python path, not this project's,"
                    " which this version does not support. Use `judgment: true` and a"
                    " `why` instead."
                )

    if errors:
        raise ValueError(f"{path} failed validation:\n" + "\n".join(f"  - {e}" for e in errors))

    return mode, lanes
