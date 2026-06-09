"""Guardrail rule loader — converts YAML rule definitions to Pydantic models.

Loads *.yaml files from guardrails/rules/ directory, validates against schema,
and returns list of GuardrailRule objects ready for evaluation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from guardrails.models import GuardrailRule, RuleLoadError


def load_rules(rules_dir: Path) -> list[GuardrailRule]:
    """Load all guardrail rules from YAML files in rules_dir.

    Args:
        rules_dir: Directory containing *.yaml rule files

    Returns:
        List of validated GuardrailRule objects (empty list if dir doesn't exist)

    Raises:
        RuleLoadError: If YAML is malformed or validation fails critically
    """
    if not rules_dir.exists() or not rules_dir.is_dir():
        return []

    rules: list[GuardrailRule] = []
    yaml_files = sorted(rules_dir.glob("*.yaml"))

    # Filter out template files
    yaml_files = [f for f in yaml_files if not f.name.startswith("_")]

    for yaml_file in yaml_files:
        try:
            content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)

            # YAML file should contain a list of rules
            if not isinstance(data, list):
                data = [data]

            for rule_data in data:
                try:
                    rule = GuardrailRule(**rule_data)
                    rules.append(rule)
                except ValidationError as e:
                    print(
                        f"[guardrail-loader] WARNING: Invalid rule in {yaml_file.name}: {e}",
                        file=sys.stderr,
                    )
                    continue

        except yaml.YAMLError as e:
            print(
                f"[guardrail-loader] WARNING: Malformed YAML in {yaml_file.name}: {e}",
                file=sys.stderr,
            )
            continue
        except Exception as e:
            print(
                f"[guardrail-loader] WARNING: Failed to load {yaml_file.name}: {e}",
                file=sys.stderr,
            )
            continue

    return rules


def load_rules_strict(rules_dir: Path) -> list[GuardrailRule]:
    """Load rules with strict validation — any error raises RuleLoadError.

    Use this for initial validation or when rules MUST be correct.

    Args:
        rules_dir: Directory containing *.yaml rule files

    Returns:
        List of validated GuardrailRule objects

    Raises:
        RuleLoadError: If any YAML file is malformed or invalid
    """
    if not rules_dir.exists():
        raise RuleLoadError(f"Rules directory does not exist: {rules_dir}")

    if not rules_dir.is_dir():
        raise RuleLoadError(f"Rules path is not a directory: {rules_dir}")

    rules: list[GuardrailRule] = []
    yaml_files = sorted(rules_dir.glob("*.yaml"))
    yaml_files = [f for f in yaml_files if not f.name.startswith("_")]

    if not yaml_files:
        raise RuleLoadError(f"No rule files found in {rules_dir}")

    for yaml_file in yaml_files:
        try:
            content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)

            if not isinstance(data, list):
                data = [data]

            for rule_data in data:
                rule = GuardrailRule(**rule_data)
                rules.append(rule)

        except yaml.YAMLError as e:
            raise RuleLoadError(f"Malformed YAML in {yaml_file.name}: {e}") from e
        except ValidationError as e:
            raise RuleLoadError(f"Invalid rule in {yaml_file.name}: {e}") from e

    return rules
