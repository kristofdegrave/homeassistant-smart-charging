#!/usr/bin/env bash
# One-time helper: create the backlog issues for the remaining use-cases (UC02–UC10).
#
# Issues are created with the `uc` context label only — NOT `needs-draft` — so they sit as a
# backlog. To start drafting one, add the `needs-draft` label to that issue yourself; the AI
# documentation pipeline's `draft` job then runs (the `ai` environment scopes the API key).
#
# Prerequisites: `gh` installed and authenticated (gh auth login), run from the repo root.
# Labels must already exist — run bash .github/setup-labels.sh once first.
# Run once: bash .github/create-uc-issues.sh

set -euo pipefail

create() {
  local title="$1" actor="$2" req="$3" slug="$4" mode="$5" notes="$6"
  gh issue create --label uc --title "$title" --body "$(cat <<EOF
## Use-case

- **Goal:** ${title#*— }
- **Primary actor:** $actor
- **Requirement(s) satisfied:** $req
- **File slug:** \`docs/analysis/use-cases/$slug.md\`
- **Mode use-case?** $mode

## Key notes / scope

$notes

## Authoring contract (for the runner)

- Follow the **write-use-case** skill and the template in \`docs/plans/2026-06-25-use-cases-design.md\`.
- Every domain term must already be in the \`system-overview.md\` glossary — add it there first if not.
- Reference (do not restate) \`control-cycle.md\` and \`resolution-rules.md\`.
- Update \`entity-catalog.md\`'s Read by / Written by columns for every entity touched.
EOF
)"
}

create "UC02 — Charge from solar only" \
  "Household energy manager" "R2" "UC02-charge-from-solar-only" \
  "yes — needs stateDiagram-v2 + State model" \
  "- No grid fallback; stop with no hold when smoothed surplus falls below the start threshold (default 1300 W).
- Sibling of UC01; a solar step-up in effect is preserved when switching between the two (R7).
- Extended by UC05 when the deadline is at risk."

create "UC03 — Charge cost-efficiently from the grid" \
  "Household energy manager" "R4" "UC03-charge-cost-efficiently-from-grid" \
  "yes — needs stateDiagram-v2 + State model" \
  "- Charge only while the low-tariff flag is active; default 0 A otherwise; grid charging up to the effective peak limit minus safety margin.
- Extended by UC05 (deadline may charge at high tariff / raised peak)."

create "UC04 — Charge at maximum power" \
  "EV driver" "R17" "UC04-charge-at-maximum-power" \
  "yes — needs stateDiagram-v2 + State model" \
  "- Ignores solar surplus and tariff; sets the maximum charging current.
- Configurable peak-protection option (R3) that may be disabled; the grid supply ceiling (C4) always applies.
- Respects the active SOC limit (R7) and C1."

create "UC05 — Guarantee the car is ready by departure" \
  "EV driver" "R5" "UC05-guarantee-ready-by-departure" \
  "no — this is the «extend» use-case (document urgency escalation once)" \
  "- Urgency escalation up to the maximum peak; never raises the active SOC limit.
- Deadline-unreachable notification when even the maximum rate cannot meet the deadline.
- Lists which use-cases it extends (UC01/UC02/UC03); consumes the departure-deadline rule (R14)."

create "UC06 — Store abundant solar by stepping up the limit" \
  "Household energy manager" "R8" "UC06-store-abundant-solar" \
  "light state model" \
  "- Applies only while charging in a solar mode; step size + interval; clamps to sc_max_solar_soc.
- References the active-SOC-limit rule (R7); extends UC01/UC02."

create "UC07 — Reserve capacity for tomorrow's solar" \
  "Household energy manager" "R9" "UC07-reserve-capacity-for-tomorrow" \
  "no" \
  "- Solar-reserve cap while the sun is down; suppresses low-tariff grid charging; a deadline may charge up to the cap but not beyond.
- Consumes the home-day flag set by UC08."

create "UC08 — Plan tomorrow's home day (evening prompt)" \
  "EV driver" "R13" "UC08-plan-tomorrow-home-day" \
  "light state model (prompt lifecycle)" \
  "- Actionable yes/no notification at a configurable time; timeout → treated as 'no'.
- Skipped if an external source already set the home-day flag; feeds UC07."

create "UC09 — Keep the charge limit in sync with the car" \
  "EV driver" "R6" "UC09-sync-charge-limit-with-car" \
  "no" \
  "- Bidirectional sync; reset to default on unplug; never change while away (C2); adopt the user's manual change."

create "UC10 — Remind me to plug in" \
  "EV driver" "R12" "UC10-remind-to-plug-in" \
  "light state model (reminder de-dup)" \
  "- Single reminder within the lead time of departure (resolved via R14); de-dup until reconnect/disconnect."

echo "Created UC02–UC10 backlog issues (label: uc). Add the 'needs-draft' label to start one."
