#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="$HOME/Library/Application Support/Meher Flow/Resolve Hub"
RUNTIME_DIR="$APP_ROOT/runtime"
BIN_DIR="$APP_ROOT/bin"
VENV_DIR="$APP_ROOT/mcp-venv"
UTILITY_DIR="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"

PYTHON="${MEHER_RESOLVE_MCP_BOOTSTRAP_PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3.10+ and retry." >&2
  exit 1
fi

"$PYTHON" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required for the MCP runtime.")
PY

mkdir -p "$RUNTIME_DIR" "$BIN_DIR" "$UTILITY_DIR"

rm -rf "$RUNTIME_DIR/meher_resolve_hub"
cp -R "$ROOT/meher_resolve_hub" "$RUNTIME_DIR/meher_resolve_hub"

cp "$ROOT/Meher Flow Resolve Hub.py" "$UTILITY_DIR/Meher Flow Resolve Hub.py"
cp "$ROOT/Media Manager.py" "$UTILITY_DIR/Media Manager.py"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$ROOT/requirements-speaker-markers.txt"

cp "$ROOT/scripts/run-installed-resolve-mcp.sh" "$BIN_DIR/run-resolve-mcp"
chmod +x "$BIN_DIR/run-resolve-mcp"

echo
echo "Installed Meher Flow Resolve Hub runtime:"
echo "  $RUNTIME_DIR"
echo
echo "Installed Resolve menu launcher:"
echo "  $UTILITY_DIR/Meher Flow Resolve Hub.py"
echo
echo "Installed Codex MCP launcher:"
echo "  $BIN_DIR/run-resolve-mcp"
echo
echo "Next:"
echo "  1. Restart DaVinci Resolve if the script menu was already open."
echo "  2. Open Workspace > Scripts > Meher Flow Resolve Hub."
echo "  3. Save the OpenAI API key under Settings > AI / OpenAI."
echo "  4. Register the MCP server with Codex:"
printf '     codex mcp add meher-resolve -- "%s"\n' "$BIN_DIR/run-resolve-mcp"
