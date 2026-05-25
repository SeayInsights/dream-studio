"""Organization-level engineering intelligence graph.

Deterministic, model-agnostic multi-repository analysis.
NO LLM dependencies. NO synthetic scoring. Fully traceable.
"""

from .model import Repository, Module, Capability, Edge, OrganizationGraph
from .ingestor import MultiRepoIngestor
from .normalizer import CapabilityNormalizer
from .graph_builder import OrganizationGraphBuilder
from .cross_repo_analyzer import CrossRepoAnalyzer
from .insight_engine import RoleBasedInsightEngine

__all__ = [
    "Repository",
    "Module",
    "Capability",
    "Edge",
    "OrganizationGraph",
    "MultiRepoIngestor",
    "CapabilityNormalizer",
    "OrganizationGraphBuilder",
    "CrossRepoAnalyzer",
    "RoleBasedInsightEngine",
]
