#!/usr/bin/env bash
# Human-in-the-loop reproduction loop, for a symptom whose only oracle is a human eye
# (a rendered dashboard tile, a displayed unit or precision, a notification as it appears).
#
# WHO RUNS IT: the human partner, in their own interactive terminal. An agent cannot —
# under a tool call stdin is not a TTY, so the first `read` hits EOF and `set -euo pipefail`
# aborts the script before a single prompt is shown. So: copy this file out of the skill
# directory, edit the steps, and ask the human partner to run it.
#
# HOW THE ANSWERS COME BACK: the captured block is printed to their terminal AND appended to
# the file named by $HITL_OUT (default ./hitl-capture.txt). Read that file if you share a
# filesystem with them; otherwise ask them to paste the `--- Captured ---` block back.
#
#   step "<instruction>"       -> show instruction, wait for Enter
#   capture VAR "<question>"   -> show question, read the answer into VAR
#
# Ask for observations with `capture`; leave anything the human must simply do (sign in,
# navigate, wait for a cycle) as a `step`. Never ask for a secret: redact before pasting.

set -euo pipefail

HITL_OUT="${HITL_OUT:-hitl-capture.txt}"

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

# --- edit below ---------------------------------------------------------

step "Open Home Assistant and go to the Smart Charging dashboard."

capture TILE_TEXT "Read the tile out exactly as shown, digits and unit included:"

step "Open Developer Tools > States and find the entity backing that tile."

capture STATE_ATTRS "Paste the entity's state and its attributes (unit_of_measurement included):"

CAPTURED=$(printf -- '--- Captured ---\nTILE_TEXT=%s\nSTATE_ATTRS=%s' "$TILE_TEXT" "$STATE_ATTRS")

# --- edit above ---------------------------------------------------------

printf '\n%s\n' "$CAPTURED"
printf '%s\n' "$CAPTURED" >>"$HITL_OUT"
printf '\n(also appended to %s)\n' "$HITL_OUT"
