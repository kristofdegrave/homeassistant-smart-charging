#!/usr/bin/env bash
# Create (or update) every label the AI documentation pipeline relies on.
#
# The pipeline adds action labels with `gh pr edit --add-label` / `gh issue edit`, which do
# NOT auto-create a missing label — so these must exist first. (peter-evans/create-pull-request
# does auto-create the context label it applies, but running this once keeps colors consistent.)
#
# Prerequisites: `gh` installed and authenticated (gh auth login), run from the repo root.
# Idempotent: `gh label create --force` updates an existing label instead of erroring.
# Run once: bash .github/setup-labels.sh

set -euo pipefail

label() { gh label create "$1" --color "$2" --description "$3" --force; }

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
label bug         d73a4a "Defect in already-shipped behaviour — verify the claim first; pair with a context label once the fixing artifact is known"
label enhancement a2eeef "Improvement to already-shipped behaviour — pair with a context label once the artifact is known"

echo "Labels created/updated."
