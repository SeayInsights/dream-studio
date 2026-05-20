from __future__ import annotations
import hashlib
from typing import Any
from urllib.parse import urlparse


def redact_prompt(raw_prompt: str) -> dict[str, Any]:
    return {
        "prompt_hash": hashlib.sha256(raw_prompt.encode("utf-8")).hexdigest(),
        "prompt_length": len(raw_prompt),
        "raw_retained": False,
    }


def redact_tool_output(tool_name: str, output: Any, *, is_error: bool = False) -> dict[str, Any]:
    if is_error:
        error_class = type(output).__name__ if not isinstance(output, str) else "Error"
        return {"success": False, "error_class": error_class, "raw_output_retained": False}
    if isinstance(output, str):
        lines = output.count("\n") + (1 if output else 0)
        return {
            "success": True,
            "byte_count": len(output.encode("utf-8")),
            "line_count": lines,
            "raw_output_retained": False,
        }
    if isinstance(output, (dict, list)):
        import json

        return {
            "success": True,
            "byte_count": len(json.dumps(output).encode("utf-8")),
            "raw_output_retained": False,
        }
    return {"success": True, "raw_output_retained": False}


def redact_bash_command(command: str) -> dict[str, Any]:
    parts = command.split()
    return {
        "binary": parts[0] if parts else "",
        "arg_count": len(parts) - 1,
        "args_retained": False,
    }


def redact_url(url: str) -> dict[str, Any]:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or (parsed.path.split("/")[0] if parsed.path else "unknown")
        return {"domain": domain, "path_retained": False}
    except Exception:
        return {"domain": "unknown", "path_retained": False}


def redact_file_path(path: str) -> str:
    return path
