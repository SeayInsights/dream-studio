"""PRD + Statement-of-Work scoring (WO P3+).

A derived, evidence-scored view over existing authority + docstore state — no new studio.db
tables. Governed by SPEC-0001 (docstore: specs/SPEC-0001-prd-sow-scoring.md) and ADR-0003.
"""

from core.prd.rescore import rescore_prd

__all__ = ["rescore_prd"]
