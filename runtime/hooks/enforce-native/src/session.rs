//! Per-session JSON state, matching `runtime/lib/enforcement.py`'s
//! `load_session`/`save_session`/`active_skill_posture`/`record_edit` exactly.
//!
//! Deliberately NOT SQLite: on-skill-load (a separate hook, still Python) is
//! the writer of `active_skill_posture`, and both sides must agree on the
//! file's shape without either importing the other.

use std::path::{Path, PathBuf};

use serde_json::{Map, Value};

/// Mirror `_session_file`: keep only `[A-Za-z0-9_-]`, truncate to 80 chars.
/// Untrusted input (`session_id` comes off hook stdin) turned into a
/// filename -- this is the one thing standing between a crafted session id
/// and writing outside `SESSION_DIR`.
fn session_file(session_dir: &Path, session_id: &str) -> PathBuf {
    let safe: String = session_id
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '-' || *c == '_')
        .take(80)
        .collect();
    session_dir.join(format!("{safe}.json"))
}

/// Mirror `load_session`: `None` for a missing file OR one that fails to
/// parse -- never an error the caller has to handle.
pub fn load_session(session_dir: &Path, session_id: &str) -> Option<Map<String, Value>> {
    let path = session_file(session_dir, session_id);
    if !path.is_file() {
        return None;
    }
    let text = std::fs::read_to_string(&path).ok()?;
    match serde_json::from_str::<Value>(&text).ok()? {
        Value::Object(map) => Some(map),
        _ => None,
    }
}

/// Mirror `save_session`: best-effort, creates `SESSION_DIR` if needed, never
/// raises. `json.dumps(data, indent=1)` uses a ONE-space indent -- matched
/// here via `serde_json::to_string_pretty`'s default two-space indent being
/// overridden with a `PrettyFormatter` using one space, since a byte-identical
/// file is not required (nothing re-reads this file expecting Python's exact
/// framing; only THIS process and a future run of this process read it back),
/// but staying close avoids a gratuitous divergence from the file's own peers.
pub fn save_session(session_dir: &Path, session_id: &str, data: &Map<String, Value>) {
    let Ok(_) = std::fs::create_dir_all(session_dir) else { return };
    let mut buf = Vec::new();
    let formatter = serde_json::ser::PrettyFormatter::with_indent(b" ");
    let mut ser = serde_json::Serializer::with_formatter(&mut buf, formatter);
    if serde::Serialize::serialize(data, &mut ser).is_err() {
        return;
    }
    let _ = std::fs::write(session_file(session_dir, session_id), buf);
}

/// Mirror `active_skill_posture`: `(mode, posture)` for the most recently
/// loaded mode, or `None` -- a hint, never proof (see the Python docstring).
pub fn active_skill_posture(session_dir: &Path, session_id: Option<&str>) -> Option<(String, String)> {
    let session_id = session_id.filter(|s| !s.is_empty())?;
    let data = load_session(session_dir, session_id)?;
    let entry = data.get("active_skill_posture")?.as_object()?;
    let mode = entry.get("mode")?.as_str()?.to_string();
    let posture = entry.get("posture")?.as_str()?.to_string();
    Some((mode, posture))
}

/// RFC 3339 UTC "now", matching `datetime.now(UTC).isoformat()`'s shape
/// closely enough for a value nothing parses back structurally -- every
/// reader of this field treats it as an opaque timestamp string.
fn now_iso() -> String {
    time::OffsetDateTime::now_utc()
        .format(&time::format_description::well_known::Rfc3339)
        .unwrap_or_default()
}

/// Mirror `record_edit`: upsert-by-normalized-path into `source_edits` or
/// `doc_edits`, then save. `resolved_file` is the ALREADY-RESOLVED path
/// (`paths::resolve_weak` output); Python's `str(_resolve(file_path) or
/// file_path)` falls back to the raw string only when resolution fails,
/// which the caller has already decided by the time it reaches here.
#[allow(clippy::too_many_arguments)]
pub fn record_edit(
    session_dir: &Path,
    session_id: &str,
    normalized_path: &str,
    kind_is_source: bool,
    project_id: &str,
    work_order_id: Option<&str>,
    claimants: &[String],
    attribution: Option<&str>,
) {
    let mut data = load_session(session_dir, session_id).unwrap_or_else(|| {
        let mut m = Map::new();
        m.insert("session_id".into(), Value::String(session_id.to_string()));
        m.insert("started_at".into(), Value::String(now_iso()));
        m.insert("source_edits".into(), Value::Array(vec![]));
        m.insert("doc_edits".into(), Value::Array(vec![]));
        m.insert("stop_blocked_at".into(), Value::Null);
        m
    });

    let bucket_key = if kind_is_source { "source_edits" } else { "doc_edits" };
    let bucket = data
        .entry(bucket_key.to_string())
        .or_insert_with(|| Value::Array(vec![]))
        .as_array_mut()
        .expect("session bucket is always an array");

    let effective_claimants: Vec<Value> = if !claimants.is_empty() {
        claimants.iter().map(|c| Value::String(c.clone())).collect()
    } else if let Some(wo) = work_order_id {
        vec![Value::String(wo.to_string())]
    } else {
        vec![]
    };

    let mut found = false;
    for entry in bucket.iter_mut() {
        if entry.get("path").and_then(Value::as_str) == Some(normalized_path) {
            let obj = entry.as_object_mut().expect("session edit entries are objects");
            obj.insert(
                "work_order_id".into(),
                work_order_id.map(|w| Value::String(w.to_string())).unwrap_or(Value::Null),
            );
            obj.insert("claimants".into(), Value::Array(effective_claimants.clone()));
            // Mirror `attribution or entry.get("attribution")`: a falsy (here, absent
            // or empty) new value keeps whatever was already recorded.
            if let Some(attr) = attribution.filter(|a| !a.is_empty()) {
                obj.insert("attribution".into(), Value::String(attr.to_string()));
            }
            obj.insert("ts".into(), Value::String(now_iso()));
            found = true;
            break;
        }
    }
    if !found && bucket.len() < 500 {
        let mut obj = Map::new();
        obj.insert("path".into(), Value::String(normalized_path.to_string()));
        obj.insert("project_id".into(), Value::String(project_id.to_string()));
        obj.insert(
            "work_order_id".into(),
            work_order_id.map(|w| Value::String(w.to_string())).unwrap_or(Value::Null),
        );
        obj.insert("claimants".into(), Value::Array(effective_claimants));
        obj.insert(
            "attribution".into(),
            attribution.map(|a| Value::String(a.to_string())).unwrap_or(Value::Null),
        );
        obj.insert("ts".into(), Value::String(now_iso()));
        bucket.push(Value::Object(obj));
    }

    save_session(session_dir, session_id, &data);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("ds-enforce-session-test-{name}-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn round_trips_a_session() {
        let dir = tmp_dir("roundtrip");
        assert!(load_session(&dir, "abc").is_none());
        let mut data = Map::new();
        data.insert("hello".into(), Value::String("world".into()));
        save_session(&dir, "abc", &data);
        let loaded = load_session(&dir, "abc").unwrap();
        assert_eq!(loaded.get("hello").and_then(Value::as_str), Some("world"));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn session_id_is_sanitized_against_path_traversal() {
        let dir = tmp_dir("traversal");
        let mut data = Map::new();
        data.insert("x".into(), Value::Bool(true));
        save_session(&dir, "../../evil", &data);
        // The sanitized filename keeps everything inside session_dir.
        let entries: Vec<_> = std::fs::read_dir(&dir).unwrap().collect();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].as_ref().unwrap().file_name(), "evil.json");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn active_skill_posture_reads_back_what_on_skill_load_would_write() {
        let dir = tmp_dir("posture");
        let mut data = Map::new();
        let mut entry = Map::new();
        entry.insert("mode".into(), Value::String("build".into()));
        entry.insert("posture".into(), Value::String("read-only".into()));
        entry.insert("at".into(), Value::String("2026-09-26T00:00:00+00:00".into()));
        data.insert("active_skill_posture".into(), Value::Object(entry));
        save_session(&dir, "s1", &data);
        assert_eq!(
            active_skill_posture(&dir, Some("s1")),
            Some(("build".to_string(), "read-only".to_string()))
        );
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn active_skill_posture_is_none_for_no_session_id() {
        let dir = tmp_dir("posture-none");
        assert_eq!(active_skill_posture(&dir, None), None);
        assert_eq!(active_skill_posture(&dir, Some("")), None);
    }

    #[test]
    fn record_edit_upserts_by_normalized_path() {
        let dir = tmp_dir("record-edit");
        record_edit(&dir, "s1", "/repo/core/x.py", true, "proj1", Some("wo1"), &[], None);
        record_edit(&dir, "s1", "/repo/core/x.py", true, "proj1", Some("wo2"), &[], Some("module_boundary"));
        let data = load_session(&dir, "s1").unwrap();
        let edits = data.get("source_edits").unwrap().as_array().unwrap();
        assert_eq!(edits.len(), 1, "the second call updates the same entry, not a new one");
        assert_eq!(edits[0].get("work_order_id").and_then(Value::as_str), Some("wo2"));
        assert_eq!(edits[0].get("attribution").and_then(Value::as_str), Some("module_boundary"));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn record_edit_caps_bucket_at_500() {
        let dir = tmp_dir("record-edit-cap");
        for i in 0..510 {
            record_edit(&dir, "s1", &format!("/repo/f{i}.py"), true, "proj1", None, &[], None);
        }
        let data = load_session(&dir, "s1").unwrap();
        let edits = data.get("source_edits").unwrap().as_array().unwrap();
        assert_eq!(edits.len(), 500);
        std::fs::remove_dir_all(&dir).ok();
    }
}
