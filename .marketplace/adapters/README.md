# dream-studio Adapters

This directory contains platform-specific exports of dream-studio conventions for use with other AI coding assistants.

## Available Adapters

### Cursor (.cursorrules)
**Location:** `cursor-rules/.cursorrules`  
**Setup Guide:** `../../docs/cursor-setup.md`

A project-level configuration file that provides Cursor AI with dream-studio workflow conventions. Place in your project root to enable:
- Skill-based workflow (Think → Plan → Build → Review → Verify → Ship)
- Git workflow conventions
- Code quality patterns
- Testing and verification guidelines

**Size:** ~3KB  
**Token count:** ~600 tokens

### GitHub Copilot (instructions.md)
**Location:** `copilot-instructions/instructions.md`  
**Setup Guide:** `../../docs/copilot-setup.md`

GitHub Copilot instructions that can be used at repository, user, or organization level. Provides comprehensive guidance on:
- Core workflow lifecycle
- Trigger patterns for different tasks
- Git and PR conventions
- Code quality and security patterns
- Deploy safety rules

**Size:** ~6KB  
**Token count:** ~1,500 tokens

## Installation

### Quick Start

**For Cursor:**
```bash
cp .marketplace/adapters/cursor-rules/.cursorrules /path/to/your/project/.cursorrules
git add .cursorrules
git commit -m "Add dream-studio Cursor conventions"
```

**For GitHub Copilot (repository-level):**
```bash
mkdir -p /path/to/your/project/.github
cp .marketplace/adapters/copilot-instructions/instructions.md /path/to/your/project/.github/copilot-instructions.md
git add .github/copilot-instructions.md
git commit -m "Add dream-studio Copilot conventions"
```

### Detailed Setup

See the setup guides:
- [Cursor Setup Guide](../../docs/cursor-setup.md)
- [Copilot Setup Guide](../../docs/copilot-setup.md)

## What's Included

Both adapters provide:
- **Systematic workflow:** Clear phases from design to deployment
- **Trigger keywords:** Help the AI understand your intent
- **Quality gates:** Built-in checks before shipping
- **Git conventions:** Consistent branch naming, PR size limits, commit standards
- **Security patterns:** Input validation, auth checks, secrets management
- **Testing guidelines:** When and how to verify changes

## Customization

These adapters are starting points. You can:
1. Copy to your project
2. Customize for your team's specific needs
3. Add project-specific conventions
4. Remove sections that don't apply

Both files are designed to be edited and committed to your repository.

## Benefits

Using dream-studio conventions with other AI assistants:
- **Consistency:** Same workflow across different tools
- **Quality:** Built-in quality gates reduce bugs
- **Efficiency:** Clear patterns reduce decision fatigue
- **Collaboration:** Standardized conventions improve teamwork
- **Safety:** Deploy safety rules prevent production incidents

## Maintenance

These adapters are auto-generated from dream-studio SKILL.md files using `scripts/build_adapters.py`. To regenerate:

```bash
py scripts/build_adapters.py
```

Note: The current versions have been manually refined for clarity and conciseness.

## Feedback

Found an issue or have a suggestion? Open an issue or PR in the dream-studio repository.
