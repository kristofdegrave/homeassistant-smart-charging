#!/usr/bin/env bash
# Run the word-budget check (.github/check-word-budget.py) with whichever Python on PATH can
# import PyYAML, as .github/check-method.sh does and for the same reason.
#
# Usage:  .github/check-word-budget.sh BASE [--root DIR]
#
# Arguments and exit codes are the script's; no usable Python exits 2 here.

set -euo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/check-word-budget.py"

py=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import yaml' >/dev/null 2>&1; then
    py="$candidate"
    break
  fi
done
if [ -z "$py" ]; then
  echo "check-word-budget: no python with PyYAML on PATH (tried python3, python)" >&2
  exit 2
fi

PYTHONUTF8=1 exec "$py" "$SCRIPT" "$@"
