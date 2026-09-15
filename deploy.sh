#!/usr/bin/env bash

set -euo pipefail

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
runtime_root="${MEHER_FLOW_RUNTIME_ROOT:-${HOME}/Library/Application Support/Meher Flow/Resolve Hub/runtime}"
utility_root="${RESOLVE_UTILITY_ROOT:-${HOME}/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility}"
resolve_python="${RESOLVE_PYTHON:-/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Applications/ResolvePython}"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This deployment helper currently supports macOS only." >&2
    exit 1
fi

for required in \
    "${source_root}/meher_resolve_hub" \
    "${source_root}/Media Manager.py" \
    "${source_root}/Meher Flow Resolve Hub.py"; do
    if [[ ! -e "${required}" ]]; then
        echo "Missing required source: ${required}" >&2
        exit 1
    fi
done

if [[ ! -x "${resolve_python}" ]]; then
    echo "ResolvePython was not found at: ${resolve_python}" >&2
    echo "Set RESOLVE_PYTHON to its location and run this command again." >&2
    exit 1
fi

echo "Validating Resolve Hub…"
"${resolve_python}" -m py_compile \
    "${source_root}/Media Manager.py" \
    "${source_root}/Meher Flow Resolve Hub.py"
"${resolve_python}" -m unittest discover \
    -s "${source_root}/tests" \
    -t "${source_root}" \
    -q

echo "Installing runtime and menu scripts…"
mkdir -p "${runtime_root}/meher_resolve_hub" "${utility_root}"
rsync -a \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    "${source_root}/meher_resolve_hub/" \
    "${runtime_root}/meher_resolve_hub/"
install -m 0644 \
    "${source_root}/Media Manager.py" \
    "${utility_root}/Media Manager.py"
install -m 0644 \
    "${source_root}/Meher Flow Resolve Hub.py" \
    "${utility_root}/Meher Flow Resolve Hub.py"

echo
echo "Resolve Hub deployed successfully."
echo "If the Hub is open, close it and reopen:"
echo "Workspace → Scripts → Meher Flow Resolve Hub"
