#!/usr/bin/env bash
# Run the watched-path check (.github/check-path-map.py) with whichever Python on PATH can
# import PyYAML — the same discovery .github/check-method.sh uses, for the same reason: `jq` is
# not on PATH in the Windows/Git Bash setup this project is driven from, and both the source
# and one of the consumers are YAML.
#
# Usage:  .github/check-path-map.sh [--root DIR] [--warn]
#
# Arguments pass straight through; the script's own header states them. Exit codes are the
# script's: 0 clean, 1 findings (0 with --warn), 2 usage or environment error — including no
# usable Python, reported here before the script is reached.

set -euo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/check-path-map.py"

py=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import yaml' >/dev/null 2>&1; then
    py="$candidate"
    break
  fi
done
if [ -z "$py" ]; then
  echo "check-path-map: no python with PyYAML on PATH (tried python3, python)" >&2
  exit 2
fi

PYTHONUTF8=1 exec "$py" "$SCRIPT" "$@"
