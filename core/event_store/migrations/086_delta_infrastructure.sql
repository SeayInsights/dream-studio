-- Migration 086: Baseline→delta infrastructure for brownfield scanning
--
-- Adds three capabilities:
--
-- 1. finding_hash + normalized_snippet + enclosing_symbol on security_findings:
--    The structural identity hash (rule_id + file_path + normalized_snippet) lets
--    exact-matched findings settle without LLM. normalized_snippet stores the
--    aggressively-normalized code excerpt (whitespace-collapsed). enclosing_symbol
--    stores the function/class name containing the finding — disambiguates two
--    findings with the same rule and file but different locations.
--
-- 2. previous_scan_id on security_scan_runs:
--    Links consecutive scans in a chain. First scan: is_baseline=1,
--    previous_scan_id=NULL. Subsequent: is_baseline=0, previous_scan_id=<prev>.
--
-- 3. resolved_finding_links — LLM verdict persistence:
--    When the LLM adjudicates a candidate pair (possibly-fixed vs possibly-new with
--    same rule + file + line proximity), the verdict is persisted here so it's
--    decided once, not re-litigated each scan.
--
-- 4. security_scan_deltas — per-scan delta summary:
--    Stores the count of new/fixed/persisting/pending findings for quick querying
--    without re-running delta computation.

-- ── 1. Finding hash + components on security_findings ─────────────────────────

ALTER TABLE security_findings ADD COLUMN finding_hash TEXT;
ALTER TABLE security_findings ADD COLUMN normalized_snippet TEXT;
ALTER TABLE security_findings ADD COLUMN enclosing_symbol TEXT;
ALTER TABLE security_findings ADD COLUMN code_excerpt TEXT;

CREATE INDEX IF NOT EXISTS idx_security_findings_hash
ON security_findings(finding_hash);

CREATE INDEX IF NOT EXISTS idx_security_findings_rule_file
ON security_findings(project_id, rule_id, file_path);

-- ── 2. Previous scan linkage on security_scan_runs ────────────────────────────

ALTER TABLE security_scan_runs ADD COLUMN previous_scan_id TEXT
    REFERENCES security_scan_runs(scan_id);

-- ── 3. Resolved finding links (LLM verdict persistence) ───────────────────────

CREATE TABLE IF NOT EXISTS resolved_finding_links (
    link_id          TEXT PRIMARY KEY,
    prev_finding_id  TEXT NOT NULL REFERENCES security_findings(finding_id),
    curr_finding_id  TEXT NOT NULL REFERENCES security_findings(finding_id),
    prev_scan_id     TEXT NOT NULL,
    curr_scan_id     TEXT NOT NULL,
    project_id       TEXT NOT NULL,
    -- 'same_edited': LLM determined same issue at same location with minor edits
    -- 'distinct':    LLM determined genuinely different issues despite proximity
    verdict          TEXT NOT NULL CHECK(verdict IN ('same_edited', 'distinct')),
    confidence       REAL,
    adjudicated_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_resolved_links_prev
ON resolved_finding_links(prev_scan_id, prev_finding_id);

CREATE INDEX IF NOT EXISTS idx_resolved_links_curr
ON resolved_finding_links(curr_scan_id, curr_finding_id);

CREATE INDEX IF NOT EXISTS idx_resolved_links_project
ON resolved_finding_links(project_id);

-- ── 4. Scan delta summary ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS security_scan_deltas (
    delta_id                   TEXT PRIMARY KEY,
    project_id                 TEXT NOT NULL REFERENCES business_projects(project_id),
    curr_scan_id               TEXT NOT NULL REFERENCES security_scan_runs(scan_id),
    prev_scan_id               TEXT NOT NULL,
    new_count                  INTEGER NOT NULL DEFAULT 0,
    fixed_count                INTEGER NOT NULL DEFAULT 0,
    persisting_count           INTEGER NOT NULL DEFAULT 0,
    pending_adjudication_count INTEGER NOT NULL DEFAULT 0,
    created_at                 TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scan_deltas_project
ON security_scan_deltas(project_id, curr_scan_id);
