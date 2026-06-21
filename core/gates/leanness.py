"""Leanness gate (advisory) — surfaces over-engineering and dead symbols.

Points the platform's own tools at its own output:
  - ruff (SIM/C4/PERF/RET/PIE/UP): non-native / over-built / verbose patterns
  - vulture (>=80% confidence): unused functions, classes, methods

Advisory: always exits 0 and prints counts as a hygiene signal. Tighten to
baseline-diff enforcement once the existing findings are cleaned (see
WO-LEANNESS-GATE). Run via the pre-push gate runner (cwd = repo root).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = [
    "core",
    "projections",
    "interfaces",
    "control",
    "guardrails",
    "spool",
    "shared",
    "runtime",
    "integrations",
    "emitters",
]


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout


def main() -> int:
    ruff = _run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            *SRC,
            "--select",
            "SIM,C4,PERF,RET,PIE,UP",
            "--statistics",
        ]
    )
    n_ruff = sum(int(p[0]) for line in ruff.splitlines() if (p := line.split()) and p[0].isdigit())
    vulture = _run([sys.executable, "-m", "vulture", *SRC, "--min-confidence", "80"])
    n_dead = sum(1 for line in vulture.splitlines() if " unused " in line)

    print(f"[leanness] over-engineering findings (ruff SIM/C4/PERF/RET/PIE/UP): {n_ruff}")
    print(f"[leanness] dead symbols (vulture >=80%): {n_dead}")
    print("[leanness] advisory — reduce these: reuse > new, one line > many, native > custom.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
