#!/usr/bin/env python3
"""
Automated Repository Analysis Wrapper

Handles GitHub URL cloning, local path validation, and repo-analyzer invocation.
Simplifies the repo analysis workflow by auto-detecting URLs vs paths.

Usage:
    python analyze-repos.py <repo1> <repo2> ... [--compare] [--verbose]
    python analyze-repos.py https://github.com/user/repo1 /path/to/repo2 --compare

Args:
    repo1, repo2, ...: GitHub URLs or local paths
    --compare: Generate comparison report (default: single repo analysis)
    --verbose: Print detailed progress
    --format: Output format (dict, json, markdown) - default: markdown
"""

import sys
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import List, Tuple, Optional
import argparse

# Add parent directories to path for imports
repo_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(repo_root))

# Import from relative path
repo_analyzer_path = repo_root / "skills" / "analyze"
sys.path.insert(0, str(repo_analyzer_path))

from repo_analyzer import analyze_repositories


def is_github_url(input_str: str) -> bool:
    """Check if input is a GitHub URL"""
    return input_str.startswith(('http://', 'https://')) and 'github.com' in input_str


def clone_repo(url: str, temp_dir: Path, verbose: bool = False) -> Path:
    """
    Clone a GitHub repository to temp directory

    Args:
        url: GitHub repository URL
        temp_dir: Temporary directory for cloning
        verbose: Print clone progress

    Returns:
        Path to cloned repository
    """
    # Extract repo name from URL
    repo_name = url.rstrip('/').split('/')[-1].replace('.git', '')
    clone_path = temp_dir / repo_name

    if verbose:
        print(f"[CLONE] Cloning {url} to {clone_path}...")

    try:
        subprocess.run(
            ['git', 'clone', url, str(clone_path)],
            check=True,
            capture_output=not verbose,
            text=True
        )
        if verbose:
            print(f"[CLONE] ✓ Cloned to {clone_path}")
        return clone_path
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to clone {url}: {e}", file=sys.stderr)
        sys.exit(1)


def prepare_repos(inputs: List[str], verbose: bool = False) -> Tuple[List[str], Optional[Path]]:
    """
    Prepare repositories for analysis (clone URLs, validate paths)

    Args:
        inputs: List of GitHub URLs or local paths
        verbose: Print preparation progress

    Returns:
        Tuple of (list of repo paths, temp directory if created)
    """
    repo_paths = []
    temp_dir = None

    for item in inputs:
        if is_github_url(item):
            # Create temp directory on first URL encountered
            if temp_dir is None:
                temp_dir = Path(tempfile.mkdtemp(prefix='repo-analysis-'))
                if verbose:
                    print(f"[TEMP] Created temp directory: {temp_dir}")

            # Clone the repository
            cloned_path = clone_repo(item, temp_dir, verbose)
            repo_paths.append(str(cloned_path))
        else:
            # Validate local path
            local_path = Path(item).resolve()
            if not local_path.exists():
                print(f"[ERROR] Path does not exist: {item}", file=sys.stderr)
                sys.exit(1)
            if not local_path.is_dir():
                print(f"[ERROR] Not a directory: {item}", file=sys.stderr)
                sys.exit(1)

            repo_paths.append(str(local_path))
            if verbose:
                print(f"[LOCAL] Using local path: {local_path}")

    return repo_paths, temp_dir


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Automated repository pattern analysis with GitHub URL cloning support',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze single local repo
  python analyze-repos.py /path/to/repo

  # Analyze single GitHub repo
  python analyze-repos.py https://github.com/user/repo

  # Compare multiple repos (URLs and local paths)
  python analyze-repos.py https://github.com/user/repo1 /path/to/repo2 --compare

  # Verbose output with JSON format
  python analyze-repos.py https://github.com/user/repo --verbose --format json
        """
    )

    parser.add_argument(
        'repos',
        nargs='+',
        help='GitHub URLs or local repository paths'
    )
    parser.add_argument(
        '--compare',
        action='store_true',
        help='Generate comparison report (for 2+ repos)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print detailed progress'
    )
    parser.add_argument(
        '--format',
        choices=['dict', 'json', 'markdown'],
        default='markdown',
        help='Output format (default: markdown)'
    )

    args = parser.parse_args()

    # Validate inputs
    if len(args.repos) == 0:
        parser.print_help()
        sys.exit(1)

    if args.compare and len(args.repos) < 2:
        print("[ERROR] --compare requires at least 2 repositories", file=sys.stderr)
        sys.exit(1)

    try:
        # Prepare repositories (clone URLs, validate paths)
        repo_paths, temp_dir = prepare_repos(args.repos, args.verbose)

        if args.verbose:
            print(f"\n[ANALYZE] Starting analysis of {len(repo_paths)} repositories...")

        # Run analysis
        result = analyze_repositories(
            repo_paths=repo_paths,
            output_format=args.format,
            verbose=args.verbose
        )

        # Print result
        if args.format in ['json', 'markdown']:
            print(result)
        else:
            # For dict format, print summary
            print("\n=== ANALYSIS SUMMARY ===")
            if 'summary' in result:
                for key, value in result['summary'].items():
                    print(f"{key}: {value}")

        if args.verbose:
            print("\n[DONE] Analysis complete!")

    except KeyboardInterrupt:
        print("\n[ABORT] Analysis interrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n[ERROR] Analysis failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup temp directory if created
        if temp_dir and temp_dir.exists():
            if args.verbose:
                print(f"[CLEANUP] Removing temp directory: {temp_dir}")
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
