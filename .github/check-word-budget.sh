#!/usr/bin/env bash
# Run the word-budget check (.github/check-word-budget.py) with whichever Python on PATH can
# import PyYAML, as .github/check-method.sh does and for the same reason.
#
# Usage:  .github/check-word-budget.sh BASE [--root DIR]
#
# Arguments and exit codes are the script's; no usable Python exits 2 here.

set -euo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/check-word-budget.py"

# No module is imported from the caller's directory or from this one. Under `-c` (and a script
# read from stdin) Python puts the cwd first on the import path, so a `yaml.py` there -- a
# task worktree's root, the pre-commit hook's cwd -- would run on every call: the probe runs from this directory
# instead, and PYTHONSAFEPATH=1 keeps even this directory off the path, for the probe and the
# run (a gitignored `yaml.pyc` here is no reviewed file). That variable needs Python 3.11; an
# older one ignores it, which leaves this directory's ignored files a gap. `-P` is not used:
# it stops the probe on an older Python.
HERE="$(cd "$(dirname "$0")" && pwd)"
py=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
    (cd "$HERE" && PYTHONSAFEPATH=1 "$candidate" -c 'import yaml') >/dev/null 2>&1; then
    py="$candidate"
    break
  fi
done
if [ -z "$py" ]; then
  echo "check-word-budget: no python with PyYAML on PATH (tried python3, python)" >&2
  exit 2
fi

PYTHONUTF8=1 PYTHONSAFEPATH=1 exec "$py" "$SCRIPT" "$@"
