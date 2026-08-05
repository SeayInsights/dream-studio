"""WO ed3aa5db — credential detection has ONE source, and the scanners share an exclusion
policy so they cannot drift.

core/gates/credential_patterns.py is the single source. The three detection surfaces
(secret_scan CI gate, repo_publication_readiness pre-publish scan, the generated-code
prefix linter) consume it, so a new provider or a tightened threshold is added once.
"""

from __future__ import annotations

from pathlib import Path

from core.gates import credential_patterns as src
from core.gates import secret_scan
from core.release import repo_publication_readiness as pub
from core.skills.build import security


def test_single_source_and_no_pub_self_trip(tmp_path: Path):
    # 1. Every surface derives credential detection from the single source — no local copies.
    assert secret_scan._PATTERNS is src.CREDENTIAL_PATTERNS
    assert secret_scan._EXCLUDED_PATH_SUBSTRINGS is src.SCANNER_EXCLUDED_PATH_SUBSTRINGS
    assert security._LEAKED_PREFIXES is src.CREDENTIAL_PREFIXES
    assert pub.SECRET_CONTENT_RULES == tuple(src.CREDENTIAL_PATTERNS.items())

    # The prefix heuristic keeps the prefixes it always had (superset — coverage only grew).
    for legacy in ("sk-", "ghp_", "AKIA", "xoxb-", "xoxp-", "-----BEGIN"):
        assert legacy in security._LEAKED_PREFIXES

    # 2. Shared exclusion policy: the pub content scanner skips pattern-definition files and
    #    the OTHER scanner's test fixtures (it used to self-trip on the PEM header literal in
    #    tests/unit/test_security_baseline.py).
    assert pub._skip_secret_scan_path("tests/unit/test_security_baseline.py") is True
    assert pub._skip_secret_scan_path("core/gates/secret_scan.py") is True
    assert pub._skip_secret_scan_path("core/gates/credential_patterns.py") is True
    assert pub._skip_secret_scan_path("core/some/other_module.py") is False

    # 3. End-to-end: a PEM literal at an excluded fixture path is skipped, but the SAME literal
    #    at a normal path still fires — the exclusion narrows noise without weakening detection.
    pem = "-----BEGIN RSA PRIVATE KEY-----"
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_security_baseline.py").write_text(
        f'x = "{pem}"', encoding="utf-8"
    )
    (tmp_path / "leak.py").write_text(f'x = "{pem}"', encoding="utf-8")

    findings = pub._content_findings(tmp_path, ["tests/unit/test_security_baseline.py", "leak.py"])
    secret_paths = [f["path"] for f in findings if f["finding_type"] == "secret_pattern"]
    assert secret_paths == ["leak.py"], findings
