# Agent Contract

Phase: 11Y - Portable Primitive Contracts

Dream Studio agents are bounded specialist execution primitives. They provide focused expertise inside a skill or workflow, but they do not own architecture or canonical state.

## Required Fields

Each portable agent definition must include:

- `agent_id`: stable identifier.
- `role`: area of expertise and when to use it.
- `allowed skills`: skills the agent may support.
- `allowed workflows`: workflows the agent may participate in.
- `allowed tools`: tool categories or explicit tools the agent may use.
- `forbidden actions`: actions the agent must not perform.
- `approval requirements`: actions that require operator approval.
- `state access level`: none, read-only, diagnostic, governed write, or explicit runtime owner access.
- `output contract`: expected final response, artifacts, or findings format.
- `audit obligations`: evidence, logs, decisions, or reports the caller must preserve.
- `execution environment requirements`: local shell, sandbox, Docker, MCP, browser, or other required runtime constraints.

## Authority

Agents may analyze, recommend, implement, test, or review within their assigned scope. Agents are not canonical state owners. They must not bypass skills, workflows, event contracts, state contracts, projection contracts, adapter contracts, governance contracts, or operator approval gates.

The calling skill/workflow owns task boundaries. The owning runtime interface owns persistence. The agent owns only its local output.

## Relationships

- Events: agents may request event emission only through approved owners.
- State: agents may read or write only according to their state access level.
- Projections: agents may inspect projections but cannot promote them to truth.
- Adapters: agent execution through a target runtime is an adapter rendering detail.
- Governance: agents must preserve privacy, approval, and audit constraints.

## Portable Rendering

| Target | Rendering expectation |
| --- | --- |
| Claude | Render as a Claude-compatible sub-agent persona or task prompt. |
| Codex | Render as bounded task instructions or delegated agent prompt. |
| ChatGPT | Render as a specialized role prompt with explicit tool/approval limits. |
| Cursor | Render as editor assistant rules or task instructions. |
| MCP tools/local models | Render as a tool-bounded execution prompt. |
| Docker validation/sandbox | Run only with disposable state and explicit test artifacts. |

Rendering must not give an agent broader authority than the canonical agent contract.

## Validation Expectations

Tests should verify:

- agent contracts require allowed tools, state access, approval, output, and audit fields;
- agents do not own canonical state;
- target-specific agent files remain renderings, not source of authority;
- agents cannot silently expand cloud/org/global scope.
