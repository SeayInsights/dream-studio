"""Adapter interfaces for dream-studio events."""

from interfaces.adapters.base import BaseAdapter
from interfaces.adapters.claude_adapter import ClaudeAdapter
from interfaces.adapters.normalizer import EventNormalizer

__all__ = ["BaseAdapter", "ClaudeAdapter", "EventNormalizer"]
