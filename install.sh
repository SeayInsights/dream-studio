#!/usr/bin/env bash
# install.sh — dream-studio Mac/Linux setup
# Validates environment, then delegates to interfaces/cli/setup.py
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANONICAL="${SCRIPT_DIR}/interfaces/cli/setup.py"

# --- Repo-root validation ---------------------------------------------------
if [[ ! -f "${CANONICAL}" ]]; then
  echo "ERROR: install.sh must be run from the dream-studio repo root." >&2
  echo "  Expected: ${CANONICAL}" >&2
  exit 1
fi

# --- Python presence ---------------------------------------------------------
pick_python() {
  for candidate in "py -3.12" "py -3.11" "py -3" python3 python; do
    set -- $candidate
    if command -v "$1" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

PYTHON="$(pick_python)" || {
  echo "ERROR: Python not found. Install Python 3.11+ from https://python.org/downloads/" >&2
  exit 1
}

# --- Python version >= 3.11 --------------------------------------------------
# shellcheck disable=SC2086  # word-split intentional for "py -3.12" style values
VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>&1) || {
  echo "ERROR: Failed to determine Python version. Ensure Python 3.11+ is installed." >&2
  exit 1
}

MAJOR="${VERSION%%.*}"
MINOR="${VERSION#*.}"
if [[ "${MAJOR}" -lt 3 ]] || { [[ "${MAJOR}" -eq 3 ]] && [[ "${MINOR}" -lt 11 ]]; }; then
  echo "ERROR: Python >= 3.11 required (found ${VERSION}). Update from https://python.org/downloads/" >&2
  exit 1
fi

# --- Delegate to canonical setup ---------------------------------------------
# shellcheck disable=SC2086  # word-split intentional for "py -3.12" style values
exec $PYTHON "${CANONICAL}" "$@"
