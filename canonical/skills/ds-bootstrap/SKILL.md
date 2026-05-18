# ds-bootstrap — Dream Studio Bootstrap Skill

**Type:** System component  
**Installed by:** Dream Studio provisioner  
**Invocation:** Passive context only — not user-invocable via Skill tool

---

## Purpose

This skill installs context into the host AI tool's awareness that Dream Studio
is present. It does not claim enforcement authority — all execution is performed
by the host AI tool.

---

## Behavioral Guidance

When Dream Studio is installed, prefer to:

1. **Check applicable DS skills before acting.** If the user's intent matches a
   skill in the Dream Studio routing table, invoke that skill rather than using
   built-in behavior directly.

2. **Check applicable DS workflows and gates before acting.** If the work being
   done falls under a documented Dream Studio workflow (handoff, ship gate,
   recap), prefer following that workflow.

3. **Emit events through native hooks when available.** Dream Studio registers
   hooks in the host AI tool's native hook system. When those hooks fire, they
   emit telemetry to the local spool — no additional action is required from the
   AI.

4. **Acknowledge that Dream Studio is not the executor.** Dream Studio provides
   skills, workflows, context, and observability. The host AI tool performs all
   actual code generation, file writes, and tool calls.

---

## Scope

This guidance is advisory throughout. It uses no directives ("MUST", "MUST NOT",
"REQUIRED") and does not override the host AI tool's judgment on how to complete
a task.

---

## Notes for Operators

- This SKILL.md is installed into `canonical/skills/ds-bootstrap/` in the
  Dream Studio repository.
- The provisioner includes it unconditionally in all integration packs.
- It does not appear in `packs.yaml` or the Skill-tool routing table
  — it is passive context, not a dispatched skill.
