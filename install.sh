#!/bin/bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Dream Studio Installer"
echo "======================"

# Check Python version
check_python() {
    local cmd=$1
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 12 ]; then
            echo "$cmd"
            return 0
        fi
    fi
    return 1
}

PYTHON=""
for cmd in python3.12 python3 python; do
    if PYTHON=$(check_python "$cmd"); then
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Python 3.12+ not found. Attempting install..."
    if command -v brew &>/dev/null; then
        brew install python@3.12
        PYTHON="python3.12"
    elif command -v apt-get &>/dev/null; then
        sudo apt-get update && sudo apt-get install -y python3.12
        PYTHON="python3.12"
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3.12
        PYTHON="python3.12"
    else
        echo "ERROR: Could not install Python automatically."
        echo "Please install Python 3.12+ from https://python.org"
        echo "Then run this script again."
        exit 1
    fi
fi

echo "Using Python: $PYTHON ($($PYTHON --version))"

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
cd "$REPO_DIR"
"$PYTHON" -m pip install -r requirements.txt || {
    echo "ERROR: pip install failed. See output above." >&2
    exit 1
}

# Install Dream Studio into its home as a versioned app (it creates or migrates the
# authority) and its Claude Code integration into one config root. Run again to upgrade.
DS_HOME_DIR="$HOME/.dream-studio"
CONFIG_ROOT="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
echo ""
echo "Installing Dream Studio into $DS_HOME_DIR (Claude Code root: $CONFIG_ROOT)..."
"$PYTHON" -m interfaces.cli.ds self-install --config-root "$CONFIG_ROOT" --execute || {
    echo "ERROR: ds self-install failed. See output above." >&2
    exit 1
}

# Report, from the installed app
echo ""
echo "Running health check..."
"$DS_HOME_DIR/bin/ds" doctor

echo ""
echo "Dream Studio installed successfully."
echo "Add $DS_HOME_DIR/bin to PATH (see INSTALL.md), then type: ds doctor"
