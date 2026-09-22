"""The anti-slop linter catches each pattern its catalog names, and only when it should.

`scripts/lint-artifact.py` is named in fourteen places across the website skills,
including a `severity: critical` gotcha reading "Run py scripts/lint-artifact.py
<output.html> before every delivery. Fix all findings before presenting to user." It had
never been tracked: `.gitignore` carried an unanchored `lint-*` under "Test / diagnostic
output captures", which swallowed the path silently. A `lint-artifact.cpython-312.pyc`
dated 2026-05-23 sits beside it, so it existed, ran here, and was never committed.

Every rule gets a positive AND a negative case. A linter that only proves it fires is
half-tested, and the half it skips is the one that decides whether people leave it on:
the catalog's own first principle is that every pattern it flags has a legitimate use.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LINTER = (
    REPO_ROOT
    / "canonical"
    / "skills"
    / "domains"
    / "modes"
    / "website"
    / "scripts"
    / "lint-artifact.py"
)


def _load():
    """Imported by path because the filename has a hyphen and is not a module name."""
    spec = importlib.util.spec_from_file_location("lint_artifact", LINTER)
    module = importlib.util.module_from_spec(spec)
    sys.modules["lint_artifact"] = module
    spec.loader.exec_module(module)
    return module


lint_artifact = _load()
lint = lint_artifact.lint


def _rules(html: str) -> set[str]:
    return {v.rule for v in lint(html)}


# --------------------------------------------------------------------------
# The file exists at the path every skill names
# --------------------------------------------------------------------------


def test_the_linter_is_where_fourteen_instructions_say_it_is():
    """The defect this file exists for. `.gitignore` must not swallow it again."""
    assert LINTER.is_file()

    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(LINTER.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    assert tracked.returncode == 0, (
        "lint-artifact.py exists on this machine but is not tracked — which is exactly"
        " how it was lost the first time. Check .gitignore for an unanchored lint-* rule."
    )


# --------------------------------------------------------------------------
# Every rule in the catalog: it fires, and it does not over-fire
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rule,bad,good",
    [
        (
            "purple-gradient",
            ".hero { background: linear-gradient(135deg, #7c3aed 0%, #8b5cf6 100%); }",
            ".hero { background: linear-gradient(135deg, var(--a) 0%, var(--b) 100%); }",
        ),
        (
            "indigo-default",
            '<button class="bg-indigo-600 text-white">Get Started</button>',
            '<button class="btn-primary">Get Started</button>',
        ),
        (
            "lorem-ipsum",
            "<p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>",
            "<p>We cut reporting time from six hours to forty minutes.</p>",
        ),
        (
            "ai-testimonial",
            '<blockquote>"This changed my life. A true game changer!"</blockquote>',
            '<blockquote>"We cut reporting from 6 hours to 40 minutes."</blockquote>',
        ),
        (
            "emoji-as-icon",
            "<li>⚡ Blazing fast performance</li>",
            '<li><svg aria-hidden="true"></svg> Blazing fast performance</li>',
        ),
        (
            "inter-as-display",
            "h1, h2 { font-family: 'Inter', system-ui, sans-serif; }",
            "body { font-family: 'Inter', system-ui, sans-serif; }",
        ),
        (
            "invented-metrics",
            "<span>99.9% uptime</span>",
            '<span>99.9% uptime <sup data-source="status-page">t</sup></span>',
        ),
        (
            "rainbow-gradient",
            ".cta { background: linear-gradient(90deg, #f97316, #22c55e, #3b82f6); }",
            ".cta { background: linear-gradient(90deg, #f97316, #eab308, #f59e0b); }",
        ),
        (
            "filler-section",
            "<h2>Why Choose Us</h2>",
            "<h2>Built for teams that ship weekly, not quarterly</h2>",
        ),
        (
            "left-accent-card",
            ".feature { border-left: 4px solid #6366f1; }",
            ".feature { border: 1px solid var(--color-border); }",
        ),
        (
            "stock-alt-text",
            '<img src="hero.jpg" alt="image">',
            '<img src="hero.jpg" alt="Aerial view of Portland at dusk">',
        ),
        (
            "excessive-shadow",
            ".card { box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 8px rgba(0,0,0,.08),"
            " 0 12px 24px rgba(0,0,0,.12); }",
            ".card { box-shadow: 0 1px 3px rgba(0,0,0,.08), 0 8px 24px rgba(0,0,0,.10); }",
        ),
        (
            "gratuitous-blur",
            ".feature-card:hover { backdrop-filter: blur(12px); }",
            ".modal { backdrop-filter: blur(12px); }",
        ),
        (
            "default-rounded",
            '<div class="p-8 rounded-full"><h3>Feature</h3></div>',
            '<div class="p-8 rounded-xl"><h3>Feature</h3></div>',
        ),
    ],
)
def test_each_rule_fires_on_its_own_example_and_not_on_the_fix(rule, bad, good):
    """Both halves come from the catalog's own bad/fix pairs wherever it gives them."""
    assert rule in _rules(bad), f"{rule} missed its own catalogued example"
    assert rule not in _rules(good), f"{rule} fires on the catalogued fix"


def test_dark_mode_afterthought_fires_on_a_colour_only_block():
    only_colours = (
        "@media (prefers-color-scheme: dark) {\n"
        "  .card { background: #1f2937; color: #f9fafb; }\n"
        "}\n"
    )
    assert "dark-mode-afterthought" in _rules(only_colours)


def test_dark_mode_afterthought_is_quiet_when_the_block_does_real_work():
    real = (
        "@media (prefers-color-scheme: dark) {\n"
        "  :root { --color-surface: #1f2937; --color-shadow: rgba(0,0,0,0.40);\n"
        "          box-shadow: 0 2px 8px var(--color-shadow); opacity: 0.9; }\n"
        "}\n"
    )
    assert "dark-mode-afterthought" not in _rules(real)


# --------------------------------------------------------------------------
# The bypass contract
# --------------------------------------------------------------------------


def test_a_bypass_comment_silences_the_line_below_it():
    """The catalog's single-line form. Bypass exists so a real purple brand is a
    deliberate, recorded choice rather than a rule somebody switches off globally."""
    html = (
        "<!-- lint-disable purple-gradient: Acme brand colour, see brand-guide.pdf -->\n"
        "background: linear-gradient(135deg, #7c3aed, #4f46e5);\n"
    )
    assert "purple-gradient" not in _rules(html)


def test_a_bypass_silences_only_the_rule_it_names():
    html = (
        "<!-- lint-disable purple-gradient -->\n"
        "background: linear-gradient(135deg, #7c3aed, #4f46e5);\n"
    )
    # indigo-default sees #4f46e5 on the same line and must still fire.
    assert "indigo-default" in _rules(html)


def test_the_block_form_silences_until_the_matching_enable():
    html = (
        "<!-- lint-disable purple-gradient -->\n"
        ".a { background: linear-gradient(90deg, #7c3aed, #a78bfa); }\n"
        ".b { background: radial-gradient(#8b5cf6, #6d28d9); }\n"
        "<!-- lint-enable purple-gradient -->\n"
        ".c { background: linear-gradient(90deg, #7c3aed, #a78bfa); }\n"
    )
    hits = [v for v in lint(html) if v.rule == "purple-gradient"]
    assert len(hits) == 1, f"the block form leaked: {[v.line for v in hits]}"
    assert hits[0].line == 5, "the violation after lint-enable is the one that must fire"


def test_the_bypass_comment_is_not_itself_a_violation():
    """`<!-- lint-disable purple-gradient -->` contains the word purple."""
    assert lint("<!-- lint-disable purple-gradient -->\n<p>Real copy.</p>\n") == []


# --------------------------------------------------------------------------
# The CLI contract the skills invoke
# --------------------------------------------------------------------------


def test_exit_codes_are_the_three_the_catalog_documents():
    """0 = clean, 1 = warnings only, 2 = critical. The skills branch on these."""
    assert lint_artifact.exit_code([]) == 0
    warnings = lint("<h2>Why Choose Us</h2>\n")
    assert warnings and lint_artifact.exit_code(warnings) == 1
    critical = lint("<p>Lorem ipsum dolor sit amet.</p>\n")
    assert lint_artifact.exit_code(critical) == 2


def test_severity_filtering_drops_the_lower_tiers():
    html = "<p>Lorem ipsum dolor sit amet.</p>\n<h2>Our Features</h2>\n"
    assert {v.severity for v in lint(html, min_severity="critical")} == {"critical"}
    assert "high" in {v.severity for v in lint(html)}


def test_the_cli_runs_end_to_end_and_returns_the_documented_code(tmp_path, capsys):
    artifact = tmp_path / "page.html"
    artifact.write_text("<p>Lorem ipsum dolor sit amet.</p>\n", encoding="utf-8")
    assert lint_artifact.main([str(artifact)]) == 2
    assert "lorem-ipsum" in capsys.readouterr().out


def test_json_output_is_machine_readable(tmp_path, capsys):
    import json

    artifact = tmp_path / "page.html"
    artifact.write_text("<h2>Why Choose Us</h2>\n", encoding="utf-8")
    assert lint_artifact.main([str(artifact), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["violations"][0]["rule"] == "filler-section"
    assert payload["counts"]["high"] == 1


def test_a_missing_file_is_an_error_not_a_clean_bill(tmp_path, capsys):
    """A linter that reports clean on a file it could not open is worse than no linter."""
    assert lint_artifact.main([str(tmp_path / "nope.html")]) == 2
    assert "no such file" in capsys.readouterr().err


# --------------------------------------------------------------------------
# The catalog and the implementation agree
# --------------------------------------------------------------------------


def test_every_rule_in_the_catalog_is_implemented_with_its_documented_severity():
    """The reference doc is the authority. A rule documented and not implemented is the
    defect this whole file exists for, one level up."""
    catalog = (
        REPO_ROOT / "canonical/skills/domains/modes/website/references/anti-slop-linter.md"
    ).read_text(encoding="utf-8")

    import re

    documented = dict(
        re.findall(r"^\|\s*`([a-z-]+)`\s*\|\s*(critical|high|medium)\s*\|", catalog, re.M)
    )
    assert len(documented) == 15, f"the catalog's quick-reference table changed: {documented}"

    implemented = {r.rule_id: r.severity for r in lint_artifact.RULES}
    assert implemented == documented
