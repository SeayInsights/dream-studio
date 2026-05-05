#!/usr/bin/env python3
"""Check analyzed repos for updates.

Queries the reg_analyzed_repos table for repos with check_for_updates=1 and
status='active', fetches the latest commit SHA from GitHub, and updates the
database if changed.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

# Add hooks to path for database access
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
from lib.studio_db import _connect  # noqa: E402
from lib.repo_analyzer import analyze_repo  # noqa: E402

_NOW = lambda: datetime.now(timezone.utc).isoformat()


def parse_github_url(url: str) -> tuple[str, str] | None:
    """Extract owner and repo name from GitHub URL.

    Args:
        url: GitHub repository URL (https://github.com/owner/repo or git@github.com:owner/repo.git)

    Returns:
        Tuple of (owner, repo) or None if not a valid GitHub URL
    """
    # Remove .git suffix if present
    url = url.rstrip("/").removesuffix(".git")

    # Handle HTTPS URLs
    if url.startswith("https://github.com/") or url.startswith("http://github.com/"):
        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            return (parts[0], parts[1])

    # Handle SSH URLs (git@github.com:owner/repo)
    if url.startswith("git@github.com:"):
        path = url.split(":", 1)[1]
        parts = path.split("/")
        if len(parts) >= 2:
            return (parts[0], parts[1])

    return None


def get_latest_commit_sha(repo_url: str, verbose: bool = False) -> str | None:
    """Get latest commit SHA from GitHub API.

    Args:
        repo_url: GitHub repository URL
        verbose: Print detailed output

    Returns:
        Latest commit SHA or None if error
    """
    parsed = parse_github_url(repo_url)
    if not parsed:
        if verbose:
            print(f"  [!] Could not parse GitHub URL: {repo_url}")
        return None

    owner, repo = parsed
    api_url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=1"

    try:
        # Use minimal headers to avoid rate limit issues
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "dream-studio-repo-checker"
        }

        response = requests.get(api_url, headers=headers, timeout=10)

        if response.status_code == 404:
            if verbose:
                print(f"  [!] Repository not found: {owner}/{repo}")
            return None

        if response.status_code == 403:
            # Rate limit hit
            if verbose:
                print(f"  [!] GitHub API rate limit exceeded")
            return None

        response.raise_for_status()

        commits = response.json()
        if commits and len(commits) > 0:
            sha = commits[0]["sha"]
            if verbose:
                print(f"  [OK] Latest commit: {sha[:8]}")
            return sha

        return None

    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  [!] API error for {owner}/{repo}: {e}")
        return None


def main() -> int:
    """Main entry point.

    Returns:
        Exit code: 0 if no updates, 1 if updates found
    """
    parser = argparse.ArgumentParser(
        description="Check analyzed repos for updates"
    )
    parser.add_argument(
        "--reanalyze-high-trust",
        action="store_true",
        help="Auto-queue high-trust repos (trust_score >= 0.9) for re-analysis"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed output"
    )
    args = parser.parse_args()

    # Connect to database
    try:
        conn = _connect()
    except Exception as e:
        print(f"Error connecting to database: {e}", file=sys.stderr)
        return 1

    # Query repos to check
    try:
        cursor = conn.execute(
            """SELECT repo_id, repo_url, repo_name, last_commit_sha, trust_score
               FROM reg_analyzed_repos
               WHERE check_for_updates = 1 AND status = 'active'
               ORDER BY repo_name"""
        )
        repos = cursor.fetchall()
    except Exception as e:
        print(f"Error querying database: {e}", file=sys.stderr)
        conn.close()
        return 1

    if not repos:
        print("No active repos configured for update checking.")
        conn.close()
        return 0

    if args.verbose:
        print(f"Checking {len(repos)} repos for updates...\n")

    updates_found = []
    errors = []

    for repo in repos:
        repo_id = repo["repo_id"]
        repo_url = repo["repo_url"]
        repo_name = repo["repo_name"]
        old_sha = repo["last_commit_sha"]
        trust_score = repo["trust_score"]

        if args.verbose:
            print(f"Checking {repo_name}...")

        # Fetch latest commit SHA
        new_sha = get_latest_commit_sha(repo_url, args.verbose)

        if new_sha is None:
            errors.append(repo_name)
            continue

        # Update last_update_check timestamp
        try:
            conn.execute(
                """UPDATE reg_analyzed_repos
                   SET last_update_check = ?
                   WHERE repo_id = ?""",
                (_NOW(), repo_id)
            )
            conn.commit()
        except Exception as e:
            if args.verbose:
                print(f"  [!] Error updating timestamp: {e}")

        # Check if SHA changed
        if old_sha and new_sha != old_sha:
            updates_found.append({
                "repo_id": repo_id,
                "repo_name": repo_name,
                "old_sha": old_sha,
                "new_sha": new_sha,
                "trust_score": trust_score
            })

            # Update last_commit_sha
            try:
                conn.execute(
                    """UPDATE reg_analyzed_repos
                       SET last_commit_sha = ?
                       WHERE repo_id = ?""",
                    (new_sha, repo_id)
                )
                conn.commit()

                if args.verbose:
                    print(f"  [UPDATE] Updated SHA: {old_sha[:8]} -> {new_sha[:8]}")
            except Exception as e:
                if args.verbose:
                    print(f"  [!] Error updating SHA: {e}")
        elif old_sha is None:
            # First time checking this repo
            try:
                conn.execute(
                    """UPDATE reg_analyzed_repos
                       SET last_commit_sha = ?
                       WHERE repo_id = ?""",
                    (new_sha, repo_id)
                )
                conn.commit()

                if args.verbose:
                    print(f"  [OK] Initialized SHA: {new_sha[:8]}")
            except Exception as e:
                if args.verbose:
                    print(f"  [!] Error initializing SHA: {e}")
        elif args.verbose:
            print(f"  [OK] No changes")

        if args.verbose:
            print()

    conn.close()

    # Print summary
    if updates_found:
        print(f"\nFound {len(updates_found)} repos with updates:")
        for update in updates_found:
            print(f"  * {update['repo_name']}")
            print(f"    {update['old_sha'][:8]} -> {update['new_sha'][:8]}")

            # Check if high-trust and should be queued for re-analysis
            if args.reanalyze_high_trust and update['trust_score'] is not None and update['trust_score'] >= 0.9:
                print(f"    (High-trust repo, queued for re-analysis)")
                try:
                    # Re-analyze the repo to extract updated patterns/blocks
                    result = analyze_repo(update['repo_name'], shallow=True)
                    print(f"    Re-analysis complete: {result['patterns_count']} patterns, {result['building_blocks_count']} blocks")
                except Exception as e:
                    print(f"    [!] Re-analysis failed: {e}")

        if errors:
            print(f"\nErrors checking {len(errors)} repos:")
            for error in errors:
                print(f"  * {error}")

        return 1  # Exit code 1 indicates updates found
    else:
        if args.verbose:
            print("All repos are up to date.")
        else:
            print("No updates found.")

        if errors:
            print(f"\nErrors checking {len(errors)} repos:")
            for error in errors:
                print(f"  * {error}")

        return 0


if __name__ == "__main__":
    sys.exit(main())
