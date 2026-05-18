"""
Example: Using GPTAdapter and DefaultAdapter with EventNormalizer.

Demonstrates how to:
1. Register model-specific adapters
2. Normalize different model outputs
3. Handle unknown model types with fallback
"""

from core.adapters.normalizers import DefaultAdapter, GPTAdapter, EventNormalizer


def main():
    """Run adapter normalization examples."""
    # Initialize normalizer and register adapters
    normalizer = EventNormalizer()
    normalizer.register_adapter("gpt", GPTAdapter())
    normalizer.register_adapter("default", DefaultAdapter())

    # Example 1: Normalize OpenAI GPT response
    print("=" * 60)
    print("Example 1: GPT-4 Chat Completion Response")
    print("=" * 60)

    gpt_response = {
        "id": "chatcmpl-abc123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "gpt-4",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "The capital of France is Paris.",
                },
                "finish_reason": "stop",
                "index": 0,
            }
        ],
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 8,
            "total_tokens": 23,
        },
    }

    gpt_event = normalizer.normalize(gpt_response, model_type="gpt")
    print(f"Event ID: {gpt_event.event_id}")
    print(f"Event Type: {gpt_event.event_type}")
    print(f"Model: {gpt_event.payload['model']}")
    print(f"Content: {gpt_event.payload['content']}")
    print(f"Adapter: {gpt_event.metadata['adapter']}")
    print()

    # Example 2: Normalize unknown model type (uses registered DefaultAdapter)
    print("=" * 60)
    print("Example 2: Unknown Model Type (Registered DefaultAdapter)")
    print("=" * 60)

    unknown_response = {
        "model": "custom-llm-v1",
        "output": "This is a custom model response",
        "confidence": 0.95,
    }

    default_event = normalizer.normalize(unknown_response, model_type="default")
    print(f"Event ID: {default_event.event_id}")
    print(f"Event Type: {default_event.event_type}")
    print(f"Entity Type: {default_event.entity_type}")
    print(f"Payload: {default_event.payload}")
    print(f"Warning: {default_event.metadata.get('warning', 'N/A')}")
    print()

    # Example 3: Normalize unregistered model (uses normalizer's built-in fallback)
    print("=" * 60)
    print("Example 3: Unregistered Model (Built-in Fallback)")
    print("=" * 60)

    unregistered_response = {"some_key": "some_value"}

    fallback_event = normalizer.normalize(unregistered_response, model_type="unregistered-model")
    print(f"Event ID: {fallback_event.event_id}")
    print(f"Event Type: {fallback_event.event_type}")
    print(f"Metadata: {fallback_event.metadata}")
    print()

    # Example 4: Export to dict for activity_log insertion
    print("=" * 60)
    print("Example 4: Export to Dict for Activity Log")
    print("=" * 60)

    event_dict = gpt_event.to_dict()
    print("Ready for activity_log.insert():")
    print(f"  event_id: {event_dict['event_id']}")
    print(f"  event_type: {event_dict['event_type']}")
    print(f"  timestamp: {event_dict['timestamp']}")
    print(f"  severity: {event_dict['severity']}")
    print(f"  trace: {event_dict['trace']}")
    print()


if __name__ == "__main__":
    main()
