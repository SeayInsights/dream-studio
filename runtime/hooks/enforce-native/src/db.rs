//! Read-only authority queries, matching the SQL in `runtime/lib/enforcement.py`'s
//! `match_registered_project`, `in_progress_work_order` and `next_created_work_order`
//! exactly -- same tables, same predicates, same ordering, same fallback-on-error
//! behaviour. This hook only ever READS the authority; every write it makes goes
//! through the append-only queue (`queue.rs`) or the per-session JSON file (`session.rs`).

use std::path::Path;

use rusqlite::{Connection, OpenFlags};

use crate::decision::{boundary_globs, path_in_boundary};
use crate::paths;

pub struct Project {
    pub project_id: String,
    pub name: String,
    pub project_path: String,
}

pub struct WorkOrder {
    pub work_order_id: String,
    pub title: String,
    pub description: String,
    pub attribution: &'static str,
    pub claimants: Vec<String>,
}

pub struct NextWorkOrder {
    pub work_order_id: String,
    pub title: String,
}

/// Mirror `_connect_ro`: a read-only connection, `None` if the file is missing
/// or cannot be opened -- never an error the caller has to handle.
fn connect_ro(db_path: &Path) -> Option<Connection> {
    if !db_path.is_file() {
        return None;
    }
    Connection::open_with_flags(db_path, OpenFlags::SQLITE_OPEN_READ_ONLY).ok()
}

/// Mirror `match_registered_project`: the registered project containing
/// `resolved`, preferring `active` over `paused` and the LONGEST matching
/// `project_path` (a nested project wins over its parent).
///
/// `resolved` must already be through `paths::resolve_weak` -- this function
/// does not touch the filesystem beyond opening the database, matching the
/// read-only, best-effort character of every other function here.
pub fn match_registered_project(authority_db: &Path, resolved: &Path) -> Option<Project> {
    let conn = connect_ro(authority_db)?;
    // A SINGLE LINE, DELIBERATELY. A `\`-continued Rust string literal strips the
    // newline AND the next line's leading whitespace -- `"a\` + newline + `   b"`
    // silently becomes `"ab"`, not `"a b"`. That exact mistake made every query in
    // an earlier draft of this file fail at `.prepare()` and fall through to the
    // fail-open `None` every OTHER error path here also produces, so it went
    // uncaught until an end-to-end run against a real database (a unit test using
    // a fake `Connection` would not have caught it either): every one of these
    // three queries is one line so the bug class cannot recur here.
    let mut stmt = conn
        .prepare("SELECT project_id, name, status, project_path FROM business_projects WHERE status IN ('active', 'paused') AND project_path IS NOT NULL")
        .ok()?;
    let rows = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
            ))
        })
        .ok()?;

    // (is_paused, -root_len, project) -- min() picks active-first, then longest root,
    // matching Python's `min(candidates)` over `(status != 'active', -len(root), row)`.
    let mut best: Option<(bool, isize, Project)> = None;
    for row in rows.flatten() {
        let (project_id, name, status, project_path) = row;
        let Some(root) = paths::resolve_weak(&project_path) else { continue };
        if !paths::is_under(resolved, &root) {
            continue;
        }
        let key = (status != "active", -(root.to_string_lossy().len() as isize));
        let candidate = Project { project_id, name, project_path };
        match &best {
            Some((bp, bl, _)) if (*bp, *bl) <= key => {}
            _ => best = Some((key.0, key.1, candidate)),
        }
    }
    best.map(|(_, _, project)| project)
}

/// Mirror `in_progress_work_order`: the in-progress work order an edit
/// belongs to, attributed by declared module boundary when the edited path is
/// known, falling back to the most recently started. See the Python
/// docstring (WO-WO-LIFECYCLE-SURFACE) for why recency alone is wrong.
pub fn in_progress_work_order(
    authority_db: &Path,
    project_id: &str,
    file_path_project_relative: Option<(&Path, &Path)>,
) -> Option<WorkOrder> {
    let conn = connect_ro(authority_db)?;
    let mut stmt = conn
        .prepare("SELECT work_order_id, title, description FROM business_work_orders WHERE project_id = ?1 AND status = 'in_progress' ORDER BY started_at DESC")
        .ok()?;
    let rows: Vec<(String, String, String)> = stmt
        .query_map([project_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, Option<String>>(2)?.unwrap_or_default(),
            ))
        })
        .ok()?
        .flatten()
        .collect();

    if rows.is_empty() {
        return None;
    }

    if let Some((resolved_file, resolved_root)) = file_path_project_relative {
        let mut matched: Vec<&(String, String, String)> = Vec::new();
        for row in &rows {
            let globs = boundary_globs(&row.2);
            if globs.is_empty() {
                continue;
            }
            let Some(rel) = paths::relative_posix(resolved_file, resolved_root) else {
                continue;
            };
            if path_in_boundary(&rel, &globs) {
                matched.push(row);
            }
        }
        if !matched.is_empty() {
            let (work_order_id, title, description) = matched[0].clone();
            return Some(WorkOrder {
                work_order_id,
                title,
                description,
                attribution: "module_boundary",
                claimants: matched.iter().map(|r| r.0.clone()).collect(),
            });
        }
    }

    let (work_order_id, title, description) = rows[0].clone();
    Some(WorkOrder {
        work_order_id,
        title,
        description,
        attribution: "most_recently_started",
        // EMPTY, deliberately -- matching Python's `_as_dict`, which does not set a
        // "claimants" key at all in this branch (only the boundary-match branch
        // does). `on-edit-enforce.py` then passes `wo.get("claimants")` (`None`
        // here) to `record_edit`, whose OWN fallback computes `[work_order_id]`.
        // A round-4 review finding caught an earlier version of this function
        // pre-computing that same fallback here instead, which produced an
        // identical final value but made `session::record_edit`'s ported fallback
        // branch unreachable from this crate's one production call site -- dead
        // code wearing the shape of a real branch.
        claimants: Vec::new(),
    })
}

/// Mirror `next_created_work_order`: the next startable work order (excluding
/// one blocked behind an unclosed dependency), falling back to the unrefined
/// query when `work_order_dependencies` does not exist on an older authority.
pub fn next_created_work_order(authority_db: &Path, project_id: &str) -> Option<NextWorkOrder> {
    let conn = connect_ro(authority_db)?;
    let refined = conn
        .prepare("SELECT wo.work_order_id, wo.title FROM business_work_orders wo LEFT JOIN business_milestones m ON m.milestone_id = wo.milestone_id WHERE wo.project_id = ?1 AND wo.status = 'created' AND NOT EXISTS (SELECT 1 FROM work_order_dependencies d JOIN business_work_orders dep ON dep.work_order_id = d.depends_on_id WHERE d.work_order_id = wo.work_order_id AND dep.status != 'closed') ORDER BY m.order_index ASC, wo.sequence_order ASC NULLS LAST, wo.created_at ASC LIMIT 1")
        .and_then(|mut stmt| {
            stmt.query_row([project_id], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
            })
        });

    let row = match refined {
        Ok(row) => Some(row),
        Err(rusqlite::Error::QueryReturnedNoRows) => None,
        Err(_) => {
            // work_order_dependencies may not exist on an older authority -- degrade
            // to the unrefined query rather than to no suggestion at all.
            conn.prepare("SELECT wo.work_order_id, wo.title FROM business_work_orders wo LEFT JOIN business_milestones m ON m.milestone_id = wo.milestone_id WHERE wo.project_id = ?1 AND wo.status = 'created' ORDER BY m.order_index ASC, wo.sequence_order ASC NULLS LAST, wo.created_at ASC LIMIT 1")
                .ok()?
                .query_row([project_id], |row| {
                    Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
                })
                .ok()
        }
    };

    row.map(|(work_order_id, title)| NextWorkOrder { work_order_id, title })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    /// A real, on-disk SQLite authority with the same tables and columns
    /// `runtime/lib/enforcement.py` queries -- these functions are read-only
    /// SQL against those tables, so a fake `Connection` or a mocked trait
    /// would not exercise the actual predicates. `connect_ro` opens the file
    /// SQLITE_OPEN_READ_ONLY, so it must already exist and be populated
    /// before these functions ever see it.
    fn fixture_db(schema_and_data: &str) -> (tempfile::TempDir, PathBuf) {
        let dir = tempfile::tempdir().unwrap();
        let db_path = dir.path().join("studio.db");
        let conn = Connection::open(&db_path).unwrap();
        conn.execute_batch(
            "CREATE TABLE business_projects (project_id TEXT, name TEXT, status TEXT, project_path TEXT);
             CREATE TABLE business_work_orders (work_order_id TEXT, title TEXT, description TEXT, project_id TEXT, status TEXT, started_at TEXT, milestone_id TEXT, sequence_order INTEGER, created_at TEXT);
             CREATE TABLE business_milestones (milestone_id TEXT, order_index INTEGER);
             CREATE TABLE work_order_dependencies (work_order_id TEXT, depends_on_id TEXT);",
        )
        .unwrap();
        conn.execute_batch(schema_and_data).unwrap();
        drop(conn);
        (dir, db_path)
    }

    fn project_dir(base: &std::path::Path, name: &str) -> PathBuf {
        let p = base.join(name);
        std::fs::create_dir_all(&p).unwrap();
        p
    }

    #[test]
    fn match_registered_project_prefers_active_over_paused() {
        let root_dir = tempfile::tempdir().unwrap();
        let active_root = project_dir(root_dir.path(), "active-proj");
        let (fixture_dir, db_path) = fixture_db(&format!(
            "INSERT INTO business_projects VALUES ('p-active', 'Active', 'active', '{root}');
             INSERT INTO business_projects VALUES ('p-paused', 'Paused', 'paused', '{root}');",
            root = active_root.to_string_lossy().replace('\\', "\\\\"),
        ));
        let file = active_root.join("f.py");
        let project = match_registered_project(&db_path, &file).expect("a project matches");
        assert_eq!(project.project_id, "p-active", "active wins over paused for the same root");
        drop(fixture_dir);
    }

    #[test]
    fn match_registered_project_prefers_the_longest_matching_root() {
        let root_dir = tempfile::tempdir().unwrap();
        let outer = project_dir(root_dir.path(), "outer");
        let inner = project_dir(&outer, "inner");
        let (fixture_dir, db_path) = fixture_db(&format!(
            "INSERT INTO business_projects VALUES ('p-outer', 'Outer', 'active', '{outer}');
             INSERT INTO business_projects VALUES ('p-inner', 'Inner', 'active', '{inner}');",
            outer = outer.to_string_lossy().replace('\\', "\\\\"),
            inner = inner.to_string_lossy().replace('\\', "\\\\"),
        ));
        let file = inner.join("f.py");
        let project = match_registered_project(&db_path, &file).expect("a project matches");
        assert_eq!(project.project_id, "p-inner", "the nested project wins over its parent");
        drop(fixture_dir);
    }

    #[test]
    fn match_registered_project_none_when_no_project_contains_the_path() {
        let root_dir = tempfile::tempdir().unwrap();
        let proj = project_dir(root_dir.path(), "proj");
        let elsewhere = project_dir(root_dir.path(), "elsewhere");
        let (fixture_dir, db_path) = fixture_db(&format!(
            "INSERT INTO business_projects VALUES ('p1', 'P1', 'active', '{proj}');",
            proj = proj.to_string_lossy().replace('\\', "\\\\"),
        ));
        assert!(match_registered_project(&db_path, &elsewhere.join("f.py")).is_none());
        drop(fixture_dir);
    }

    #[test]
    fn in_progress_work_order_attributes_by_module_boundary_over_recency() {
        let root_dir = tempfile::tempdir().unwrap();
        let proj = project_dir(root_dir.path(), "proj");
        std::fs::create_dir_all(proj.join("core")).unwrap();
        let (fixture_dir, db_path) = fixture_db(
            "INSERT INTO business_work_orders VALUES ('wo-recent', 'Recent', 'Module boundary: interfaces.', 'p1', 'in_progress', '2026-01-02T00:00:00Z', NULL, NULL, '2026-01-02T00:00:00Z');
             INSERT INTO business_work_orders VALUES ('wo-boundary', 'Boundary', 'Module boundary: core.', 'p1', 'in_progress', '2026-01-01T00:00:00Z', NULL, NULL, '2026-01-01T00:00:00Z');",
        );
        let file = proj.join("core").join("x.py");
        let wo = in_progress_work_order(&db_path, "p1", Some((&file, &proj))).expect("a WO matches");
        assert_eq!(wo.work_order_id, "wo-boundary", "boundary match wins over the more recently started WO");
        assert_eq!(wo.attribution, "module_boundary");
        drop(fixture_dir);
    }

    #[test]
    fn in_progress_work_order_falls_back_to_most_recently_started() {
        let root_dir = tempfile::tempdir().unwrap();
        let proj = project_dir(root_dir.path(), "proj");
        let (fixture_dir, db_path) = fixture_db(
            "INSERT INTO business_work_orders VALUES ('wo-old', 'Old', '', 'p1', 'in_progress', '2026-01-01T00:00:00Z', NULL, NULL, '2026-01-01T00:00:00Z');
             INSERT INTO business_work_orders VALUES ('wo-new', 'New', '', 'p1', 'in_progress', '2026-01-02T00:00:00Z', NULL, NULL, '2026-01-02T00:00:00Z');",
        );
        let file = proj.join("x.py");
        let wo = in_progress_work_order(&db_path, "p1", Some((&file, &proj))).expect("a WO matches");
        assert_eq!(wo.work_order_id, "wo-new", "no declared boundary anywhere -- falls back to recency");
        assert_eq!(wo.attribution, "most_recently_started");
        assert!(
            wo.claimants.is_empty(),
            "matches Python's _as_dict: no claimants key in the recency-fallback branch -- \
             record_edit's own fallback (not this function) fills it in from work_order_id"
        );
        drop(fixture_dir);
    }

    #[test]
    fn in_progress_work_order_none_when_nothing_in_progress() {
        let (fixture_dir, db_path) = fixture_db(
            "INSERT INTO business_work_orders VALUES ('wo1', 'T', '', 'p1', 'created', NULL, NULL, NULL, '2026-01-01T00:00:00Z');",
        );
        assert!(in_progress_work_order(&db_path, "p1", None).is_none());
        drop(fixture_dir);
    }

    #[test]
    fn next_created_work_order_excludes_one_blocked_on_an_open_dependency() {
        let (fixture_dir, db_path) = fixture_db(
            "INSERT INTO business_work_orders VALUES ('wo-dep', 'Dep', '', 'p1', 'created', NULL, NULL, 1, '2026-01-01T00:00:00Z');
             INSERT INTO business_work_orders VALUES ('wo-blocked', 'Blocked', '', 'p1', 'created', NULL, NULL, 0, '2026-01-01T00:00:00Z');
             INSERT INTO work_order_dependencies VALUES ('wo-blocked', 'wo-dep');",
        );
        let next = next_created_work_order(&db_path, "p1").expect("a startable WO exists");
        assert_eq!(next.work_order_id, "wo-dep", "the WO blocked on an unclosed dependency is excluded");
        drop(fixture_dir);
    }

    #[test]
    fn next_created_work_order_degrades_gracefully_without_the_dependency_table() {
        let dir = tempfile::tempdir().unwrap();
        let db_path = dir.path().join("studio.db");
        let conn = Connection::open(&db_path).unwrap();
        // No work_order_dependencies table at all -- an older authority.
        conn.execute_batch(
            "CREATE TABLE business_projects (project_id TEXT, name TEXT, status TEXT, project_path TEXT);
             CREATE TABLE business_work_orders (work_order_id TEXT, title TEXT, description TEXT, project_id TEXT, status TEXT, started_at TEXT, milestone_id TEXT, sequence_order INTEGER, created_at TEXT);
             CREATE TABLE business_milestones (milestone_id TEXT, order_index INTEGER);
             INSERT INTO business_work_orders VALUES ('wo1', 'T', '', 'p1', 'created', NULL, NULL, NULL, '2026-01-01T00:00:00Z');",
        )
        .unwrap();
        drop(conn);
        let next = next_created_work_order(&db_path, "p1").expect("degrades to the unrefined query");
        assert_eq!(next.work_order_id, "wo1");
    }

    #[test]
    fn next_created_work_order_none_when_nothing_is_created() {
        let (fixture_dir, db_path) = fixture_db(
            "INSERT INTO business_work_orders VALUES ('wo1', 'T', '', 'p1', 'in_progress', '2026-01-01T00:00:00Z', NULL, NULL, '2026-01-01T00:00:00Z');",
        );
        assert!(next_created_work_order(&db_path, "p1").is_none());
        drop(fixture_dir);
    }
}
