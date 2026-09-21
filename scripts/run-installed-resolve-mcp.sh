#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${MEHER_RESOLVE_HUB_RUNTIME:-$HOME/Library/Application Support/Meher Flow/Resolve Hub/runtime}"
VENV_DIR="${MEHER_RESOLVE_MCP_VENV:-$HOME/Library/Application Support/Meher Flow/Resolve Hub/mcp-venv}"
RESOLVE_MODULES="${RESOLVE_PYTHON_MODULES:-/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules}"
RESOLVE_SCRIPT_API="${RESOLVE_SCRIPT_API:-/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting}"

PYTHON="${MEHER_RESOLVE_MCP_PYTHON:-$VENV_DIR/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  echo "Meher Flow MCP Python runtime not found: $PYTHON" >&2
  echo "Run scripts/install-resolve-hub-runtime.sh from the Davinci-Resolve repository." >&2
  exit 1
fi

export RESOLVE_SCRIPT_API
export PYTHONPATH="$RUNTIME_DIR:$RESOLVE_MODULES${PYTHONPATH:+:$PYTHONPATH}"

exec "$PYTHON" -m meher_resolve_hub.mcp_server
