# dream-studio Workflows

This document describes the five major workflows in dream-studio, showing the sequence of operations, actors involved, state transitions, and failure handling.

---

## Workflow 1: Session Lifecycle

**Purpose:** Tracks a complete Claude Code session from first prompt to stop, recording telemetry, health checks, and handoffs.

**Triggers:** User submits first prompt (UserPromptSubmit event), user stops session (Stop event)

---

### Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant Harness as Claude Code
    participant Dispatch as on-prompt-dispatch.py
    participant SessionStart as on-session-start.py
    participant Pulse as on-pulse.py
    participant Context as on-context-threshold.py
    participant DB as studio.db
    
    User->>Harness: Submit first prompt
    Harness->>Dispatch: UserPromptSubmit event
    
    Dispatch->>SessionStart: Check sentinel
    SessionStart->>DB: has_sentinel("session-started-{id}")?
    alt Sentinel exists
        DB-->>SessionStart: True (already started)
        SessionStart-->>Dispatch: Skip (no-op)
    else First prompt
        DB-->>SessionStart: False
        SessionStart->>DB: upsert_project(project_id, path)
        SessionStart->>DB: insert_session(session_id, project_id)
        SessionStart->>DB: set_sentinel("session-started-{id}")
        SessionStart-->>Dispatch: Success
    end
    
    Dispatch->>Pulse: Run health check
    Pulse->>DB: Read draft lessons, corrections
    Pulse->>GitHub: API calls (if token set)
    GitHub-->>Pulse: Branches, PRs, milestones, CI status
    Pulse->>DB: insert_operational_snapshot()
    Pulse->>User: Print pulse summary
    
    Dispatch->>Context: Check context budget
    Context->>Harness: Read context token count
    Harness-->>Context: Token count
    alt Context < 65%
        Context-->>Dispatch: Silent (no warning)
    else Context 65-75%
        Context->>User: Warning: context at 65%
    else Context 75-82%
        Context->>User: Warning: context at 75%, handoff suggested
    else Context > 82%
        Context->>User: Block: context at 82%, handoff required
    end
    
    Dispatch-->>User: Session started
    
    Note over User,Harness: User works...
    
    User->>Harness: Stop
    Harness->>Dispatch: Stop event
    
    Dispatch->>SessionStart: on-session-end
    SessionStart->>DB: end_session(outcome, tokens, tasks)
    
    Dispatch->>SessionStart: on-stop-handoff (if needed)
    SessionStart->>DB: insert_handoff(session_id, context)
    
    Dispatch->>SessionStart: on-skill-telemetry
    SessionStart->>DB: Batch write raw_skill_telemetry
    
    Dispatch->>SessionStart: on-token-log
    SessionStart->>DB: insert_token_usage()
    
    Dispatch-->>User: Session ended
```

---

### Implementation

| Step | File | Function |
|------|------|----------|
| Dispatch UserPromptSubmit | `packs/meta/hooks/on-prompt-dispatch.py` | `main()` |
| Check/create session | `packs/meta/hooks/on-session-start.py` | `main()` |
| First-run setup | `packs/meta/hooks/on-first-run.py` | `main()` |
| Memory retrieval | `packs/meta/hooks/on-memory-retrieve.py` | `main()` |
| Milestone tracking | `packs/core/hooks/on-milestone-start.py` | `main()` |
| Context check | `packs/meta/hooks/on-context-threshold.py` | `main()` |
| Health check (pulse) | `packs/meta/hooks/on-pulse.py` | `main()`, `gh_api()` |
| Dispatch Stop | `packs/meta/hooks/on-stop-dispatch.py` | `main()` |
| End session | `packs/meta/hooks/on-session-end.py` | `main()` |
| Create handoff | `packs/core/hooks/on-stop-handoff.py` | `main()` |
| Quality scoring | `packs/quality/hooks/on-quality-score.py` | `main()` |
| Skill telemetry | `packs/meta/hooks/on-skill-telemetry.py` | `main()` |
| Token logging | `packs/meta/hooks/on-token-log.py` | `main()` |
| DB operations | `hooks/lib/studio_db.py` | `insert_session()`, `end_session()`, `insert_handoff()` |

---

### State Transitions

```mermaid
stateDiagram-v2
    [*] --> SessionCreated: UserPromptSubmit + no sentinel
    SessionCreated --> SessionActive: insert_session()
    SessionActive --> ContextWarning65: Token count 65-75%
    SessionActive --> ContextWarning75: Token count 75-82%
    SessionActive --> ContextBlocked: Token count > 82%
    ContextWarning65 --> SessionActive: Continue
    ContextWarning75 --> SessionActive: Continue (handoff suggested)
    ContextBlocked --> SessionActive: User acknowledges
    SessionActive --> SessionEnding: Stop event
    SessionEnding --> HandoffCreated: Context high or user requested
    SessionEnding --> SessionCompleted: Normal end
    HandoffCreated --> [*]
    SessionCompleted --> [*]
```

**Session outcome values:**
- `"completed"` - Normal session end
- `"aborted"` - User aborted mid-session
- `"handoff"` - Context threshold exceeded, handoff created

---

### Failure Handling

- **Hook failures:** All hooks wrapped in try/except, failures logged to `~/.dream-studio/state/hook-errors.log` but never block session
- **GitHub API failures:** Pulse check continues with partial data (local state only)
- **Database lock (SQLITE_BUSY):** Retry 3× with exponential backoff (100ms, 500ms, 2s)
- **Sentinel corruption:** If sentinel check fails, worst case is duplicate session row (acceptable)

**Retry strategy:** No session-level retry. Hook failures are logged, session continues.

---

## Workflow 2: Skill Invocation

**Purpose:** Tracks skill invocation, loads skill instructions, and records telemetry (tokens, success, duration).

**Triggers:** User invokes skill via Skill tool

---

### Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant Claude
    participant Harness as Claude Code
    participant SkillLoad as on-skill-load.py
    participant SkillMetrics as on-skill-metrics.py
    participant DB as studio.db
    participant SkillFile as skills/*/SKILL.md
    
    User->>Claude: Invoke skill (e.g., /build)
    Claude->>Harness: Skill(skill="core", args="build")
    
    Harness->>Harness: PostToolUse event (Skill matcher)
    Harness->>SkillMetrics: Skill invocation detected
    SkillMetrics->>DB: Log skill start timestamp
    
    Claude->>Harness: Read(file_path="skills/core/build/SKILL.md")
    Harness->>Harness: PostToolUse event (Read matcher)
    Harness->>SkillLoad: Detect skill file pattern
    
    SkillLoad->>SkillLoad: Check if skill path is safe (no symlinks outside home)
    SkillLoad->>SkillFile: Read file content
    SkillFile-->>SkillLoad: SKILL.md content
    
    SkillLoad->>SkillLoad: Check for {{director_name}} placeholder
    alt Placeholder found
        SkillLoad->>DB: Read config.json for director_name
        DB-->>SkillLoad: Director name
        SkillLoad->>User: Print resolved director_name
    end
    
    SkillLoad->>DB: Append to ~/.dream-studio/meta/skill-usage.log
    SkillLoad->>User: Print "Skill loaded: core/build"
    
    Claude->>Claude: Execute SKILL.md instructions
    Claude->>Harness: Tool calls (Edit, Write, Bash, etc.)
    
    Harness->>Harness: PostToolUse event (Skill matcher)
    Harness->>SkillMetrics: Skill invocation ended
    
    SkillMetrics->>SkillMetrics: Compute heuristic success (based on errors in output)
    SkillMetrics->>Harness: Read token count
    Harness-->>SkillMetrics: Input/output tokens
    SkillMetrics->>DB: insert into raw_skill_telemetry
    
    SkillMetrics-->>Claude: Success (telemetry recorded)
```

---

### Implementation

| Step | File | Function |
|------|------|----------|
| Detect skill invocation | `hooks/hooks.json` | PostToolUse matcher on "Skill" |
| Load skill file | `packs/meta/hooks/on-skill-load.py` | `main()`, `extract_skill_name()` |
| Resolve director placeholder | `packs/meta/hooks/on-skill-load.py` | `maybe_announce_director()` |
| Record telemetry | `packs/meta/hooks/on-skill-metrics.py` | `main()` |
| Write to database | `hooks/lib/studio_db.py` | (telemetry written via `on-skill-telemetry.py` at Stop event) |

---

### State Transitions

```mermaid
stateDiagram-v2
    [*] --> SkillInvoked: Skill() tool call
    SkillInvoked --> SkillLoading: Read SKILL.md
    SkillLoading --> DirectorResolved: {{director_name}} found
    SkillLoading --> SkillLoaded: No placeholder
    DirectorResolved --> SkillLoaded: Placeholder resolved
    SkillLoaded --> Executing: Claude reads instructions
    Executing --> Success: No errors detected
    Executing --> Failure: Errors in output
    Success --> TelemetryWritten: insert raw_skill_telemetry (success=1)
    Failure --> TelemetryWritten: insert raw_skill_telemetry (success=0)
    TelemetryWritten --> [*]
```

---

### Failure Handling

- **Skill file not found:** Hook silently skips (no error to user)
- **Telemetry write failure:** Logged but doesn't block skill execution
- **Heuristic misclassification:** User can manually correct via `cor_skill_corrections` table

**No retry:** Telemetry is fire-and-forget

---

## Workflow 3: YAML Workflow Execution

**Purpose:** Executes declarative YAML workflows as directed acyclic graphs (DAGs), tracking state and archiving to SQLite.

**Triggers:** User invokes `/workflow run <name>` via workflow skill

---

### Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant Skill as workflow skill
    participant WFState as workflow_state.py
    participant WFEngine as workflow_engine.py
    participant YAML as workflows/*.yaml
    participant StateFile as workflows.json
    participant DB as studio.db
    participant Claude
    
    User->>Skill: /workflow run idea-to-pr
    Skill->>WFState: start "idea-to-pr" "workflows/idea-to-pr.yaml"
    
    WFState->>YAML: Read YAML template
    YAML-->>WFState: Workflow definition
    WFState->>WFEngine: parse_workflow(yaml_content)
    WFEngine->>WFEngine: Validate DAG (no cycles)
    WFEngine-->>WFState: Parsed workflow
    
    WFState->>WFEngine: resolve_templates(workflow)
    WFEngine-->>WFState: Resolved workflow
    
    WFState->>WFState: Generate run_key (UUID)
    WFState->>StateFile: Write active workflow state
    StateFile-->>WFState: State persisted
    WFState->>Skill: Return run_key
    
    loop For each ready node
        Skill->>WFState: next <run_key>
        WFState->>WFEngine: _compute_ready_nodes(workflow, state)
        WFEngine-->>WFState: [node_ids]
        WFState->>Skill: Ready nodes
        
        alt Node is skill invocation
            Skill->>WFState: update <run_key> <node_id> running
            Skill->>Claude: Invoke skill
            Claude-->>Skill: Skill result
            Skill->>WFState: update <run_key> <node_id> completed --output <result> --duration <sec>
        else Node is gate
            Skill->>WFState: update <run_key> <node_id> running
            Skill->>WFState: eval <run_key> <expression>
            WFState->>WFEngine: _evaluate(expression, context)
            WFEngine-->>WFState: True/False
            alt Gate passes
                WFState->>Skill: Exit 0 (true)
                Skill->>WFState: update <run_key> <node_id> completed
            else Gate fails
                WFState->>Skill: Exit 1 (false)
                Skill->>WFState: abort <run_key>
                WFState->>StateFile: Mark workflow aborted
            end
        end
        
        WFState->>StateFile: Update node status
        WFState->>WFEngine: compress_node_output(output)
        WFEngine-->>WFState: Compressed output
    end
    
    Skill->>WFState: status <run_key>
    WFState->>StateFile: Read workflow state
    StateFile-->>WFState: Workflow completed
    
    WFState->>DB: archive_workflow(run_key, workflow_state)
    DB-->>WFState: Archived to raw_workflow_runs + raw_workflow_nodes
    
    WFState->>StateFile: Remove active workflow
    WFState->>Skill: Workflow completed
    Skill->>User: Workflow completed
```

---

### Implementation

| Step | File | Function |
|------|------|----------|
| Start workflow | `hooks/lib/workflow_state.py` | `cmd_start()` |
| Parse YAML | `hooks/lib/workflow_validate.py` | `parse_workflow()` |
| Resolve templates | `hooks/lib/workflow_engine.py` | `resolve_templates()` |
| Compute ready nodes | `hooks/lib/workflow_engine.py` | `_compute_ready_nodes()` |
| Evaluate gate conditions | `hooks/lib/workflow_engine.py` | `_evaluate()` |
| Update node status | `hooks/lib/workflow_state.py` | `cmd_update()` |
| Compress output | `hooks/lib/workflow_engine.py` | `compress_node_output()` |
| Archive to SQLite | `hooks/lib/studio_db.py` | `archive_workflow()` |
| State file I/O | `hooks/lib/workflow_state.py` | `_read_state()`, `_write_state()` |

---

### State Transitions

```mermaid
stateDiagram-v2
    [*] --> WorkflowStarted: start command
    WorkflowStarted --> NodesReady: Compute ready nodes
    NodesReady --> NodeRunning: update <node> running
    NodeRunning --> NodeCompleted: update <node> completed
    NodeRunning --> NodeFailed: update <node> failed
    NodeRunning --> GateEvaluating: Node is gate
    GateEvaluating --> NodeCompleted: Gate passes
    GateEvaluating --> WorkflowAborted: Gate fails
    NodeCompleted --> NodesReady: More nodes pending
    NodeCompleted --> WorkflowCompleted: All nodes done
    NodeFailed --> NodesReady: on_failure: continue
    NodeFailed --> WorkflowFailed: on_failure: abort
    WorkflowCompleted --> Archived: archive_workflow()
    WorkflowFailed --> Archived: archive_workflow()
    WorkflowAborted --> Archived: archive_workflow()
    Archived --> [*]
```

**Workflow status values:**
- `"active"` - Currently executing
- `"completed"` - All nodes completed successfully
- `"completed_with_failures"` - Completed but some nodes failed
- `"aborted"` - User aborted or gate failed

**Node status values:**
- `"pending"` - Not yet started
- `"running"` - Currently executing
- `"completed"` - Finished successfully
- `"failed"` - Finished with error
- `"skipped"` - Skipped due to dependency failure

---

### Failure Handling

- **Gate failure:** Workflow aborts, state archived with status `"aborted"`
- **Node failure with `on_failure: continue`:** Workflow continues, dependent nodes skipped
- **Node failure with `on_failure: abort`:** Workflow aborts immediately
- **File lock contention:** Retry with backoff (workflow_state.py uses file locking)
- **Database lock on archive:** Retry 3× with exponential backoff

**Retry strategy:** Node-level retry (if configured in YAML `retries:` field), no workflow-level retry

---

## Workflow 4: Analytics Dashboard Generation

**Purpose:** Collects data from SQLite, analyzes trends/anomalies, and generates HTML dashboard or serves via API.

**Triggers:** 
- Script mode: `py scripts/ds_dashboard.py`
- API mode: `uvicorn analytics.api.main:app`

---

### Sequence Diagram (Script Mode)

```mermaid
sequenceDiagram
    actor User
    participant Script as ds_dashboard.py
    participant Collectors as analytics/core/collectors/
    participant DB as studio.db
    participant Analyzers as analytics/core/analyzers/
    participant Generator as generators/production_dashboard.py
    participant Output as analytics-dashboard.html
    
    User->>Script: py scripts/ds_dashboard.py
    
    Script->>Collectors: Import collectors
    Collectors->>DB: Query raw_sessions
    DB-->>Collectors: Session data
    Collectors->>DB: Query raw_skill_telemetry
    DB-->>Collectors: Skill data
    Collectors->>DB: Query raw_workflow_runs
    DB-->>Collectors: Workflow data
    Collectors->>DB: Query raw_token_usage
    DB-->>Collectors: Token data
    Collectors->>DB: Query raw_lessons
    DB-->>Collectors: Lesson data
    
    Collectors-->>Script: DataFrames (pandas)
    
    Script->>Analyzers: trend_analyzer.analyze(sessions_df)
    Analyzers-->>Script: Trend metrics
    Script->>Analyzers: anomaly_detector.detect(skill_df)
    Analyzers-->>Script: Anomalies
    Script->>Analyzers: predictor.forecast(token_df)
    Analyzers-->>Script: Predictions (scikit-learn)
    
    Script->>Generator: render_dashboard(data)
    Generator->>Generator: Apply Jinja2 templates
    Generator->>Generator: Generate charts (inline JS)
    Generator->>Output: Write HTML file
    Output-->>User: Dashboard generated at ~/.dream-studio/analytics-dashboard.html
```

---

### Sequence Diagram (API Mode)

```mermaid
sequenceDiagram
    actor User
    participant Browser
    participant API as FastAPI (analytics/api/main.py)
    participant Routes as analytics/api/routes/
    participant Collectors
    participant DB as studio.db
    participant Analyzers
    
    User->>API: uvicorn analytics.api.main:app
    API-->>User: Server running on localhost:8000
    
    User->>Browser: Open http://localhost:8000/api/docs
    Browser->>API: GET /api/v1/metrics
    API->>Routes: metrics.router
    Routes->>Collectors: session_collector.get_recent()
    Collectors->>DB: SELECT * FROM raw_sessions WHERE started_at > ...
    DB-->>Collectors: Rows
    Collectors-->>Routes: Session metrics
    Routes-->>API: JSON response
    API-->>Browser: Display metrics
    
    Browser->>API: GET /api/v1/insights
    API->>Routes: insights.router
    Routes->>Analyzers: insight_engine.generate()
    Analyzers->>Collectors: Fetch data
    Collectors->>DB: Multiple queries
    DB-->>Collectors: Data
    Collectors-->>Analyzers: DataFrames
    Analyzers->>Analyzers: Pattern matching, ML
    Analyzers-->>Routes: Insights
    Routes-->>API: JSON response
    API-->>Browser: Display insights
    
    Browser->>API: WebSocket /api/v1/realtime
    API->>Routes: WebSocket connection
    loop Every 5 seconds
        Routes->>Collectors: Get current metrics
        Collectors->>DB: Query
        DB-->>Collectors: Data
        Collectors-->>Routes: Metrics
        Routes-->>API: WebSocket message
        API-->>Browser: Update UI
    end
```

---

### Implementation

**Script Mode:**

| Step | File | Function |
|------|------|----------|
| Entry point | `scripts/ds_dashboard.py` | `main()` |
| Session collection | `analytics/core/collectors/session_collector.py` | `collect_sessions()` |
| Skill collection | `analytics/core/collectors/skill_collector.py` | `collect_skills()` |
| Workflow collection | `analytics/core/collectors/workflow_collector.py` | `collect_workflows()` |
| Token collection | `analytics/core/collectors/token_collector.py` | `collect_tokens()` |
| Trend analysis | `analytics/core/analyzers/trend_analyzer.py` | `analyze_trends()` |
| Anomaly detection | `analytics/core/analyzers/anomaly_detector.py` | `detect_anomalies()` |
| Forecasting | `analytics/core/analyzers/predictor.py` | `forecast()` |
| Dashboard generation | `analytics/generators/production_dashboard.py` | `generate()` |

**API Mode:**

| Endpoint | Route File | Function |
|----------|-----------|----------|
| GET /api/v1/metrics | `analytics/api/routes/metrics.py` | `get_metrics()` |
| GET /api/v1/insights | `analytics/api/routes/insights.py` | `get_insights()` |
| GET /api/v1/reports | `analytics/api/routes/reports.py` | `generate_report()` |
| GET /api/v1/export | `analytics/api/routes/exports.py` | `export_data()` |
| GET /api/v1/ml | `analytics/api/routes/ml.py` | `ml_predict()` |
| WebSocket /api/v1/realtime | `analytics/api/routes/realtime.py` | `websocket_endpoint()` |

---

### State Transitions

No persistent state changes (read-only workflow).

---

### Failure Handling

**Script Mode:**
- **Database read failure:** Exit with error message
- **Insufficient data for ML:** Gracefully degrade (skip forecasting)
- **Template rendering error:** Print error, output partial dashboard

**API Mode:**
- **Database read failure:** Return HTTP 500 with error message
- **WebSocket disconnect:** Clean up connection, log event
- **Missing data:** Return empty arrays (not 500 errors)

**No retry:** Read-only operations don't retry (fail fast)

---

## Workflow 5: Health Monitoring (Pulse)

**Purpose:** Proactive health check combining GitHub API data and local state to generate health score and snapshot.

**Triggers:** UserPromptSubmit event (with 60s cooldown to prevent spamming)

---

### Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant Harness as Claude Code
    participant Pulse as on-pulse.py
    participant DB as studio.db
    participant Config as ~/.dream-studio/config.json
    participant GitHub as GitHub API
    participant Output as ~/.dream-studio/meta/
    
    User->>Harness: Submit prompt
    Harness->>Pulse: UserPromptSubmit event
    
    Pulse->>DB: Check cooldown sentinel
    alt Cooldown active (< 60s since last)
        DB-->>Pulse: Sentinel exists
        Pulse-->>Harness: Skip (silent)
    else Cooldown expired
        DB-->>Pulse: No sentinel
        
        Pulse->>Config: Read github_repo
        Config-->>Pulse: Repo name (e.g., "SeayInsights/dream-studio")
        
        alt GITHUB_PERSONAL_ACCESS_TOKEN set
            Pulse->>GitHub: GET /repos/{repo}/branches?per_page=100
            GitHub-->>Pulse: Branch list
            Pulse->>Pulse: Filter stale branches (> 7 days)
            
            Pulse->>GitHub: GET /repos/{repo}/milestones
            GitHub-->>Pulse: Milestone list
            Pulse->>Pulse: Filter overdue milestones
            
            Pulse->>GitHub: GET /repos/{repo}/pulls
            GitHub-->>Pulse: Open PRs
            
            Pulse->>GitHub: GET /repos/{repo}/commits/{sha}/check-runs
            GitHub-->>Pulse: CI status
        else No token
            Pulse->>Pulse: Skip GitHub checks
        end
        
        Pulse->>Output: List draft lessons directory
        Output-->>Pulse: Draft lesson count
        
        Pulse->>Pulse: Compute health score
        alt All green
            Pulse->>Pulse: Health = HEALTHY
        else Warnings
            Pulse->>Pulse: Health = DEGRADED
        else Critical issues
            Pulse->>Pulse: Health = UNHEALTHY
        end
        
        Pulse->>Output: Write pulse-YYYY-MM-DD.md
        Pulse->>Output: Write pulse-latest.json
        Pulse->>DB: insert_operational_snapshot()
        
        Pulse->>DB: Set cooldown sentinel (expires in 60s)
        
        Pulse->>User: Print pulse summary
        User-->>User: See system-reminder with health status
    end
```

---

### Implementation

| Step | File | Function |
|------|------|----------|
| Trigger check | `packs/meta/hooks/on-pulse.py` | `main()` |
| Read config | `hooks/lib/state.py` | `read_config()` |
| GitHub API calls | `packs/meta/hooks/on-pulse.py` | `gh_api()`, `check_stale_branches()`, `check_overdue_milestones()` |
| Local state inspection | `packs/meta/hooks/on-pulse.py` | (inline file reads) |
| Health scoring | `packs/meta/hooks/on-pulse.py` | `compute_health_score()` |
| Write outputs | `packs/meta/hooks/on-pulse.py` | (inline file writes) |
| Database snapshot | `hooks/lib/studio_db.py` | `insert_operational_snapshot()` |

---

### State Transitions

```mermaid
stateDiagram-v2
    [*] --> CooldownCheck: UserPromptSubmit
    CooldownCheck --> Skipped: Sentinel exists (< 60s)
    CooldownCheck --> DataCollection: Sentinel expired
    Skipped --> [*]
    DataCollection --> GitHubFetch: Token available
    DataCollection --> LocalOnly: No token
    GitHubFetch --> HealthCompute: API calls complete
    LocalOnly --> HealthCompute: Local data collected
    HealthCompute --> HEALTHY: All metrics green
    HealthCompute --> DEGRADED: Warnings detected
    HealthCompute --> UNHEALTHY: Critical issues
    HEALTHY --> OutputWritten: Write pulse files
    DEGRADED --> OutputWritten: Write pulse files
    UNHEALTHY --> OutputWritten: Write pulse files
    OutputWritten --> SnapshotRecorded: insert_operational_snapshot()
    SnapshotRecorded --> CooldownSet: Set sentinel (60s)
    CooldownSet --> [*]
```

**Health status values:**
- `"HEALTHY"` - All checks green
- `"DEGRADED"` - 1+ warnings (stale branches, pending drafts, etc.)
- `"UNHEALTHY"` - Critical issues (overdue milestones, CI failures, open escalations)

---

### Failure Handling

- **GitHub API timeout:** Log error, continue with local data only
- **GitHub API rate limit:** Skip GitHub checks, use local data
- **Config read failure:** Use defaults (no GitHub repo configured)
- **Database write failure:** Log error but don't block session

**Retry strategy:** No retry on GitHub API failures (graceful degradation)

**Cooldown bypass:** Set `PULSE_COOLDOWN_SEC=0` to disable cooldown (for testing)

---

## Summary

Five distinct workflows orchestrate dream-studio's operation:

1. **Session Lifecycle** - Full session tracking from start to stop (6+9 hooks batched)
2. **Skill Invocation** - Skill load → execute → telemetry (2-3 hooks)
3. **YAML Workflow Execution** - DAG-based pipeline with state machine (CLI + database archive)
4. **Analytics Generation** - Data collection → analysis → visualization (script or API)
5. **Health Monitoring** - GitHub + local → health score → snapshot (with cooldown)

All workflows converge on SQLite as the single source of truth. No external service dependencies except optional GitHub API for pulse checks. Failure handling is graceful: hooks never block sessions, telemetry is fire-and-forget, and workflows archive state even on abort.
