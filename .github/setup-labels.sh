#!/usr/bin/env bash
# Create (or update) every label this repo's issue conventions define — the ones the AI
# documentation pipeline relies on, plus the kind-of-work labels it deliberately ignores.
#
# The label set itself is not in this file. It is `.claude/profile.yml`'s `labels` section —
# the one place the project's label vocabulary is spelled — and this script writes exactly
# that set, every group in it, in the order the file lists them. Adding or changing a label
# means editing the profile, then re-running this.
#
# The pipeline adds action labels with `gh pr edit --add-label` / `gh issue edit`, which do
# NOT auto-create a missing label — so these must exist first. (peter-evans/create-pull-request
# does auto-create the context label it applies, but running this once keeps colors consistent.)
#
# Prerequisites: `gh` installed and authenticated (gh auth login); a Python with PyYAML on
# PATH (this repo's test environment has one — requirements-test.txt pulls it in through
# homeassistant); run from the repo root.
# Idempotent: `gh label create --force` updates an existing label instead of erroring.
# Run once: bash .github/setup-labels.sh
#
# A description longer than GitHub's 100-character cap is rejected by the API, so `label()`
# refuses it up front, and the final pass re-reads the repo's labels to confirm each one
# actually carries the description defined in the profile — "the script ran" is not "the
# labels are right".

set -euo pipefail

PROFILE="${PROFILE:-.claude/profile.yml}"

expected=$(mktemp)
actual=$(mktemp)
defined=$(mktemp)
trap 'rm -f "$expected" "$actual" "$defined"' EXIT

# --- Read the label set out of the profile ------------------------------------------------
# Captured to a file whose exit status is checked, never piped into the loop below: a
# `while … < <(python …)` puts the reader's failure out of reach of errexit, and an empty
# result would then read as "no labels to write" and the run would report success.
# PYTHONUTF8=1 because a Windows Python writes stdout in the console code page by default,
# which would turn every em dash in a description into a different byte sequence than the
# one `gh` reads back.
py=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import yaml' >/dev/null 2>&1; then
    py="$candidate"
    break
  fi
done
if [ -z "$py" ]; then
  echo "error: no python with PyYAML on PATH (tried python3, python); cannot read $PROFILE" >&2
  exit 2
fi

PYTHONUTF8=1 "$py" - "$PROFILE" >"$defined" <<'PY'
import sys

import yaml

# A Windows Python translates LF to CRLF on a redirected stdout; the shell reading these lines
# would then carry a trailing CR into every value. Emit LF regardless of platform.
sys.stdout.reconfigure(newline="\n")

with open(sys.argv[1], encoding="utf-8") as fh:
    labels = yaml.safe_load(fh)["labels"]

# Every group, in file order. A group is a list of {name, color, description}; nothing here
# knows or cares what a group means — that is the profile's and Issue conventions' business.
for group in labels.values():
    for entry in group:
        name, color, description = entry["name"], entry["color"], entry["description"]
        for field, value in (("name", name), ("color", color), ("description", description)):
            if "\t" in str(value) or "\n" in str(value):
                sys.exit(f"error: label {name!r}: {field} contains a tab or newline")
        print(f"{name}\t{color}\t{description}")
PY

if [ ! -s "$defined" ]; then
  echo "error: $PROFILE defines no labels" >&2
  exit 2
fi

# `${#3}` counts characters under a UTF-8 locale and bytes under LC_ALL=C, and most
# descriptions contain an em dash — so the two readings differ by two per em dash. Both stay
# covered as long as the margins do, and the verification pass at the bottom is the backstop
# for anything the API refuses regardless. A refused description stops the run where it
# stands, leaving the labels before it already written; that is harmless, since re-running
# after fixing the profile applies the rest.
label() {
  if [ "${#3}" -gt 100 ]; then
    echo "error: description for label '$1' is ${#3} characters, over GitHub's 100 limit." >&2
    exit 1
  fi
  # Written raw, while the read-back below comes through jq's @tsv — which escapes backslashes
  # and tabs. No description may contain either, or the two spellings diverge and every run
  # reports a mismatch that re-running never clears.
  case "$3" in
    *\\*)
      echo "error: description for label '$1' contains a backslash." >&2
      exit 1
      ;;
  esac
  printf '%s\t%s\n' "$1" "$3" >>"$expected"
  gh label create "$1" --color "$2" --description "$3" --force
}

while IFS=$'\t' read -r name color description; do
  label "$name" "$color" "$description"
done <"$defined"

# --- Verify the repo now matches the profile ----------------------------------------------
# A REST read, not `gh label list`: that command is GraphQL, and straight after the writes
# above it has returned the last label written with a stale description for longer than the
# retry below waits, so the read-back reported a false mismatch — the same transport split
# docs/reference/tracker-mechanics.md describes. `{owner}/{repo}` is filled in by `gh` from
# the checkout, which is why this runs from the repo root. `--paginate` with an explicit page
# size, or the read silently truncates at 30 and reports false mismatches. `tr -d '\r'`
# because `gh` on Windows ends its lines with CRLF, and a trailing CR would make every
# exact-line match fail. A mismatch is still re-read a few times before it is reported, so a
# slow write cannot fail the run; only one that survives every attempt is real.
readback() {
  # Called as an `until` condition, where errexit does not fire — so the transport failure is
  # tested explicitly (pipefail is still in force for the pipeline's status). A `gh api` that
  # cannot list the labels — auth, rate limit, network — is not a mismatch and must not be
  # reported as one, or a dead network would read as "every label is wrong".
  if ! gh api -X GET "repos/{owner}/{repo}/labels" -f per_page=100 --paginate \
      --jq '.[] | [.name, .description] | @tsv' | tr -d '\r' >"$actual"; then
    echo "error: could not list the repository's labels (gh api failed); nothing verified." >&2
    exit 2
  fi
  status=0
  while IFS= read -r want; do
    grep -Fqx -- "$want" "$actual" || status=1
  done <"$expected"
  return "$status"
}

attempt=1
until readback; do
  if [ "$attempt" -ge 5 ]; then
    while IFS= read -r want; do
      grep -Fqx -- "$want" "$actual" ||
        echo "mismatch: label '${want%%$'\t'*}' does not carry the description defined in $PROFILE." >&2
    done <"$expected"
    echo "Labels written, but the repo does not match $PROFILE — see mismatches above." >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep 3
done

echo "Labels created/updated and verified against $PROFILE."
