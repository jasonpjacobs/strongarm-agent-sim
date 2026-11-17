#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$task_root/.local/env.sh" ]]; then
  source "$task_root/.local/env.sh"
fi
cd -- "$task_root"
exec "${STRONGARM_PYTHON:-${PYTHON_BIN:-python3}}" -m strongarm_sim "$@"
