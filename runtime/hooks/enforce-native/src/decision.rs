//! The enforce decision, as pure functions over the contract in
//! `tests/unit/test_enforce_decision_parity.py`.
//!
//! Every rule here was read off the Python implementation and is asserted
//! against the same table the Python side asserts against -- the contract is
//! emitted as JSON (`DS_ENFORCE_CONTRACT_OUT`) so these tests consume the rows
//! rather than a translation someone typed twice. Hand-copying a contract is
//! how two implementations drift while both look tested.
//!
//! Nothing in this file touches SQLite or the filesystem: the decision splits
//! cleanly into "what do these strings mean" (here, testable in microseconds)
//! and "what does the authority say" (the caller). That split is why the
//! contract can be checked exhaustively.

/// The enforcement ladder, least to most intrusive.
#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum Tier {
    Off,
    Observe,
    Warn,
    Enforce,
}

/// Resolve the tier from ONE variable, matching `enforcement.resolve_tier`.
///
/// `DS_ENFORCE` takes `0` or any tier name. `DS_ENFORCE_TIER` is the deprecated
/// second spelling, still read so an existing setup does not silently get
/// STRICTER than its owner asked for. Unset or unrecognized means `Enforce`:
/// enforcement stays on by default and only an explicit value lowers it.
pub fn resolve_tier(ds_enforce: Option<&str>, legacy_tier: Option<&str>) -> Tier {
    let named = |v: &str| match v.trim().to_ascii_lowercase().as_str() {
        "0" | "off" => Some(Tier::Off),
        "observe" => Some(Tier::Observe),
        "warn" => Some(Tier::Warn),
        "enforce" => Some(Tier::Enforce),
        _ => None,
    };
    if let Some(t) = ds_enforce.and_then(named) {
        return t;
    }
    legacy_tier.and_then(named).unwrap_or(Tier::Enforce)
}

/// What kind of file this is, which decides WHICH rule applies.
#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum PathKind {
    Source,
    Doc,
    DocstoreOnly,
}

/// Classify a repo-relative path, matching `enforcement.classify_path`.
///
/// SOURCE IS THE DEFAULT, and that is deliberate on the Python side: tests/,
/// README.md and a bare notes.txt all classify as source. A port that narrowed
/// this would stop enforcing on files the Python one covers, which is the
/// failure direction that produces no error -- just an absence.
pub fn classify(rel_path: &str) -> PathKind {
    let p = rel_path.replace('\\', "/");
    let p = p.trim_start_matches("./");
    if p == ".planning" || p.starts_with(".planning/") {
        return PathKind::DocstoreOnly;
    }
    if p == "docs" || p.starts_with("docs/") {
        return PathKind::Doc;
    }
    PathKind::Source
}

/// Parse a work order description's `Module boundary: a, b, c.` clause.
///
/// The clause STOPS AT A NEWLINE. Unbounded it ran on into the following
/// paragraph, and one live work order's final entry was a path with two
/// newlines and a sentence of prose glued to it, matching nothing at all.
pub fn boundary_globs(description: &str) -> Vec<String> {
    let Some(idx) = description.find("Module boundary:") else {
        return Vec::new();
    };
    let rest = &description[idx + "Module boundary:".len()..];
    // A "." INSIDE A FILENAME IS NOT THE END OF THE CLAUSE. Python's regex is
    // `[^.\n]+(?:\.[a-z]+[^.\n]*)*`: a dot followed by lowercase letters is an
    // extension and continues the clause; a dot followed by anything else (a
    // space, a capital, end of string) ends the sentence. Stopping at the first
    // dot truncated `core/config/paths.py` to `core/config/paths`, which matches
    // no file -- caught by the contract test, which is the point of having one.
    let chars: Vec<char> = rest.chars().collect();
    let mut end = chars.len();
    for (i, c) in chars.iter().enumerate() {
        if *c == '\n' {
            end = i;
            break;
        }
        if *c == '.' {
            let is_extension = chars.get(i + 1).is_some_and(|n| n.is_ascii_lowercase());
            if !is_extension {
                end = i;
                break;
            }
        }
    }
    let clause: String = chars[..end].iter().collect();
    clause
        .split(',')
        .map(|p| p.trim().trim_end_matches('.').trim().to_string())
        .filter(|p| !p.is_empty())
        .collect()
}

/// Does this path fall inside any declared boundary?
///
/// TWO RULES, AND THE SECOND ONE IS A DELIBERATE ABSENCE.
///
/// An EMPTY boundary list returns true -- undeclared claims everything -- which
/// matches Python and is load-bearing for the advisory path. Callers that use
/// this to DEMAND an authority write must check for a declared boundary first,
/// exactly as `in_progress_work_order` does.
///
/// A declared FILE claims that file, not its directory. Python used to also
/// accept a dirname match; measured against one edited test file on the live
/// authority, 24 work orders claimed it and 15 claimed it only through that
/// widening. Removed there, and deliberately not reproduced here.
pub fn path_in_boundary(rel_path: &str, globs: &[String]) -> bool {
    if globs.is_empty() {
        return true;
    }
    let p = rel_path.replace('\\', "/").to_ascii_lowercase();
    globs.iter().any(|g| {
        let g = g.replace('\\', "/");
        let g = g.trim_matches('/').to_ascii_lowercase();
        p == g || p.starts_with(&format!("{}/", g.trim_end_matches('/')))
    })
}

/// Write targets a Bash command would create, matching `extract_write_targets`.
///
/// The hook inspects Bash too, so a port that finds different targets lets an
/// edit through the door this exists to watch. Returns (targets, saw_redirect).
pub fn extract_write_targets(command: &str) -> (Vec<String>, bool) {
    let mut targets = Vec::new();
    let bytes: Vec<char> = command.chars().collect();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == '>' {
            // skip a second '>' for append, then any whitespace
            let mut j = i + 1;
            if j < bytes.len() && bytes[j] == '>' {
                j += 1;
            }
            while j < bytes.len() && bytes[j].is_whitespace() {
                j += 1;
            }
            let start = j;
            while j < bytes.len() && !bytes[j].is_whitespace() {
                j += 1;
            }
            if j > start {
                let t: String = bytes[start..j].iter().collect();
                // A redirect to a device is not a write target.
                if !t.starts_with("/dev/") && t != "NUL" {
                    targets.push(t);
                }
            }
            i = j;
            continue;
        }
        i += 1;
    }
    let saw = !targets.is_empty();
    (targets, saw)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tier_ladder_matches_the_contract() {
        assert_eq!(resolve_tier(None, None), Tier::Enforce);
        assert_eq!(resolve_tier(Some("0"), None), Tier::Off);
        assert_eq!(resolve_tier(Some("off"), None), Tier::Off);
        assert_eq!(resolve_tier(Some("observe"), None), Tier::Observe);
        assert_eq!(resolve_tier(Some("warn"), None), Tier::Warn);
        assert_eq!(resolve_tier(Some("yes"), None), Tier::Enforce, "fails safe");
        assert_eq!(resolve_tier(None, Some("observe")), Tier::Observe, "legacy honoured");
        assert_eq!(resolve_tier(Some("0"), Some("enforce")), Tier::Off, "new wins");
    }

    #[test]
    fn classification_matches_the_contract() {
        assert_eq!(classify("core/config/paths.py"), PathKind::Source);
        assert_eq!(classify("tests/unit/test_x.py"), PathKind::Source);
        assert_eq!(classify("README.md"), PathKind::Source);
        assert_eq!(classify("notes.txt"), PathKind::Source);
        assert_eq!(classify("docs/DATABASE.md"), PathKind::Doc);
        assert_eq!(classify(".planning/work-orders/x.md"), PathKind::DocstoreOnly);
        assert_eq!(classify(".planning/personal/notes.md"), PathKind::DocstoreOnly);
    }

    #[test]
    fn boundary_parsing_matches_the_contract() {
        assert_eq!(boundary_globs("Module boundary: core, docs."), vec!["core", "docs"]);
        assert_eq!(
            boundary_globs("Module boundary: core/config/paths.py."),
            vec!["core/config/paths.py"]
        );
        assert!(boundary_globs("no clause here at all").is_empty());
        assert!(boundary_globs("").is_empty());
    }

    #[test]
    fn an_undeclared_boundary_claims_every_file() {
        assert!(path_in_boundary("anything/at/all.py", &[]));
    }

    #[test]
    fn a_declared_file_claims_that_file_not_its_neighbours() {
        let g = vec!["core/config/paths.py".to_string()];
        assert!(path_in_boundary("core/config/paths.py", &g));
        assert!(!path_in_boundary("core/config/other.py", &g), "the widening is gone");
        assert!(!path_in_boundary("interfaces/cli/ds.py", &g));
    }

    #[test]
    fn a_declared_subtree_covers_its_files() {
        let g = vec!["core".to_string()];
        assert!(path_in_boundary("core/config/paths.py", &g));
        assert!(!path_in_boundary("interfaces/cli/ds.py", &g));
    }

    #[test]
    fn bash_write_targets_match_the_contract() {
        assert_eq!(extract_write_targets("echo hi > out.txt").0, vec!["out.txt"]);
        assert_eq!(extract_write_targets("echo hi >> out.txt").0, vec!["out.txt"]);
        assert!(extract_write_targets("cat a.txt").0.is_empty());
        assert!(extract_write_targets("ls -la").0.is_empty());
    }
}
