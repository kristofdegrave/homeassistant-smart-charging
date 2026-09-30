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
  echo "check-source-lines: no python with PyYAML on PATH (tried python3, python)" >&2
  exit 2
fi

PYTHONUTF8=1 exec "$py" "$SCRIPT" "$@"
