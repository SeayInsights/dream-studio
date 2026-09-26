//! Path resolution mirroring Python's `Path(path_str).expanduser().resolve()`
//! and `_is_under`, from `runtime/lib/enforcement.py`'s `_resolve`/`_is_under`.
//!
//! THIS IS NOT `std::fs::canonicalize`. Canonicalize refuses a path that does
//! not exist yet, and a `Write` tool call names a file that is about to be
//! CREATED -- at PreToolUse time it is not on disk. Python's non-strict
//! `resolve()` still answers for it: it walks up to the deepest EXISTING
//! ancestor, resolves symlinks for that much, and lexically appends whatever
//! comes after. A port that used `canonicalize` directly would treat every
//! new-file Write as unresolvable, and `classify_path`'s fail path for an
//! unresolvable file is "exempt" -- enforcement would silently stop applying
//! to the one case it exists to catch most: a new product-source file with
//! no work order yet.
//!
//! `~user` (another account's home): Windows and POSIX Python disagree on this,
//! and this function follows each platform's own real behavior rather than one
//! answer for both. `ntpath.expanduser` (Windows) is a PURE STRING heuristic --
//! it substitutes the requested username for the current one in `USERPROFILE`
//! and always succeeds, never checking the name is real. A round-4 review
//! finding caught this file's own earlier claim that Windows had "no pwd
//! equivalent" and so never expands `~user` -- false, verified against real
//! CPython (`Lib/ntpath.py`) and live execution: `ntpath.expanduser('~foo/x')`
//! returns an absolute, unrelated path, while the un-expanded version this
//! function used to produce stayed relative to the CWD instead -- a real,
//! reachable parity break for a hook that classifies and attributes paths.
//! `posixpath.expanduser` (POSIX) instead does a real `pwd.getpwnam(name)`
//! lookup and leaves the string untouched when no such system user exists --
//! matched here by leaving it untouched unconditionally, which agrees with
//! Python for every case this hook actually sees (nobody's edited file names a
//! second real system account's home).

use std::env;
use std::path::{Component, Path, PathBuf};

fn home_dir() -> Option<PathBuf> {
    env::var_os("USERPROFILE").or_else(|| env::var_os("HOME")).map(PathBuf::from)
}

#[cfg(windows)]
fn expand_user(path: &str) -> PathBuf {
    let Some(rest) = path.strip_prefix('~') else { return PathBuf::from(path) };
    if rest.is_empty() || rest.starts_with('/') || rest.starts_with('\\') {
        let Some(home) = home_dir() else { return PathBuf::from(path) };
        let stripped = rest.trim_start_matches(['/', '\\']);
        return if stripped.is_empty() { home } else { home.join(stripped) };
    }
    // `~user` or `~user/...`: ntpath replaces the username segment of
    // USERPROFILE (its own last path component) with the requested one, then
    // appends whatever followed the token EXACTLY as written -- not through
    // `Path::join`, which would normalize its separator instead of preserving
    // the caller's own (verified: `~foo/x` stays `foo/x`, `~foo\x` stays `foo\x`).
    let Some(home) = home_dir() else { return PathBuf::from(path) };
    let Some(parent) = home.parent() else { return PathBuf::from(path) };
    let split_at = rest.find(['/', '\\']).unwrap_or(rest.len());
    let (userhead, remainder) = rest.split_at(split_at);
    let mut result = parent.join(userhead).into_os_string();
    result.push(remainder);
    PathBuf::from(result)
}

#[cfg(not(windows))]
fn expand_user(path: &str) -> PathBuf {
    let Some(rest) = path.strip_prefix('~') else { return PathBuf::from(path) };
    if rest.is_empty() || rest.starts_with('/') || rest.starts_with('\\') {
        if let Some(home) = home_dir() {
            let stripped = rest.trim_start_matches(['/', '\\']);
            return if stripped.is_empty() { home } else { home.join(stripped) };
        }
    }
    PathBuf::from(path)
}

/// Collapse `.` and `..` components with no filesystem access, so it works
/// identically for a path that does not exist. `..` above the root is
/// discarded rather than kept literally -- POSIX `realpath("/..")` (and
/// Windows' equivalent) stays at the root, and `_resolve`'s input is always
/// made absolute before this point, so a leading root/prefix is always
/// present by the time any `..` is seen.
fn normalize_lexical(path: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for comp in path.components() {
        match comp {
            Component::CurDir => {}
            Component::ParentDir => {
                out.pop();
            }
            other => out.push(other.as_os_str()),
        }
    }
    out
}

/// Mirror `Path(path_str).expanduser().resolve()`: absolute, symlinks resolved
/// for the deepest EXISTING ancestor, `.`/`..` collapsed for the rest.
///
/// Returns `None` only for an empty string or when the current directory
/// itself cannot be read -- the same narrow set of cases Python's `_resolve`
/// catches via `(OSError, ValueError)`. A merely-nonexistent path is not one
/// of them; that is the entire point of this function.
pub fn resolve_weak(path_str: &str) -> Option<PathBuf> {
    if path_str.is_empty() {
        return None;
    }
    let expanded = expand_user(path_str);
    let absolute =
        if expanded.is_absolute() { expanded } else { env::current_dir().ok()?.join(expanded) };
    let lexical = normalize_lexical(&absolute);

    // Walk up to the deepest ancestor that actually exists, canonicalize it
    // (resolving symlinks the way Python's realpath-based resolve does), then
    // lexically re-append whatever came after it.
    let mut existing = lexical.clone();
    let mut suffix: Vec<std::ffi::OsString> = Vec::new();
    loop {
        if existing.as_os_str().is_empty() {
            return Some(lexical);
        }
        match dunce::canonicalize(&existing) {
            Ok(mut result) => {
                for part in suffix.iter().rev() {
                    result.push(part);
                }
                return Some(result);
            }
            Err(_) => {
                let popped_name = existing.file_name().map(|n| n.to_os_string());
                if !existing.pop() {
                    return Some(lexical);
                }
                match popped_name {
                    Some(name) => suffix.push(name),
                    None => return Some(lexical),
                }
            }
        }
    }
}

/// Mirror `_is_under`: is `path` inside `root`, exactly or (Windows paths
/// compare case-insensitively) case-insensitively.
pub fn is_under(path: &Path, root: &Path) -> bool {
    if path.starts_with(root) {
        return true;
    }
    let lower_path = path.to_string_lossy().to_lowercase();
    let lower_root = root.to_string_lossy().to_lowercase();
    Path::new(&lower_path).starts_with(Path::new(&lower_root))
}

/// `resolved.relative_to(root)`, exact or case-insensitive, as a `/`-joined
/// string (mirrors `.as_posix()`). `None` when `resolved` is not under `root`
/// either way -- callers choose their own fail-open default, matching Python:
/// `classify_path` treats that as "exempt", `path_in_boundary` treats it as a
/// match (the same asymmetry those two functions have in Python).
pub fn relative_posix(resolved: &Path, root: &Path) -> Option<String> {
    if let Ok(rel) = resolved.strip_prefix(root) {
        return Some(rel.components().map(|c| c.as_os_str().to_string_lossy()).collect::<Vec<_>>().join("/"));
    }
    let lower_resolved = PathBuf::from(resolved.to_string_lossy().to_lowercase());
    let lower_root = PathBuf::from(root.to_string_lossy().to_lowercase());
    lower_resolved.strip_prefix(&lower_root).ok().map(|rel| {
        rel.components().map(|c| c.as_os_str().to_string_lossy()).collect::<Vec<_>>().join("/")
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Verified against real CPython first: `ntpath.expanduser('~foo/file.py')`
    /// == `'C:\\Users\\foo/file.py'` (the OWN username segment of USERPROFILE
    /// replaced, the rest of the string carried through with its OWN separator
    /// untouched, not normalized). A round-4 review finding caught this file's
    /// earlier claim that Windows had no `~user` equivalent to expand.
    #[cfg(windows)]
    #[test]
    fn tilde_user_matches_ntpath_exactly() {
        let home = home_dir().expect("USERPROFILE must be set to run this test");
        let parent = home.parent().expect("USERPROFILE has a parent").to_path_buf();

        assert_eq!(expand_user("~foo"), parent.join("foo"));
        assert_eq!(expand_user("~foo/file.py"), {
            let mut p = parent.join("foo").into_os_string();
            p.push("/file.py");
            PathBuf::from(p)
        });
        assert_eq!(expand_user("~foo\\file.py"), {
            let mut p = parent.join("foo").into_os_string();
            p.push("\\file.py");
            PathBuf::from(p)
        });
        assert_eq!(expand_user("~foo/"), {
            let mut p = parent.join("foo").into_os_string();
            p.push("/");
            PathBuf::from(p)
        });
        // Bare ~ and ~/... are unaffected by this change -- still the caller's
        // own home, exactly as before.
        assert_eq!(expand_user("~"), home);
        assert_eq!(expand_user("~/file.py"), home.join("file.py"));
    }

    #[test]
    fn resolves_a_file_that_does_not_exist_yet() {
        let dir = std::env::temp_dir().join(format!("ds-enforce-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let target = dir.join("brand-new-file.py");
        assert!(!target.exists());
        let resolved = resolve_weak(target.to_str().unwrap()).expect("resolves despite absence");
        assert!(resolved.ends_with("brand-new-file.py"));
        assert!(is_under(&resolved, &dunce::canonicalize(&dir).unwrap()));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn resolves_a_nested_new_path_under_an_existing_root() {
        let dir = std::env::temp_dir().join(format!("ds-enforce-test-nested-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let target = dir.join("a").join("b").join("c.py");
        let resolved = resolve_weak(target.to_str().unwrap()).expect("resolves nested absence");
        assert!(resolved.ends_with(Path::new("a").join("b").join("c.py")));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn collapses_dot_and_dotdot_lexically() {
        let dir = std::env::temp_dir().join(format!("ds-enforce-test-dots-{}", std::process::id()));
        std::fs::create_dir_all(dir.join("x")).unwrap();
        let messy = dir.join("x").join("..").join("x").join(".").join("file.py");
        let resolved = resolve_weak(messy.to_str().unwrap()).unwrap();
        assert!(resolved.ends_with(Path::new("x").join("file.py")));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn is_under_matches_case_insensitively() {
        let dir = std::env::temp_dir().join(format!("ds-enforce-test-case-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let root = dunce::canonicalize(&dir).unwrap();
        let upper = PathBuf::from(root.to_string_lossy().to_uppercase()).join("f.py");
        assert!(is_under(&upper, &root));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn relative_posix_joins_with_forward_slashes() {
        let root = Path::new("/repo");
        let resolved = Path::new("/repo/core/config/paths.py");
        assert_eq!(relative_posix(resolved, root).as_deref(), Some("core/config/paths.py"));
    }

    #[test]
    fn relative_posix_none_when_not_under_root() {
        let root = Path::new("/repo");
        let resolved = Path::new("/elsewhere/f.py");
        assert_eq!(relative_posix(resolved, root), None);
    }
}
