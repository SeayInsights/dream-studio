"""GitHub execution adapter - real branch/PR/patch operations.

UNIFIED (2026-05-07): Now emits decisions AND events to track execution flow.
"""

from __future__ import annotations
import subprocess
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime, timezone

from core.decisions import emit_decision
from core.events import emit_event
from core.events.types import EventType


@dataclass
class DiffStats:
    """Statistics about a code diff."""

    files_changed: int
    insertions: int
    deletions: int
    complexity_delta: float = 0.0  # Computed from diff analysis


@dataclass
class GitHubExecutionResult:
    """Result of a real GitHub execution."""

    action_id: str
    repo_path: str
    branch_name: str

    # Execution status
    status: str  # created | failed | unknown

    # GitHub operations
    commit_sha: Optional[str] = None
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None

    # Changes applied
    patch_applied: bool = False
    diff_stats: Optional[DiffStats] = None

    # Errors
    error_message: Optional[str] = None

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GitHubAdapter:
    """Execute repository actions as real GitHub operations.

    Uses `gh` CLI for GitHub operations and `git` for local operations.
    """

    def __init__(self, repo_path: str, remote: str = "origin"):
        self.repo_path = Path(repo_path)
        self.remote = remote
        self._validate_environment()

    def _validate_environment(self):
        """Validate that gh and git are available."""
        try:
            subprocess.run(["gh", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("gh CLI not found. Install: https://cli.github.com/")

        try:
            subprocess.run(["git", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("git not found. Install git.")

    def create_branch(self, branch_name: str, base_branch: str = "main") -> tuple[bool, str]:
        """Create a new Git branch.

        Args:
            branch_name: Name of branch to create
            base_branch: Base branch (default: main)

        Returns:
            (success, error_message)
        """
        try:
            # Fetch latest
            subprocess.run(
                ["git", "fetch", self.remote, base_branch],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            # Create and checkout branch
            subprocess.run(
                ["git", "checkout", "-b", branch_name, f"{self.remote}/{base_branch}"],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            return True, ""
        except subprocess.CalledProcessError as e:
            return False, f"Failed to create branch: {e.stderr.decode()}"

    def apply_patch(self, patch_content: str) -> tuple[bool, str]:
        """Apply a patch to the current branch.

        Args:
            patch_content: Git patch content

        Returns:
            (success, error_message)
        """
        try:
            result = subprocess.run(
                ["git", "apply", "-"],
                input=patch_content.encode(),
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )
            return True, ""
        except subprocess.CalledProcessError as e:
            return False, f"Failed to apply patch: {e.stderr.decode()}"

    def commit_changes(
        self, message: str, file_paths: Optional[List[str]] = None
    ) -> tuple[bool, str, Optional[str]]:
        """Commit changes to current branch.

        Args:
            message: Commit message
            file_paths: Specific files to commit (None = commit all)

        Returns:
            (success, error_message, commit_sha)
        """
        try:
            # Stage files
            if file_paths:
                for path in file_paths:
                    subprocess.run(
                        ["git", "add", path], cwd=self.repo_path, capture_output=True, check=True
                    )
            else:
                subprocess.run(
                    ["git", "add", "-A"], cwd=self.repo_path, capture_output=True, check=True
                )

            # Commit
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            # Get commit SHA
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
                text=True,
            )
            commit_sha = result.stdout.strip()

            return True, "", commit_sha
        except subprocess.CalledProcessError as e:
            return False, f"Failed to commit: {e.stderr.decode()}", None

    def push_branch(self, branch_name: str) -> tuple[bool, str]:
        """Push branch to remote.

        Args:
            branch_name: Branch to push

        Returns:
            (success, error_message)
        """
        try:
            subprocess.run(
                ["git", "push", "-u", self.remote, branch_name],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )
            return True, ""
        except subprocess.CalledProcessError as e:
            return False, f"Failed to push: {e.stderr.decode()}"

    def open_pull_request(
        self, title: str, body: str, base_branch: str = "main"
    ) -> tuple[bool, str, Optional[int], Optional[str]]:
        """Open a pull request using gh CLI.

        Args:
            title: PR title
            body: PR description
            base_branch: Base branch (default: main)

        Returns:
            (success, error_message, pr_number, pr_url)
        """
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--title",
                    title,
                    "--body",
                    body,
                    "--base",
                    base_branch,
                    "--json",
                    "number,url",
                ],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
                text=True,
            )

            data = json.loads(result.stdout)
            pr_number = data.get("number")
            pr_url = data.get("url")

            return True, "", pr_number, pr_url
        except subprocess.CalledProcessError as e:
            return False, f"Failed to create PR: {e.stderr.decode()}", None, None
        except json.JSONDecodeError:
            return False, "Failed to parse PR response", None, None

    def fetch_ci_status(self, pr_number: int) -> tuple[bool, str, Optional[Dict]]:
        """Fetch CI status for a PR.

        Args:
            pr_number: PR number

        Returns:
            (success, error_message, ci_data)

        ci_data format:
        {
            "status": "pending | success | failure",
            "checks": [
                {"name": str, "status": str, "conclusion": str}
            ]
        }
        """
        try:
            result = subprocess.run(
                ["gh", "pr", "checks", str(pr_number), "--json", "name,status,conclusion"],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
                text=True,
            )

            checks = json.loads(result.stdout)

            # Determine overall status
            if not checks:
                status = "pending"
            elif all(c.get("conclusion") == "success" for c in checks):
                status = "success"
            elif any(c.get("conclusion") == "failure" for c in checks):
                status = "failure"
            else:
                status = "pending"

            ci_data = {"status": status, "checks": checks}

            return True, "", ci_data
        except subprocess.CalledProcessError as e:
            return False, f"Failed to fetch CI status: {e.stderr.decode()}", None
        except json.JSONDecodeError:
            return False, "Failed to parse CI response", None

    def fetch_diff_stats(
        self, branch_name: str, base_branch: str = "main"
    ) -> tuple[bool, str, Optional[DiffStats]]:
        """Fetch diff statistics.

        Args:
            branch_name: Feature branch
            base_branch: Base branch

        Returns:
            (success, error_message, diff_stats)
        """
        try:
            result = subprocess.run(
                ["git", "diff", "--shortstat", f"{self.remote}/{base_branch}...{branch_name}"],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
                text=True,
            )

            # Parse shortstat: "3 files changed, 45 insertions(+), 12 deletions(-)"
            output = result.stdout.strip()
            files_changed = 0
            insertions = 0
            deletions = 0

            if "file" in output:
                parts = output.split(",")
                for part in parts:
                    part = part.strip()
                    if "file" in part:
                        files_changed = int(part.split()[0])
                    elif "insertion" in part:
                        insertions = int(part.split()[0])
                    elif "deletion" in part:
                        deletions = int(part.split()[0])

            stats = DiffStats(
                files_changed=files_changed, insertions=insertions, deletions=deletions
            )

            return True, "", stats
        except subprocess.CalledProcessError as e:
            return False, f"Failed to fetch diff stats: {e.stderr.decode()}", None

    def execute_action(
        self,
        action_id: str,
        branch_name: str,
        patch_content: str,
        commit_message: str,
        pr_title: str,
        pr_body: str,
        base_branch: str = "main",
    ) -> GitHubExecutionResult:
        """Execute a complete action: branch → patch → commit → push → PR.

        Args:
            action_id: Action identifier
            branch_name: Branch name
            patch_content: Patch to apply
            commit_message: Commit message
            pr_title: PR title
            pr_body: PR description
            base_branch: Base branch

        Returns:
            GitHubExecutionResult
        """
        # Decision: Starting execution
        emit_decision(
            decision_type="execution.action_start",
            context={
                "action_id": action_id,
                "branch_name": branch_name,
                "repo_path": str(self.repo_path),
                "base_branch": base_branch,
            },
            outcome={"status": "approved"},
            reasoning={"rationale": f"Executing action {action_id} on branch {branch_name}"},
            confidence=1.0,
            policy_applied="AUTO",
            source_subsystem="execution.github_adapter",
        )

        result = GitHubExecutionResult(
            action_id=action_id,
            repo_path=str(self.repo_path),
            branch_name=branch_name,
            status="failed",
        )

        # 1. Create branch
        success, error = self.create_branch(branch_name, base_branch)
        if not success:
            result.error_message = error
            return result

        # 2. Apply patch
        success, error = self.apply_patch(patch_content)
        if not success:
            result.error_message = error
            return result

        result.patch_applied = True

        # 3. Commit
        success, error, commit_sha = self.commit_changes(commit_message)
        if not success:
            result.error_message = error
            return result

        result.commit_sha = commit_sha

        # 4. Push
        success, error = self.push_branch(branch_name)
        if not success:
            result.error_message = error
            return result

        # 5. Get diff stats
        success, error, diff_stats = self.fetch_diff_stats(branch_name, base_branch)
        if success:
            result.diff_stats = diff_stats

        # 6. Open PR
        success, error, pr_number, pr_url = self.open_pull_request(pr_title, pr_body, base_branch)
        if not success:
            result.error_message = error
            return result

        result.pr_number = pr_number
        result.pr_url = pr_url
        result.status = "created"

        # Decision: Execution completed successfully
        emit_decision(
            decision_type="execution.action_complete",
            context={
                "action_id": action_id,
                "branch_name": branch_name,
                "pr_number": pr_number,
                "pr_url": pr_url,
            },
            outcome={
                "status": "success",
                "commit_sha": commit_sha,
                "files_changed": diff_stats.files_changed if diff_stats else 0,
                "insertions": diff_stats.insertions if diff_stats else 0,
                "deletions": diff_stats.deletions if diff_stats else 0,
            },
            reasoning={"rationale": f"Successfully created PR #{pr_number} for action {action_id}"},
            confidence=1.0,
            policy_applied="AUTO",
            source_subsystem="execution.github_adapter",
        )

        # Event: For analytics consumption
        emit_event(
            event_type=EventType.EXECUTION_COMPLETE,
            payload={
                "action_id": action_id,
                "branch_name": branch_name,
                "pr_number": pr_number,
                "pr_url": pr_url,
                "commit_sha": commit_sha,
                "files_changed": diff_stats.files_changed if diff_stats else 0,
                "status": "success",
            },
        )

        return result
