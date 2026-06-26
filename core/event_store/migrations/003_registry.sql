-- Migration 003: Skill registry (gotchas)
-- reg_skills, reg_workflows, reg_skill_deps removed in migration 128
-- (dead tables: hydrate_registry pipeline removed; no live consumer)

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

