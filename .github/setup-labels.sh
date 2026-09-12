#!/usr/bin/env bash
# Create (or update) every label this repo's issue conventions define — the ones the AI
# documentation pipeline relies on, plus the kind-of-work labels it deliberately ignores.
#
# The pipeline adds action labels with `gh pr edit --add-label` / `gh issue edit`, which do
# NOT auto-create a missing label — so these must exist first. (peter-evans/create-pull-request
# does auto-create the context label it applies, but running this once keeps colors consistent.)
#
# Prerequisites: `gh` installed and authenticated (gh auth login), run from the repo root.
# Idempotent: `gh label create --force` updates an existing label instead of erroring.
# Run once: bash .github/setup-labels.sh
#
# A description longer than GitHub's 100-character cap is rejected by the API, so `label()`
# refuses it up front, and the final pass re-reads the repo's labels to confirm each one
# actually carries the description defined here — "the script ran" is not "the labels are
# right".

set -euo pipefail

expected=$(mktemp)
trap 'rm -f "$expected" "${actual:-}"' EXIT
actual=$(mktemp)

# `${#3}` counts characters under a UTF-8 locale and bytes under LC_ALL=C, and every
# description below contains an em dash — so the two readings differ by two per em dash. Both
# stay covered as long as the margins do (the longest description here is 95), and the
# verification pass at the bottom is the backstop for anything the API refuses regardless.
# A refused description stops the run where it stands, leaving the labels before it already
# written; that is harmless, since re-running after fixing the line applies the rest.
label() {
  if [ "${#3}" -gt 100 ]; then
    echo "error: description for label '$1' is ${#3} characters, over GitHub's 100 limit." >&2
    exit 1
  fi
  # Written raw, while the read-back below comes through jq's @tsv — which escapes backslashes
  # and tabs. No description may contain either, or the two spellings diverge and every run
  # reports a mismatch that re-running never clears.
  printf '%s\t%s\n' "$1" "$3" >>"$expected"
  gh label create "$1" --color "$2" --description "$3" --force
}

# --- Pre-triage label ---------------------------------------------------------------------
label idea            f2a101 "Not yet scoped — work it with the work-idea skill before adding needs-draft"

# --- Action / state labels ---------------------------------------------------------------
label needs-draft    0e8a16 "Issue: with one context label, trigger the CI drafter"
label needs-review   fbca04 "PR: trigger the fresh AI review"
label needs-work     d93f0b "PR: trigger the AI fix pass to address review remarks"
label needs-approval b60205 "PR: reviewed clean, or automatic review/fix cap reached — a maintainer must decide"

# --- Context / artifact-type labels ------------------------------------------------------
label uc          1d76db "Use-case analysis document"
label requirement 0052cc "Requirement / constraint / glossary change"
label adr         5319e7 "Architecture Decision Record"
label specs       006b75 "Implementation spec (design + TDD plan) work"
label development c5def5 "Implementation task (code + tests), pinned to a Plan: docs/plans task"
label testing     bfd4f2 "Test-authoring work, pinned to a Plan: docs/plans task"
label workflow    e99695 "CI/skill/agent-authoring change (review only — no auto-drafter)"
label documentation ededed "Design-doc change (docs/design/**); review only, not yet wired into the CI drafter's label set"

# --- Kind-of-work labels (orthogonal to the context label, never a substitute) ------------
# GitHub creates both by default with a vaguer description; --force rewrites it to the
# meaning docs/reference/contribution-workflow.md's Issue conventions gives them. Colors are
# GitHub's own defaults, so re-running this never recolors labels already on open issues.
label bug         d73a4a "Defect in shipped behaviour — verify the claim first; pair with a context label once known"
label enhancement a2eeef "Improvement to already-shipped behaviour — pair with a context label once the artifact is known"

# --- Verify the repo now matches this file ------------------------------------------------
# --limit must exceed the label count (this file's, plus GitHub's own defaults) or the
# read-back silently truncates and reports false mismatches.
gh label list --limit 200 --json name,description --jq '.[] | [.name, .description] | @tsv' >"$actual"

status=0
while IFS= read -r want; do
  grep -Fqx -- "$want" "$actual" || {
    echo "mismatch: label '${want%%$'\t'*}' does not carry the description defined here." >&2
    status=1
  }
done <"$expected"

if [ "$status" -ne 0 ]; then
  echo "Labels written, but the repo does not match this file — see mismatches above." >&2
  exit 1
fi

echo "Labels created/updated and verified."
