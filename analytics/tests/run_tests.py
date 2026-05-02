"""
Test runner for analytics test suite

Usage:
    python -m analytics.tests.run_tests
    python -m analytics.tests.run_tests --coverage
    python -m analytics.tests.run_tests --verbose
"""
import sys
import pytest
from pathlib import Path


def main():
    """Run analytics test suite"""
    test_dir = Path(__file__).parent

    # Default pytest args
    args = [
        str(test_dir),
        "-v",  # Verbose
        "--tb=short",  # Short traceback format
        "-ra",  # Show summary of all test outcomes
    ]

    # Check for coverage flag
    if "--coverage" in sys.argv:
        args.extend([
            "--cov=analytics",
            "--cov-report=html",
            "--cov-report=term-missing",
        ])
        print("Running with coverage analysis...")

    # Check for verbose flag
    if "--verbose" in sys.argv or "-vv" in sys.argv:
        args.remove("-v")
        args.append("-vv")

    # Run pytest
    print(f"Running tests from: {test_dir}")
    print(f"Arguments: {' '.join(args)}\n")

    exit_code = pytest.main(args)

    # Print summary
    print("\n" + "="*70)
    if exit_code == 0:
        print("✓ All tests passed!")
    else:
        print(f"✗ Tests failed with exit code {exit_code}")
    print("="*70)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
