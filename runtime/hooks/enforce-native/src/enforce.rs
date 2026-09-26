//! Orchestration, matching `runtime/hooks/meta/on-edit-enforce.py`'s
//! `_enforce`/`_apply` exactly: candidate extraction, the per-candidate
//! authority check, the tier ladder, and the advisory (never decision-
//! affecting) observations.
//!
//! Structured as a pure-ish function over already-resolved paths and an
//! already-parsed payload so it is testable without a real stdin, a real
//! authority DB, or a real session directory -- `Env` is the one seam.

use std::io::Write as _;
use std::path::PathBuf;

use serde_json::{Map, Value};

use crate::db;
use crate::decision::{self, PathKind};
use crate::paths;
use crate::queue;
use crate::session;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Decision {
    Allow,
    Deny,
    Observe,
    Noop,
}

impl Decision {
    pub fn as_str(self) -> &'static str {
        match self {
            Decision::Allow => "allow",
            Decision::Deny => "deny",
            Decision::Observe => "observe",
            Decision::Noop => "noop",
        }
    }
}

/// Rules that RECORD rather than block, whatever the global tier says.
/// Mirrors `_OBSERVE_ONLY` -- see its Python docstring for why
/// `authority_source_edit` is here and `zero_disk_planning` deliberately is not.
const OBSERVE_ONLY: &[&str] = &["authority_source_edit"];

/// The filesystem locations this hook reads/writes, resolved ONCE by the
/// caller so every function here is a plain value transform.
pub struct Env {
    pub authority_db: PathBuf,
    pub session_dir: PathBuf,
    pub ds_home: PathBuf,
    pub temp_root: PathBuf,
}

/// Truncate to at most `n` CHARACTERS (not bytes), matching Python's `s[:n]`
/// on a `str`. Byte-slicing here could panic mid multi-byte character.
fn truncate_chars(s: &str, n: usize) -> String {
    s.chars().take(n).collect()
}

fn tool_input_of(payload: &Value) -> Map<String, Value> {
    match payload.get("tool_input") {
        Some(Value::String(s)) => match serde_json::from_str::<Value>(s) {
            Ok(Value::Object(m)) => m,
            _ => Map::new(),
        },
        Some(Value::Object(m)) => m.clone(),
        _ => Map::new(),
    }
}

fn non_empty_str(v: Option<&Value>) -> Option<String> {
    match v {
        Some(Value::String(s)) if !s.is_empty() => Some(s.clone()),
        _ => None,
    }
}

/// Mirror `_apply`: apply the graduated tier to a would-be denial. Returns
/// the effective decision; the deny JSON (if any) is written to `out`.
fn apply(
    tier: &str,
    rule: &str,
    reason: &str,
    session_id: Option<&str>,
    out: &mut dyn std::io::Write,
) -> Decision {
    let effective_tier = if OBSERVE_ONLY.contains(&rule) && tier == "enforce" { "observe" } else { tier };

    if effective_tier == "enforce" {
        let payload = serde_json::json!({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        });
        if let Ok(s) = serde_json::to_string(&payload) {
            let _ = writeln!(out, "{s}");
            let _ = out.flush();
        }
        return Decision::Deny;
    }

    queue::record_observation("on_edit_enforce", "PreToolUse", rule, reason, effective_tier, session_id);
    if effective_tier == "warn" {
        let _ = writeln!(std::io::stderr(), "{reason}");
        let _ = std::io::stderr().flush();
    }
    Decision::Observe
}

/// Mirror `_enforce`'s candidate extraction: `file_path`/`notebook_path`/`path`
/// directly, else Bash write-target extraction. Returns the candidate paths
/// (possibly empty) and whether an `unparsed_write` bypass was already
/// recorded (in which case the caller returns `Noop` without looking further).
fn extract_candidates(payload: &Value, tool_input: &Map<String, Value>, session_id: Option<&str>) -> (Vec<String>, bool) {
    if let Some(fp) = non_empty_str(tool_input.get("file_path"))
        .or_else(|| non_empty_str(tool_input.get("notebook_path")))
        .or_else(|| non_empty_str(tool_input.get("path")))
    {
        return (vec![fp], false);
    }

    let command = non_empty_str(tool_input.get("command")).unwrap_or_default();
    let tool_name_is_bash = matches!(payload.get("tool_name"), Some(Value::String(s)) if s == "Bash");
    if !(tool_name_is_bash || !command.is_empty()) {
        return (Vec::new(), false);
    }

    let (targets, has_write) = decision::extract_write_targets(&command);
    if !targets.is_empty() {
        return (targets, false);
    }
    if has_write {
        queue::record_bypass(
            "on_edit_enforce",
            "PreToolUse",
            "unparsed_write",
            &format!("write-shaped command, no resolvable target: {}", truncate_chars(&command, 300)),
            session_id,
        );
    }
    (Vec::new(), true)
}

/// Mirror `_enforce`. Returns `(decision, session_id)`. Writes the deny JSON
/// to `out` on the deny path only, matching the Python docstring's "callers
/// must not write stdout" contract.
pub fn enforce(env: &Env, tier: &str, payload: &Value, out: &mut dyn std::io::Write) -> (Decision, Option<String>) {
    let tool_input = tool_input_of(payload);
    let session_id = non_empty_str(payload.get("session_id"));

    let (candidates, bash_checked_but_empty) = extract_candidates(payload, &tool_input, session_id.as_deref());
    if candidates.is_empty() {
        // Mirrors Python precisely: a Bash command that WAS inspected (and
        // found no usable target) keeps session_id; a tool call with no path
        // and no Bash shape at all (e.g. Read) returns None instead.
        return if bash_checked_but_empty { (Decision::Noop, session_id) } else { (Decision::Noop, None) };
    }

    let mut outcome = Decision::Noop;
    for cand in &candidates {
        let Some(resolved) = paths::resolve_weak(cand) else { continue };
        if paths::is_under(&resolved, &env.ds_home) || paths::is_under(&resolved, &env.temp_root) {
            continue;
        }
        let Some(project) = db::match_registered_project(&env.authority_db, &resolved) else { continue };
        let Some(project_root) = paths::resolve_weak(&project.project_path) else { continue };

        let rel = paths::relative_posix(&resolved, &project_root);
        // Mirror classify_path's own fail-to-exempt: unresolvable relative to
        // its own matched project's root is not a realistic case (the match
        // itself proved containment), but the fallback is exempt, not source.
        let kind = rel.as_deref().map(decision::classify).unwrap_or(PathKind::Exempt);
        if kind == PathKind::Exempt {
            continue;
        }

        if kind == PathKind::DocstoreOnly {
            let reason = "[dream-studio] Zero-disk .planning: working notes, specs, plans, and reports are authored in the files.db docstore, never on disk. Use:\n  py -m interfaces.cli.ds files write \"<name>\" --category planning [--work-order <id>]\n  (read: ds files read <name>  \u{b7}  list: ds files list --category planning)\nOperator escape hatch: set DS_ENFORCE=0 (or run at a lower DS_ENFORCE_TIER).";
            let decision = apply(tier, "zero_disk_planning", reason, session_id.as_deref(), out);
            return (decision, session_id);
        }

        let wo = db::in_progress_work_order(&env.authority_db, &project.project_id, Some((&resolved, &project_root)));

        if wo.is_none() && kind == PathKind::Source {
            let next = db::next_created_work_order(&env.authority_db, &project.project_id);
            let mut lines = vec![format!(
                "[dream-studio] Authority enforcement: no work order is in_progress for project '{}'. Product-source edits require an active work order in the SQLite authority.",
                project.name
            )];
            if let Some(next) = &next {
                lines.push(format!(
                    "Run: py -m interfaces.cli.ds work-order start {}  (next: {})",
                    next.work_order_id, next.title
                ));
            }
            lines.push(format!("Or list work orders: py -m interfaces.cli.ds work-order list {}", project.project_id));
            lines.push("Operator escape hatch: set DS_ENFORCE=0 (or run at a lower DS_ENFORCE_TIER).".to_string());
            let reason = lines.join("\n");
            let decision = apply(tier, "authority_source_edit", &reason, session_id.as_deref(), out);
            return (decision, session_id);
        }

        if let Some(wo) = &wo {
            if kind == PathKind::Source {
                let globs = decision::boundary_globs(&wo.description);
                if !globs.is_empty() {
                    let in_boundary = rel.as_deref().map(|r| decision::path_in_boundary(r, &globs)).unwrap_or(true);
                    if !in_boundary {
                        queue::record_observation(
                            "on_edit_enforce",
                            "PreToolUse",
                            "module_boundary_advisory",
                            &format!(
                                "edit outside the module boundary of WO {} ({}): {}",
                                truncate_chars(&wo.work_order_id, 8),
                                truncate_chars(&wo.title, 60),
                                cand
                            ),
                            "observe",
                            session_id.as_deref(),
                        );
                    }
                }
            }
        }

        if kind == PathKind::Source {
            if let Some((mode, posture)) = session::active_skill_posture(&env.session_dir, session_id.as_deref()) {
                if posture == "read-only" {
                    queue::record_observation(
                        "on_edit_enforce",
                        "PreToolUse",
                        "write_posture_advisory",
                        &format!("mode {mode} declares write_posture read-only, and a source write reached {cand}"),
                        "observe",
                        session_id.as_deref(),
                    );
                }
            }
        }

        if let Some(sid) = &session_id {
            let normalized = paths::resolve_weak(cand).map(|p| p.to_string_lossy().into_owned()).unwrap_or_else(|| cand.clone());
            let (work_order_id, claimants, attribution): (Option<String>, Vec<String>, Option<&'static str>) = match &wo {
                Some(w) => (Some(w.work_order_id.clone()), w.claimants.clone(), Some(w.attribution)),
                None => (None, Vec::new(), None),
            };
            session::record_edit(
                &env.session_dir,
                sid,
                &normalized,
                kind == PathKind::Source,
                &project.project_id,
                work_order_id.as_deref(),
                &claimants,
                attribution,
            );
        }

        outcome = Decision::Allow;
    }

    (outcome, session_id)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    fn env_at(dir: &Path) -> Env {
        Env {
            authority_db: dir.join("nonexistent.db"),
            session_dir: dir.join("enforce"),
            ds_home: dir.join("ds-home-never-matches"),
            temp_root: dir.join("temp-never-matches"),
        }
    }

    /// No registered projects means every candidate is exempt-by-absence
    /// (`match_registered_project` returns `None`) -- a broken/missing
    /// authority DB must never deny.
    #[test]
    fn no_authority_db_means_allow_not_deny() {
        let dir = std::env::temp_dir().join(format!("ds-enforce-e2e-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let target = dir.join("f.py");
        let payload = serde_json::json!({
            "tool_name": "Write",
            "tool_input": {"file_path": target.to_string_lossy()},
            "session_id": "s1",
        });
        let mut out = Vec::new();
        let (decision, _) = enforce(&env_at(&dir), "enforce", &payload, &mut out);
        assert_eq!(decision, Decision::Noop, "no matching project at all -> nothing to enforce");
        assert!(out.is_empty(), "never writes stdout on a non-deny path");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn a_read_only_tool_with_no_path_is_noop_with_no_session() {
        let dir = std::env::temp_dir().join(format!("ds-enforce-e2e-read-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let payload = serde_json::json!({"tool_name": "Read", "tool_input": {}, "session_id": "s1"});
        let mut out = Vec::new();
        let (decision, session_id) = enforce(&env_at(&dir), "enforce", &payload, &mut out);
        assert_eq!(decision, Decision::Noop);
        assert_eq!(session_id, None, "matches Python: no candidate at all drops session_id");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn a_bash_write_with_no_resolvable_target_keeps_the_session_id() {
        let dir = std::env::temp_dir().join(format!("ds-enforce-e2e-bash-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let payload = serde_json::json!({
            "tool_name": "Bash",
            "tool_input": {"command": "cp a.txt b.txt"},
            "session_id": "s1",
        });
        let mut out = Vec::new();
        let (decision, session_id) = enforce(&env_at(&dir), "enforce", &payload, &mut out);
        assert_eq!(decision, Decision::Noop);
        assert_eq!(session_id.as_deref(), Some("s1"), "a Bash command that WAS inspected keeps session_id");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn a_double_encoded_tool_input_string_is_parsed() {
        let dir = std::env::temp_dir().join(format!("ds-enforce-e2e-dbl-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let target = dir.join("f.py");
        let inner = serde_json::json!({"file_path": target.to_string_lossy()}).to_string();
        let payload = serde_json::json!({"tool_name": "Write", "tool_input": inner, "session_id": "s1"});
        let mut out = Vec::new();
        let (decision, session_id) = enforce(&env_at(&dir), "enforce", &payload, &mut out);
        assert_eq!(decision, Decision::Noop, "no project registered, but the path WAS extracted (not an empty-candidate noop)");
        // Distinguishes "decode succeeded, one candidate ran the loop and fell through"
        // (session_id preserved) from "decode silently failed, empty-candidate early
        // return for a non-Bash tool" (session_id dropped to None) -- see `enforce`'s
        // `if candidates.is_empty()` branch.
        assert_eq!(session_id.as_deref(), Some("s1"), "the inner JSON string must have been decoded, not silently dropped");
        std::fs::remove_dir_all(&dir).ok();
    }
}
