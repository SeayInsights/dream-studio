#!/usr/bin/env bash
export PYTHONIOENCODING=utf-8
exec py -c '
import sys, io, json, subprocess, os, tempfile, time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

raw = sys.stdin.read() or "{}"
data = json.loads(raw)

# --- inputs ----------------------------------------------------------------
model = (data.get("model") or {}).get("display_name") or "Claude"
used = (data.get("context_window") or {}).get("used_percentage")
cwd = data.get("cwd") or ""

effort = (
    (data.get("session") or {}).get("thinking_effort")
    or data.get("thinking_effort")
    or (data.get("model") or {}).get("thinking_effort")
)

# --- context metrics bridge (read by on-context-warning PostToolUse hook) --
session_id = data.get("session_id") or (data.get("session") or {}).get("id") or ""
COMPACT_THRESHOLD = 83.0

# Fallback: after /compact Claude Code may not send used_percentage — read bridge file
if used is None and session_id:
    try:
        bp = Path(tempfile.gettempdir()) / f"claude-ctx-{session_id}.json"
        if bp.exists():
            bd = json.loads(bp.read_text())
            if time.time() - bd.get("timestamp", 0) < 120 and bd.get("post_compact"):
                used = 0.0
    except Exception:
        pass

if used is not None and session_id:
    try:
        raw_pct = float(used)
        normalized_pct = min(100.0, raw_pct * 100.0 / COMPACT_THRESHOLD)
        bridge = {
            "session_id": session_id,
            "remaining_percentage": round(100.0 - normalized_pct, 1),
            "used_pct": round(normalized_pct, 1),
            "raw_pct": round(raw_pct, 1),
            "timestamp": int(time.time()),
        }
        bp = Path(tempfile.gettempdir()) / f"claude-ctx-{session_id}.json"
        bp.write_text(json.dumps(bridge))
    except Exception:
        pass

# --- ansi ------------------------------------------------------------------
def a(c): return f"\033[{c}m"
RESET = a("0")
WHITE = a("97")
GREEN = a("32")
YELLOW = a("33")
RED = a("31")
GRAY = a("90")

# --- git branch + dirty + repo --------------------------------------------
# Hide the repo segment entirely when the cwd resolves to the Studio OS
# infrastructure itself (not "a project"). Show it for any other repo.
STUDIO_HOME = os.path.normcase(os.path.normpath(
    os.path.expanduser("~/studio")
))
branch = ""
dirty = False
repo = ""
if cwd and os.path.isdir(cwd):
    try:
        top = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=2)
        toplevel = top.stdout.strip() if top.returncode == 0 else ""
        is_studio_itself = (
            toplevel
            and os.path.normcase(os.path.normpath(toplevel)) == STUDIO_HOME
        )
        if toplevel and not is_studio_itself:
            b = subprocess.run(["git", "-C", cwd, "branch", "--show-current"],
                               capture_output=True, text=True, timeout=2)
            if b.returncode == 0:
                branch = b.stdout.strip()
            s = subprocess.run(["git", "-C", cwd, "status", "--porcelain"],
                               capture_output=True, text=True, timeout=2)
            if s.returncode == 0 and s.stdout.strip():
                dirty = True
            r = subprocess.run(["git", "-C", cwd, "remote", "get-url", "origin"],
                               capture_output=True, text=True, timeout=2)
            if r.returncode == 0:
                url = r.stdout.strip()
                if url:
                    if url.endswith(".git"):
                        url = url[:-4]
                    if "@" in url and ":" in url and not url.startswith("http"):
                        tail = url.split(":", 1)[1]
                    else:
                        tail = url.split("://", 1)[-1]
                        if "/" in tail:
                            tail = tail.split("/", 1)[1]
                    parts = [p for p in tail.split("/") if p]
                    if parts:
                        repo = parts[-1]
    except Exception:
        pass

# --- studio pulse (health + ci) -------------------------------------------
health = ""
ci = ""
if cwd:
    pulse = Path(cwd) / "meta" / "pulse-latest.json"
    if not pulse.exists():
        p = Path(cwd)
        for _ in range(4):
            cand = p / "meta" / "pulse-latest.json"
            if cand.exists():
                pulse = cand
                break
            p = p.parent
    if pulse.exists():
        try:
            ps = json.loads(pulse.read_text(encoding="utf-8"))
            health = (ps.get("health") or "").upper()
            ci = (ps.get("ci_status") or "").lower()
        except Exception:
            pass

# --- branch icon color = overall pulse health ----------------------------
if health in ("FAIL", "CRITICAL"):
    branch_color = RED
elif health in ("WARN", "DEGRADED"):
    branch_color = YELLOW
elif health == "HEALTHY":
    branch_color = GREEN
else:
    branch_color = WHITE  # unknown / no pulse

# --- context bar -----------------------------------------------------------
# Rescale to Claude Code auto-compact threshold: 100% on the bar = compact point.
# Raw used_percentage is token-window %; auto-compact fires around 83%.
COMPACT_THRESHOLD = 83.0
if used is None:
    bar = "░" * 10
    pct_str = "-"
    bar_color = WHITE
else:
    raw = float(used)
    u = min(100.0, raw * 100.0 / COMPACT_THRESHOLD)
    filled = max(0, min(10, int(round(u / 10))))
    bar = "█" * filled + "░" * (10 - filled)
    pct_str = f"{int(round(u))}"
    if u >= 80:
        bar_color = RED
    elif u >= 65:
        bar_color = YELLOW
    else:
        bar_color = GREEN

# --- effort glyph ---------------------------------------------------------
effort_map = {"high": "◉", "medium": "◐", "low": "○", "none": "·"}
effort_glyph = ""
if effort:
    effort_glyph = effort_map.get(str(effort).lower(), "·")

# --- compose: left → right ------------------------------------------------
segs = [f"{WHITE}{model}{RESET}"]

if branch:
    dirty_mark = f"{WHITE}●{RESET}" if dirty else ""
    label = f"{repo}:{branch}" if repo else branch
    segs.append(f"{branch_color}\u2b22{RESET} {WHITE}{label}{RESET}{dirty_mark}")

segs.append(f"{bar_color}{bar}{RESET} {WHITE}{pct_str}%{RESET}")

# effort on far right
if effort_glyph:
    segs.append(f"{WHITE}Effort {effort_glyph}{RESET}")

sys.stdout.write("  ".join(segs))
'
