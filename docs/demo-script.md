# Demo Video Script: Idea to PR in dream-studio

**Duration**: 2-5 minutes  
**Format**: Screen recording with voiceover  
**Resolution**: 1080p, MP4  
**Target**: New users considering dream-studio

---

## Opening (0:00-0:15)

**Visual**: Desktop with terminal open, clean workspace

**Narration**:
> "Welcome! In the next 3 minutes, I'll show you how dream-studio takes you from an idea to a production-ready pull request - automatically."

**Action**:
- Show terminal prompt
- Type: `cd my-project`

---

## 1. The Idea (0:15-0:30)

**Visual**: Text editor showing project README or codebase

**Narration**:
> "Let's say we want to add user authentication to our app. Instead of jumping into code, we start with think mode."

**Action**:
- Open Claude Code
- Type in chat: `think: add user authentication with email/password`
- Press Enter

---

## 2. Think Mode → Spec Generation (0:30-1:00)

**Visual**: Claude generating the spec in real-time

**Narration**:
> "Think mode analyzes our request and generates a comprehensive spec with user stories, technical approach, edge cases, and security considerations."

**Action**:
- Show spec being generated
- Highlight key sections as they appear:
  - Problem statement
  - User stories ("As a user, I want to...")
  - Technical architecture
  - Security (password hashing, session management)
  - Success metrics

**Visual**: Spec saved to `.planning/specs/user-authentication/spec.md`

**Narration**:
> "The spec is saved automatically. Now let's break it down into tasks."

---

## 3. Plan Mode → Task Breakdown (1:00-1:30)

**Action**:
- Type: `plan: .planning/specs/user-authentication/spec.md`
- Press Enter

**Visual**: Plan being generated

**Narration**:
> "Plan mode takes the spec and creates a detailed implementation plan with tasks, dependencies, and complexity tracking."

**Action**:
- Show plan.md and tasks.md being created
- Open tasks.md and scroll through tasks:
  - T001: Create User model
  - T002: Add password hashing
  - T003: Implement login endpoint
  - T004: Add session management
  - T005: Write tests

**Narration**:
> "Five tasks, organized by dependency. Let's build it."

---

## 4. Build Mode → Implementation (1:30-2:30)

**Action**:
- Type: `build: .planning/specs/user-authentication/tasks.md`
- Press Enter

**Visual**: Build mode executing tasks in waves

**Narration**:
> "Build mode reads the task list and implements them in dependency order."

**Action**:
- Show tasks being executed:
  - Wave 1: T001, T002 (can run in parallel)
  - Creating User model (show file being created)
  - Adding password hashing logic
  - Each task commits automatically

**Visual**: Git log showing commits:
```
feat(task-2): add bcrypt password hashing [TR-002]
feat(task-1): create User model with email field [TR-001]
```

**Narration**:
> "Each task gets its own commit with traceability to requirements. Five tasks completed in under a minute."

---

## 5. Review Mode → Quality Check (2:30-3:00)

**Action**:
- Type: `review: code`
- Press Enter

**Visual**: Review mode analyzing the implementation

**Narration**:
> "Before we ship, let's run a two-stage quality review."

**Action**:
- Show review findings:
  - ✅ Code quality: PASS
  - ✅ Security: PASS  
  - ⚠️ Test coverage: Add integration test for login flow
  - ✅ Documentation: PASS

**Narration**:
> "One suggestion - add an integration test. Let's do that."

**Action**:
- Type: `build: add integration test for login flow`
- Show test being created and committed

---

## 6. Verify Mode → Evidence (3:00-3:30)

**Action**:
- Type: `verify: authentication works end-to-end`
- Press Enter

**Visual**: Verify mode running tests

**Narration**:
> "Verify mode provides evidence-based validation. It runs tests, checks the implementation, and confirms everything works."

**Action**:
- Show test results:
  - ✅ Unit tests: 12/12 passing
  - ✅ Integration test: Login flow works
  - ✅ Security audit: No vulnerabilities found

**Narration**:
> "All green. Time to ship."

---

## 7. Ship Mode → Pre-Deploy Gate (3:30-4:00)

**Action**:
- Type: `ship:`
- Press Enter

**Visual**: Ship mode running final checks

**Narration**:
> "Ship mode is the final quality gate before deployment."

**Action**:
- Show checklist:
  - ✅ All tests passing
  - ✅ No security vulnerabilities
  - ✅ Branch up to date with main
  - ✅ CI checks passing
  - ✅ Code reviewed (self-review complete)
  - ✅ Documentation updated

**Narration**:
> "Everything passes. Creating the pull request."

---

## 8. Pull Request Created (4:00-4:30)

**Visual**: GitHub PR view

**Action**:
- Show PR being created automatically:
  - Title: "feat: Add user authentication"
  - Description with:
    - Summary of changes
    - Test plan
    - Traceability links to spec
  - 7 commits
  - All CI checks passing

**Narration**:
> "The PR is ready for team review - complete with tests, documentation, and full traceability from idea to implementation."

---

## Closing (4:30-5:00)

**Visual**: Side-by-side comparison:
- Left: "Without dream-studio" (manual process, scattered notes, hours of work)
- Right: "With dream-studio" (think → plan → build → review → verify → ship, 10 minutes)

**Narration**:
> "From idea to production-ready PR in under 10 minutes. That's dream-studio - turning ideas into reality, faster."

**Action**:
- Show dream-studio logo
- Display: "Get started at github.com/SeayInsights/dream-studio"

**End screen**:
```
dream-studio
think → plan → build → review → verify → ship

github.com/SeayInsights/dream-studio
```

---

## Technical Notes for Recording

### Equipment/Software Needed
- Screen recording: OBS Studio (free) or ScreenFlow (Mac) or Camtasia
- Microphone: USB mic or headset with good audio
- Video editing: DaVinci Resolve (free) or Final Cut Pro

### Recording Settings
- Resolution: 1920x1080 (1080p)
- Frame rate: 30 fps
- Format: MP4 (H.264 codec)
- Audio: 48kHz, stereo
- Bitrate: 8-10 Mbps (for crisp text)

### Terminal Setup
- Font size: 16-18pt (readable in 1080p)
- Color scheme: High contrast (dark background, light text)
- Zoom level: 125-150%
- Clear terminal history before starting

### Editing Tips
- Add subtle background music (royalty-free, low volume)
- Use text overlays for key points
- Add transitions between sections (simple cuts or 0.5s crossfade)
- Export with quality settings:
  - Codec: H.264
  - Quality: High (85-90%)
  - File size target: < 100 MB

### Alternative: No Voiceover Version
If recording voiceover is difficult, create a silent version with text captions:
- Add larger text overlays explaining each step
- Use annotations/arrows to highlight actions
- Include upbeat background music throughout
- Extend duration slightly to give viewers time to read

---

## B-Roll Ideas (Optional Enhancements)

- Before/after comparison: messy planning docs vs clean dream-studio specs
- Testimonials: "Saved our team 10 hours per week"
- Feature callouts: "Automatic traceability", "Quality gates", "Self-improving"
- Live coding vs dream-studio speed comparison

---

## Distribution Checklist

Once video is complete:
- [ ] Upload to YouTube (Twin Roots LLC channel)
- [ ] Add to dream-studio README (embedded player)
- [ ] Share on Twitter/X, LinkedIn
- [ ] Submit to Show HN
- [ ] Add to claudemarketplace.com submission
- [ ] Create thumbnail (1280x720, with title overlay)
- [ ] Add closed captions (accessibility)
