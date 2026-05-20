"""Workstream 2 gate: interfaces/adapters/ retirement assertions."""

from __future__ import annotations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OLD_ADAPTERS = REPO_ROOT / "interfaces" / "adapters"
CORE_ADAPTERS = REPO_ROOT / "core" / "adapters"


def test_interfaces_adapters_dir_removed():
    assert not OLD_ADAPTERS.exists(), "interfaces/adapters/ must not exist after Slice 4 retirement"


def test_core_adapters_dir_exists():
    assert CORE_ADAPTERS.is_dir(), "core/adapters/ must exist as the new adapter home"


def test_core_adapters_models_exists():
    assert (CORE_ADAPTERS / "models.py").is_file(), "core/adapters/models.py missing"


def test_core_adapters_normalizers_exists():
    assert (CORE_ADAPTERS / "normalizers.py").is_file(), "core/adapters/normalizers.py missing"


def test_core_adapters_init_exports_all_symbols():
    import importlib

    mod = importlib.import_module("core.adapters")
    for sym in (
        "BaseAdapter",
        "CanonicalEvent",
        "ClaudeAdapter",
        "DefaultAdapter",
        "EventNormalizer",
        "GPTAdapter",
        "SeverityLevel",
    ):
        assert hasattr(mod, sym), f"core.adapters missing export: {sym}"


def test_canonical_event_importable_from_core_adapters_models():
    from core.adapters.models import CanonicalEvent

    event = CanonicalEvent(event_type="test.event", entity_type="test", entity_id="id-1")
    assert event.event_type == "test.event"
    d = event.to_dict()
    assert d["event_type"] == "test.event"


def test_event_normalizer_routes_claude():
    from core.adapters.normalizers import ClaudeAdapter, EventNormalizer

    normalizer = EventNormalizer()
    normalizer.register_adapter("claude", ClaudeAdapter())
    raw = {
        "id": "msg_abc",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "hi"}],
        "model": "claude-sonnet-4-5",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    event = normalizer.normalize(raw, model_type="claude")
    assert event.event_type == "claude.message.completed"
    assert event.entity_id == "msg_abc"
    assert event.severity == "info"


def test_event_normalizer_falls_back_to_default():
    from core.adapters.normalizers import EventNormalizer

    normalizer = EventNormalizer()
    event = normalizer.normalize({"some": "data"}, model_type="unknown-model")
    assert event.event_type == "ai.completion.unknown"
    assert event.metadata["adapter"] == "default"


def test_gpt_adapter_normalizes():
    from core.adapters.normalizers import GPTAdapter

    adapter = GPTAdapter()
    raw = {
        "id": "chatcmpl-xyz",
        "object": "chat.completion",
        "model": "gpt-4",
        "choices": [{"message": {"content": "Hello"}}],
    }
    event = adapter.normalize(raw)
    assert event.event_type == "ai.completion.created"
    assert event.entity_id == "chatcmpl-xyz"


def test_studio_db_does_not_import_interfaces_adapters():
    studio_db = REPO_ROOT / "core" / "event_store" / "studio_db.py"
    source = studio_db.read_text(encoding="utf-8")
    assert (
        "from interfaces.adapters" not in source
    ), "core/event_store/studio_db.py still imports from interfaces.adapters"
    assert (
        "import interfaces.adapters" not in source
    ), "core/event_store/studio_db.py still imports from interfaces.adapters"


def test_engine_does_not_import_interfaces_adapters():
    engine = REPO_ROOT / "control" / "analysis" / "engine.py"
    source = engine.read_text(encoding="utf-8")
    assert (
        "from interfaces.adapters" not in source
    ), "control/analysis/engine.py still imports from interfaces.adapters"
