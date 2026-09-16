#!/usr/bin/env bash
# Run the upstream-pin drift check (.github/check-upstream-drift.py) with whichever Python on
# PATH can import PyYAML - the same discovery .github/check-method.sh uses, for the same
# reason: `jq` is not on PATH in the Windows/Git Bash setup this project is driven from, and
# the profile is YAML.
#
# Usage:  .github/check-upstream-drift.sh [--root DIR] [--out FILE] [--responses FILE]
#
# Arguments pass straight through; the script's own header states them. Exit codes are the
# script's: 0 every pin current, 1 something needs a human, 2 usage or environment error -
# including no usable Python, reported here before the script is reached.

set -euo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/check-upstream-drift.py"

py=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import yaml' >/dev/null 2>&1; then
    py="$candidate"
    break
  fi
done
if [ -z "$py" ]; then
  echo "check-upstream-drift: no python with PyYAML on PATH (tried python3, python)" >&2
  exit 2
fi

PYTHONUTF8=1 exec "$py" "$SCRIPT" "$@"
