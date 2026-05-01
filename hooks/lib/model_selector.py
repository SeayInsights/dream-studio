"""Model tier recommender for dream-studio skills.

CLI:  py hooks/lib/model_selector.py --skill=<name> [--default=sonnet]
API:  from hooks.lib.model_selector import recommend_model, get_model_for_skill

Outputs exactly one of: haiku | sonnet | opus
"""
from __future__ import annotations
import argparse, re, sqlite3, sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TIERS: list[str] = ["haiku", "sonnet", "opus"]

# Keywords that mandate opus as the minimum floor (never go below sonnet for these)
_COMPLEX_SKILLS: frozenset[str] = frozenset({"think", "secure", "analyze", "review"})

_SUCCESS_RATE_HIGH = 0.95   # >= this on haiku → recommend haiku
_SUCCESS_RATE_LOW  = 0.80   # <  this on current tier → upgrade


# ---------------------------------------------------------------------------
# DB helpers (stdlib-only; mirrors studio_db.py patterns)
# ---------------------------------------------------------------------------
def _db_path() -> Path:
    try:
        # Reuse studio_db path resolution if available on sys.path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from lib import paths  # type: ignore[import]
        return paths.state_dir() / "studio.db"
    except Exception:
        return Path.home() / ".dream-studio" / "state" / "studio.db"


def _connect(db_path: Path) -> sqlite3.Connection | None:
    """Return an open connection, or None if the file does not exist."""
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core recommendation logic
# ---------------------------------------------------------------------------
def _query_model_stats(conn: sqlite3.Connection, skill: str) -> dict[str, dict]:
    """Return {model_tier: {invocations, successes, success_rate}} for a skill.

    Queries raw_skill_telemetry directly because sum_skill_summary aggregates
    across all models and has no per-model breakdown.
    """
    try:
        rows = conn.execute(
            """
            SELECT
                LOWER(TRIM(model))        AS tier,
                COUNT(*)                  AS invocations,
                SUM(success)              AS successes
            FROM raw_skill_telemetry
            WHERE skill_name = ?
              AND model IS NOT NULL
              AND LOWER(TRIM(model)) IN ('haiku', 'sonnet', 'opus')
            GROUP BY tier
            """,
            (skill,),
        ).fetchall()
    except Exception:
        return {}

    result: dict[str, dict] = {}
    for row in rows:
        inv = row["invocations"] or 0
        suc = row["successes"] or 0
        result[row["tier"]] = {
            "invocations": inv,
            "successes": suc,
            "success_rate": (suc / inv) if inv > 0 else None,
        }
    return result


def _most_used_tier(stats: dict[str, dict]) -> str | None:
    """Return the tier with the highest invocation count, or None if empty."""
    if not stats:
        return None
    return max(stats, key=lambda t: stats[t]["invocations"])


def _is_complex_skill(skill: str) -> bool:
    return skill.lower().strip() in _COMPLEX_SKILLS


def recommend_model(skill: str, default: str = "sonnet") -> str:
    """Return 'haiku', 'sonnet', or 'opus' for the given skill name.

    Never raises; falls back to *default* on any error or missing data.
    """
    # Validate / normalise default
    default = default.lower().strip() if default.lower().strip() in TIERS else "sonnet"

    # Determine floor for complex/architecture skills.
    # Rule 4: think/secure/analyze/review keywords → opus is the floor.
    # The "(never downgrade below sonnet)" note means even with a DB upgrade
    # we stay at opus minimum; haiku is never valid for these skills.
    complex_floor = "opus" if _is_complex_skill(skill) else "haiku"

    try:
        db_path = _db_path()
        conn = _connect(db_path)

        if conn is None:
            return _apply_floor(default, complex_floor)

        try:
            stats = _query_model_stats(conn, skill)
        finally:
            conn.close()

        # --- Rule 1: no history → return default (respecting floor) ---
        if not stats:
            return _apply_floor(default, complex_floor)

        # --- Rule 4: complex keywords → opus is the recommendation ---
        # (but we still check data to potentially confirm sonnet is enough)
        if _is_complex_skill(skill):
            # Always recommend opus for think/secure/analyze/review skills
            return "opus"

        # --- Rule 2: haiku succeeding well → recommend haiku ---
        haiku_stats = stats.get("haiku")
        if haiku_stats and haiku_stats["success_rate"] is not None:
            if haiku_stats["success_rate"] >= _SUCCESS_RATE_HIGH:
                return "haiku"

        # --- Rule 3: current tier underperforming → upgrade ---
        current_tier = _most_used_tier(stats)
        if current_tier:
            current_stats = stats.get(current_tier, {})
            rate = current_stats.get("success_rate")
            if rate is not None and rate < _SUCCESS_RATE_LOW:
                upgraded = _upgrade_tier(current_tier)
                return _apply_floor(upgraded, complex_floor)

        # --- Rule 5: return most-used tier ---
        if current_tier:
            return _apply_floor(current_tier, complex_floor)

    except Exception:
        pass

    return _apply_floor(default, complex_floor)


def _upgrade_tier(tier: str) -> str:
    """Return the next tier up: haiku→sonnet, sonnet→opus, opus stays opus."""
    idx = TIERS.index(tier) if tier in TIERS else 1
    return TIERS[min(idx + 1, len(TIERS) - 1)]


def _apply_floor(tier: str, floor: str) -> str:
    """Ensure returned tier is at least as capable as the floor."""
    tier_idx  = TIERS.index(tier)  if tier  in TIERS else 1
    floor_idx = TIERS.index(floor) if floor in TIERS else 0
    return TIERS[max(tier_idx, floor_idx)]


# ---------------------------------------------------------------------------
# Frontmatter-based model tier lookup
# ---------------------------------------------------------------------------
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_MODEL_TIER_RE = re.compile(r"^model_tier:\s*(\S+)", re.MULTILINE)


def _resolve_skill_md(skill_specifier: str) -> Path | None:
    """Resolve a skill specifier to its SKILL.md path.

    Accepts:
      "dream-studio:quality debug"  → skills/quality/modes/debug/SKILL.md
      "dream-studio:core think"     → skills/core/modes/think/SKILL.md
      "quality debug"               → skills/quality/modes/debug/SKILL.md
      "debug"                       → searches all packs for modes/debug/SKILL.md
    """
    try:
        root = _plugin_root_cached()
    except Exception:
        return None

    spec = skill_specifier.strip()
    if spec.startswith("dream-studio:"):
        spec = spec[len("dream-studio:"):]

    parts = spec.split(None, 1)
    if len(parts) == 2:
        pack, mode = parts[0], parts[1]
        candidate = root / "skills" / pack / "modes" / mode / "SKILL.md"
        if candidate.is_file():
            return candidate

    # Single token — try as mode name across all packs
    mode_name = parts[-1] if parts else spec
    skills_dir = root / "skills"
    if skills_dir.is_dir():
        for pack_dir in skills_dir.iterdir():
            if not pack_dir.is_dir():
                continue
            candidate = pack_dir / "modes" / mode_name / "SKILL.md"
            if candidate.is_file():
                return candidate

    return None


def _plugin_root_cached() -> Path:
    if not hasattr(_plugin_root_cached, "_val"):
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from lib import paths  # type: ignore[import]
            _plugin_root_cached._val = paths.plugin_root()
        except Exception:
            candidate = Path(__file__).resolve().parents[2]
            if (candidate / "skills").is_dir():
                _plugin_root_cached._val = candidate
            else:
                raise
    return _plugin_root_cached._val


def _read_model_tier(skill_md: Path) -> str | None:
    """Read model_tier from a SKILL.md frontmatter. Returns None if absent."""
    try:
        text = skill_md.read_text(encoding="utf-8-sig")
    except Exception:
        return None
    fm_match = _FRONTMATTER_RE.search(text)
    if not fm_match:
        return None
    tier_match = _MODEL_TIER_RE.search(fm_match.group(1))
    if not tier_match:
        return None
    tier = tier_match.group(1).lower().strip()
    return tier if tier in TIERS else None


def get_model_for_skill(skill_specifier: str, default: str = "sonnet") -> str:
    """Return the declared model_tier from a skill's SKILL.md frontmatter.

    Falls back to *default* if the skill can't be found or has no model_tier.
    """
    default = default.lower().strip() if default.lower().strip() in TIERS else "sonnet"
    skill_md = _resolve_skill_md(skill_specifier)
    if skill_md is None:
        return default
    tier = _read_model_tier(skill_md)
    return tier if tier else default


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Recommend a model tier (haiku/sonnet/opus) for a dream-studio skill."
    )
    ap.add_argument("--skill",    required=True, help="Skill name to look up")
    ap.add_argument("--default",  default="sonnet",
                    choices=TIERS, help="Fallback tier when no history exists")
    ap.add_argument("--frontmatter", action="store_true",
                    help="Read model_tier from SKILL.md frontmatter instead of DB stats")
    args = ap.parse_args()

    if args.frontmatter:
        result = get_model_for_skill(args.skill, args.default)
    else:
        result = recommend_model(args.skill, args.default)
    sys.stdout.write(result + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
