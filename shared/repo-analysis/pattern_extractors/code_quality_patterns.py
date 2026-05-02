"""
Code Quality Patterns Extractor

Detects code quality tools, linting configurations, and formatting standards.
Helps identify code quality enforcement across repositories.
"""

import re
from pathlib import Path
from typing import Dict, List


def extract(content: str, file_path: Path, repo: str) -> Dict:
    """
    Extract code quality pattern indicators from SKILL.md content

    Args:
        content: Full content of SKILL.md file
        file_path: Path to SKILL.md file
        repo: Repository name

    Returns:
        Dictionary with pattern detection results:
        {
            'detected': bool,
            'quality_tools': List[str],
            'has_pre_commit': bool,
            'has_type_checking': bool
        }
    """
    content_lower = content.lower()

    # Quality tool detection
    quality_tools = []
    tool_patterns = [
        # Linters
        'eslint', 'pylint', 'flake8', 'black', 'ruff', 'golangci-lint',
        'rubocop', 'clippy', 'shellcheck', 'yamllint',
        # Formatters
        'prettier', 'autopep8', 'gofmt', 'rustfmt', 'clang-format',
        # Type checkers
        'mypy', 'pyright', 'typescript', 'flow', 'sorbet',
        # Static analysis
        'sonarqube', 'codeclimate', 'codeql', 'semgrep', 'bandit'
    ]

    for tool in tool_patterns:
        if tool in content_lower:
            quality_tools.append(tool)

    # Pre-commit hook detection
    has_pre_commit = 'pre-commit' in content_lower or 'pre_commit' in content_lower

    # Type checking detection
    type_keywords = ['type checking', 'type hints', 'type safety', 'static typing']
    has_type_checking = any(kw in content_lower for kw in type_keywords)

    return {
        'detected': len(quality_tools) > 0 or has_pre_commit,
        'quality_tools': quality_tools,
        'has_pre_commit': has_pre_commit,
        'has_type_checking': has_type_checking
    }


def analyze_quality_configs(repo_path: Path) -> Dict:
    """
    Analyze code quality configuration files in repository

    Args:
        repo_path: Path to repository root

    Returns:
        Dictionary with config file analysis:
        {
            'config_files': List[str],
            'linters': List[str],
            'formatters': List[str],
            'has_editorconfig': bool
        }
    """
    config_files = []
    linters = []
    formatters = []

    # Linter configs
    linter_configs = {
        '.eslintrc.js': 'eslint',
        '.eslintrc.json': 'eslint',
        '.eslintrc.yml': 'eslint',
        '.pylintrc': 'pylint',
        'pyproject.toml': 'ruff/black',
        '.flake8': 'flake8',
        '.golangci.yml': 'golangci-lint',
        '.rubocop.yml': 'rubocop',
        'clippy.toml': 'clippy'
    }

    for config_file, linter in linter_configs.items():
        if (repo_path / config_file).exists():
            config_files.append(config_file)
            linters.append(linter)

    # Formatter configs
    formatter_configs = {
        '.prettierrc': 'prettier',
        '.prettierrc.js': 'prettier',
        'prettier.config.js': 'prettier',
        '.rustfmt.toml': 'rustfmt',
        '.clang-format': 'clang-format'
    }

    for config_file, formatter in formatter_configs.items():
        if (repo_path / config_file).exists():
            config_files.append(config_file)
            formatters.append(formatter)

    # EditorConfig
    has_editorconfig = (repo_path / '.editorconfig').exists()
    if has_editorconfig:
        config_files.append('.editorconfig')

    # Pre-commit
    has_pre_commit_config = (repo_path / '.pre-commit-config.yaml').exists()
    if has_pre_commit_config:
        config_files.append('.pre-commit-config.yaml')

    return {
        'config_files': config_files,
        'linters': list(set(linters)),
        'formatters': list(set(formatters)),
        'has_editorconfig': has_editorconfig,
        'has_pre_commit': has_pre_commit_config
    }


def analyze_type_checking(repo_path: Path) -> Dict:
    """
    Analyze type checking configuration

    Args:
        repo_path: Path to repository root

    Returns:
        Dictionary with type checking analysis:
        {
            'has_type_checking': bool,
            'type_checkers': List[str],
            'config_files': List[str]
        }
    """
    type_checkers = []
    config_files = []

    # TypeScript
    tsconfig = repo_path / 'tsconfig.json'
    if tsconfig.exists():
        type_checkers.append('typescript')
        config_files.append('tsconfig.json')

    # Python type checkers
    mypy_ini = repo_path / 'mypy.ini'
    if mypy_ini.exists():
        type_checkers.append('mypy')
        config_files.append('mypy.ini')

    pyright_config = repo_path / 'pyrightconfig.json'
    if pyright_config.exists():
        type_checkers.append('pyright')
        config_files.append('pyrightconfig.json')

    # Check pyproject.toml for type checker configs
    pyproject = repo_path / 'pyproject.toml'
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding='utf-8', errors='ignore')
            if '[tool.mypy]' in content:
                if 'mypy' not in type_checkers:
                    type_checkers.append('mypy')
                if 'pyproject.toml' not in config_files:
                    config_files.append('pyproject.toml')
            if '[tool.pyright]' in content:
                if 'pyright' not in type_checkers:
                    type_checkers.append('pyright')
                if 'pyproject.toml' not in config_files:
                    config_files.append('pyproject.toml')
        except (IOError, OSError):
            pass

    return {
        'has_type_checking': len(type_checkers) > 0,
        'type_checkers': type_checkers,
        'config_files': config_files
    }
