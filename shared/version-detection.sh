#!/usr/bin/env bash
# version-detection.sh - Detect installed tool versions
# Outputs JSON with python, node, powerbi_desktop versions

set -euo pipefail

# Initialize version variables
PYTHON_VERSION="not_installed"
NODE_VERSION="not_installed"
POWERBI_VERSION="not_installed"

# Detect Python version
detect_python() {
    local version=""

    # Try python3 first, then python, then py (Windows)
    if command -v python3 >/dev/null 2>&1; then
        version=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)
    elif command -v python >/dev/null 2>&1; then
        version=$(python --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)
    elif command -v py >/dev/null 2>&1; then
        version=$(py --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)
    fi

    if [[ -n "$version" ]]; then
        PYTHON_VERSION="$version"
    fi
}

# Detect Node version
detect_node() {
    if command -v node >/dev/null 2>&1; then
        local version
        version=$(node --version 2>&1)
        # Remove leading 'v' if present
        version="${version#v}"
        # Extract semver pattern
        version=$(echo "$version" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)

        if [[ -n "$version" ]]; then
            NODE_VERSION="$version"
        fi
    fi
}

# Detect Power BI Desktop version (Windows only)
detect_powerbi() {
    # Only attempt on Windows (check for WINDIR or OS env var)
    if [[ -n "${WINDIR:-}" ]] || [[ "${OS:-}" == "Windows_NT" ]]; then
        # Try registry query (requires reg.exe on Windows)
        if command -v reg.exe >/dev/null 2>&1; then
            local version
            # Query registry for Power BI Desktop installation
            version=$(reg.exe query "HKLM\\SOFTWARE\\Microsoft\\Microsoft Power BI Desktop" //v Version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -n1 || echo "")

            if [[ -z "$version" ]]; then
                # Try alternative registry path
                version=$(reg.exe query "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Microsoft Power BI Desktop" //v Version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -n1 || echo "")
            fi

            if [[ -z "$version" ]]; then
                # Try checking installation path
                local pbi_path="/c/Program Files/Microsoft Power BI Desktop/bin/PBIDesktop.exe"
                if [[ -f "$pbi_path" ]]; then
                    # Get file version using PowerShell
                    if command -v powershell.exe >/dev/null 2>&1; then
                        version=$(powershell.exe -NoProfile -Command "(Get-Item 'C:\\Program Files\\Microsoft Power BI Desktop\\bin\\PBIDesktop.exe').VersionInfo.FileVersion" 2>/dev/null | tr -d '\r' || echo "")
                    fi
                fi
            fi

            if [[ -n "$version" ]]; then
                POWERBI_VERSION="$version"
            fi
        fi
    fi
}

# Run detection
detect_python
detect_node
detect_powerbi

# Output JSON
cat <<EOF
{
  "python": "$PYTHON_VERSION",
  "node": "$NODE_VERSION",
  "powerbi_desktop": "$POWERBI_VERSION"
}
EOF
