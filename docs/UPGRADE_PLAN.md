# Design Skill Upgrade Plan
**Created:** 2026-05-07  
**Target:** Upgrade ds-domains design mode to 9.0+/10.0 capability score  
**Current:** Basic design mode with minimal tooling  
**Approach:** 90% open-design + 10% ui-ux-pro-max reasoning system

---

## Executive Summary

Upgrade the design skill by extracting best-in-class capabilities from analyzed repositories:
- **Foundation (90%):** open-design - 7 out of 10 perfect scores (10.0/10.0)
- **Reasoning (10%):** ui-ux-pro-max-skill - structured design decision database
- **Custom Build:** Components, anti-patterns, quality gates (all repos weak)

**Target Score:** 9.0+/10.0 (current best external repo: 7.8/10.0)

---

## Current State

### Existing Design Mode Location
```
skills/domains/modes/design/
├── SKILL.md           # Current design mode instructions
├── gotchas.yml        # Known issues (if exists)
└── [minimal tooling]
```

### Current Capabilities
- Basic design prompts
- Limited asset generation
- No structured reasoning
- No quality gates
- No comprehensive design system

---

## Phase 1: Foundation Extraction (Weeks 1-3)
**Source:** open-design repository  
**Priority:** CRITICAL  
**Effort:** 2-3 weeks

### 1.1 Color Systems (Weight: 15%)
**Target Score:** 10.0/10.0

**Extract from open-design:**
- `colors.csv` - Color palette definitions
- OKLCH color space implementation
- Contrast checking tools
- Color system documentation

**Integration:**
```
skills/domains/modes/design/
├── systems/
│   └── colors/
│       ├── colors.csv              # Main color palette
│       ├── oklch-converter.py      # OKLCH color space tools
│       ├── contrast-checker.py     # WCAG contrast validation
│       └── README.md               # Color system docs
```

**Actions:**
- [ ] Clone open-design repository
- [ ] Extract color system files
- [ ] Adapt OKLCH tools for dream-studio
- [ ] Test color generation with Canva MCP
- [ ] Document color system usage

---

### 1.2 Typography (Weight: 12%)
**Target Score:** 10.0/10.0

**Extract from open-design:**
- `typography.md` - Type system documentation
- Type ramp configurations
- Font pairing logic
- Modular scale calculations

**Integration:**
```
skills/domains/modes/design/
├── systems/
│   └── typography/
│       ├── typography.md           # Type system docs
│       ├── type-ramps.json         # Scale configurations
│       ├── font-pairings.csv       # Curated font combinations
│       └── modular-scale.py        # Scale calculator
```

**Actions:**
- [ ] Extract typography framework
- [ ] Adapt for web and print use cases
- [ ] Integrate with Canva text generation
- [ ] Create typography templates

---

### 1.3 Design Systems (Weight: 12%)
**Target Score:** 10.0/10.0

**Extract from open-design:**
- `DESIGN.md` structure
- Design system documentation templates
- Pattern library organization
- Design token schemas

**Integration:**
```
skills/domains/modes/design/
├── systems/
│   └── design-system/
│       ├── DESIGN.md.template      # Design doc template
│       ├── pattern-library/        # UI patterns
│       ├── tokens/                 # Design tokens (JSON/CSS)
│       └── documentation/          # System docs
```

**Actions:**
- [ ] Extract design system structure
- [ ] Create dream-studio design system template
- [ ] Build token generation workflow
- [ ] Document pattern library

---

### 1.4 Brand Protocols (Weight: 10%)
**Target Score:** 10.0/10.0

**Extract from open-design:**
- `brand-spec.md` - Brand specification template
- Asset management protocols
- Brand governance structure
- Core asset protocols

**Integration:**
```
skills/domains/modes/design/
├── brand/
│   ├── brand-spec.md.template      # Brand spec template
│   ├── asset-protocol.md           # Asset management rules
│   ├── governance.md               # Brand governance
│   └── examples/                   # Example brand specs
```

**Actions:**
- [ ] Extract brand protocol files
- [ ] Adapt for client work (ds-domains client-work integration)
- [ ] Create brand spec generator
- [ ] Build asset management workflow

---

### 1.5 Export Formats (Weight: 6%)
**Target Score:** 10.0/10.0

**Extract from open-design:**
- Video export pipeline (ffmpeg)
- Multi-format rendering
- Export configuration templates
- Batch export scripts

**Integration:**
```
skills/domains/modes/design/
├── export/
│   ├── video-pipeline.py           # ffmpeg wrapper
│   ├── format-configs/             # Export presets
│   ├── batch-export.py             # Batch processing
│   └── README.md                   # Export documentation
```

**Actions:**
- [ ] Extract video export scripts
- [ ] Test ffmpeg integration
- [ ] Add Canva export integration
- [ ] Document export workflows

---

### 1.6 Register System (Weight: 5%)
**Target Score:** 10.0/10.0

**Extract from open-design:**
- `brand.md` - Brand register template
- `product.md` - Product register template
- Context-aware design patterns
- Register-aware prompt engineering

**Integration:**
```
skills/domains/modes/design/
├── registers/
│   ├── brand.md.template           # Brand voice/tone
│   ├── product.md.template         # Product register
│   ├── context-engine.py           # Register detection
│   └── examples/                   # Example registers
```

**Actions:**
- [ ] Extract register system files
- [ ] Adapt for dream-studio context
- [ ] Integrate with design prompt generation
- [ ] Create register templates for common use cases

---

## Phase 2: Reasoning System (Weeks 4-5)
**Source:** ui-ux-pro-max-skill repository  
**Priority:** CRITICAL  
**Effort:** 1-2 weeks

### 2.1 Design Reasoning Database (Weight: 12%)
**Target Score:** 10.0/10.0

**Extract from ui-ux-pro-max-skill:**
- `ui-reasoning.csv` - Design decision database
- Reasoning search engine (BM25)
- Reasoning capture workflow
- Critique-reasoning integration

**Integration:**
```
skills/domains/modes/design/
├── reasoning/
│   ├── ui-reasoning.csv            # Design decisions database
│   ├── search-engine.py            # BM25 reasoning search
│   ├── capture.py                  # Capture design decisions
│   ├── critique-integration.py     # Connect to quality checks
│   └── README.md                   # Reasoning system docs
```

**CSV Schema:**
```csv
decision_id,context,decision,rationale,outcome,tags,timestamp
001,landing-page-hero,blue-accent,"Brand recognition, trust",positive,"color,branding",2026-05-07
002,mobile-nav,hamburger-menu,"Screen real estate, convention",positive,"mobile,navigation",2026-05-07
```

**Actions:**
- [ ] Extract ui-reasoning.csv and schema
- [ ] Port BM25 search engine (or rebuild with existing lib)
- [ ] Build reasoning capture tool
- [ ] Integrate with ds-quality critique workflow
- [ ] Populate initial reasoning database (100+ entries)

---

## Phase 3: Fill Critical Gaps (Weeks 6-8)
**Source:** Custom development  
**Priority:** HIGH  
**Effort:** 3-4 weeks

### 3.1 Component Library (Weight: 15%)
**Target Score:** 9.0/10.0 (from 3.0)

**Build from scratch:**
- UI kit library (buttons, forms, cards, layouts)
- Device frames (extract base from open-design, expand)
- Design tokens (JSON/CSS variables)
- Component documentation

**Integration:**
```
skills/domains/modes/design/
├── components/
│   ├── ui-kit/
│   │   ├── buttons/                # Button components
│   │   ├── forms/                  # Form components
│   │   ├── cards/                  # Card layouts
│   │   └── layouts/                # Layout systems
│   ├── device-frames/              # Phone/tablet/desktop frames
│   ├── tokens/
│   │   ├── design-tokens.json      # Design tokens
│   │   └── css-variables.css       # CSS custom properties
│   └── README.md                   # Component docs
```

**Actions:**
- [ ] Extract device frames from open-design
- [ ] Build core UI component library
- [ ] Generate design tokens system
- [ ] Create Canva templates for components
- [ ] Document component usage

---

### 3.2 Anti-Patterns System (Weight: 8%)
**Target Score:** 8.0/10.0 (from 2.5)

**Build from scratch:**
- Anti-pattern rule engine
- HTML/CSS validation (jsdom)
- CLI checking tool
- CI integration

**Integration:**
```
skills/domains/modes/design/
├── quality/
│   ├── anti-patterns/
│   │   ├── rules.yml               # Anti-pattern rules
│   │   ├── validator.py            # Validation engine
│   │   ├── cli.py                  # CLI checker
│   │   └── README.md               # Anti-pattern docs
```

**Anti-Pattern Rules:**
```yaml
rules:
  - id: AP001
    name: "Low color contrast"
    severity: error
    check: contrast_ratio < 4.5
    
  - id: AP002
    name: "Tiny touch targets"
    severity: warning
    check: button_size < 44px
    
  - id: AP003
    name: "Unreadable font size"
    severity: error
    check: body_font_size < 16px
```

**Actions:**
- [ ] Define anti-pattern rule set (50+ rules)
- [ ] Build validation engine
- [ ] Create CLI tool
- [ ] Integrate with ds-quality debug/polish
- [ ] Add to CI/CD pipeline

---

### 3.3 Quality Gates (Weight: 5%)
**Target Score:** 9.0/10.0 (from 5.5)

**Build from scratch:**
- Unified quality pipeline
- Accessibility checks (WCAG 2.2)
- Contrast validation
- Design system compliance
- CI/CD integration

**Integration:**
```
skills/domains/modes/design/
├── quality/
│   ├── gates/
│   │   ├── pipeline.py             # Quality pipeline orchestrator
│   │   ├── accessibility.py        # WCAG checks
│   │   ├── contrast.py             # Contrast validation
│   │   ├── compliance.py           # Design system compliance
│   │   └── README.md               # Quality gates docs
```

**Quality Gate Workflow:**
```
1. Accessibility Check → WCAG 2.2 compliance
2. Contrast Check → WCAG color contrast ratios
3. Anti-Pattern Check → Rule violations
4. Design System Check → Token compliance
5. Export → Generate quality report
```

**Actions:**
- [ ] Build quality pipeline orchestrator
- [ ] Integrate accessibility checker
- [ ] Add contrast validation
- [ ] Create compliance checker
- [ ] Generate quality reports (HTML/JSON)

---

## Phase 4: Integration & Polish (Weeks 9-10)
**Priority:** MEDIUM  
**Effort:** 1-2 weeks

### 4.1 Workflow Integration

**Connect to existing skills:**
- `ds-quality polish` → Design critique + quality gates
- `ds-quality secure` → Accessibility compliance
- `ds-domains client-work` → Brand protocols + design systems
- `ds-domains website` → Components + export formats

**Actions:**
- [ ] Update ds-quality polish to use design reasoning
- [ ] Add design quality gates to ds-quality secure
- [ ] Integrate brand protocols with client-work intake
- [ ] Connect component library to website mode

---

### 4.2 Documentation

**Create:**
```
skills/domains/modes/design/
├── SKILL.md                        # Updated skill instructions
├── UPGRADE_PLAN.md                 # This file
├── IMPLEMENTATION_LOG.md           # Implementation progress
├── USAGE_GUIDE.md                  # User guide
├── EXAMPLES.md                     # Example workflows
└── TROUBLESHOOTING.md              # Common issues
```

**Actions:**
- [ ] Update SKILL.md with new capabilities
- [ ] Write comprehensive usage guide
- [ ] Create example workflows
- [ ] Document troubleshooting steps

---

### 4.3 Testing

**Test scenarios:**
1. **Color System:** Generate brand color palette with OKLCH
2. **Typography:** Create type system for landing page
3. **Components:** Build button library with design tokens
4. **Brand Protocol:** Create brand spec for client
5. **Reasoning:** Capture design decisions, search database
6. **Quality Gates:** Run full quality pipeline on design
7. **Export:** Generate video from design assets

**Actions:**
- [ ] Create test cases for each capability
- [ ] Run integration tests
- [ ] Fix bugs and edge cases
- [ ] Document test results

---

## File Structure (Final)

```
skills/domains/modes/design/
├── SKILL.md                        # Main skill instructions
├── UPGRADE_PLAN.md                 # This plan
├── IMPLEMENTATION_LOG.md           # Progress tracking
├── USAGE_GUIDE.md                  # User documentation
├── EXAMPLES.md                     # Example workflows
├── TROUBLESHOOTING.md              # Common issues
├── gotchas.yml                     # Known issues
│
├── systems/                        # Design systems (Phase 1)
│   ├── colors/
│   │   ├── colors.csv
│   │   ├── oklch-converter.py
│   │   ├── contrast-checker.py
│   │   └── README.md
│   ├── typography/
│   │   ├── typography.md
│   │   ├── type-ramps.json
│   │   ├── font-pairings.csv
│   │   └── modular-scale.py
│   └── design-system/
│       ├── DESIGN.md.template
│       ├── pattern-library/
│       ├── tokens/
│       └── documentation/
│
├── brand/                          # Brand protocols (Phase 1)
│   ├── brand-spec.md.template
│   ├── asset-protocol.md
│   ├── governance.md
│   └── examples/
│
├── export/                         # Export formats (Phase 1)
│   ├── video-pipeline.py
│   ├── format-configs/
│   ├── batch-export.py
│   └── README.md
│
├── registers/                      # Register system (Phase 1)
│   ├── brand.md.template
│   ├── product.md.template
│   ├── context-engine.py
│   └── examples/
│
├── reasoning/                      # Reasoning system (Phase 2)
│   ├── ui-reasoning.csv
│   ├── search-engine.py
│   ├── capture.py
│   ├── critique-integration.py
│   └── README.md
│
├── components/                     # Component library (Phase 3)
│   ├── ui-kit/
│   │   ├── buttons/
│   │   ├── forms/
│   │   ├── cards/
│   │   └── layouts/
│   ├── device-frames/
│   ├── tokens/
│   │   ├── design-tokens.json
│   │   └── css-variables.css
│   └── README.md
│
└── quality/                        # Quality systems (Phase 3)
    ├── anti-patterns/
    │   ├── rules.yml
    │   ├── validator.py
    │   ├── cli.py
    │   └── README.md
    └── gates/
        ├── pipeline.py
        ├── accessibility.py
        ├── contrast.py
        ├── compliance.py
        └── README.md
```

---

## Dependencies

### Python Packages
```bash
# Color system
pip install coloraide  # OKLCH color space

# Reasoning search
pip install rank-bm25  # BM25 search engine

# Quality gates
pip install axe-selenium  # Accessibility checks
pip install beautifulsoup4  # HTML parsing

# Export
# ffmpeg (system package)
```

### External Tools
- **ffmpeg** - Video export (Phase 1.5)
- **Canva MCP** - Asset generation (existing integration)
- **Blender MCP** - 3D rendering (future enhancement)

---

## Migration Strategy

### Backward Compatibility
- Keep existing design mode functional during upgrade
- Create new mode subdirectories without breaking current SKILL.md
- Test each phase before replacing old mode

### Rollout Plan
1. **Phase 1 (Weeks 1-3):** Add foundation alongside existing mode
2. **Phase 2 (Weeks 4-5):** Add reasoning system
3. **Phase 3 (Weeks 6-8):** Add quality systems
4. **Phase 4 (Weeks 9-10):** Replace old mode with upgraded version

---

## Success Metrics

### Phase 1 Complete
- ✓ Color system generates OKLCH palettes
- ✓ Typography system creates type ramps
- ✓ Design system templates working
- ✓ Brand protocols integrated with client-work
- ✓ Video export functional

### Phase 2 Complete
- ✓ ui-reasoning.csv populated with 100+ entries
- ✓ Reasoning search returns relevant decisions
- ✓ Design decision capture workflow working

### Phase 3 Complete
- ✓ Component library has 50+ components
- ✓ Anti-pattern validator catches 20+ rule violations
- ✓ Quality gates run full pipeline

### Final Target
- ✓ **Overall capability score: 9.0+/10.0**
- ✓ All 10 capabilities scoring 7.0+
- ✓ No capability below 7.0
- ✓ Full integration with ds-quality and ds-domains modes

---

## Risk Mitigation

### Technical Risks
1. **OKLCH browser compatibility** → Include color space fallbacks
2. **ffmpeg dependencies** → Document setup, provide install scripts
3. **Reasoning search performance** → Use BM25 for efficiency

### Strategic Risks
1. **Scope creep** → Phase 3 can be deferred if needed
2. **Maintenance burden** → Document provenance, keep simple
3. **User adoption** → Create clear examples and guides

---

## Next Actions (This Week)

1. **Review this plan** with user
2. **Clone repositories:**
   - `git clone https://github.com/[open-design-repo]`
   - `git clone https://github.com/[ui-ux-pro-max-repo]`
3. **Start Phase 1.1:** Extract color system
4. **Create IMPLEMENTATION_LOG.md** to track progress

---

## Timeline Summary

| Phase | Duration | Priority | Outcome |
|-------|----------|----------|---------|
| **Phase 1: Foundation** | 3 weeks | CRITICAL | Color, typography, design systems, brand, export, registers |
| **Phase 2: Reasoning** | 2 weeks | CRITICAL | Design decision database + search |
| **Phase 3: Fill Gaps** | 3 weeks | HIGH | Components, anti-patterns, quality gates |
| **Phase 4: Polish** | 2 weeks | MEDIUM | Integration, docs, testing |
| **Total** | **10 weeks** | - | **9.0+/10.0 capability score** |

**Can be compressed to 6-8 weeks by deferring Phase 3 (custom builds)**

---

## Approval & Sign-off

- [ ] Plan reviewed and approved
- [ ] Repositories identified and accessible
- [ ] Dependencies documented
- [ ] Phase 1 ready to start

**Approved by:** [User]  
**Date:** [TBD]
