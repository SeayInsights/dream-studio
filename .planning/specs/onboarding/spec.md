# Feature Specification: dream-studio Onboarding

**Topic Directory**: `.planning/specs/onboarding/`  
**Created**: 2026-04-30  
**Status**: Draft  
**Input**: User request: "assume the user has nothing installed when getting dream-studio so how do we onboard them properly to have the best experience?"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - First-Run Detection with Graceful Fallbacks (Priority: P1)

A new user clones dream-studio from GitHub and invokes their first skill. The system detects this is their first run, asks one question about setup preference, and saves their choice. Skills work immediately regardless of their answer, using built-in tool fallbacks.

**Why this priority**: This is the MVP — without this, new users hit hard failures when skills try to call missing tools. Every other feature depends on graceful fallback logic.

**Independent Test**: Clone dream-studio fresh, run any skill (e.g., `dream-studio:core think`), verify: (1) first-run prompt appears, (2) skill completes successfully regardless of user's choice, (3) second invocation skips the prompt.

**Acceptance Scenarios**:

1. **Given** fresh dream-studio clone with no setup preferences, **When** user invokes any skill, **Then** system prompts "First time using dream-studio! Run full setup wizard, or prompt as-needed when skills need tools? [wizard/as-needed/read-docs]"
2. **Given** user selects "as-needed", **When** skill needs web scraping, **Then** skill uses WebSearch/WebFetch fallback without prompting, works successfully
3. **Given** user has saved setup preference, **When** user invokes any skill, **Then** no first-run prompt appears

---

### User Story 2 - Interactive Setup Wizard (Priority: P2)

A user who chose "wizard" path runs the setup skill, which detects what's already installed (gh CLI, Firecrawl, Playwright, etc.), shows what each tool unlocks, and offers to install missing tools with one command per tool. User can skip any tool. Setup completes with a summary of what's enabled.

**Why this priority**: This enables the "best experience" path for users who want all capabilities. P2 because skills work without it (thanks to P1 fallbacks), but this is the upsell to full-featured usage.

**Independent Test**: Run `dream-studio:setup` on a machine with only gh installed, verify: (1) detection shows gh as installed, others as missing, (2) user can selectively install tools, (3) post-setup, skills use installed tools instead of fallbacks.

**Acceptance Scenarios**:

1. **Given** dream-studio with no tools installed, **When** user runs `dream-studio:setup`, **Then** system detects missing tools, shows what each unlocks, and prompts for installation
2. **Given** user approves Firecrawl install, **When** wizard runs install command, **Then** Firecrawl CLI is installed, API key is configured, and wizard confirms success
3. **Given** setup wizard completes, **When** user runs a web-scraping skill, **Then** skill uses Firecrawl instead of WebSearch fallback

---

### User Story 3 - Just-In-Time Tool Prompts (Priority: P2)

A user who chose "as-needed" path uses dream-studio over time. When a skill could benefit from a missing tool (e.g., Firecrawl for web scraping), it prompts once: "This skill works better with Firecrawl. Install now? [y/n/never]". User's choice is saved per tool. If "never", skill never prompts again and uses fallback.

**Why this priority**: This serves users who want progressive enhancement without upfront commitment. P2 because it's an alternative to the wizard (not cumulative).

**Independent Test**: Choose "as-needed" on first run, invoke a skill that benefits from Firecrawl, verify: (1) prompt appears, (2) selecting "never" prevents future prompts, (3) selecting "y" installs and uses the tool.

**Acceptance Scenarios**:

1. **Given** user chose "as-needed" and has no Firecrawl, **When** user runs web scraping skill, **Then** system prompts once to install Firecrawl
2. **Given** user selects "never ask", **When** same skill runs again, **Then** no prompt appears, skill uses fallback
3. **Given** user approves install, **When** tool is installed, **Then** future skill invocations use the tool automatically

---

### User Story 4 - README-Driven Manual Setup (Priority: P3)

A user who prefers reading documentation first opens the README, finds three documented paths (Minimal, Standard, Full), picks one, and manually runs the listed install commands. They can verify their setup with a `dream-studio:setup status` command that shows what's installed.

**Why this priority**: This serves "read first" users who don't want interactive prompts. P3 because it's documentation-only — no new tooling required beyond what P1/P2 build.

**Independent Test**: Follow README instructions for "Standard" profile, run `dream-studio:setup status`, verify output shows installed tools and what they unlock.

**Acceptance Scenarios**:

1. **Given** user reads README, **When** they run "Standard" profile commands, **Then** gh CLI and basic tools are installed
2. **Given** user has partially followed setup, **When** they run `dream-studio:setup status`, **Then** system shows what's installed vs missing
3. **Given** user chose "read-docs" on first run, **When** skills run, **Then** no runtime prompts appear, relies on pure fallbacks

---

### User Story 5 - Fallback Architecture for Core Modules (Priority: P1)

Core modules (web.md, git.md) detect what tools are available and choose the best option automatically. Example: web.md tries Firecrawl first, falls back to scraper-mcp, then WebSearch/WebFetch. Users never see "command not found" errors.

**Why this priority**: This is part of P1 MVP — without this, skills break for users who haven't installed optional tools. The fallback logic is what makes "minimum viable" viable.

**Independent Test**: Remove Firecrawl from PATH, run a web scraping skill, verify: (1) no error, (2) skill uses WebSearch instead, (3) output quality is acceptable (markdown extraction works).

**Acceptance Scenarios**:

1. **Given** Firecrawl is not installed, **When** skill needs web data, **Then** web.md falls back to WebSearch/WebFetch without error
2. **Given** gh CLI is not installed, **When** skill needs GitHub ops, **Then** git.md prompts user for manual GitHub actions or uses API fallback
3. **Given** multiple tools are missing, **When** skill runs, **Then** all fallbacks work in sequence, skill completes successfully

---

### Edge Cases

- What happens when user has Firecrawl installed but no API key configured?
  - Wizard detects this as "partially installed", offers to complete auth flow
  - JIT prompt includes both install + auth steps
  - Fallback triggers if API key is invalid/expired

- How does system handle cross-platform differences (Windows/Mac/Linux)?
  - Detection uses platform-agnostic commands (`which` on Unix, `where` on Windows)
  - Install commands documented per platform in README
  - Wizard detects OS and shows OS-specific commands

- What happens when user chooses "wizard" but cancels mid-setup?
  - Partial progress is saved (e.g., if gh is installed but Firecrawl cancelled)
  - User can re-run wizard to resume from where they left off
  - Skills use fallbacks for any incomplete tool installs

- How do we handle tools that need accounts/API keys (Firecrawl, GitHub)?
  - Wizard guides user through browser auth flows
  - JIT prompts link to sign-up pages with context
  - Fallbacks don't require authentication (WebSearch, manual git)

- What happens when a tool version is outdated or incompatible?
  - Status command shows version + warns if outdated
  - Skills gracefully degrade if tool version doesn't support a feature
  - README includes version requirements per tool

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST detect first-run state on any skill invocation and prompt user once for setup preference
- **FR-002**: System MUST save user's setup preference to `.dream-studio/setup-prefs.json` and never prompt again
- **FR-003**: System MUST provide three onboarding paths: wizard, as-needed, read-docs
- **FR-004**: System MUST include fallback tool logic in core modules so skills work with zero external dependencies
- **FR-005**: Setup wizard MUST detect installed tools (gh, firecrawl, playwright, etc.) and show current state
- **FR-006**: Setup wizard MUST show what each tool unlocks (which skills/features benefit)
- **FR-007**: Setup wizard MUST provide one-command install per tool with platform detection
- **FR-008**: JIT prompts MUST appear maximum once per tool, with "never ask" option
- **FR-009**: User's per-tool preferences (install, skip, never) MUST be saved to `.dream-studio/setup-prefs.json`
- **FR-010**: README MUST document three profiles: Minimal (nothing), Standard (gh + basics), Full (everything)
- **FR-011**: README MUST include per-tool explanations (what it is, what it unlocks, how to install)
- **FR-012**: System MUST provide `dream-studio:setup status` command showing installed tools
- **FR-013**: Core modules MUST detect tool availability at runtime and choose best available option
- **FR-014**: Fallback logic MUST be silent (no warnings/errors when using fallback tools)
- **FR-015**: Wizard MUST handle browser auth flows for tools requiring API keys (Firecrawl, GitHub)

### Key Entities

- **Setup Preference**: User's chosen onboarding path (wizard/as-needed/read-docs), saved on first run
- **Tool Status**: Per-tool state (installed, missing, partially-configured), detected at runtime
- **Tool Metadata**: Definition of each tool (name, detection command, install command, what it unlocks, docs link)
- **Core Module**: Shared skill component (web.md, git.md) with fallback logic
- **Profile**: Named collection of tools (Minimal, Standard, Full) documented in README

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: New user can clone dream-studio and run any skill successfully within 2 minutes (using fallbacks)
- **SC-002**: User who runs setup wizard can install all tools in under 10 minutes (assuming accounts already exist)
- **SC-003**: 90% of skills work with zero external dependencies (fallback mode)
- **SC-004**: Setup preference prompt appears exactly once per fresh installation
- **SC-005**: Status command shows tool detection accuracy of 100% (no false positives/negatives)
- **SC-006**: JIT prompts appear maximum once per tool per installation (user's "never" choice is respected)
- **SC-007**: README instructions result in successful manual setup (verified by status command)

## Acceptance Criteria

| AC-ID | Given | When | Then |
|-------|-------|------|------|
| AC-001 | Fresh dream-studio clone | User runs first skill | First-run prompt appears with 3 choices |
| AC-002 | User selects "wizard" | Wizard runs | All tools are detected, install options shown |
| AC-003 | User selects "as-needed" | Skill needs Firecrawl | JIT prompt appears once, user choice saved |
| AC-004 | User selects "read-docs" | Skills run | No runtime prompts, fallbacks used |
| AC-005 | Firecrawl not installed | Skill needs web data | web.md uses WebSearch/WebFetch fallback |
| AC-006 | gh CLI not installed | Skill needs GitHub ops | git.md prompts for manual action or uses API |
| AC-007 | Setup wizard completes | User runs skill | Skill uses installed tools, not fallbacks |
| AC-008 | User runs status command | Tools partially installed | Status shows installed (green), missing (yellow) |
| AC-009 | User has Firecrawl API key expired | Skill tries web scraping | Fallback triggers, no hard error |
| AC-010 | User cancels wizard mid-setup | User re-runs wizard | Partial progress preserved, resume offered |

**Rules:**
- AC-001, AC-005, AC-006 map to FR-001, FR-004 (P1 MVP)
- AC-002, AC-007, AC-010 map to FR-005, FR-006, FR-007 (P2 wizard)
- AC-003 map to FR-008, FR-009 (P2 JIT prompts)
- AC-004, AC-008 map to FR-010, FR-011, FR-012 (P3 README)
- AC-009 validates edge case (partial/invalid config)

## Assumptions

- Users have terminal access and basic CLI familiarity (can run commands, understand PATH)
- Users can create accounts on external services (GitHub, Firecrawl) if they want full features
- Platform detection works via standard commands (Windows: `where`, Unix: `which`)
- Claude Code is already installed and dream-studio is available as a plugin
- Network connectivity is available for tool downloads and API calls
- User's environment allows npm/npx for Firecrawl CLI install
- README is the entry point for documentation (users find it naturally on GitHub)

## dream-studio Integration

**Skill Flow**: think → plan → build → review → verify → ship

**New Skills Created**:
- `dream-studio:setup` (wizard mode, status command)
- `dream-studio:setup-check` (detection utility, used by core modules)

**New Core Modules**:
- `skills/core/web.md` (web access with Firecrawl → scraper-mcp → WebSearch fallback)
- `skills/core/setup.md` (detection logic, preference management)

**Modified Core Modules**:
- `skills/core/git.md` (add gh CLI detection + fallback to manual GitHub ops)

**Output Location**: `.planning/specs/onboarding/spec.md`

**Next Steps**: 
1. Run `dream-studio:plan` to break this spec into implementation tasks
2. Output will be `.planning/specs/onboarding/plan.md` and `tasks.md`

## PRD Context

**Problem Statement:** 
New users who clone dream-studio from GitHub have zero context on setup requirements. Skills reference external tools (Firecrawl, gh CLI, Playwright) without any onboarding flow. When a skill calls a missing tool, it fails with "command not found", creating a broken first impression.

**Target User:** 
Two personas:
1. **BI Developer** (like Dannis) — comfortable with CLI, wants best experience, willing to set up tools
2. **Casual Developer** — evaluating dream-studio, wants to try it without commitment, needs it to "just work"

**Business Goal:** 
Reduce time-to-first-success for new users. Support both "try with zero setup" (fallback mode) and "unlock full power" (guided setup) paths.

**Success looks like:** 
30 days after ship:
- New users report skills work immediately (no "command not found" issues)
- Power users have clear path to install optional tools
- Support questions about "how to install X" answered by README
- Metrics: 90%+ first-skill success rate, 50%+ wizard completion rate for users who choose it
