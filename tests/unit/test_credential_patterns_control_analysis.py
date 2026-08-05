"""WO d84efdc4 — the control/analysis heuristic scanners derive credential detection from
the single source, not their own copies.

quality_scoring (the quality-score `check_secrets` pass) and security_patterns (the
on-security-scan hook) are loose heuristic scanners — a different modality from the strict
secret_scan gate. Their token-shape and PEM detection must still come from
core/gates/credential_patterns.py so a new provider or a tightened shape is added once.
"""

from __future__ import annotations

from pathlib import Path

from control.analysis import quality_scoring, security_patterns
from core.gates.credential_patterns import CREDENTIAL_PATTERNS, TOKEN_SHAPED_PATTERN

REPO = Path(__file__).resolve().parents[2]


def test_control_analysis_scanners_use_single_source():
    # 1. Both scanners reference the single source for token/PEM detection.
    assert TOKEN_SHAPED_PATTERN in quality_scoring.SECRET_PATTERNS
    sec_patterns = [p for p, _label in security_patterns.PATTERNS]
    assert TOKEN_SHAPED_PATTERN in sec_patterns
    assert CREDENTIAL_PATTERNS["private_key_block"] in sec_patterns

    # 2. No divergent structured token / PEM literal survives in either module's source.
    for mod in (quality_scoring, security_patterns):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        for needle in ("AKIA", "ghp_", "sk-", "BEGIN"):
            assert needle not in src, f"{Path(mod.__file__).name} still hardcodes {needle!r}"

    # 3. The unified patterns still detect — a real-shaped token and a PEM header.
    assert TOKEN_SHAPED_PATTERN.search("ghp_" + "a" * 36)
    assert TOKEN_SHAPED_PATTERN.search("AKIA" + "A" * 16)
    assert CREDENTIAL_PATTERNS["private_key_block"].search("-----BEGIN RSA PRIVATE KEY-----")

    # ...but a prefix embedded mid-word is not a token (the \b boundary): ordinary hyphenated
    # prose like "task-completion" must not trip the "sk-" inside "ta[sk-]".
    assert not TOKEN_SHAPED_PATTERN.search("task-completion")
    assert not TOKEN_SHAPED_PATTERN.search("a risky-business decision")

    # 4. The name-based / code-smell heuristics stay local (not moved into the credential
    #    source — they are not credential formats).
    assert any(label == "eval()" for _p, label in security_patterns.PATTERNS)
    assert len(quality_scoring.SECRET_PATTERNS) == 3  # two name-based + one shared token-shape
