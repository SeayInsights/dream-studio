"""
Example: EventNormalizer usage with multiple adapters.

Demonstrates:
1. Creating and registering adapters
2. Normalizing different model outputs
3. Fallback to DefaultAdapter
4. Integration with activity_log
"""

from interfaces.adapters.normalizer import EventNormalizer
from interfaces.adapters.base import BaseAdapter
from interfaces.adapters.models import CanonicalEvent, TraceContext


class ClaudeAdapter(BaseAdapter):
    """Example adapter for Claude API responses."""

    def normalize(self, raw_output: dict) -> CanonicalEvent:
        return CanonicalEvent(
            event_type="claude.completion",
            entity_type="model_completion",
            entity_id=raw_output.get("id", "unknown"),
            severity="info",
            payload={
                "model": raw_output.get("model", "claude-3"),
                "usage": raw_output.get("usage", {}),
                "content": raw_output.get("content", []),
            },
            trace=TraceContext(
                project_id="dream-studio",
                task_id=raw_output.get("task_id"),
            ),
            metadata={
                "adapter": "claude",
                "stop_reason": raw_output.get("stop_reason"),
            },
        )


class GPTAdapter(BaseAdapter):
    """Example adapter for OpenAI API responses."""

    def normalize(self, raw_output: dict) -> CanonicalEvent:
        return CanonicalEvent(
            event_type="gpt.completion",
            entity_type="model_completion",
            entity_id=raw_output.get("id", "unknown"),
            severity="info",
            payload={
                "model": raw_output.get("model", "gpt-4"),
                "choices": raw_output.get("choices", []),
                "usage": raw_output.get("usage", {}),
            },
            metadata={
                "adapter": "gpt",
                "finish_reason": raw_output.get("choices", [{}])[0].get("finish_reason"),
            },
        )


def main():
    """Demonstrate EventNormalizer usage."""

    # 1. Initialize normalizer
    normalizer = EventNormalizer()

    # 2. Register adapters
    normalizer.register_adapter("claude", ClaudeAdapter())
    normalizer.register_adapter("gpt", GPTAdapter())

    print("Registered models:", normalizer.get_registered_models())
    print()

    # 3. Normalize Claude output
    claude_raw = {
        "id": "msg_123",
        "model": "claude-sonnet-4",
        "content": [{"type": "text", "text": "Hello world"}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "stop_reason": "end_turn",
        "task_id": "task-456",
    }

    claude_event = normalizer.normalize(claude_raw, model_type="claude")
    print("Claude event:")
    print(f"  event_type: {claude_event.event_type}")
    print(f"  entity_id: {claude_event.entity_id}")
    print(f"  payload: {claude_event.payload}")
    print(f"  metadata: {claude_event.metadata}")
    print()

    # 4. Normalize GPT output
    gpt_raw = {
        "id": "chatcmpl-789",
        "model": "gpt-4-turbo",
        "choices": [{"message": {"content": "Hello world"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 15, "completion_tokens": 8},
    }

    gpt_event = normalizer.normalize(gpt_raw, model_type="gpt")
    print("GPT event:")
    print(f"  event_type: {gpt_event.event_type}")
    print(f"  entity_id: {gpt_event.entity_id}")
    print(f"  payload: {gpt_event.payload}")
    print()

    # 5. Normalize unknown model (uses DefaultAdapter)
    unknown_raw = {"some": "data", "from": "unknown_model"}

    unknown_event = normalizer.normalize(unknown_raw, model_type="gemini")
    print("Unknown model event (via DefaultAdapter):")
    print(f"  event_type: {unknown_event.event_type}")
    print(f"  entity_type: {unknown_event.entity_type}")
    print(f"  metadata: {unknown_event.metadata}")
    print()

    # 6. Convert to dict for activity_log insertion
    print("Ready for activity_log insertion:")
    print(f"  to_dict(): {claude_event.to_dict()}")


if __name__ == "__main__":
    main()
