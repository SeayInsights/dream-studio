//! Shared primitives for the append-only hook queue: the path convention and
//! the JSON-string escaping, extracted so a second native hook (`ds-enforce`)
//! can append to the SAME file the SAME way instead of hand-copying this
//! logic a second time in another crate.
//!
//! `main.rs` (the `ds-enqueue` binary) is a thin CLI wrapper over these three
//! functions. Behaviour is unchanged by this split -- `tests/unit/test_hook_queue.py`
//! exercises the compiled binary, not this file, and still passes unmodified.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;

/// Resolve the Dream Studio home directory.
///
/// `DS_HOME` first, then `DREAM_STUDIO_HOME`, then the default. Two things are
/// both true and both drove this order:
///
/// - In real (non-test) use, an operator sets `DREAM_STUDIO_HOME` (`ds --home
///   X`) and never `DS_HOME` -- Claude Code invokes hooks.json entries
///   DIRECTLY, never through `ds.py`, so a hook only ever sees the operator's
///   own ambient environment, and `DS_HOME` is a second, narrower channel
///   `ds.py` sets as a synced mirror for its OWN subprocesses. A round-4
///   review finding caught this function reading ONLY `DS_HOME` before this
///   fix -- silently resolving a different, usually-default path than the
///   Python hook this crate replaces (`core/config/paths.py::home_dir()`
///   reads only `DREAM_STUDIO_HOME`) whenever an operator used the documented
///   override without also separately exporting `DS_HOME`.
/// - `tests/conftest.py` forces `DREAM_STUDIO_HOME` to a session-wide temp
///   directory at collection time, for every test in the suite, as a
///   contamination guard against the real `~/.dream-studio`. `DS_HOME` is
///   deliberately the ONE variable that guard never touches, so a per-test
///   fixture (`tests/unit/test_hook_queue.py::ds_home`) can redirect just this
///   native binary's state without fighting it. Checking `DREAM_STUDIO_HOME`
///   FIRST would silently ignore every such fixture and resolve to the
///   session-wide guard path instead -- exactly what broke when this fix was
///   first written with the two checked in the other order.
pub fn dream_studio_home() -> Option<PathBuf> {
    for var in ["DS_HOME", "DREAM_STUDIO_HOME"] {
        if let Ok(h) = std::env::var(var) {
            if !h.is_empty() {
                return Some(PathBuf::from(h));
            }
        }
    }
    // USERPROFILE on Windows, HOME elsewhere -- same answer as
    // os.path.expanduser("~") for the cases that matter here.
    let base = std::env::var("USERPROFILE").or_else(|_| std::env::var("HOME")).ok()?;
    Some(PathBuf::from(base).join(".dream-studio"))
}

/// Resolve the queue file. Mirrors `_queue_path()` in `enqueue.py` and
/// `hookq.queue_path()` in Python; `test_hook_queue.py` pins all copies in sync.
pub fn queue_path() -> Option<PathBuf> {
    Some(dream_studio_home()?.join("state").join("hookq.jsonl"))
}

/// Escape a string into a JSON string body (without the surrounding quotes).
///
/// Written out rather than pulled from serde: the queue's wire format is one
/// flat object with three string/number fields, and the drain side must be
/// able to parse every line either writer produces. Control characters below
/// 0x20 are the ones that would otherwise break the one-record-per-line
/// contract, so they are escaped explicitly.
pub fn escape_json(input: &str, out: &mut String) {
    for c in input.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0c}' => out.push_str("\\f"),
            c if (c as u32) < 0x20 => {
                out.push_str(&format!("\\u{:04x}", c as u32));
            }
            c => out.push(c),
        }
    }
}

/// Append one already-framed line (caller includes the trailing `\n`) to the
/// queue file, creating its parent directory first.
///
/// ONE write of ONE line, to a handle opened for append. Concurrent hook
/// processes share this file with no lock between them; a single sub-4KB
/// append is what keeps their lines from interleaving. Do not split this into
/// several writes, and do not wrap it in a `BufWriter` that might flush at a
/// buffer boundary rather than a record boundary.
pub fn append_line(path: &std::path::Path, line: &str) -> Option<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).ok()?;
    }
    let mut fh = OpenOptions::new().create(true).append(true).open(path).ok()?;
    fh.write_all(line.as_bytes()).ok()?;
    Some(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    // Both env vars this function reads are process-global, and cargo test runs
    // tests in parallel threads within one process -- without this, two tests
    // race on the same vars even with distinct expected outcomes.
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    fn with_env<F: FnOnce() -> R, R>(vars: &[(&str, Option<&str>)], f: F) -> R {
        let _guard = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        for (name, _) in vars {
            std::env::remove_var(name);
        }
        for (name, value) in vars {
            if let Some(v) = value {
                std::env::set_var(name, v);
            }
        }
        let result = f();
        for (name, _) in vars {
            std::env::remove_var(name);
        }
        result
    }

    /// Neither existing test suite (this crate had none; the Python side's
    /// `tests/unit/test_hook_queue.py` only ever set `DS_HOME`) exercised
    /// `DREAM_STUDIO_HOME`-only resolution -- exactly the gap that let a
    /// round-4 review finding catch this function reading only `DS_HOME`.
    #[test]
    fn prefers_ds_home_when_both_are_set() {
        with_env(&[("DS_HOME", Some("C:/ds-home-wins")), ("DREAM_STUDIO_HOME", Some("C:/dsh-home-loses"))], || {
            assert_eq!(dream_studio_home(), Some(PathBuf::from("C:/ds-home-wins")));
        });
    }

    #[test]
    fn falls_back_to_dream_studio_home_when_ds_home_is_unset() {
        with_env(&[("DS_HOME", None), ("DREAM_STUDIO_HOME", Some("C:/dsh-only"))], || {
            assert_eq!(dream_studio_home(), Some(PathBuf::from("C:/dsh-only")));
        });
    }

    #[test]
    fn falls_back_to_default_when_neither_is_set() {
        with_env(&[("DS_HOME", None), ("DREAM_STUDIO_HOME", None)], || {
            let resolved = dream_studio_home().expect("USERPROFILE/HOME must be set to run this test");
            assert!(resolved.ends_with(".dream-studio"));
        });
    }
}
