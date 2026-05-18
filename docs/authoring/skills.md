# Skill Authoring Guide

## What a Skill Is

A Dream Studio skill is a structured instruction set for an AI tool that encodes a specific development practice. Skills are not scripts — they are context packets that tell the AI model what to do, what constraints to respect, what gates to check, and what outputs to produce.

Skills are organized into packs. Each pack is a top-level routing unit with multiple modes. The `ds-core` pack has modes like `think`, `plan`, `build`, and `ship`. The `ds-quality` pack has modes like `debug`, `pr-security-scan`, and `audit`. Invoking a skill means invoking a pack with a specific mode arg.

---

## Directory Structure and Naming

All skills live under `canonical/skills/`. The layout follows:

```
canonical/skills/
  <pack-key>/                  # e.g., quality, core, security
    config.yml                 # Pack metadata
    SKILL.md                   # Main skill instructions for this pack
    modes/                     # Individual mode content
      <mode-name>/
        SKILL.md               # Mode-specific instructions
        examples.md            # (optional) Worked examples
        config.yml             # (optional) Mode-level config
```

Pack keys match the keys in `packs.yaml`. Mode names match the entries in the `modes` list under each pack.

**Naming rules:**
- Pack keys: lowercase, hyphen-separated (e.g., `ds-project`, `quality`)
- Mode names: lowercase, hyphen-separated (e.g., `pr-security-scan`, `game-dev`)
- File names: `SKILL.md` (uppercase), `config.yml` (lowercase)

---

## Required SKILL.md Sections

Every `SKILL.md` must contain these sections in order:

### 1. Frontmatter (YAML)
```yaml
---
ds:
  pack: <pack-key>
  mode: <mode-name>
  version: "1.0"
---
```

### 2. Purpose
One paragraph describing what this skill/mode does and when to invoke it. Be specific — describe the output, not just the activity.

### 3. Context
What the AI needs to know before starting: which files to read, which DB records to check, which prior artifacts matter.

### 4. Instructions
The step-by-step procedure. Use numbered lists. Be imperative. Each step should produce a verifiable artifact or state change.

### 5. Gate Artifacts
What the skill produces that the work order gate checks will verify. See the Gate Artifacts section below for format.

### 6. Output Contract
The format of the skill's output (JSON, markdown, file path, etc.) and what the caller can depend on.

---

## Gate Artifacts: Paths and Formats

Gate artifacts are files written to `.planning/<work_order_id>/` during skill execution. The work order close command checks for these files before allowing close.

Standard gate artifact paths:
```
.planning/<work_order_id>/
  design_critique.md       # Required for ui_component and ui_page work orders
  anti_slop_passed.txt     # Required for ui_component and ui_page work orders
  cwv-results.md           # Required if work order has web performance requirements
  test_results.json        # Test pass/fail summary
  security_findings.json   # Security scan output
```

Format for `design_critique.md`:
```markdown
# Design Critique

## Score: <0-10>
## Status: PASS | FAIL

### What works
- ...

### What needs improvement
- ...
```

Format for `anti_slop_passed.txt`:
```
PASS
Reviewed: <timestamp>
```

Gate names are defined in `ds_work_order_types.post_build_gate` as a pipe-separated list. Check the type definition before writing a skill that needs to satisfy a gate.

---

## Adding to packs.yaml

After creating the skill directory and SKILL.md, register the mode in `packs.yaml`:

```yaml
packs:
  your-pack:
    description: One-line pack description
    skill: your-pack             # skill ID (ds- prefix is added by compiler)
    modes: [existing-mode, new-mode]   # add your new mode here
```

The compiler reads `packs.yaml` and regenerates the routing table in `CLAUDE.md` on every `integrate install` run. No manual routing table edits are required.

If you are adding an entirely new pack (not a mode to an existing pack), also add display name to `_PACK_DISPLAY_NAMES` in `integrations/compiler/claude_code.py`.

---

## Dual-Mode Invocation Contract

Every skill must work in two invocation modes:

### Interactive mode
The user invokes the skill from Claude Code chat: `Skill(skill="ds-quality", args="pr-security-scan")`. The skill reads context from the active work order (loaded by `ds work-order start`), executes, and writes output to `.planning/`.

### CLI mode
The skill is invoked from the CLI: `ds skill invoke quality:pr-security-scan --work-order <id>`. The CLI loads the work order context, passes it to the skill, and the skill executes identically to interactive mode.

**Contract requirements:**
1. The skill must read `context.md` from `.planning/<work_order_id>/` if available
2. The skill must write all gate artifacts to `.planning/<work_order_id>/`
3. The skill must not assume an interactive session — all required context must be in context.md or the DB
4. The skill must be idempotent — running it twice must not corrupt state
5. The skill output must match the declared output contract exactly
