#!/usr/bin/env bash
# Run the `Source:` line check (.github/check-source-lines.py) with whichever Python on PATH
# can import PyYAML - the same discovery .github/check-method.sh uses, for the same reason:
# `jq` is not on PATH in the Windows/Git Bash setup this project is driven from, and the
# profile is YAML.
#
# Usage:  .github/check-source-lines.sh (--body FILE | --issue N) [--root DIR] [--ref REF]
#
# Arguments pass straight through; what each does, and the exit codes, are the script's own
# header: 0 every line resolves, 1 one does not, 2 usage or environment error - including no
# usable Python, reported here before the script is reached - and 3 the body could not be
# fetched, which is no verdict.

set -euo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/check-source-lines.py"

py=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import yaml' >/dev/null 2>&1; then
    py="$candidate"
    break
  fi
done
if [ -z "$py" ]; then
  echo "check-source-lines: no python with PyYAML on PATH (tried python3, python)" >&2
  exit 2
fi

PYTHONUTF8=1 exec "$py" "$SCRIPT" "$@"
