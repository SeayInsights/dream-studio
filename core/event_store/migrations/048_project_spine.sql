-- Migration 048: Project Spine — ds_projects / ds_milestones / ds_work_orders / ds_tasks
-- Created: 2026-05-16 (Slice 4 Workstream 3)
--
-- Advisory: 034_execution_graph.sql uses project_id as a denormalized column on
-- execution_nodes. Rows registered here via `ds project register` become the
-- authoritative project_id value; execution_nodes.project_id should match.
-- No FK enforced cross-table to avoid bootstrap ordering issues.

CREATE TABLE IF NOT EXISTS ds_projects (
    project_id   TEXT    PRIMARY KEY,           -- UUID
    name         TEXT    NOT NULL,
    description  TEXT,
    status       TEXT    NOT NULL DEFAULT 'active'
                         CHECK(status IN ('active', 'paused', 'archived', 'complete')),
    created_at   TEXT    NOT NULL,              -- ISO-8601 UTC
    updated_at   TEXT    NOT NULL               -- ISO-8601 UTC
);

CREATE TABLE IF NOT EXISTS ds_milestones (
    milestone_id TEXT    PRIMARY KEY,           -- UUID
    project_id   TEXT    NOT NULL REFERENCES ds_projects(project_id),
    title        TEXT    NOT NULL,
    description  TEXT,
    due_date     TEXT,                          -- ISO-8601 UTC, nullable
    status       TEXT    NOT NULL DEFAULT 'pending'
                         CHECK(status IN ('pending', 'active', 'complete', 'skipped')),
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS ds_work_orders (
    work_order_id TEXT   PRIMARY KEY,           -- UUID
    project_id    TEXT   NOT NULL REFERENCES ds_projects(project_id),
    milestone_id  TEXT   REFERENCES ds_milestones(milestone_id),
    title         TEXT   NOT NULL,
    description   TEXT,
    status        TEXT   NOT NULL DEFAULT 'open'
                         CHECK(status IN ('open', 'in_progress', 'review', 'complete', 'cancelled')),
    created_at    TEXT   NOT NULL,
    updated_at    TEXT   NOT NULL
);

CREATE TABLE IF NOT EXISTS ds_tasks (
    task_id       TEXT   PRIMARY KEY,           -- UUID
    work_order_id TEXT   NOT NULL REFERENCES ds_work_orders(work_order_id),
    project_id    TEXT   NOT NULL REFERENCES ds_projects(project_id),
    title         TEXT   NOT NULL,
    description   TEXT,
    status        TEXT   NOT NULL DEFAULT 'pending'
                         CHECK(status IN ('pending', 'in_progress', 'blocked', 'complete', 'cancelled')),
    created_at    TEXT   NOT NULL,
    updated_at    TEXT   NOT NULL
);

-- Fast project-scoped lookups
CREATE INDEX IF NOT EXISTS idx_ds_milestones_project  ON ds_milestones(project_id);
CREATE INDEX IF NOT EXISTS idx_ds_work_orders_project ON ds_work_orders(project_id);
CREATE INDEX IF NOT EXISTS idx_ds_work_orders_milestone ON ds_work_orders(milestone_id);
CREATE INDEX IF NOT EXISTS idx_ds_tasks_work_order    ON ds_tasks(work_order_id);
CREATE INDEX IF NOT EXISTS idx_ds_tasks_project       ON ds_tasks(project_id);
