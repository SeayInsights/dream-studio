"""
Response Contracts Pattern Extractor

Detects response contract definitions that specify expected output format/schema.
These contracts ensure consistent, structured responses from LLMs.
"""

import re
from pathlib import Path
from typing import Dict, List


def extract(content: str, file_path: Path, repo: str) -> Dict:
    """
    Extract response contract pattern from SKILL.md content

    Args:
        content: Full content of SKILL.md file
        file_path: Path to SKILL.md file
        repo: Repository name

    Returns:
        Dictionary with pattern detection results:
        {
            'detected': bool,
            'contract_indicators': List[str],
            'schema_blocks': List[str]
        }
    """
    content_lower = content.lower()

    # Keywords indicating response contracts
    contract_keywords = [
        'response contract',
        'output contract',
        'output format',
        'response format',
        'expected output',
        'must return',
        'must respond with',
        'output schema',
        'response schema'
    ]

    # Find contract indicator phrases
    indicators = []
    for keyword in contract_keywords:
        if keyword in content_lower:
            indicators.append(keyword)

    # Extract schema-like code blocks (JSON, YAML, TypeScript interfaces)
    schema_patterns = [
        r'```(?:json|yaml|typescript|ts)\s*\n[\s\S]*?{[\s\S]*?}[\s\S]*?```',
        r'interface\s+\w+\s*{[^}]+}',
        r'type\s+\w+\s*=\s*{[^}]+}'
    ]

    schema_blocks = []
    for pattern in schema_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        schema_blocks.extend(matches)

    return {
        'detected': len(indicators) > 0 or len(schema_blocks) > 0,
        'contract_indicators': indicators,
        'schema_blocks': schema_blocks
    }


def extract_required_fields(schema_content: str) -> List[str]:
    """
    Extract required field names from a schema definition

    Args:
        schema_content: JSON/YAML/TypeScript schema content

    Returns:
        List of required field names
    """
    # Pattern: Look for field definitions like "field_name:" or "field_name:"
    field_pattern = r'["\']?(\w+)["\']?\s*:'
    fields = re.findall(field_pattern, schema_content)

    # Pattern: Look for "required" arrays in JSON Schema
    required_pattern = r'"required"\s*:\s*\[(.*?)\]'
    required_match = re.search(required_pattern, schema_content, re.DOTALL)

    if required_match:
        required_content = required_match.group(1)
        required_fields = re.findall(r'["\'](\w+)["\']', required_content)
        return required_fields

    # If no explicit "required" array, return all fields
    return list(set(fields))
