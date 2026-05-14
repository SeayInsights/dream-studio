-- Migration 002: Approach capture (tracks what works vs fails per skill)

CREATE TABLE IF NOT EXISTS raw_approaches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,
    session_date TEXT NOT NULL,
    approach TEXT NOT NULL,
    outcome TEXT NOT NULL,
    context TEXT,
    why_worked TEXT,
    tokens_used INTEGER,
    duration_s REAL,
    model TEXT,
    captured_at TEXT NOT NULL
);

CREATE VIEW IF NOT EXISTS vw_approach_patterns AS
SELECT
    skill_id,
    approach,
    COUNT(*) AS times_tried,
    SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes,
    ROUND(
        CAST(SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS REAL)
        / COUNT(*) * 100, 1
    ) AS success_pct,
    CAST(AVG(tokens_used) AS INTEGER) AS avg_tokens,
    ROUND(AVG(duration_s), 1) AS avg_duration
FROM raw_approaches
GROUP BY skill_id, approach
HAVING COUNT(*) >= 2;
