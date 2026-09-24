"""`ds render` — turn normalised findings into something an operator can read.

Writes a single self-contained HTML file (Type 3 diagnostic output) and prints
its path. Open it in VS Code with the built-in Simple Browser — no server, no
extension, no port:

    ds render findings --open

The page embeds all of its CSS and JS, so it renders with no network access.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from core.findings import collect_findings, summarize
from core.findings.render import render_findings_html, render_findings_json


def _ds_home() -> Path:
    env = os.environ.get("DS_DREAM_STUDIO_HOME") or os.environ.get("DREAM_STUDIO_HOME")
    from core.config.paths import home_dir

    return Path(env) if env else home_dir()


def _default_out(repo: str) -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _ds_home() / "diagnostics" / day / repo / "render" / "findings.html"


def _open_in_editor(path: Path) -> str:
    """Prefer VS Code's Simple Browser; fall back to the OS browser.

    RESOLVED, NOT SHELLED. This used shell=True on Windows because the VS Code
    launcher there is a .CMD shim that a bare exec will not find on PATH. But
    shell=True hands the whole command line to cmd.exe, and at that point the
    URI stops being an argument and becomes text the shell parses -- while the
    path it is built from is one the caller chose with --out. shutil.which()
    finds the same shim and returns its full path, which subprocess can run
    directly, so the argument vector stays a vector and no shell sees it.
    """
    uri = path.resolve().as_uri()
    for name in ("code", "code-insiders"):
        exe = shutil.which(name)
        if exe is None:
            continue
        try:
            subprocess.run(
                [exe, "--open-url", uri],
                check=True,
                capture_output=True,
                timeout=20,
            )
            return f"opened in {name}"
        except Exception:
            continue
    try:
        webbrowser.open(uri)
        return "opened in default browser"
    except Exception as exc:  # noqa: BLE001
        return f"could not open automatically ({exc})"


def _cmd_findings(args) -> int:
    home = _ds_home()
    findings, sources = collect_findings(
        db_path=home / "state" / "studio.db",
        files_db=home / "state" / "files.db",
        guard_log=home / "diagnostics" / "guard-findings.jsonl",
        project_id=getattr(args, "project_id", None),
    )

    if getattr(args, "json", False):
        print(render_findings_json(findings, sources))
        return 0

    repo = Path.cwd().name
    out = Path(args.out).resolve() if getattr(args, "out", None) else _default_out(repo)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_findings_html(findings, sources, title=f"Findings — {repo}"),
        encoding="utf-8",
        newline="\n",
    )

    summary = summarize(findings)
    result = {
        "ok": True,
        "path": str(out),
        "summary": summary,
        "sources": sources,
    }
    if getattr(args, "open", False):
        result["open"] = _open_in_editor(out)

    print(json.dumps(result, indent=2))

    failed = [s for s in sources if s.get("status") == "failed"]
    if failed:
        print(
            "warning: {} findings source(s) could not be read: {}".format(
                len(failed), ", ".join(s["source"] for s in failed)
            ),
            file=sys.stderr,
        )
    return 0


def add_render_subcommand(subparsers) -> None:
    """Register the 'render' subcommand group."""
    render_parser = subparsers.add_parser(
        "render",
        help="Render Dream Studio state as a readable, self-contained HTML page",
    )
    render_sub = render_parser.add_subparsers(dest="render_cmd", required=True)

    findings = render_sub.add_parser(
        "findings",
        help="Every finding from every producer, in one page",
    )
    findings.add_argument(
        "--project-id",
        default=None,
        dest="project_id",
        help="Limit to one project",
    )
    findings.add_argument(
        "--out",
        default=None,
        help="Write the page here instead of the dated diagnostics directory",
    )
    findings.add_argument(
        "--open",
        action="store_true",
        default=False,
        help="Open the page in VS Code's Simple Browser (falls back to the OS browser)",
    )
    findings.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit normalised findings as JSON instead of writing a page",
    )
    findings.set_defaults(func=_cmd_findings)
