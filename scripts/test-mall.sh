#!/usr/bin/env bash
set -euo pipefail
mall_repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mall_python="$mall_repo_root/backend/.venv/bin/python"
if [[ ! -x "$mall_python" ]]; then
  mall_python=python3
fi
exec "$mall_python" "$mall_repo_root/scripts/mall_test_runner.py" "$@"
