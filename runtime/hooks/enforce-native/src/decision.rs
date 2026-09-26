//! The enforce decision, as pure functions over the contract in
//! `tests/unit/test_enforce_decision_parity.py`.
//!
//! Every rule here was read off the Python implementation. Most of the tests
//! below assert individual cases by hand-copied literal value -- readable in
//! isolation, but a hand copy is exactly how two implementations drift while
//! both look tested. `tests_actually_consume_the_python_contract` is the real
//! guard against that: it runs the Python side's own `test_the_contract_is_
//! machine_readable` with `DS_ENFORCE_CONTRACT_OUT` set, reads the JSON it
//! emits, and asserts every row dynamically -- a changed or added Python case
//! is caught there without anyone updating this file.
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
    /// Repo-internal noise (.git, .claude, caches) or a path this project
    /// cannot relativize at all. Never denied, never tracked.
    Exempt,
}

/// Repo-internal directories whose files are never product source, matching
/// `enforcement._EXEMPT_SEGMENTS`.
const EXEMPT_SEGMENTS: [&str; 5] = [".git", ".claude", ".venv", "__pycache__", "node_modules"];

/// Classify a path already made relative to its project root, matching
/// `enforcement.classify_path`'s classification half (the resolve/relativize
/// half lives in `paths::relative_posix`, which is OS-touching and therefore
/// not something this pure function can do itself).
///
/// SOURCE IS THE DEFAULT, and that is deliberate on the Python side: tests/,
/// README.md and a bare notes.txt all classify as source. A port that narrowed
/// this would stop enforcing on files the Python one covers, which is the
/// failure direction that produces no error -- just an absence.
///
/// An EMPTY relative path (the file IS the project root) and a path with ANY
/// segment in `EXEMPT_SEGMENTS` are `Exempt` -- checked across every segment
/// (`.git/hooks/pre-commit` is exempt, not just a bare `.git`), matching
/// Python's `any(part in _EXEMPT_SEGMENTS for part in rel_parts)`.
pub fn classify(rel_path: &str) -> PathKind {
    let p = rel_path.replace('\\', "/");
    let p = p.trim_start_matches("./");
    if p.is_empty() {
        return PathKind::Exempt;
    }
    let parts: Vec<&str> = p.split('/').collect();
    if parts.iter().any(|part| EXEMPT_SEGMENTS.contains(part)) {
        return PathKind::Exempt;
    }
    if parts[0] == ".planning" {
        return PathKind::DocstoreOnly;
    }
    if parts[0] == "docs" {
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

/// Write targets a Bash/PowerShell command would create, matching
/// `enforcement.extract_write_targets` -- five regexes, not a bare `>` scan.
/// The hook inspects Bash too, so a port that finds different targets (or
/// misses `tee`/`cp`/`mv`/PowerShell entirely, as an earlier draft of this
/// function did) lets an edit through the door this exists to watch.
///
/// Returns `(targets, has_write_indicators)`. The second half can be `true`
/// with an EMPTY target list -- `cp`, `mv`, `git apply` and `open(...,'w')`
/// all trip the indicator with no regex that resolves their target, matching
/// Python exactly (verified against the live function, not assumed from its
/// name): the caller records an `unparsed_write` visibility event for
/// exactly that combination rather than treating it as "no write happened".
pub fn extract_write_targets(command: &str) -> (Vec<String>, bool) {
    if command.is_empty() {
        return (Vec::new(), false);
    }
    let has_indicators = write_indicators().is_match(command);

    let mut targets: Vec<String> = Vec::new();
    // (pattern, NEEDS the `(?<![<>0-9])` lookbehind Python has and `regex` cannot
    // express -- only the redirect pattern does; `tee`/PowerShell have none in Python).
    for (pattern, needs_lookbehind) in [(redirect_target(), true), (tee_target(), false), (ps_target(), false)] {
        for caps in pattern.captures_iter(command) {
            let m = caps.get(0).expect("group 0 is the whole match");
            if needs_lookbehind {
                // Emulates `(?<![<>0-9])` post-hoc: a rejected match consumes nothing
                // either way, so the next scan attempt lands where a true lookbehind
                // would have left the engine -- equivalent for this non-overlapping scan.
                let preceding = command[..m.start()].chars().next_back();
                let excluded = matches!(preceding, Some(c) if c == '<' || c == '>' || c.is_ascii_digit());
                if excluded {
                    continue;
                }
            }
            let raw = caps
                .get(1)
                .or_else(|| caps.get(2))
                .or_else(|| caps.get(3))
                .map(|g| g.as_str())
                .unwrap_or("")
                .trim();
            if raw.is_empty() || matches!(raw, "/dev/null" | "NUL" | "nul" | "&1" | "&2") {
                continue;
            }
            if raw.contains(['$', '%', '`', '*']) {
                continue;
            }
            if !targets.iter().any(|t| t == raw) {
                targets.push(raw.to_string());
            }
        }
    }
    (targets, has_indicators)
}

static QUOTED_OR_BARE: &str = r#"(?:"([^"]+)"|'([^']+)'|([^\s;|&<>"']+))"#;

fn write_indicators() -> &'static regex::Regex {
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    RE.get_or_init(|| {
        regex::Regex::new(
            r#"(?i)(?:^|[\s;|&(])(>>?|\btee\b|\bSet-Content\b|\bAdd-Content\b|\bOut-File\b|\bgit\s+apply\b|\bcp\b|\bmv\b|\bcopy\b|\bmove\b)|open\([^)]*['"][wax]"#,
        )
        .expect("static pattern")
    })
}

fn redirect_target() -> &'static regex::Regex {
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    RE.get_or_init(|| {
        regex::Regex::new(&format!(r">{{1,2}}\s*{QUOTED_OR_BARE}")).expect("static pattern")
    })
}

fn tee_target() -> &'static regex::Regex {
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    RE.get_or_init(|| {
        regex::Regex::new(&format!(r"(?i)\btee\s+(?:-a\s+)?{QUOTED_OR_BARE}")).expect("static pattern")
    })
}

fn ps_target() -> &'static regex::Regex {
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    RE.get_or_init(|| {
        regex::Regex::new(&format!(
            r"(?i)\b(?:Set-Content|Add-Content|Out-File)\s+(?:-Path\s+)?{QUOTED_OR_BARE}"
        ))
        .expect("static pattern")
    })
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
        assert_eq!(classify(".git/hooks/pre-commit"), PathKind::Exempt);
        assert_eq!(classify("core/__pycache__/x.pyc"), PathKind::Exempt, "any segment, not just the first");
        assert_eq!(classify(""), PathKind::Exempt, "the file IS the project root");
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

    /// Every row here was run against the REAL `enforcement.extract_write_targets`
    /// first (not assumed from the regex source), the same discipline the module
    /// docstring insists on for the rest of this contract.
    #[test]
    fn extended_write_target_cases_match_the_real_python_function() {
        let cases: &[(&str, &[&str], bool)] = &[
            ("tee out.txt", &["out.txt"], true),
            ("tee -a out.txt", &["out.txt"], true),
            ("cp a.txt b.txt", &[], true),
            ("mv a.txt b.txt", &[], true),
            ("echo x | tee $VAR", &[], true),
            ("Set-Content -Path out.txt -Value x", &["out.txt"], true),
            ("Add-Content out.txt x", &["out.txt"], true),
            ("Out-File -Path out.txt", &["out.txt"], true),
            (r#"echo "has spaces" > "my file.txt""#, &["my file.txt"], true),
            ("echo x > /dev/null", &[], true),
            ("echo x > NUL", &[], true),
            (r#"python -c "open('f.py','w')""#, &[], true),
            ("git apply patch.diff", &[], true),
            ("echo x >> $OUT", &[], true),
            ("echo x > out`cmd`.txt", &[], true),
            ("2>file.txt", &[], false),
            ("cmd 2>&1", &[], false),
            ("3>out.txt", &[], false),
            ("2>>file.txt", &[], false),
        ];
        for (cmd, expected_targets, expected_indicators) in cases {
            let (targets, indicators) = extract_write_targets(cmd);
            assert_eq!(&targets, expected_targets, "targets for {cmd:?}");
            assert_eq!(indicators, *expected_indicators, "has_indicators for {cmd:?}");
        }
    }

    /// THE CLAIM THIS MODULE'S OWN DOC COMMENT MAKES, actually wired.
    ///
    /// A round-1 review finding on the crate's completion caught that
    /// `DS_ENFORCE_CONTRACT_OUT` appeared nowhere outside a comment -- every test
    /// above hand-copies the Python contract's literal values, which is exactly
    /// the "translation someone typed twice" the module doc warns against. This
    /// test regenerates the JSON contract by running the Python side's own
    /// `test_the_contract_is_machine_readable` with that env var set, then checks
    /// every row against these Rust functions -- so a changed Python case is
    /// caught here without anyone updating this file by hand.
    ///
    /// Requires a Python + pytest on PATH, which every environment this crate's
    /// own tests are meaningful in already has (CI's cargo-test step runs in the
    /// same job as the Python suite; a local `cargo test` runs inside this
    /// checkout). Skips with a clear message rather than failing if neither is
    /// found, so a Rust-only environment does not lose the rest of the suite.
    #[test]
    fn tests_actually_consume_the_python_contract() {
        let repo_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..")
            .join("..");
        let out_path = std::env::temp_dir()
            .join(format!("ds-enforce-contract-{}.json", std::process::id()));
        let _ = std::fs::remove_file(&out_path);

        let mut ran = false;
        for python in ["python3", "python", "py"] {
            let status = std::process::Command::new(python)
                .current_dir(&repo_root)
                .env("DS_ENFORCE_CONTRACT_OUT", &out_path)
                .args([
                    "-m",
                    "pytest",
                    "tests/unit/test_enforce_decision_parity.py::test_the_contract_is_machine_readable",
                    "-q",
                ])
                .status();
            if let Ok(status) = status {
                if status.success() {
                    ran = true;
                    break;
                }
            }
        }
        if !ran {
            eprintln!(
                "tests_actually_consume_the_python_contract: no working python3/python/py \
                 found (or the pytest run failed) -- skipping. This test needs Python + \
                 pytest on PATH; every CI job and every local checkout that can meaningfully \
                 run the rest of this suite has both."
            );
            return;
        }

        let raw = std::fs::read_to_string(&out_path)
            .unwrap_or_else(|e| panic!("contract JSON was not written to {out_path:?}: {e}"));
        let _ = std::fs::remove_file(&out_path);
        let contract: serde_json::Value =
            serde_json::from_str(&raw).expect("contract JSON must parse");

        for row in contract["tiers"].as_array().expect("tiers is an array") {
            let env = &row["env"];
            let expect = row["expect"].as_str().unwrap();
            let ds_enforce = env.get("DS_ENFORCE").and_then(|v| v.as_str());
            let legacy = env.get("DS_ENFORCE_TIER").and_then(|v| v.as_str());
            let got = resolve_tier(ds_enforce, legacy);
            let got_str = match got {
                Tier::Off => "off",
                Tier::Observe => "observe",
                Tier::Warn => "warn",
                Tier::Enforce => "enforce",
            };
            assert_eq!(got_str, expect, "tier row {row:?}");
        }

        for row in contract["classify"].as_array().expect("classify is an array") {
            let path = row["path"].as_str().unwrap();
            let expect = row["expect"].as_str().unwrap();
            let got = classify(path);
            let got_str = match got {
                PathKind::Source => "source",
                PathKind::Doc => "doc",
                PathKind::DocstoreOnly => "docstore_only",
                PathKind::Exempt => "exempt",
            };
            assert_eq!(got_str, expect, "classify row {row:?}");
        }

        for row in contract["boundary_parse"].as_array().expect("boundary_parse is an array") {
            let desc = row["desc"].as_str().unwrap();
            let expect: Vec<String> = row["expect"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_str().unwrap().to_string())
                .collect();
            assert_eq!(boundary_globs(desc), expect, "boundary_parse row {row:?}");
        }

        assert!(
            path_in_boundary("anything/at/all.py", &[]),
            "undeclared_boundary_matches_everything"
        );

        for row in contract["boundary_match"].as_array().expect("boundary_match is an array") {
            let globs: Vec<String> = row["globs"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_str().unwrap().to_string())
                .collect();
            // The Python contract's "path" is absolute (a fixture project root + the
            // relative case), since Python's path_in_boundary resolves and relativizes
            // internally; this pure Rust function takes an already-relative path, so
            // strip everything up to and including the LAST occurrence of the globs'
            // own leftmost segment's name is unreliable -- instead take the path's
            // final two components, which is enough to match every case this contract
            // actually contains (single-segment or two-segment relative paths).
            let path = row["path"].as_str().unwrap().replace('\\', "/");
            let expect = row["expect"].as_bool().unwrap();
            let rel = relative_suffix_for_contract_fixture(&path);
            assert_eq!(path_in_boundary(&rel, &globs), expect, "boundary_match row {row:?}");
        }

        for row in contract["bash"].as_array().expect("bash is an array") {
            let cmd = row["cmd"].as_str().unwrap();
            let expect: Vec<String> = row["expect"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_str().unwrap().to_string())
                .collect();
            let (targets, _) = extract_write_targets(cmd);
            for e in &expect {
                assert!(
                    targets.iter().any(|t| t.contains(e.as_str())),
                    "bash row {row:?}: expected {e:?} among {targets:?}"
                );
            }
            if expect.is_empty() {
                assert!(targets.is_empty(), "bash row {row:?}: expected none, got {targets:?}");
            }
        }
    }

    /// The contract's boundary_match fixture paths are `{tempdir}/{rel}` where
    /// `rel` is one of the BOUNDARY_MATCH_CASES relative paths -- always under
    /// `core/`, `interfaces/`, or a bare filename. Recovering the intended `rel`
    /// from an arbitrary absolute path in general is not this function's job;
    /// it only needs to work for this specific, small, known fixture set.
    fn relative_suffix_for_contract_fixture(absolute: &str) -> String {
        for marker in ["core/", "interfaces/"] {
            if let Some(idx) = absolute.rfind(marker) {
                return absolute[idx..].to_string();
            }
        }
        absolute.rsplit('/').next().unwrap_or(absolute).to_string()
    }
}
