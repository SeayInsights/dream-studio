-- Migration 009: Project Intelligence Wave 2 - Core Analysis Capabilities

-- ── Extend reg_projects with analysis metadata ──────────────────────────────

ALTER TABLE reg_projects ADD COLUMN stack_detected TEXT;
ALTER TABLE reg_projects ADD COLUMN stack_json TEXT;
ALTER TABLE reg_projects ADD COLUMN adapter TEXT;
ALTER TABLE reg_projects ADD COLUMN health_score REAL CHECK (health_score IS NULL OR (health_score >= 0.0 AND health_score <= 1.0));
ALTER TABLE reg_projects ADD COLUMN security_score REAL CHECK (security_score IS NULL OR (security_score >= 0.0 AND security_score <= 1.0));
ALTER TABLE reg_projects ADD COLUMN maintainability_score REAL CHECK (maintainability_score IS NULL OR (maintainability_score >= 0.0 AND maintainability_score <= 1.0));
ALTER TABLE reg_projects ADD COLUMN total_files INTEGER;
ALTER TABLE reg_projects ADD COLUMN lines_of_code INTEGER;
ALTER TABLE reg_projects ADD COLUMN first_analyzed TEXT;
ALTER TABLE reg_projects ADD COLUMN last_analyzed TEXT;

-- ── Component tracking (modules, classes, functions, routes, etc.) ──────────

CREATE TABLE IF NOT EXISTS pi_components (
    component_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    path TEXT NOT NULL,
    name TEXT NOT NULL,
    component_type TEXT NOT NULL,
    lines INTEGER,
    complexity_score REAL,
    change_frequency REAL,
    bug_density REAL,
    imports TEXT,
    imported_by TEXT,
    last_analyzed TEXT DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_component_type CHECK (component_type IN ('module', 'class', 'function', 'component', 'route', 'api')),
    CONSTRAINT chk_complexity_range CHECK (complexity_score IS NULL OR (complexity_score >= 0.0)),
    CONSTRAINT chk_change_freq_range CHECK (change_frequency IS NULL OR (change_frequency >= 0.0)),
    CONSTRAINT chk_bug_density_range CHECK (bug_density IS NULL OR (bug_density >= 0.0)),
    FOREIGN KEY (project_id) REFERENCES reg_projects(project_id)
);

-- ── Dependency graph tracking ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pi_dependencies (
    dependency_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    from_component TEXT NOT NULL,
    to_component TEXT NOT NULL,
    dependency_type TEXT NOT NULL,
    strength REAL,
    CONSTRAINT chk_dependency_type CHECK (dependency_type IN ('import', 'extends', 'implements', 'calls', 'references')),
    CONSTRAINT chk_strength_range CHECK (strength IS NULL OR (strength >= 0.0 AND strength <= 1.0)),
    FOREIGN KEY (project_id) REFERENCES reg_projects(project_id),
    FOREIGN KEY (from_component) REFERENCES pi_components(component_id),
    FOREIGN KEY (to_component) REFERENCES pi_components(component_id)
);

-- ── Architecture and style violations ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pi_violations (
    violation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    violation_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    files TEXT,
    lines TEXT,
    description TEXT NOT NULL,
    impact TEXT,
    fix_recommendation TEXT,
    effort_estimate TEXT,
    status TEXT DEFAULT 'open',
    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    CONSTRAINT chk_violation_type CHECK (violation_type IN ('architecture', 'style', 'security', 'performance')),
    CONSTRAINT chk_violation_severity CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    CONSTRAINT chk_effort_estimate CHECK (effort_estimate IS NULL OR effort_estimate IN ('trivial', 'small', 'medium', 'large')),
    CONSTRAINT chk_violation_status CHECK (status IN ('open', 'acknowledged', 'fixed', 'wontfix')),
    FOREIGN KEY (project_id) REFERENCES reg_projects(project_id)
);

-- ── Bug detection with risk scoring ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pi_bugs (
    bug_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    bug_type TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    file TEXT NOT NULL,
    line INTEGER,
    issue TEXT NOT NULL,
    description TEXT NOT NULL,
    proof TEXT,
    impact TEXT,
    fix_recommendation TEXT,
    effort_estimate TEXT,
    likelihood REAL,
    risk_score REAL,
    status TEXT DEFAULT 'open',
    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
    fixed_at TEXT,
    CONSTRAINT chk_bug_type CHECK (bug_type IN ('null_pointer', 'race_condition', 'resource_leak', 'logic_error', 'security_flaw')),
    CONSTRAINT chk_bug_category CHECK (category IN ('correctness', 'security', 'performance', 'reliability')),
    CONSTRAINT chk_bug_severity CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    CONSTRAINT chk_bug_effort CHECK (effort_estimate IS NULL OR effort_estimate IN ('trivial', 'small', 'medium', 'large')),
    CONSTRAINT chk_likelihood_range CHECK (likelihood IS NULL OR (likelihood >= 0.0 AND likelihood <= 1.0)),
    CONSTRAINT chk_risk_score_range CHECK (risk_score IS NULL OR (risk_score >= 0.0 AND risk_score <= 1.0)),
    CONSTRAINT chk_bug_status CHECK (status IN ('open', 'acknowledged', 'fixed', 'wontfix')),
    FOREIGN KEY (project_id) REFERENCES reg_projects(project_id)
);

-- ── Suggested improvements (refactors, optimizations, modernizations) ────────

CREATE TABLE IF NOT EXISTS pi_improvements (
    improvement_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    improvement_type TEXT NOT NULL,
    priority_score REAL,
    target_files TEXT,
    current_state TEXT,
    recommendation TEXT NOT NULL,
    benefit TEXT,
    effort_estimate TEXT,
    example_code TEXT,
    status TEXT DEFAULT 'proposed',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    implemented_at TEXT,
    CONSTRAINT chk_improvement_type CHECK (improvement_type IN ('refactor', 'optimize', 'modernize', 'test_coverage', 'documentation')),
    CONSTRAINT chk_priority_range CHECK (priority_score IS NULL OR (priority_score >= 0.0 AND priority_score <= 1.0)),
    CONSTRAINT chk_improvement_effort CHECK (effort_estimate IS NULL OR effort_estimate IN ('trivial', 'small', 'medium', 'large')),
    CONSTRAINT chk_improvement_status CHECK (status IN ('proposed', 'approved', 'implemented', 'rejected')),
    FOREIGN KEY (project_id) REFERENCES reg_projects(project_id)
);

-- ── Analysis run tracking ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pi_analysis_runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    run_type TEXT NOT NULL,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    duration_seconds REAL,
    discovery_completed INTEGER DEFAULT 0,
    research_completed INTEGER DEFAULT 0,
    audit_completed INTEGER DEFAULT 0,
    bug_analysis_completed INTEGER DEFAULT 0,
    synthesis_completed INTEGER DEFAULT 0,
    violations_found INTEGER DEFAULT 0,
    bugs_found INTEGER DEFAULT 0,
    improvements_suggested INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    error_message TEXT,
    CONSTRAINT chk_run_type CHECK (run_type IN ('full', 'incremental', 'targeted')),
    CONSTRAINT chk_discovery_bool CHECK (discovery_completed IN (0, 1)),
    CONSTRAINT chk_research_bool CHECK (research_completed IN (0, 1)),
    CONSTRAINT chk_audit_bool CHECK (audit_completed IN (0, 1)),
    CONSTRAINT chk_bug_analysis_bool CHECK (bug_analysis_completed IN (0, 1)),
    CONSTRAINT chk_synthesis_bool CHECK (synthesis_completed IN (0, 1)),
    CONSTRAINT chk_run_status CHECK (status IN ('running', 'completed', 'failed')),
    FOREIGN KEY (project_id) REFERENCES reg_projects(project_id)
);

-- ── Indexes for query performance ─────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_components_project ON pi_components(project_id);
CREATE INDEX IF NOT EXISTS idx_components_type ON pi_components(component_type);
CREATE INDEX IF NOT EXISTS idx_dependencies_project ON pi_dependencies(project_id);
CREATE INDEX IF NOT EXISTS idx_violations_project ON pi_violations(project_id);
CREATE INDEX IF NOT EXISTS idx_violations_severity ON pi_violations(severity);
CREATE INDEX IF NOT EXISTS idx_bugs_project ON pi_bugs(project_id);
CREATE INDEX IF NOT EXISTS idx_bugs_severity ON pi_bugs(severity);
CREATE INDEX IF NOT EXISTS idx_improvements_project ON pi_improvements(project_id);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_project ON pi_analysis_runs(project_id);
