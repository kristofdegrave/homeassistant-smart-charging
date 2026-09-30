#!/usr/bin/env bash
# Run the word-budget check (.github/check-word-budget.py) with whichever Python on PATH can
# import PyYAML, as .github/check-method.sh does and for the same reason.
#
# Usage:  .github/check-word-budget.sh BASE [--root DIR]
#
# Arguments and exit codes are the script's; no usable Python exits 2 here.

set -euo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/check-word-budget.py"

# The probe runs from this script's own directory: under `-c` (and a script read from stdin)
# Python puts the current directory first on the import path, so a `yaml.py` in the cwd -- a
# task worktree's root, say, the pre-commit hook's cwd -- would run on every call. This
# directory is .github/, whose files are reviewed like the script itself.
HERE="$(cd "$(dirname "$0")" && pwd)"
py=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
    (cd "$HERE" && "$candidate" -c 'import yaml') >/dev/null 2>&1; then
    py="$candidate"
    break
  fi
done
if [ -z "$py" ]; then
  echo "check-word-budget: no python with PyYAML on PATH (tried python3, python)" >&2
  exit 2
fi

PYTHONUTF8=1 exec "$py" "$SCRIPT" "$@"
