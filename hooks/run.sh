#!/usr/bin/env bash
# dream-studio hook launcher (macOS / Linux / Windows-under-Git-Bash).
#
# Usage: run.sh <handler-name> [args...]
#
# Resolves the plugin root, picks a Python interpreter, and searches
# packs/{pack}/hooks/ for the named handler. Falls back to the legacy
# hooks/handlers/ path during migration.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: run.sh <handler-name> [args...]" >&2
  exit 2
fi

HANDLER="$1"
shift

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"

# Resolution order is explicit, not a filesystem glob — first match wins.
# If two packs ever define the same handler name, the earlier pack takes priority.
HANDLER_PATH=""
for pack in core quality career analyze domains meta; do
  candidate="${PLUGIN_ROOT}/packs/${pack}/hooks/${HANDLER}.py"
  if [[ -f "${candidate}" ]]; then
    HANDLER_PATH="${candidate}"
    break
  fi
done
if [[ -z "${HANDLER_PATH}" ]]; then
  candidate="${PLUGIN_ROOT}/hooks/handlers/${HANDLER}.py"
  if [[ -f "${candidate}" ]]; then
    HANDLER_PATH="${candidate}"
  fi
fi
if [[ -z "${HANDLER_PATH}" ]]; then
  echo "run.sh: handler not found: ${HANDLER}" >&2
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
