#!/usr/bin/env bash
# Run the upstream-pin drift check (.github/check-upstream-drift.py) with whichever Python on
# PATH can import PyYAML - the same discovery .github/check-method.sh uses, for the same
# reason: `jq` is not on PATH in the Windows/Git Bash setup this project is driven from, and
# the profile is YAML.
#
# Usage:  .github/check-upstream-drift.sh [--root DIR] [--out FILE] [--responses FILE]
#                                         [--validate] [--markers]
#                                         [--splice --body FILE --report FILE [--out FILE]]
#
# Arguments pass straight through; what each mode does is the script's own header. Exit codes
# are the script's too: 0 every pin current (or, under --splice, a merged body written), 1
# something needs a human, 2 usage or environment error - including no usable Python, reported
# here before the script is reached - and 3 for --splice's "nothing changed".

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
