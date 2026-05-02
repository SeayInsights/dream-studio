"""
CI/CD Patterns Extractor

Detects continuous integration and deployment patterns, workflows, and automation.
Helps identify CI/CD maturity and deployment strategies across repositories.
"""

import re
import yaml
from pathlib import Path
from typing import Dict, List


def extract(content: str, file_path: Path, repo: str) -> Dict:
    """
    Extract CI/CD pattern references from SKILL.md content

    Args:
        content: Full content of SKILL.md file
        file_path: Path to SKILL.md file
        repo: Repository name

    Returns:
        Dictionary with pattern detection results:
        {
            'detected': bool,
            'cicd_mentions': int,
            'platforms': List[str],
            'deployment_types': List[str]
        }
    """
    content_lower = content.lower()

    # CI/CD platform detection
    platforms = []
    platform_patterns = [
        'github actions', 'gitlab ci', 'circleci', 'jenkins', 'travis ci',
        'azure pipelines', 'bitbucket pipelines', 'drone', 'buildkite',
        'teamcity', 'bamboo', 'codeship', 'semaphore'
    ]

    for platform in platform_patterns:
        if platform in content_lower:
            platforms.append(platform)

    # Deployment type detection
    deployment_types = []
    deployment_patterns = {
        'continuous deployment': r'\bcontinuous deployment\b',
        'continuous delivery': r'\bcontinuous delivery\b',
        'blue-green': r'\b(blue-green|blue/green)\b',
        'canary': r'\bcanary\s+(deployment|release)',
        'rolling': r'\brolling\s+(deployment|update)',
        'feature flags': r'\b(feature flag|feature toggle)',
        'automated rollback': r'\b(automated? rollback|auto-rollback)'
    }

    for deploy_type, pattern in deployment_patterns.items():
        if re.search(pattern, content_lower):
            deployment_types.append(deploy_type)

    # Count CI/CD mentions
    cicd_keywords = ['ci/cd', 'pipeline', 'workflow', 'automation', 'deploy']
    cicd_mentions = sum(content_lower.count(kw) for kw in cicd_keywords)

    return {
        'detected': len(platforms) > 0 or len(deployment_types) > 0,
        'cicd_mentions': cicd_mentions,
        'platforms': platforms,
        'deployment_types': deployment_types
    }


def analyze_workflow_files(repo_path: Path) -> Dict:
    """
    Analyze CI/CD workflow configuration files in repository

    Args:
        repo_path: Path to repository root

    Returns:
        Dictionary with workflow file analysis:
        {
            'has_github_actions': bool,
            'has_gitlab_ci': bool,
            'has_circleci': bool,
            'workflow_files': List[str],
            'workflow_count': int
        }
    """
    workflows = []

    # GitHub Actions
    github_workflows_dir = repo_path / '.github' / 'workflows'
    has_github_actions = False
    if github_workflows_dir.exists():
        workflow_files = list(github_workflows_dir.glob('*.yml')) + list(github_workflows_dir.glob('*.yaml'))
        if workflow_files:
            has_github_actions = True
            workflows.extend([f.name for f in workflow_files])

    # GitLab CI
    gitlab_ci_file = repo_path / '.gitlab-ci.yml'
    has_gitlab_ci = gitlab_ci_file.exists()
    if has_gitlab_ci:
        workflows.append('.gitlab-ci.yml')

    # CircleCI
    circleci_config = repo_path / '.circleci' / 'config.yml'
    has_circleci = circleci_config.exists()
    if has_circleci:
        workflows.append('.circleci/config.yml')

    # Travis CI
    travis_config = repo_path / '.travis.yml'
    if travis_config.exists():
        workflows.append('.travis.yml')

    # Jenkins
    jenkinsfile = repo_path / 'Jenkinsfile'
    if jenkinsfile.exists():
        workflows.append('Jenkinsfile')

    return {
        'has_github_actions': has_github_actions,
        'has_gitlab_ci': has_gitlab_ci,
        'has_circleci': has_circleci,
        'workflow_files': workflows,
        'workflow_count': len(workflows)
    }


def parse_github_workflow(workflow_path: Path) -> Dict:
    """
    Parse GitHub Actions workflow file

    Args:
        workflow_path: Path to workflow YAML file

    Returns:
        Dictionary with workflow details:
        {
            'name': str,
            'triggers': List[str],
            'jobs': List[str],
            'uses_actions': List[str]
        }
    """
    try:
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow_data = yaml.safe_load(f)

        if not workflow_data:
            return {}

        # Extract workflow name
        name = workflow_data.get('name', workflow_path.stem)

        # Extract triggers (on: push, pull_request, etc.)
        triggers = []
        if 'on' in workflow_data:
            on_data = workflow_data['on']
            if isinstance(on_data, dict):
                triggers = list(on_data.keys())
            elif isinstance(on_data, list):
                triggers = on_data
            elif isinstance(on_data, str):
                triggers = [on_data]

        # Extract job names
        jobs = list(workflow_data.get('jobs', {}).keys())

        # Extract actions used (uses: owner/repo@version)
        uses_actions = []
        for job_name, job_data in workflow_data.get('jobs', {}).items():
            if isinstance(job_data, dict) and 'steps' in job_data:
                for step in job_data['steps']:
                    if isinstance(step, dict) and 'uses' in step:
                        uses_actions.append(step['uses'])

        return {
            'name': name,
            'triggers': triggers,
            'jobs': jobs,
            'uses_actions': uses_actions
        }

    except (yaml.YAMLError, FileNotFoundError, IOError):
        return {}
