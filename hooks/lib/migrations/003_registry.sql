-- Migration 003: Skill registry (skills, gotchas, workflows, dependencies)

CREATE TABLE IF NOT EXISTS reg_skills (
    skill_id TEXT PRIMARY KEY,
    pack TEXT NOT NULL,
    mode TEXT NOT NULL,
    description TEXT,
    triggers TEXT,
    skill_path TEXT NOT NULL,
    gotchas_path TEXT,
    word_count INTEGER,
    chains_to TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS reg_gotchas (
    gotcha_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    context TEXT,
    fix TEXT,
    keywords TEXT,
    discovered TEXT,
    times_hit INTEGER DEFAULT 0,
    last_hit TEXT,
    PRIMARY KEY (gotcha_id, skill_id)
);

CREATE TABLE IF NOT EXISTS reg_workflows (
    workflow_id TEXT PRIMARY KEY,
    yaml_path TEXT NOT NULL,
    description TEXT,
    node_count INTEGER,
    skills_used TEXT,
    category TEXT,
    est_tokens INTEGER,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS reg_skill_deps (
    from_skill TEXT NOT NULL,
    to_skill TEXT NOT NULL,
    dep_type TEXT NOT NULL,
    PRIMARY KEY (from_skill, to_skill, dep_type)
);
