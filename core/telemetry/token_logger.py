"""Token usage logging utilities"""

import json
from pathlib import Path


def extract_usage_from_transcript(transcript_path: str) -> tuple[str, int, int, int]:
    """Parse JSONL transcript for model and token usage"""
    model = "unknown"
    prompt_t = completion_t = 0
    try:
        path = Path(transcript_path)
        if not path.exists():
            return model, 0, 0, 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                usage = entry.get("usage") or entry.get("message", {}).get("usage", {})
                if usage:
                    prompt_t += usage.get("input_tokens", 0)
                    completion_t += usage.get("output_tokens", 0)
                m = entry.get("model") or entry.get("message", {}).get("model", "")
                if m and model == "unknown":
                    model = m
    except Exception:
        pass
    return model, prompt_t, completion_t, prompt_t + completion_t


def write_token_log(
    log_path: Path,
    timestamp: str,
    session_name: str,
    model: str,
    prompt_t: int,
    completion_t: int,
    total_t: int,
    hook_output_bytes: int,
    hook_overhead_est: int,
) -> None:
    """Append token usage row to log file"""
    row = (
        f"| {timestamp} | {session_name} | {model} | {prompt_t} | {completion_t}"
        f" | {total_t} | {hook_output_bytes} | {hook_overhead_est} |\n"
    )
    try:
        if not log_path.exists():
            log_path.write_text(
                "# Token Log\n\n"
                "| Timestamp | Session | Model | Prompt | Completion | Total"
                " | HookOutputBytes | HookOverheadEst |\n"
                "|---|---|---|---|---|---|---|---|\n",
                encoding="utf-8",
            )
        with log_path.open("a", encoding="utf-8") as f:
            f.write(row)
    except Exception as e:
        print(f"[token_logger] failed to write: {e}", flush=True)

    try:
        from core.telemetry.emitters import emit_token_usage_record

        emit_token_usage_record(
            session_name=session_name,
            model=model,
            input_tokens=prompt_t,
            output_tokens=completion_t,
            total_tokens=total_t,
            context={
                "project_id": "dream-studio",
                "process_run_id": session_name,
                "session_name": session_name,
                "source_refs": [
                    "runtime/hooks/meta/on-token-log.py",
                    "core/telemetry/token_logger.py",
                ],
            },
        )
    except Exception:
        pass
