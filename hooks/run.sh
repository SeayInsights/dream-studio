#!/usr/bin/env bash
# dream-studio hook launcher (macOS / Linux / Windows-under-Git-Bash).
#
# Usage: run.sh <handler-name> [args...]
#
# Resolves the plugin root, picks a Python interpreter via lib.python_shim,
# and executes hooks/handlers/<handler-name>.py, forwarding CLAUDE_PLUGIN_ROOT
# and any remaining arguments. Claude Code sets CLAUDE_PLUGIN_ROOT when it
# invokes a hook; we preserve it so the handler can resolve plugin assets.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: run.sh <handler-name> [args...]" >&2
  exit 2
fi

HANDLER="$1"
shift

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
HANDLER_PATH="${PLUGIN_ROOT}/hooks/handlers/${HANDLER}.py"

if [[ ! -f "${HANDLER_PATH}" ]]; then
  echo "run.sh: handler not found: ${HANDLER_PATH}" >&2
  exit 3
fi

pick_python() {
  for candidate in py python3 python; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      echo "${candidate}"
      return 0
    fi
  done
  return 1
}

PYTHON="$(pick_python)" || {
  echo "run.sh: no Python interpreter found on PATH (tried: py, python3, python)" >&2
  exit 4
}

export CLAUDE_PLUGIN_ROOT="${PLUGIN_ROOT}"
export PYTHONPATH="${PLUGIN_ROOT}/hooks:${PYTHONPATH:-}"
exec "${PYTHON}" "${HANDLER_PATH}" "$@"
