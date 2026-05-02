"""
Validate test suite structure and coverage

Checks:
1. All test files are properly structured
2. Test functions follow naming conventions
3. Required fixtures exist
4. Coverage targets are achievable

Usage:
    python analytics/tests/validate_tests.py
"""
import os
import sys
from pathlib import Path
import ast


def validate_test_file(file_path: Path) -> dict:
    """Validate a single test file"""
    issues = []
    stats = {
        "test_classes": 0,
        "test_functions": 0,
        "fixtures": 0,
        "has_docstring": False
    }

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        issues.append(f"Syntax error: {e}")
        return {"issues": issues, "stats": stats}

    # Check module docstring
    if ast.get_docstring(tree):
        stats["has_docstring"] = True
    else:
        issues.append("Missing module docstring")

    # Analyze classes and functions
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if node.name.startswith("Test"):
                stats["test_classes"] += 1
                # Check test methods in class
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                        stats["test_functions"] += 1

        elif isinstance(node, ast.FunctionDef):
            if node.name.startswith("test_"):
                stats["test_functions"] += 1
            # Check for fixtures
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Attribute):
                    if decorator.attr == "fixture":
                        stats["fixtures"] += 1
                elif isinstance(decorator, ast.Name):
                    if decorator.id == "fixture":
                        stats["fixtures"] += 1

    # Validation checks
    if stats["test_functions"] == 0:
        issues.append("No test functions found")

    return {"issues": issues, "stats": stats}


def main():
    """Run validation on all test files"""
    test_dir = Path(__file__).parent
    test_files = [
        "test_reports.py",
        "test_exporters.py",
        "test_email.py",
        "test_scheduler.py"
    ]

    print("=" * 70)
    print("Analytics Test Suite Validation")
    print("=" * 70)
    print()

    all_issues = []
    total_stats = {
        "files": 0,
        "test_classes": 0,
        "test_functions": 0,
        "fixtures": 0
    }

    for test_file in test_files:
        file_path = test_dir / test_file
        if not file_path.exists():
            print(f"[FAIL] {test_file}: FILE NOT FOUND")
            all_issues.append(f"{test_file}: Missing")
            continue

        result = validate_test_file(file_path)
        issues = result["issues"]
        stats = result["stats"]

        # Update totals
        total_stats["files"] += 1
        total_stats["test_classes"] += stats["test_classes"]
        total_stats["test_functions"] += stats["test_functions"]
        total_stats["fixtures"] += stats["fixtures"]

        # Print results
        status = "PASS" if not issues else "WARN"
        print(f"[{status}] {test_file}")
        print(f"   Test Classes: {stats['test_classes']}")
        print(f"   Test Functions: {stats['test_functions']}")
        print(f"   Fixtures: {stats['fixtures']}")
        print(f"   Docstring: {'Yes' if stats['has_docstring'] else 'No'}")

        if issues:
            print(f"   Issues:")
            for issue in issues:
                print(f"     - {issue}")
            all_issues.extend([f"{test_file}: {i}" for i in issues])

        print()

    # Summary
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Total Files: {total_stats['files']}")
    print(f"Total Test Classes: {total_stats['test_classes']}")
    print(f"Total Test Functions: {total_stats['test_functions']}")
    print(f"Total Fixtures: {total_stats['fixtures']}")
    print()

    if all_issues:
        print(f"Issues Found: {len(all_issues)}")
        print("WARNING: Some tests have issues (see above)")
        return 1
    else:
        print("SUCCESS: All tests validated successfully!")

        # Check coverage target
        expected_min_tests = 50  # Minimum test functions for >70% coverage
        if total_stats["test_functions"] >= expected_min_tests:
            print(f"PASS: Test count ({total_stats['test_functions']}) meets coverage target")
        else:
            print(f"WARNING: Test count ({total_stats['test_functions']}) may be below coverage target ({expected_min_tests}+)")

        return 0


if __name__ == "__main__":
    sys.exit(main())
