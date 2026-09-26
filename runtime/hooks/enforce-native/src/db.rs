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
        work_order_id: work_order_id.clone(),
        title,
        description,
        attribution: "most_recently_started",
        claimants: vec![work_order_id],
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
