# Dream Studio Adapters Reference

Adapter surfaces and event normalization layer.

**Source:** `core/adapters/`, `interfaces/cli/adapter_templates/`  
**Authority:** SQLite `adapter_authority_profiles` (migration 038)  
**Generated projection:** `.claude/CLAUDE.md`

---

## Adapter Principle

Adapters are **projections only** — they do not own canonical decisions, evidence, routes, or state. The SQLite authority database is the source of truth. Adapter config is generated from that authority and must not be mutated directly.

```
adapter_authority_profiles (SQLite)
    → adapter_config_projection.py
        → .claude/CLAUDE.md  (Claude Code adapter projection)
```

---

## Claude Code Adapter

**Adapter ID:** `claude`  
**Adapter type:** `claude`  
**Projection file:** `.claude/CLAUDE.md`

**Supported context packets:** `resume`, `work_order_execution`, `review`  
**Supported result types:** `decision`, `code_change`, `validation`, `evidence`

The Claude Code adapter is the primary Dream Studio integration surface. It receives user intent, routes to the appropriate skill pack via the CLAUDE.md routing table, and normalizes results back into Dream Studio records.

**Routing:** User intent → keyword match → `Skill(skill="ds-<pack>", args="<mode>")` → skill execution → spool event → ingest → projection.

---

## Event Normalization Adapters

`core/adapters/normalizers.py` — Routes raw AI model outputs to the appropriate `CanonicalEvent` schema.

| Class | Purpose |
|-------|---------|
| `BaseAdapter` | Abstract base; `normalize(raw_output) → CanonicalEvent` |
| `ClaudeAdapter` | Normalizes Claude API responses. Handles stop reasons, tool use, errors. Maps severity. Tracks adapter version, model, API version. |
| `GPTAdapter` | Proof-of-concept OpenAI compatibility. Extracts model, completion_id, content, usage. |
| `DefaultAdapter` | Fallback for unknown model types. Logs warning, wraps raw input gracefully. |
| `EventNormalizer` | Central registry. Routes raw output to the appropriate adapter class. |

**Performance constraint:** <10ms overhead per event.

**Output schema** (`core/adapters/models.py`):

```python
@dataclass
class CanonicalEvent:
    event_type: str
    entity_type: str
    severity: SeverityLevel
    payload: dict
    trace: TraceContext
    metadata: dict   # adapter version, model, API version
```

---

## Multi-AI Platform Adapters

Generated for IDE integrations from `interfaces/cli/adapter_templates/*.j2`.  
Built via `interfaces/cli/build_adapters.py`.

| Platform | Template | Output path | Domain knowledge included |
|----------|----------|-------------|--------------------------|
| Cursor | `cursor.j2` | `.marketplace/adapters/cursor-rules/.cursorrules` | No |
| GitHub Copilot | `copilot.j2` | `.marketplace/adapters/copilot-instructions/instructions.md` | Yes |
| Windsurf | `windsurf.j2` | `.marketplace/adapters/windsurf/.windsurfrules` | Yes |
| System Prompt (generic) | `system-prompt.j2` | `.marketplace/adapters/system-prompt/system-prompt.md` | Yes (truncated to 8k tokens) |

**Build process:**
1. Discovers skills from `canonical/skills/*/modes/*/SKILL.md`
2. Parses YAML frontmatter, trigger keywords, workflow steps, gotchas
3. Loads domain knowledge from `skills/domains/`
4. Renders templates with skill + domain data
5. Enforces token budget: system-prompt max 8,000 tokens

---

## Adapter Config Projection

`core/shared_intelligence/adapter_config_projection.py`

- Reads from SQLite `adapter_authority_profiles` table
- Generates non-mutating projections (JSON for MCP/shell, Markdown for Claude)
- Enforces: `config_write_authorized=False`, `adapter_owns_source_of_truth=False`
- SHA256 hash of content for integrity verification

---

## Layer Constraints

From `docs/reference/layer-map.md`:

| Rule | Enforced by |
|------|------------|
| Adapters never write to authority tables | Adapter projection contract |
| Projections are read-only | `adapter_config_projection.py` — non-mutating |
| Skills route via function calls, not subprocess | `skill-sync` pre-push gate |
| Ingestor is the sole writer to canonical event tables | `spool.ingestor` module boundary |

---

## Cross-references

- Routing table: [`docs/reference/skills-index.md`](skills-index.md) — full pack × mode × keyword matrix
- Layer model: `docs/reference/layer-map.md`
- API map: `docs/reference/skill-api-map.md`
- Events: [`docs/reference/events.md`](events.md) — `skill.invoked`, `skill.lifecycle.*`
