# dream-studio Workflows

The harness orchestrates session lifecycle through event-driven hooks that bootstrap sessions, enforce context budgets, monitor project health, and persist telemetry to SQLite.

---

## Session Lifecycle

```mermaid
sequenceDiagram
    actor User
    participant Harness as Claude Code
    participant Hooks
    participant DB as studio.db
    
    User->>Harness: Submit first prompt
    Harness->>Hooks: UserPromptSubmit event
    Hooks->>DB: Start session
    Hooks->>Hooks: Run health check
    Hooks->>User: Print pulse summary
    Hooks->>Harness: Check context budget
    Harness-->>Hooks: Token count
    Hooks->>User: Context warning (if needed)
    
    Note over User,Harness: User works
    
    User->>Harness: Stop
    Harness->>Hooks: Stop event
    Hooks->>DB: End session
    Hooks->>DB: Write telemetry
    Hooks->>User: Session ended
```

The hooks layer handles four distinct concerns: session bootstrapping, health monitoring, context budget enforcement, and shutdown persistence. Each is detailed below.

---

### Session Bootstrapping

```mermaid
sequenceDiagram
    participant Hooks
    participant DB as studio.db
    
    Hooks->>DB: has_sentinel("session-started")?
    alt Sentinel exists
        DB-->>Hooks: True (already started)
        Hooks->>Hooks: Skip (no-op)
    else First prompt
        DB-->>Hooks: False
        Hooks->>DB: Create project record
        Hooks->>DB: Create session record
        Hooks->>DB: Set sentinel
    end
```

Runs on the first prompt of each session. The sentinel prevents duplicate session records if hooks fire multiple times.

---

### Health Monitoring

```mermaid
sequenceDiagram
    participant Hooks
    participant DB as studio.db
    participant GitHub as GitHub API
    participant User
    
    Hooks->>DB: Read draft lessons, corrections
    Hooks->>GitHub: Fetch branches, PRs, milestones, CI
    GitHub-->>Hooks: Status data
    Hooks->>DB: Write operational snapshot
    Hooks->>User: Print pulse summary
```

Runs on every prompt with a 60-second cooldown. GitHub API is optional; if no token is set, health check uses local state only.

---

### Context Budget Enforcement

```mermaid
sequenceDiagram
    participant Hooks
    participant Harness as Claude Code
    participant User
    
    Hooks->>Harness: Read context token count
    Harness-->>Hooks: Token count
    Hooks->>Hooks: Calculate usage %
    Hooks->>User: Warning or block message
```

Runs on every prompt. Thresholds are enforced as follows:

| Context Usage | Status | Action |
|--------------|--------|--------|
| < 65% | Normal | Silent (no warning) |
| 65-75% | Warning | Print "context at 65%" |
| 75-82% | Warning | Print "context at 75%, handoff suggested" |
| > 82% | Block | Print "context at 82%, handoff required" |

Warnings are informational; blocks require user acknowledgment before continuing.

---

### Shutdown Persistence

```mermaid
sequenceDiagram
    participant Hooks
    participant DB as studio.db
    
    Hooks->>DB: end_session(outcome, tokens, tasks)
    alt Context high or user requested
        Hooks->>DB: insert_handoff(context)
    end
    Hooks->>DB: Batch write skill_telemetry
    Hooks->>DB: Write token_usage
```

Runs on session stop. Handoff creation is conditional: triggered when context exceeds 75% or user explicitly requests it. Telemetry is batched and written in a single transaction.

---

**Details:** [docs/WORKFLOWS.md](docs/WORKFLOWS.md)
