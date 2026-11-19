#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$task_root"
# MCP_PYTHON may select another installed environment; no login shell is used.
if [[ -n "${MCP_PYTHON:-}" ]]; then
  task_python="$MCP_PYTHON"
elif [[ -x "$task_root/.venv-mcp/bin/python" ]]; then
  task_python="$task_root/.venv-mcp/bin/python"
else
  task_python="${PYTHON_BIN:-python3}"
fi
# Use this checkout and its environment, not an inherited EDA Python path.
unset PYTHONPATH PYTHONHOME
exec "$task_python" -m ngspice_mcp "$@"
