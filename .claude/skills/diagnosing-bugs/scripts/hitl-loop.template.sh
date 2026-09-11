#!/usr/bin/env bash
# Human-in-the-loop reproduction loop, for a symptom whose only oracle is a human eye
# (a rendered dashboard tile, a displayed unit or precision, a notification as it appears).
#
# WHO RUNS IT: the human partner, in their own interactive terminal. An agent cannot —
# under a tool call stdin is not a TTY, so the first `read` hits EOF and `set -e` exits the
# script before a single prompt is shown. So: copy this template to your session scratchpad
# (never into the repo or a worktree), adapt the steps to the claim under test, and ask the
# human partner to run that copy.
#
# HOW THE ANSWERS COME BACK: the captured block is printed to their terminal AND appended to
# the file named by $HITL_OUT, which defaults into the OS temp directory — deliberately not
# the working directory, since these captures hold the installation's raw entity state and
# must never be swept into a commit. Read that file if you share a filesystem with them;
# otherwise ask them to paste the block back. Each block is stamped with a UTC timestamp so a
# stale run is never mistaken for the current one, and a run that is interrupted still flushes
# whatever was answered, marked INCOMPLETE, so the human does not repeat the whole sequence.
#
#   step "<instruction>"       -> show instruction, wait for Enter
#   capture VAR "<question>"   -> show question, read the answer into VAR
#
# Ask for observations with `capture`; leave anything the human must simply do (sign in,
# navigate, wait for a cycle) as a `step`. Never ask for a secret: redact before pasting.

set -euo pipefail

HITL_OUT="${HITL_OUT:-${TMPDIR:-/tmp}/hitl-capture.txt}"

# Every variable a `capture` writes to, so the flush below can report partial runs.
CAPTURED_VARS=(TILE_TEXT STATE_ATTRS)
COMPLETE=0

flush() {
  local marker="--- Captured $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  [ "$COMPLETE" = 1 ] && marker="$marker ---" || marker="$marker INCOMPLETE ---"
  {
    printf '%s\n' "$marker"
    for v in "${CAPTURED_VARS[@]}"; do printf '%s=%s\n' "$v" "${!v-<unanswered>}"; done
  } | tee -a "$HITL_OUT"
  printf '\n(also appended to %s)\n' "$HITL_OUT"
}
trap 'printf "\n"; flush' EXIT

step() {
  printf '\n>>> %s\n' "$1"
  read -r -p "    [Enter when done] " _
}

# Name the target variable in UPPERCASE: `capture var "..."` would collide with this
# function's own locals and silently lose the answer.
capture() {
  local var="$1" question="$2" answer
  printf '\n>>> %s\n' "$question"
  read -r -p "    > " answer
  printf -v "$var" '%s' "$answer"
}

# --- edit below (keep CAPTURED_VARS above in sync with the `capture` calls) ----

step "Open Home Assistant and go to the Smart Charging dashboard."

capture TILE_TEXT "Read the tile out exactly as shown, digits and unit included:"

step "Open Developer Tools > States and find the entity backing that tile."

capture STATE_ATTRS "Paste the entity's state and its attributes (unit_of_measurement included):"

# --- edit above ---------------------------------------------------------------

COMPLETE=1
