# dream-studio Build Roadmap

**Last Updated**: 2026-04-30  
**Status**: Active — three approved specs awaiting sequencing

---

## Current State

### Active Specs

| Spec | Status | Location | Created | Priority |
|------|--------|----------|---------|----------|
| **onboarding** | Draft (needs approval) | `.planning/specs/onboarding/spec.md` | 2026-04-30 | P0 (blocks new user adoption) |
| **ds-analytics** | Approved (parked) | `.planning/specs/ds-analytics/spec.md` | 2026-04-29 | P1 (observability) |
| **multi-ai-adapters** | Approved (parked) | `.planning/specs/multi-ai-adapters/spec.md` | 2026-04-29 | P1 (portability) |

### Current Blocker
**Wedding website editor** (`C:\Users\Dannis Seay\builds\dannis-naomi`) — must ship before resuming dream-studio work.

---

## Spec Summaries

### 1. Onboarding (NEW)
**Purpose**: First-run setup experience for users who clone dream-studio from GitHub

**Key Features**:
- First-run detection with one-time setup prompt
- Three paths: wizard (full install), as-needed (progressive), read-docs (manual)
- Fallback architecture — skills work with zero external dependencies
- Tool detection and guided installation (gh, Firecrawl, Playwright)
- README with three profiles: Minimal, Standard, Full

**User Impact**: 
- New users can run skills immediately (no "command not found" errors)
- Power users get clear path to full-featured setup
- Cross-platform support (Windows/Mac/Linux)

**Deliverables**:
- `dream-studio:setup` skill (wizard + status commands)
- `skills/core/web.md` (web access with Firecrawl fallback)
- `skills/core/setup.md` (detection and preference management)
- Updated README with setup profiles

---

### 2. ds-analytics (PARKED)
**Purpose**: Analytics engine that reads dream-studio's own data for observability

**Key Features**:
- Data harvester (pulse reports, specs, git log, memory index)
- Statistical analysis (spec conversion rate, skill velocity, session health)
- Phase 1: Standalone HTML dashboard
- Phase 2: `.pbip` Power BI Projects output for PLMarketing
- Phase 3: TORII integration with PandasAI

**User Impact**:
- Visibility into dream-studio health (are specs getting built? which skills are used?)
- Orphaned plan detection (specs that never shipped)
- Session quality trends over time

**Deliverables**:
- Python harvester (`scripts/harvest_analytics.py`)
- Analysis engine (pandas + scikit-learn)
- HTML dashboard template
- `.pbip` generator (Phase 2)

---

### 3. multi-ai-adapters (PARKED)
**Purpose**: Portability layer to make dream-studio work on Cursor, Copilot, Windsurf

**Key Features**:
- Build script reads all `skills/*/SKILL.md` files as source of truth
- Template-per-platform (Jinja2)
- Outputs: `.cursorrules` (Cursor), `copilot-instructions.md` (Copilot), `system-prompt.md` (generic)
- No manual skill edits — adapters are generated artifacts

**User Impact**:
- dream-studio skills work on other AI platforms (guidance-only, no hook enforcement)
- Domain knowledge portable across all LLMs
- One `make adapters` command regenerates all platform files

**Deliverables**:
- `scripts/build_adapters.py` (build script)
- `scripts/adapter_templates/<platform>.j2` (templates)
- `dist/adapters/<platform>/` (generated outputs)
- Makefile target: `make adapters`

---

## Dependencies & Relationships

### Cross-Spec Dependencies

```
onboarding ──┬──> multi-ai-adapters (README references adapter setup for non-Claude-Code users)
             │
             └──> ds-analytics (optional: onboarding metrics as data source)

ds-analytics ───> onboarding (can track setup completion rate, tool adoption)

multi-ai-adapters ──> onboarding (adapter users follow different setup path)
```

### Integration Points

1. **onboarding → multi-ai-adapters**
   - README must include setup path for Cursor/Copilot users
   - "If using Cursor, run `make adapters` after setup to generate `.cursorrules`"
   - Adapter README links back to main onboarding README

2. **onboarding → ds-analytics**
   - Setup wizard can emit telemetry to `.dream-studio/meta/setup-events.log`
   - ds-analytics Phase 2 can add "Setup Completion Funnel" dashboard
   - Track: which tools are most/least adopted, wizard vs as-needed vs manual paths

3. **multi-ai-adapters ← onboarding**
   - Adapter build script should work regardless of user's setup choice
   - Generated adapters should mention fallback behavior for missing tools
   - System-prompt adapter includes condensed setup instructions

---

## Proposed Build Sequence

### Phase 0: Current Blocker (IN PROGRESS)
**Wedding website editor** — ship before resuming dream-studio

**Milestone**: Editor deployed, handoff complete

---

### Phase 1: Onboarding (NEXT — Priority P0)
**Why first**: Blocks new user adoption. Every other feature assumes users can set up dream-studio successfully.

**Build sequence**:
1. `skills/core/setup.md` — detection logic, preference management
2. `skills/core/web.md` — Firecrawl → WebSearch fallback
3. `dream-studio:setup` skill — wizard + status command
4. Update `skills/core/git.md` — gh CLI detection + fallback
5. README — three profiles (Minimal, Standard, Full)
6. Verify: fresh clone → run any skill → works without setup

**Deliverable**: New users can clone and run skills immediately

**Milestone**: SC-001 met (skills work within 2 minutes of clone)

---

### Phase 2: ds-analytics Phase 1 (AFTER onboarding)
**Why second**: Now that onboarding is solid, we can observe adoption patterns. Analytics helps validate onboarding success.

**Build sequence** (from existing spec):
1. Data harvester — reads pulse files, planning specs, git log, memory index
2. Analysis engine — pandas ETL + scikit-learn stats
3. HTML dashboard — Claude-rendered, single-page, no server
4. *Optional*: Add onboarding metrics data source

**Deliverable**: Standalone HTML analytics dashboard

**Milestone**: Can identify orphaned specs, skill velocity trends

---

### Phase 3: multi-ai-adapters (AFTER ds-analytics Phase 1)
**Why third**: By now, onboarding is tested and analytics are tracking. Adapters expand reach to other platforms.

**Build sequence** (from existing spec):
1. `scripts/build_adapters.py` — extraction logic, template engine
2. `scripts/adapter_templates/` — Cursor, Copilot, system-prompt templates
3. `Makefile` target: `make adapters`
4. Update README with adapter setup instructions for non-Claude-Code users
5. Link onboarding README → adapter README

**Deliverable**: `.cursorrules`, `copilot-instructions.md`, `system-prompt.md`

**Milestone**: Cursor user can run dream-studio workflows

---

### Phase 4: ds-analytics Phase 2 (AFTER adapters)
**Why last**: Power BI output for PLMarketing. Not user-blocking, but valuable for work context.

**Build sequence** (from existing spec):
1. `.pbip` generator — same data → Power BI Projects output
2. Deneb visuals — match HTML design in Power BI native format
3. *Optional*: Add adapter usage metrics (which platforms are adopted)

**Deliverable**: `.pbip` file for Power BI Desktop

**Milestone**: Analytics dashboard opens in Power BI at PLMarketing

---

## Timeline Estimates

| Phase | Effort | Duration | Dependency |
|-------|--------|----------|------------|
| Wedding editor | (in progress) | ~1 week | None |
| **Onboarding** | Medium | 3-5 days | Wedding editor complete |
| **ds-analytics P1** | Medium | 3-4 days | Onboarding shipped |
| **multi-ai-adapters** | Medium | 2-3 days | ds-analytics P1 shipped |
| **ds-analytics P2** | Low | 1-2 days | multi-ai-adapters shipped |

**Total post-wedding**: ~10-14 days for all three specs

---

## Success Criteria (Roadmap-Level)

### Onboarding Success
- **RS-001**: New user clones dream-studio, runs first skill within 2 minutes (using fallbacks)
- **RS-002**: 90% of skills work with zero external dependencies
- **RS-003**: Setup wizard completion rate ≥ 70% for users who choose "wizard" path

### ds-analytics Success
- **RS-004**: HTML dashboard shows skill velocity trends across all 38 skills
- **RS-005**: Orphaned specs detected with 100% accuracy
- **RS-006**: `.pbip` opens in Power BI Desktop at PLMarketing without manual edits

### multi-ai-adapters Success
- **RS-007**: Cursor user runs `make adapters` and gets working `.cursorrules` with all skill triggers
- **RS-008**: system-prompt.md under 8,000 tokens (fits in most LLM contexts)
- **RS-009**: Adapter regeneration completes in under 10 seconds

### Integration Success
- **RS-010**: Onboarding README references adapter setup for non-Claude-Code users
- **RS-011**: ds-analytics dashboard includes onboarding funnel metrics (Phase 2)
- **RS-012**: No spec conflicts — all three can coexist without breaking changes

---

## Open Questions / Decisions Needed

### Onboarding
- **Q1**: Should onboarding emit telemetry by default, or opt-in only?
  - **Recommendation**: Opt-in during wizard, silent for "as-needed" and "read-docs" paths
- **Q2**: Should `dream-studio:setup status` show recommended next tools based on user's skill usage?
  - **Recommendation**: Phase 2 enhancement (after ds-analytics can track skill usage)

### ds-analytics
- **Q3**: Where does `.pbip` output go — dream-studio repo or separate PLMarketing repo?
  - **Recommendation**: dream-studio repo for Phase 2, sync to PLMarketing repo manually
- **Q4**: Should onboarding metrics be included in Phase 1 or Phase 2?
  - **Recommendation**: Phase 2 (after onboarding is stable and producing data)

### multi-ai-adapters
- **Q5**: Is `dist/adapters/` gitignored (generated artifacts) or committed (release artifacts)?
  - **Recommendation**: Committed — users who clone should get adapters without running build
- **Q6**: Does Windsurf rules format match Cursor closely enough to share one template?
  - **Recommendation**: Verify during build, create separate template if needed

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Onboarding complexity delays other specs | Start with P1 only (fallbacks), defer wizard to P2 if needed |
| ds-analytics data sources change format | Abstract data layer, version harvester schemas |
| Adapters break when skill format changes | CI check: regenerate adapters on every commit, fail if token budget exceeded |
| Cross-platform onboarding fails on Windows | Test onboarding on all three platforms before merge |
| Specs drift out of sync | Roadmap review every 2 weeks, update ROADMAP.md with actuals |

---

## Approval Checklist

Before proceeding to `plan` phase for any spec:

- [ ] **onboarding**: Approved by Director (PENDING)
- [x] **ds-analytics**: Approved (2026-04-29)
- [x] **multi-ai-adapters**: Approved (2026-04-29)
- [ ] Build sequence confirmed (this roadmap approved)
- [ ] Integration points documented (see "Integration Points" above)
- [ ] Open questions resolved (see "Open Questions" above)

---

## Next Action

**AWAITING**: Director approval on:
1. This roadmap (build sequence, integration points)
2. onboarding spec (`.planning/specs/onboarding/spec.md`)
3. Answers to open questions Q1-Q6

Once approved, run:
```bash
dream-studio:plan onboarding
```

This will break the onboarding spec into tasks and start Phase 1.
