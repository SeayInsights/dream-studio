"""Capability normalizer.

RULE-BASED normalization of raw module signals into unified capability ontology.
NO ML. NO heuristics. Explicit pattern matching only.
"""

from __future__ import annotations
from pathlib import Path

from .model import Module, Capability

# CANONICAL CAPABILITY ONTOLOGY (Explicit rules)
CAPABILITY_PATTERNS = {
    "knowledge_processing": {
        "patterns": ["research", "analysis", "engine", "analyzer", "processor"],
        "examples": ["research_engine", "analysis_engine", "knowledge_base"],
    },
    "compliance_system": {
        "patterns": ["guardrail", "evaluator", "validator", "compliance", "audit"],
        "examples": ["guardrails", "evaluator", "compliance_check"],
    },
    "decision_system": {
        "patterns": ["decision", "choice", "selector", "picker"],
        "examples": ["decision_log", "decision_engine", "choice_maker"],
    },
    "event_system": {
        "patterns": ["event", "emitter", "publisher", "subscriber"],
        "examples": ["event_store", "event_emitter", "event_bus"],
    },
    "storage_system": {
        "patterns": ["storage", "database", "store", "repository", "cache"],
        "examples": ["document_store", "cache", "database"],
    },
    "workflow_system": {
        "patterns": ["workflow", "orchestrator", "pipeline", "flow"],
        "examples": ["workflow_engine", "orchestrator", "pipeline"],
    },
    "skill_system": {
        "patterns": ["skill", "capability", "agent", "handler"],
        "examples": ["skill_router", "agent", "handler"],
    },
    "validation_system": {
        "patterns": ["validation", "checker", "verifier"],
        "examples": ["validator", "checker", "verifier"],
    },
    "web_interface": {
        "patterns": ["web", "api", "endpoint", "route", "server"],
        "examples": ["api", "web_server", "endpoint"],
    },
    "security_system": {
        "patterns": ["security", "auth", "permission", "access"],
        "examples": ["auth", "permission", "security"],
    },
    "llm_integration": {
        "patterns": ["llm", "openai", "anthropic", "claude", "gpt"],
        "examples": ["llm_client", "openai_api", "claude_integration"],
    },
    "reporting_system": {
        "patterns": ["report", "dashboard", "metrics", "analytics"],
        "examples": ["reporter", "dashboard", "analytics"],
    },
}


class CapabilityNormalizer:
    """Normalize modules into unified capability ontology.

    STRICT RULES:
    - Pattern matching only (no ML)
    - Deterministic (same input → same output)
    - Traceable (all tags justify their source pattern)
    """

    def __init__(self):
        self.capabilities: dict[str, Capability] = {}

    def normalize_modules(
        self, modules: dict[str, Module], repositories: dict[str, any]
    ) -> dict[str, Capability]:
        """Normalize modules into capabilities.

        Args:
            modules: Module dict
            repositories: Repository dict (for metadata)

        Returns:
            Capability dict
        """
        # Step 1: Tag modules with capability patterns
        for module in modules.values():
            module.capability_tags = self._tag_module(module)

        # Step 2: Group modules by capability
        capability_groups: dict[str, list[str]] = {}  # capability_name → module_ids

        for module_id, module in modules.items():
            for tag in module.capability_tags:
                if tag not in capability_groups:
                    capability_groups[tag] = []
                capability_groups[tag].append(module_id)

        # Step 3: Create capability nodes
        for cap_name, module_ids in capability_groups.items():
            if not module_ids:
                continue

            # Get source repositories
            source_repos = set(modules[mid].repo_id for mid in module_ids)

            # Compute metrics
            total_loc = sum(modules[mid].loc for mid in module_ids)
            avg_coupling = (
                sum(modules[mid].coupling_score for mid in module_ids) / len(module_ids)
                if module_ids
                else 0.0
            )

            capability = Capability(
                capability_id=f"cap:{cap_name}",
                normalized_name=cap_name,
                source_modules=module_ids,
                source_repos=source_repos,
                loc=total_loc,
                module_count=len(module_ids),
                coupling_score=avg_coupling,
                risk_score=0.0,  # Will be set by graph builder from decision signals
                reusability_score=0.0,  # Will be set by graph builder from usage edges
            )

            self.capabilities[capability.capability_id] = capability

        return self.capabilities

    def _tag_module(self, module: Module) -> list[str]:
        """Tag module with capability patterns.

        Args:
            module: Module to tag

        Returns:
            List of capability tags
        """
        tags = []

        # Extract searchable text from file path
        file_path_lower = module.file_path.lower()
        path_parts = Path(module.file_path).parts

        # Check each capability pattern
        for cap_name, cap_def in CAPABILITY_PATTERNS.items():
            patterns = cap_def["patterns"]

            # Check if any pattern matches
            for pattern in patterns:
                if pattern in file_path_lower:
                    tags.append(cap_name)
                    break  # One match per capability is enough

        # If no tags, assign "unclassified"
        if not tags:
            # Try to infer from directory structure
            if len(path_parts) > 1:
                # Use first directory as capability
                tags.append(f"module:{path_parts[0]}")
            else:
                tags.append("unclassified")

        return tags

    def get_capability_ontology(self) -> dict[str, dict]:
        """Get capability ontology as dict (for YAML export).

        Returns:
            Ontology dict
        """
        ontology = {"version": "1.0", "capabilities": {}}

        for cap_name, cap_def in CAPABILITY_PATTERNS.items():
            ontology["capabilities"][cap_name] = {
                "patterns": cap_def["patterns"],
                "examples": cap_def["examples"],
            }

        # Add discovered custom capabilities
        custom_caps = set()
        for cap in self.capabilities.values():
            if cap.normalized_name.startswith("module:"):
                custom_caps.add(cap.normalized_name)

        if custom_caps:
            ontology["custom_capabilities"] = list(custom_caps)

        return ontology
