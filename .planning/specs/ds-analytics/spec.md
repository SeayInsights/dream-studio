---
title: Dream-Studio Analytics Engine (DSAE)
status: approved
created: 2026-04-29
phase: parked — build after wedding website editor
---

# Dream-Studio Analytics Engine

## What it is
A Python-powered analytics system that reads dream-studio's own data, runs statistical
analysis, and outputs both HTML dashboards and `.pbip` Power BI projects. Eventually
surfaces in TORII as the analytics panel.

---

## Data Sources

| Source | Location | What we extract |
|---|---|---|
| Pulse reports | `.dream-studio/meta/pulse-*.md` | Health trends over time, PR velocity, draft backlog |
| Planning specs | `.planning/specs/**/spec.md` | All plans ever written |
| Orphaned specs | `.planning/specs/**/` with no corresponding build commit | Plans that never shipped |
| Lesson drafts | Dream-studio lessons store | Pending vs. published, topic clusters |
| GOTCHAS / CONSTITUTION | Per-project `.planning/` | Repeat failure patterns |
| Git log | `git log --oneline` | Spec → build conversion rate |
| Memory index | `.claude/projects/*/memory/MEMORY.md` | Knowledge accumulation over time |

**Orphaned plan detection logic:** A spec is "orphaned" if no `dream-studio:build`
invocation appears in git history within 14 days of the spec file's creation date.

---

## Analysis Layer

Statistical computations via pandas + scikit-learn:

- **Spec conversion rate** — what % of plans reach build
- **Skill velocity** — which skills get invoked most / least over time
- **Session health trends** — pulse scores over time (degrading? improving?)
- **Lesson backlog growth** — are drafts piling up faster than they're published?
- **Plan topic clustering** — group orphaned specs by theme (NLP, k-means on spec content)
- **Repeat GOTCHA patterns** — same failure type appearing across projects

---

## Outputs

### Phase 1 — HTML Dashboard
Single-page interactive report. Standalone HTML, no server needed. Beautiful charts.
Exportable for sharing.

### Phase 2 — `.pbip` Power BI Project
Power BI Projects format (plain JSON, git-friendly). Opens in Power BI Desktop at work
(PLMarketing). Deneb visuals for custom charts that match the HTML design spec.

### Phase 3 — TORII Integration
Analytics panel inside TORII. Claude-queryable via PandasAI NL interface.

---

## Repo Roles

| Repo | Role |
|---|---|
| pandas | Core ETL — parse markdown, JSON, git log |
| scikit-learn | Clustering (topic grouping), trend detection |
| PandasAI | Optional: NL queries on the dataset |
| Streamlit | Dev/preview mode during build only |
| CyberChef | Parse raw log/security data if Kroger data feeds in |
| Airbyte | Phase 2+ — ingest external data sources |
| TrendRadar / BettaFish | Phase 3 — external signal feeds |
| LogisticReg / PyTorch pipelines | Reference patterns only |
| scientific-agent-skills | Phase 3 — agent-driven analysis queries |
| best-of-ml-python | Reference only — not a runtime dep |
| Superset / DataEase / Gradio / Reflex | Skip — Power BI + HTML covers the use case |

---

## Build Sequence

```
Phase 1 (after wedding editor)
  1. Data harvester — reads pulse files, planning specs, git log, memory index
  2. Analysis engine — pandas ETL + scikit-learn stats
  3. HTML dashboard — Claude-rendered, single-page, no server

Phase 2
  4. .pbip generator — same data → Power BI Projects output
  5. Deneb visuals — match HTML design in Power BI native format

Phase 3
  6. TORII analytics panel
  7. PandasAI NL query interface
  8. External data feeds (Airbyte, TrendRadar, BettaFish)
```

---

## Success Criteria

- SC-001: Can identify all orphaned specs (plans with no build) across all projects
- SC-002: Pulse health trend visible over time (not just latest snapshot)
- SC-003: `.pbip` opens in Power BI Desktop without manual data entry
- SC-004: HTML dashboard is standalone — no Python server required to view
- SC-005: Skill velocity chart shows which dream-studio skills are over/underused

---

## Out of Scope (for now)
- TORII integration
- Real-time / live data refresh
- External data sources (Airbyte, social feeds)
- Predictive modeling (Phase 3+)
