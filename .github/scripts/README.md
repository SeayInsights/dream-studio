# GitHub Actions Scripts

This directory contains scripts used by GitHub Actions workflows.

## validate-skills.py

Validates SKILL.md files against dream-studio LLM consumption standards.

### Usage

**Validate all SKILL.md files:**
```bash
python .github/scripts/validate-skills.py
```

**Validate specific files:**
```bash
python .github/scripts/validate-skills.py skills/core/SKILL.md skills/quality/modes/debug/SKILL.md
```

### Validation Checks

1. **Line Count Limits** (ERROR if violated)
   - Main SKILL.md files: max 300 lines
   - Mode SKILL.md files: max 150 lines

2. **YAML Frontmatter Validation** (ERROR if invalid)
   - Checks that frontmatter blocks are syntactically valid YAML
   - Uses PyYAML for validation

3. **Banned Phrases Check** (WARNING only)
   - Detects scaffolding language that should be removed
   - Phrases: "this section", "refer to", "following explains", etc.

4. **Reference Link Validation** (WARNING only)
   - Checks that all `[text](#anchor)` links have corresponding `{#anchor}` headings
   - Validates both explicit anchors and auto-generated heading anchors

### Exit Codes

- `0` - All validations passed (warnings are allowed)
- `1` - One or more ERROR-level violations found

### Dependencies

- Python 3.10+
- PyYAML (`pip install PyYAML`)

### CI Integration

This script is automatically run by `.github/workflows/validate-skills.yml` on PRs that modify SKILL.md files.
