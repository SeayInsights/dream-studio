"""Contract registry schema constants and doc/artifact patterns.

WO-GF-SHARED-INTEL-SPLIT: extracted from contract_registry.py.
"""

from __future__ import annotations

CONTRACT_REGISTRY_SCHEMA = "dream_studio.contract_registry.v1"
DOC_DRIFT_GATE_SCHEMA = "dream_studio.contract_docs_drift_gate.v1"

PRD_DOC = "docs/product/dream-studio-prd.md"
README_DOC = "README.md"
PUBLICATION_BOUNDARY_DOC = "docs/PUBLICATION_BOUNDARY.md"
CONTRACT_ATLAS_DOC = "docs/architecture/contract-atlas.md"

PRIVATE_ARTIFACT_PATTERNS: tuple[str, ...] = (
    ".dream-studio/**",
    "**/.dream-studio/**",
    "**/*.db",
    "**/*.sqlite",
    "**/*.sqlite3",
    "**/*-wal",
    "**/*-shm",
    "**/backups/**",
    "**/meta/work-orders/**",
    "**/meta/audit/**",
    "**/raw_telemetry/**",
    "**/operator_decisions/**",
)

PUBLICATION_RISK_PATTERNS: tuple[str, ...] = (
    "README.md",
    "LICENSE",
    "docs/**",
    ".github/**",
    "adapter-projections/**",
)
