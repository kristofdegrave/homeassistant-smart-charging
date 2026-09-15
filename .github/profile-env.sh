#!/usr/bin/env bash
# Print the project profile's tracker values as shell assignments, so the recipes in
# docs/reference/method/tracker-mechanics.md can be pasted as written:
#
#   eval "$(bash .github/profile-env.sh)"
#
# Emits OWNER, REPO_NAME, REPO (owner/name), BOARD, PROJECT_ID, the three field ids
# (SIZE_FIELD, ESTIMATE_FIELD, STATUS_FIELD), one SIZE_<tier> per Size option and one
# STATUS_<Column> per Status option (spaces in a column name become underscores:
# STATUS_In_progress). Every value comes from .claude/profile.yml and nowhere else.
#
# Needs a Python with PyYAML — present in this repo's test environment
# (requirements-test.txt pulls it in through homeassistant). `jq` is deliberately not used:
# it is not on PATH in the Windows/Git Bash setup this project is driven from.
#
# Exit 0 with the assignments on stdout. Any failure — no usable Python, an unreadable
# profile (both exit 2), or a profile missing a key the reader needs (Python's own exit 1,
# with the traceback naming the key) — prints nothing on stdout: the whole set is built
# before the first line is written, so an `eval` of a failed run assigns nothing rather
# than half the set.

set -euo pipefail

PROFILE="${PROFILE:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.claude/profile.yml}"

if [ ! -r "$PROFILE" ]; then
  echo "profile-env: cannot read $PROFILE" >&2
  exit 2
fi

py=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import yaml' >/dev/null 2>&1; then
    py="$candidate"
    break
  fi
done
if [ -z "$py" ]; then
  echo "profile-env: no python with PyYAML on PATH (tried python3, python)" >&2
  exit 2
fi

PYTHONUTF8=1 "$py" - "$PROFILE" <<'PY'
import re
import shlex
import sys

import yaml

# A Windows Python translates LF to CRLF on a redirected stdout; the shell reading these lines
# would then carry a trailing CR into every value. Emit LF regardless of platform.
sys.stdout.reconfigure(newline="\n")

with open(sys.argv[1], encoding="utf-8") as fh:
    profile = yaml.safe_load(fh)

repo = profile["repo"]
board = profile["board"]
fields = board["fields"]

out = {
    "OWNER": repo["owner"],
    "REPO_NAME": repo["name"],
    "REPO": f"{repo['owner']}/{repo['name']}",
    "BOARD": board["number"],
    "PROJECT_ID": board["project_id"],
    "SIZE_FIELD": fields["size"]["id"],
    "ESTIMATE_FIELD": fields["estimate"]["id"],
    "STATUS_FIELD": fields["status"]["id"],
}
# Keys are sanitised as well as values: the documented call site is `eval`, so an option name
# is executed as part of an assignment, and only [A-Za-z0-9_] may reach it.
for tier, option_id in fields["size"]["options"].items():
    out["SIZE_" + re.sub(r"\W", "_", str(tier))] = option_id
for column, option_id in fields["status"]["options"].items():
    out["STATUS_" + re.sub(r"\W", "_", str(column))] = option_id

for key, value in out.items():
    print(f"{key}={shlex.quote(str(value))}")
PY
