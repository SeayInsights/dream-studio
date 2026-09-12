import pathlib

p = pathlib.Path("core/gates/round_table.py")
s = p.read_text(encoding="utf-8")

# 1. convene gains a distinct change_root.
old_sig = """    all_seats: bool = False,
    paths: list[str] | None = None,
    prior_findings: list | None = None,
) -> dict:"""
new_sig = """    all_seats: bool = False,
    paths: list[str] | None = None,
    prior_findings: list | None = None,
    change_root: Path | None = None,
) -> dict:"""
assert s.count(old_sig) == 1
s = s.replace(old_sig, new_sig)

old_doc = """    `prior_findings` is the previous verdict's findings, which the Reviewer's-reviewer seat
    re-checks."""
new_doc = """    TWO ROOTS, BECAUSE THEY ARE TWO QUESTIONS. `repo_root` says where the REGISTRY lives
    -- the Dream Studio tree, or an install that ships only `review/review_lanes.yml`.
    `change_root` says which working tree holds the CHANGE SET being reviewed, and is
    where the detectors run. For a work order delivering into another repository these
    differ, and collapsing them breaks whichever one loses: pointing both at the target
    repo raises `no review-lane registry`, and pointing both at Dream Studio selects lanes
    by relevance to the wrong diff and runs detectors over the wrong tree. `change_root`
    defaults to `repo_root`, so a caller reviewing this repo passes neither.

    `prior_findings` is the previous verdict's findings, which the Reviewer's-reviewer seat
    re-checks."""
assert s.count(old_doc) == 1
s = s.replace(old_doc, new_doc)

# 2. The change set and the detectors use change_root; the registry keeps repo_root.
old_body = """    seats: list[dict] = []
    started = monotonic()
    lanes = _lanes(repo_root)

    selected_by_scope = False
    if not all_seats and seat is None and lane_id is None:
        change_set = changed_paths(repo_root) if paths is None else paths"""
new_body = """    seats: list[dict] = []
    started = monotonic()
    lanes = _lanes(repo_root)
    _change_root = change_root if change_root is not None else repo_root

    selected_by_scope = False
    if not all_seats and seat is None and lane_id is None:
        change_set = changed_paths(_change_root) if paths is None else paths"""
assert s.count(old_body) == 1
s = s.replace(old_body, new_body)

old_det = """                    clean, detail = _run_detector(lane["detector"], repo_root)"""
new_det = """                    clean, detail = _run_detector(lane["detector"], _change_root)"""
assert s.count(old_det) == 1
s = s.replace(old_det, new_det)

old_self = """    self_review = sorted(
        path
        for path in (changed_paths(repo_root) if paths is None else paths)
        if path in _SELF
    )"""
new_self = """    self_review = sorted(
        path
        for path in (changed_paths(_change_root) if paths is None else paths)
        if path in _SELF
    )"""
assert s.count(old_self) == 1
s = s.replace(old_self, new_self)

p.write_text(s, encoding="utf-8")
print("convene separates the registry root from the change root")

# 3. verify passes the work order's root as the CHANGE root only.
q = pathlib.Path("core/work_orders/verify_main.py")
t = q.read_text(encoding="utf-8")
old_call = """            _table = _convene(
                run_detectors=True,
                prior_findings=_prior_findings,
                repo_root=Path(_search_root),
            )"""
new_call = """            _table = _convene(
                run_detectors=True,
                prior_findings=_prior_findings,
                # The CHANGE set only. The registry stays where convene() finds it by
                # default: a work order delivering into another repository has no
                # canonical/review_lanes.yml of its own, and passing this as repo_root
                # made the whole table unavailable rather than merely misaimed.
                change_root=Path(_search_root),
            )"""
assert t.count(old_call) == 1, t.count(old_call)
q.write_text(t.replace(old_call, new_call), encoding="utf-8")
print("verify passes it as change_root")
