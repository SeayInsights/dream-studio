//! Append-only Dream Studio hook entry point: record the event, exit.
//!
//! This is a native rewrite of `runtime/hooks/enqueue.py`, which is itself a
//! rewrite of "import the whole platform to write one telemetry row".
//!
//! Measured on the operator's machine, 2026-09-21, per hook invocation:
//!
//!     the original dispatcher ...............  283 ms
//!     enqueue.py (Python, no DS imports) ....   55 ms
//!     this binary ...........................   see tests/bench in the PR
//!
//! The first jump was architectural and is where most of the win lives: the
//! old hook cold-loaded pydantic, jsonschema and the event store so it could
//! append a line. The second jump is the language, and it is worth taking only
//! because PostToolUse fires on every single tool call -- 92,315 runs against
//! 19,787 prompts in one timing log. At that frequency the ~33 ms Python
//! interpreter floor is itself the remaining cost.
//!
//! Behaviour is intentionally identical to enqueue.py, including the failure
//! mode: THIS MUST NEVER FAIL THE TOOL CALL IT OBSERVES. Every error path here
//! ends in exit code 0. A dropped telemetry record costs a row in a chart; a
//! non-zero exit costs the user their work.

use std::env;
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

/// Matches `_MAX_PAYLOAD` in enqueue.py. A hook payload larger than this is a
/// bug upstream, and truncating beats spooling megabytes per tool call.
const MAX_PAYLOAD: usize = 64 * 1024;

/// Resolve the queue file. Mirrors `_queue_path()` in enqueue.py and
/// `hookq.queue_path()` in Python; `test_hook_queue.py` pins all three in sync.
fn queue_path() -> Option<PathBuf> {
    let home = match env::var("DS_HOME") {
        Ok(h) if !h.is_empty() => PathBuf::from(h),
        _ => {
            // USERPROFILE on Windows, HOME elsewhere -- same answer as
            // os.path.expanduser("~") for the cases that matter here.
            let base = env::var("USERPROFILE").or_else(|_| env::var("HOME")).ok()?;
            PathBuf::from(base).join(".dream-studio")
        }
    };
    Some(home.join("state").join("hookq.jsonl"))
}

/// Escape a string into a JSON string body (without the surrounding quotes).
///
/// Written out rather than pulled from serde: this is the only JSON this
/// program produces, and the drain side must be able to parse every line it
/// writes. Control characters below 0x20 are the ones that would otherwise
/// break the one-record-per-line contract, so they are escaped explicitly.
fn escape_json(input: &str, out: &mut String) {
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

fn run() -> Option<()> {
    let event = env::args().nth(1).unwrap_or_default();

    // Read at most MAX_PAYLOAD. take() bounds it without allocating for a
    // pathological writer, and a lossy conversion keeps a non-UTF-8 payload
    // from turning into a dropped record.
    let mut buf = Vec::with_capacity(4096);
    std::io::stdin()
        .take(MAX_PAYLOAD as u64)
        .read_to_end(&mut buf)
        .ok()?;
    let payload = String::from_utf8_lossy(&buf);

    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);

    let mut line = String::with_capacity(buf.len() + 128);
    line.push_str("{\"event\":\"");
    escape_json(&event, &mut line);
    line.push_str("\",\"ts\":");
    line.push_str(&format!("{ts}"));
    line.push_str(",\"payload\":\"");
    escape_json(&payload, &mut line);
    line.push_str("\"}\n");

    let path = queue_path()?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).ok()?;
    }

    // ONE write of ONE line, to a handle opened for append. Concurrent hook
    // processes share this file with no lock between them; a single sub-4KB
    // append is what keeps their lines from interleaving. Do not split this
    // into several writes, and do not wrap it in a BufWriter that might flush
    // at a buffer boundary rather than a record boundary.
    let mut fh = OpenOptions::new().create(true).append(true).open(&path).ok()?;
    fh.write_all(line.as_bytes()).ok()?;
    Some(())
}

fn main() {
    // Deliberately ignores the result. See the module docs: every failure path
    // exits 0, because this process observes the user's work and must never be
    // able to interrupt it.
    let _ = run();
}
