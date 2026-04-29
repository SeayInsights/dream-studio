# dream-studio — Project Instructions

## Skill Routing

When the user's intent matches a dream-studio skill, invoke it via the Skill tool — never fall back to built-in Claude behavior. Match on the trigger keywords below. Exception: if the user explicitly says "built-in" (e.g. "built-in plan"), use native behavior.

### Exploration & Research
Not every request needs a full skill. Casual lookups get dispatched as lightweight subagents:
- **"go check", "look into", "investigate", "what's going on with"** → Spawn an Explore subagent (Haiku model). Quick codebase/file lookup, report back.
- **"research", "dig into", "explore options"** → If scoped to a codebase question, use Explore. If it needs design thinking or spec work, escalate to `dream-studio:think` with the `research:` trigger.
- **"go find", "where is", "search for"** → Explore subagent or direct Grep/Glob — no skill needed.

### Build Pipeline (sequential: think → plan → build → review → verify → ship)
| Intent | Skill | Triggers |
|--------|-------|----------|
| Spec / design before code | `dream-studio:think` | think:, spec:, shape ux:, design brief:, research: |
| Break spec into tasks | `dream-studio:plan` | plan:, make a plan, /plan |
| Execute a plan | `dream-studio:build` | build:, execute plan: |
| Code review | `dream-studio:review` | review:, review code, review commits, review PR: |
| Prove it works | `dream-studio:verify` | verify:, prove it: |
| Pre-deploy gate | `dream-studio:ship` | ship:, pre-deploy: |

### Quality & Learning
| Intent | Skill | Triggers |
|--------|-------|----------|
| Systematic debugging | `dream-studio:debug` | debug:, diagnose: |
| Explain code / system | `dream-studio:explain` | explain:, how does X work, walk me through, what is this doing |
| UI polish | `dream-studio:polish` | polish ui:, clean up ui:, critique design:, redesign:, make it premium: |
| Security review | `dream-studio:secure` | secure:, check security, review architecture |
| Project hardening | `dream-studio:harden` | /harden, harden audit |
| Capture lessons | `dream-studio:learn` | learn:, capture lesson: |
| Workflow coaching | `dream-studio:coach` | /coach, coach: |
| Structure audit | `dream-studio:structure-audit` | /structure-audit |

### Security Pack
| Intent | Skill | Triggers |
|--------|-------|----------|
| Scan org, security scan, generate rules | `dream-studio:scan` | scan org:, run security scan, generate scan rules |
| Mitigate findings, how to fix | `dream-studio:mitigate` | mitigate:, how to fix, generate mitigations |
| Compliance map, audit evidence | `dream-studio:comply` | comply:, compliance map, audit evidence, framework map |
| Zscaler compat, proxy check | `dream-studio:netcompat` | netcompat:, zscaler check, proxy compat |
| Security dashboard, export dataset | `dream-studio:security-dashboard` | security dashboard:, refresh dashboard, export dataset |
| DAST, web scan, pen test web | `dream-studio:dast` | dast:, web scan, pen test web, zap scan |
| Binary analysis, scan exe | `dream-studio:binary-scan` | binary-scan:, scan binary, analyze exe, checksec |

### Visual & Design
| Intent | Skill | Triggers |
|--------|-------|----------|
| Visual design / branding / direction | `dream-studio:design` | design art:, brand:, apply theme:, ad creative:, design direction:, visual identity: |
| HTML prototypes / slides / animations | `huashu-design` | prototype:, mockup:, slides:, deck:, animate:, motion:, export pptx:, export mp4: |

**Design skill routing:**
- **dream-studio:design** — Brand asset acquisition, design direction advisory, visual identity, theme application, generative art (p5.js), ad creative. Creates brand-spec.md with logo/images/colors.
- **huashu-design** — Interactive prototypes (iOS/Android), slide decks (HTML + editable PPTX), motion design (MP4/GIF with 60fps), design variations with Tweaks, infographics (PDF/PNG/SVG).
- **Workflow:** dream-studio:design establishes brand assets → huashu-design produces deliverables using those assets.

### Domain Builders
| Intent | Skill | Triggers |
|--------|-------|----------|
| SaaS features | `dream-studio:saas-build` | build feature:, build api:, build page:, build component: |
| Godot game dev | `dream-studio:game-dev` | game build, game review, game QA |
| MCP server dev | `dream-studio:mcp-build` | build mcp:, new mcp:, extend mcp: |
| Dashboard / Tauri | `dream-studio:dashboard-dev` | dashboard:, build dashboard: |
| Power Platform / client | `dream-studio:client-work` | intake:, sow:, review powerbi:, optimize dax:, build flow: |
| Real estate domain | `dream-studio:domain-re` | /domain-re, re: |

### Analysis & Career
| Intent | Skill | Triggers |
|--------|-------|----------|
| Multi-perspective analysis | `dream-studio:analyze` | /analyze, analyze: |
| Career command center | `dream-studio:career-ops` | /career-ops |

### Session Management
| Intent | Skill | Triggers |
|--------|-------|----------|
| Session handoff | `dream-studio:handoff` | handoff: |
| Session recap | `dream-studio:recap` | recap:, session recap: |
| YAML workflow orchestration | `dream-studio:workflow` | workflow:, workflow list |

### Routing Fallback

If the user's intent does not match any trigger keyword in the tables above, route to `dream-studio:coach` with mode `route-classify`. Coach will classify the intent, map it to the nearest skill, and explain confidence + alternatives. This prevents unmatched intents from falling through to raw Claude default behavior.

## GitHub Workflow
- **Never push directly to `main`** — always create a feature branch first.
- Before starting PR work, check for open PRs on the repo (`gh pr list`) to avoid conflicts or duplicate work.
- Branch naming: `feat/<topic>`, `fix/<topic>`, `chore/<topic>` — keep it short and descriptive.
- Keep PRs under ~120 lines of changes. Split larger work into independent PRs.
- Before creating a PR, check for a pull request template in the repo (`.github/PULL_REQUEST_TEMPLATE.md` or `.github/PULL_REQUEST_TEMPLATE/`).
- Use `gh` CLI for all GitHub operations (PRs, issues, releases), not the MCP GitHub tools.
- Never force-push without explicit user approval.
- Never push to stale/old branches — check branch freshness first.
- **Before pushing to a branch with an existing PR**, run `gh pr view <branch> --json state` to check if it's been merged or closed. If merged/closed, pull latest main, create a new branch, cherry-pick or reapply changes, and open a new PR. Never push commits to a branch whose PR is already merged.

## Commits
- Never add Co-Authored-By attribution to git commits.
- One logical change per commit. Commit messages should explain why, not what.

## Deploys
- Never run `wrangler deploy` or any direct deploy command — push to GitHub and let CI handle it.

## Model Usage
- Use Haiku for searches/exploration subagents; Sonnet for code-change subagents.

## Portable Setup
If using dream-studio as a plugin in another project, add this to your global `~/.claude/CLAUDE.md`:
```markdown
## dream-studio overrides
- When the user's intent matches a dream-studio skill trigger, invoke the skill via the Skill tool — never fall back to built-in Claude behavior. See the Skill Routing table in the dream-studio CLAUDE.md for the full mapping.
- For GitHub workflow, follow the conventions in the dream-studio CLAUDE.md.
```
