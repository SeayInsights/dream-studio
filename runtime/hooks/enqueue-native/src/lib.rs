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

/// Resolve the queue file. Mirrors `_queue_path()` in `enqueue.py` and
/// `hookq.queue_path()` in Python; `test_hook_queue.py` pins all copies in sync.
pub fn queue_path() -> Option<PathBuf> {
    let home = match std::env::var("DS_HOME") {
        Ok(h) if !h.is_empty() => PathBuf::from(h),
        _ => {
            // USERPROFILE on Windows, HOME elsewhere -- same answer as
            // os.path.expanduser("~") for the cases that matter here.
            let base = std::env::var("USERPROFILE").or_else(|_| std::env::var("HOME")).ok()?;
            PathBuf::from(base).join(".dream-studio")
        }
    };
    Some(home.join("state").join("hookq.jsonl"))
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
