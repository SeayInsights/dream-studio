# Architecture Skill — Audit Mode

## What This Does

Automated architectural quality scan. Reports god objects, layer violations, coupling/cohesion
issues, and abstraction quality. Read-only — classifies and reports only, never modifies code.

## Invocation

```
ds-quality audit: architecture <path>
```

## Pipeline

1. **Stack detection** — `detect_stack(path)` → `DetectedStack`
   Reads: `stack_family` (frontend/backend/library), `frontend_framework`, `monorepo_type`, `architecture_framework`

2. **Config load** — load `config.yml` defaults; merge project-level `architecture_config.yml` if present
   Stack family determines which threshold set to use (frontend/backend/library/default).

3. **Static pass** — AST-based rules per language
   - arch-001: class LOC + method count → CANDIDATE if above threshold
   - arch-002: external import count → DEFINITIVE if > threshold × 1.5; CANDIDATE if between 1.0×–1.5×
   - arch-003: directory depth → DEFINITIVE above threshold
   - arch-004: layer heuristic (layer name in import path) → DEFINITIVE when layer names known
   - arch-009: total import count (all modules) → same threshold logic as arch-002
   - arch-011: interface/abstract implementer count → DEFINITIVE if < min_implementer_count

4. **LLM confirmation** — for CANDIDATE findings from static pass (arch-001, arch-002)
   Batched by rule; context_scope per rule (class/file/directory).

5. **LLM-only rules** — arch-005, arch-006, arch-010, arch-012, arch-013, arch-014, arch-015
   Applied to files matching applies_to criteria. Sampled on large repos (>200 files).

6. **Report** — findings table with: rule_id, severity, file_path, line, excerpt, explanation

## Finding Hash

| Rule category | Hash input |
|---------------|-----------|
| God objects (arch-001, 011) | `rule_id + file_path + class_name + method_count` |
| Import count (arch-002, 009) | `rule_id + file_path + import_count` |
| Depth (arch-003) | `rule_id + file_path + depth` |
| Layer (arch-004, 005, 006) | `rule_id + source_module + dest_module + violation_type` |
| Abstraction (arch-012, 013) | `rule_id + file_path + pattern_type` |
| Pattern-level (arch-014, 015) | `rule_id + file_path + pattern_type` |

Hash is SHA-256. Findings table column: `finding_hash`. Stable on rescan when code is unchanged.

## Token Budget

Estimated per full-repo audit:
- Static-only rules (arch-001 partial, 002, 003, 009, 011): ~0 LLM tokens
- LLM confirmation (arch-001 candidates): ~500 tokens × candidate count
- LLM-only rules (arch-005, 006, 010, 012–015): ~600 tokens × file count sampled
- Typical full-repo estimate (100-file project): 25,000–40,000 tokens

Use `--sample N` to limit LLM rules to N files when auditing large repos.

## Config Override

Default thresholds live in `canonical/skills/quality/modes/architecture/config.yml`.

Project-level override — create `architecture_config.yml` at project root:
```yaml
thresholds:
  god_class_loc:
    default: 1000   # raise threshold for generated code repos
layer_map:
  layers:
    - name: "controllers"
      rank: 0
    - name: "services"
      rank: 1
    - name: "repositories"
      rank: 2
```

Keys not specified inherit defaults. Override is merged, not replaced.
