#!/usr/bin/env bash
# Human-in-the-loop reproduction loop, for a symptom whose only oracle is a human eye
# (a rendered dashboard tile, a displayed unit or precision, a notification as it appears).
#
# Copy this file out of the skill directory, edit the steps, and run it. The agent runs the
# script; the human partner answers the prompts in their own terminal. Captured answers are
# printed as KEY=VALUE at the end for the agent to read.
#
#   step "<instruction>"       -> show instruction, wait for Enter
#   capture VAR "<question>"   -> show question, read the answer into VAR
#
# Ask for observations with `capture`; leave anything the human must simply do (sign in,
# navigate, wait for a cycle) as a `step`. Never ask for a secret: redact before pasting.

set -euo pipefail

step() {
  printf '\n>>> %s\n' "$1"
  read -r -p "    [Enter when done] " _
}

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

# --- edit above ---------------------------------------------------------

printf '\n--- Captured ---\n'
printf 'TILE_TEXT=%s\n' "$TILE_TEXT"
printf 'STATE_ATTRS=%s\n' "$STATE_ATTRS"
