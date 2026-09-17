"""Render normalised findings as one self-contained HTML page.

Deliberately self-contained — no CDN, no external stylesheet, no fonts fetched
over the network. The page is opened inside VS Code's built-in Simple Browser,
which may have no network access, and a findings report that renders blank
offline is worse than plain text.

Why HTML rather than Mermaid: Mermaid in VS Code needs a third-party extension,
and it has no tables, no sorting and no drill-down — it is a good notation for
architecture and flow, and a poor one for a list of findings with severity,
location and provenance. Mermaid stays useful elsewhere; findings get a table.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any, Iterable

from .model import SEVERITY_ORDER, Finding

_SEVERITY_COLOR = {
    "critical": ("#A32018", "#FBE9E7", "#F08B81", "#3A1A17"),
    "high": ("#8A5D00", "#FBF0D9", "#E0B45C", "#33280E"),
    "medium": ("#1F6B7A", "#E3F0F2", "#5FB6C6", "#16323A"),
    "low": ("#5A5F6B", "#EDEFF2", "#A8B0BC", "#252A32"),
    "info": ("#5A5F6B", "#EDEFF2", "#A8B0BC", "#252A32"),
    "pass": ("#186B45", "#E2F2EA", "#63C79A", "#10301F"),
}


def _sev_css() -> str:
    out = []
    for sev, (fg, bg, fg_dark, bg_dark) in _SEVERITY_COLOR.items():
        out.append(f".sev-{sev}{{color:{fg};background:{bg};}}")
        out.append(
            f"@media (prefers-color-scheme:dark){{:root:not([data-theme='light']) "
            f".sev-{sev}{{color:{fg_dark};background:{bg_dark};}}}}"
        )
        out.append(f":root[data-theme='dark'] .sev-{sev}{{color:{fg_dark};background:{bg_dark};}}")
    return "".join(out)


_CSS = """
:root{--ground:#F4F6F8;--surface:#fff;--surface2:#EDF0F4;--ink:#161B23;--ink2:#3D4757;
--muted:#6B7688;--line:#D8DEE7;--accent:#1F6B7A;}
@media (prefers-color-scheme:dark){:root:not([data-theme='light']){--ground:#0E1319;
--surface:#161C25;--surface2:#1E2630;--ink:#E6EBF2;--ink2:#B4BECD;--muted:#8A94A4;
--line:#2A3340;--accent:#5FB6C6;}}
:root[data-theme='dark']{--ground:#0E1319;--surface:#161C25;--surface2:#1E2630;--ink:#E6EBF2;
--ink2:#B4BECD;--muted:#8A94A4;--line:#2A3340;--accent:#5FB6C6;}
*{box-sizing:border-box;}
body{margin:0;background:var(--ground);color:var(--ink);
font:14px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;}
.wrap{max-width:1100px;margin:0 auto;padding:28px 20px 64px;}
h1{font-size:1.6rem;margin:0 0 4px;letter-spacing:-.01em;}
.sub{color:var(--muted);font-size:.85rem;margin:0 0 20px;}
.tiles{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 22px;}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:6px;
padding:10px 14px;min-width:92px;}
.tile b{display:block;font-size:1.5rem;line-height:1.1;font-variant-numeric:tabular-nums;}
.tile span{font-size:.7rem;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);}
.src{background:var(--surface2);border:1px solid var(--line);border-radius:6px;
padding:10px 14px;margin:0 0 22px;font-size:.82rem;color:var(--ink2);}
.src code{font-size:.92em;}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px;}
.bar button{font:inherit;font-size:.82rem;padding:5px 12px;border-radius:999px;cursor:pointer;
border:1px solid var(--line);background:var(--surface);color:var(--ink2);}
.bar button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff;}
.tscroll{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:6px;}
table{border-collapse:collapse;width:100%;min-width:760px;}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top;}
th{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
position:sticky;top:0;background:var(--surface);}
tr:last-child td{border-bottom:none;}
.pill{display:inline-block;padding:2px 8px;border-radius:3px;font-size:.68rem;font-weight:700;
text-transform:uppercase;letter-spacing:.06em;white-space:nowrap;}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.82rem;
color:var(--ink2);word-break:break-all;}
.blocking{font-weight:700;color:#A32018;}
@media (prefers-color-scheme:dark){:root:not([data-theme='light']) .blocking{color:#F08B81;}}
:root[data-theme='dark'] .blocking{color:#F08B81;}
.detail{color:var(--ink2);font-size:.86rem;}
.empty{padding:40px;text-align:center;color:var(--muted);}
footer{margin-top:26px;color:var(--muted);font-size:.78rem;}
"""

_JS = """
(function(){
  var buttons=document.querySelectorAll('[data-filter]');
  var rows=document.querySelectorAll('tbody tr');
  function apply(f){
    buttons.forEach(function(b){b.setAttribute('aria-pressed', String(b.dataset.filter===f));});
    var shown=0;
    rows.forEach(function(r){
      var ok = (f==='all') || (f==='blocking' ? r.dataset.blocking==='1' : r.dataset.sev===f);
      r.hidden=!ok; if(ok) shown++;
    });
    var e=document.getElementById('noresults'); if(e) e.hidden = shown>0;
  }
  buttons.forEach(function(b){b.addEventListener('click',function(){apply(b.dataset.filter);});});
  apply('all');
})();
"""


def _esc(v: Any) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def render_findings_html(
    findings: Iterable[Finding],
    sources: list[dict[str, Any]],
    *,
    title: str = "Dream Studio Findings",
    generated_at: str | None = None,
) -> str:
    findings = list(findings)
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    counts: dict[str, int] = {}
    blocking = 0
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
        if f.blocking:
            blocking += 1

    tiles = [f'<div class="tile"><b>{len(findings)}</b><span>total</span></div>']
    tiles.append(f'<div class="tile"><b class="blocking">{blocking}</b><span>blocking</span></div>')
    for sev in SEVERITY_ORDER:
        if counts.get(sev):
            tiles.append(f'<div class="tile"><b>{counts[sev]}</b><span>{_esc(sev)}</span></div>')

    src_bits = []
    for s in sources:
        status = s.get("status")
        mark = {
            "ok": "read",
            "absent": "not present",
            "failed": "FAILED",
            "skipped": "skipped",
        }.get(status, str(status))
        bit = f"<code>{_esc(s.get('source'))}</code> {_esc(mark)}"
        if status == "ok":
            bit += f" ({s.get('count')})"
        if status == "failed":
            bit += f" — {_esc(s.get('error'))}"
        src_bits.append(bit)
    src_line = " &middot; ".join(src_bits) or "no sources"

    filters = ['<button data-filter="all" aria-pressed="true">All</button>']
    if blocking:
        filters.append('<button data-filter="blocking">Blocking</button>')
    for sev in SEVERITY_ORDER:
        if counts.get(sev):
            filters.append(
                f'<button data-filter="{_esc(sev)}">{_esc(sev.title())} ({counts[sev]})</button>'
            )

    rows = []
    for f in findings:
        rows.append(
            "<tr data-sev={sev} data-blocking={blk}>"
            '<td><span class="pill sev-{sev}">{sev}</span></td>'
            "<td>{title}{detail}</td>"
            '<td class="mono">{loc}</td>'
            '<td class="mono">{source}</td>'
            '<td class="mono">{ref}</td>'
            "</tr>".format(
                sev=_esc(f.severity),
                blk='"1"' if f.blocking else '"0"',
                title=(
                    f'<span class="blocking">{_esc(f.title)}</span>'
                    if f.blocking
                    else _esc(f.title)
                ),
                detail=(
                    f'<br><span class="detail">{_esc(f.detail[:300])}</span>'
                    if f.detail and f.detail != f.title
                    else ""
                ),
                loc=_esc(f.location) or "&mdash;",
                source=_esc(f.source),
                ref=_esc(f.ref[:70]),
            )
        )

    body = (
        "".join(rows)
        if rows
        else '<tr><td colspan="5" class="empty">No findings recorded.</td></tr>'
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<style>{_CSS}{_sev_css()}</style></head>
<body><div class="wrap">
<h1>{_esc(title)}</h1>
<p class="sub">Generated {_esc(stamp)} &middot; normalised across every findings producer</p>
<div class="tiles">{''.join(tiles)}</div>
<div class="src"><strong>Sources:</strong> {src_line}</div>
<div class="bar">{''.join(filters)}</div>
<div class="tscroll"><table>
<thead><tr><th>Severity</th><th>Finding</th><th>Location</th><th>Source</th><th>Ref</th></tr></thead>
<tbody>{body}</tbody></table></div>
<p class="empty" id="noresults" hidden>Nothing matches that filter.</p>
<footer>security_event = authority DB rows &middot; audit_markdown = docstore audit/harden
artifacts &middot; guard_log = guardrail fire log. Self-contained: no network required.</footer>
</div><script>{_JS}</script></body></html>"""


def render_findings_json(findings: Iterable[Finding], sources: list[dict[str, Any]]) -> str:
    return json.dumps(
        {"findings": [f.to_dict() for f in findings], "sources": sources},
        indent=2,
    )
