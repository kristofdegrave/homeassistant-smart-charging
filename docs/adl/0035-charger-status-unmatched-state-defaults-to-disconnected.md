# ADR-0035: Unmatched `charger_status` raw states default to disconnected, not fault

Date: 2026-09-04
Status: Accepted

## Context

The `charger_status` adapter role maps a household's charger connection-state entity to one
of three canonical values (`disconnected`/`connected`/`charging`, per the
[glossary](../analysis/system-overview.md#ubiquitous-language)). Both
[ADR-0003](0003-hardware-abstraction-adapters.md)'s Decision and
[ADR-0007](0007-fault-handling.md)'s Decision describe the config flow as letting the user
map *each* of their hardware's actual state strings to the three canonical states, and treat
a raw state with no translation-table entry as a fault, the same as a missing or unavailable
entity.

The shipped config flow's `ev_charger` step diverges from that: it collects exactly two
fields, `connected_states` and `charging_states` (comma-separated raw states);
`_build_translation()` in `config_flow.py` is the resulting translation table's only
producer, and it only ever assigns `STATE_CONNECTED` or `STATE_CHARGING` as values — there is
no third field through which a household names their charger's disconnected-state
vocabulary. `StatusReadAdapter.read()` (`adapters/status.py`) looks up the charger's raw
state in that table and returns whatever it finds, or `None` if the raw state has no entry;
per ADR-0007, that `None` forces 0 A and sets `Fault`.

Because no raw state is ever assigned to `disconnected` by either config-flow field, a
charger's genuine "unplugged" state is *itself* a raw state with no translation-table entry.
Every real disconnection therefore faults the control cycle instead of producing a
`disconnected` reading — on every installation, since the gap is structural, not a
per-household misconfiguration. This leaves `STATE_DISCONNECTED` (`const.py`) unreachable in
practice, even though it is real, referenced code — it is `CHARGEABLE_STATES`'s complement,
drives the disconnect transition in `managers/vehicle_limit.py` (charge-limit restore on
disconnect) and feeds `CHARGEABLE_STATES` membership checks throughout the coordinator and
mode logic — at minimum `managers/notification_manager.py` (plug-in reminder eligibility),
`coordinator.py` (EV SOC read gating, and `_dispatch_mode`'s per-cycle mode-state/has-charged
reset on any non-chargeable status), `coordinator_cycle.py` (R8 solar step-up gating), and
`modes/power.py` (0 A vs. the Power-mode target current) — and it is one of
`sensor.smart_charging_charger_status`'s three `ENUM` options per
[ADR-0034](0034-dedicated-charger-status-diagnostic-sensor.md), part of R19 AC1's "charger
status (connected/charging/disconnected)" dashboard requirement.

ADR-0034's own Consequences already documented the `None`-on-unmatched-state behavior as a
premise the new sensor had to render as "unknown" — that premise is exactly what this ADR
revisits.

[ADR-0009](0009-testing-strategy.md)'s Context carries the same expectation in passing, describing
an enum role's unmapped raw state as "the same case the error-handling decision … treats as
equivalent to a missing entity" — also narrowed by this ADR for `charger_status` specifically.
ADR-0009's Decision and Consequences (adapters are tested against four HA-state cases, including
unmapped-raw-state for enum roles) are otherwise unaffected: that test case still needs covering,
only the expected outcome changes.

This ADR covers only what an unmatched raw charger-status state means, for required roles whose
adapter faults on a missing/unmapped value per ADR-0007's general rule. It does not touch ADR-0007's
fault treatment of a missing or unavailable *entity* for this role, or documented non-fault
exceptions already in place for other roles (e.g. grid voltage's NF4 fallback and
`low_tariff`'s own default-to-negative behavior for an unmatched value — both unaffected).

## Considered options

### Option A — Add a third `disconnected_states` config-flow field

Mirror `connected_states`/`charging_states` with a third field, so a household explicitly
lists which raw states mean disconnected; a state matching none of the three fields would
still fault. This is also the option that requires no change to ADR-0003 or ADR-0007: it
completes the three-field, fully-authored translation table those decisions already
describe, rather than diverging further from it.

- Pro: Symmetric with the two existing fields — every canonical value has an explicit,
  household-authored source, so a charger firmware *error* state, or any other raw state a
  household never anticipated, still surfaces as `Fault` exactly as ADR-0007 intends, rather
  than resolving to a specific canonical value nobody chose.
- Con: Every existing and new installation must positively enumerate a disconnected
  vocabulary before the dashboard can ever show `disconnected` — the exact gap that made
  `STATE_DISCONNECTED` unreachable on every installation today would only close once a
  household does this extra step correctly; the failure mode (unplugged reads as `Fault`)
  stays the *default* experience rather than becoming impossible. It also adds a field to the
  `ev_charger` step, which is a step-table content change, not merely an adapter change
  (touches the step ADR-0027/ADR-0033 already shape).

### Option B — Unmatched raw state defaults to `disconnected` (chosen)

Change `StatusReadAdapter.read()` so a raw state that matches neither `connected_states` nor
`charging_states` resolves to `STATE_DISCONNECTED` instead of `None`. No config-flow change.

- Pro: Closes the gap for every installation immediately, including ones already configured
  — a charger's real disconnected state (whatever string it happens to be) reaches
  `disconnected` without any household needing to re-visit Configure. Matches the practical
  shape of the vocabulary: a charger has a small, enumerable set of connected/charging states
  and a much larger, harder-to-enumerate set of ways it reports "not plugged in" (vendor
  firmware differences, idle/off/standby-style strings) — the axis where "everything else"
  is the natural default already runs through this integration's own precedent: the
  `low_tariff` adapter role (NF3) treats every raw state not on its own single positive list
  as "not low tariff" rather than asking for an exhaustive enumeration, and `adapters/tariff.py`
  documents that as a deliberate, restrictive default for a present-but-unmatched state.
- Con: Reverses ADR-0003's and ADR-0007's fault-on-unmatched-charger-status-state clauses,
  and the regression is not limited to a slow failure signal for typos. `disconnected` is not
  an inert reading: every `CHARGEABLE_STATES` membership check throughout the coordinator and
  mode logic treats it identically to a genuine unplug — including, non-exhaustively, the
  disconnect transition in `managers/vehicle_limit.py`, plug-in-reminder eligibility in
  `managers/notification_manager.py`, EV-SOC read gating and the per-cycle mode-state/
  has-charged reset in `coordinator.py`, R8 solar step-up gating in `coordinator_cycle.py`,
  and Power mode commanding 0 A instead of its target current in `modes/power.py`. So a raw
  state that should have matched `connected_states`/`charging_states` but doesn't — whether
  from a typo, an unanticipated firmware string, or (more seriously) a charger *error/fault*
  state the household never listed anywhere — no longer just fails to raise `Fault`; every
  cycle it persists, it emits a positive, wrong `disconnected` reading that drives all of the
  above as if the car had genuinely been unplugged.

### Option C — Keep today's behavior (do nothing)

Leave `StatusReadAdapter.read()` as is: any raw state outside `connected_states`/
`charging_states`, including the charger's real disconnected state, faults the cycle.

- Pro: No ADR, no code change; ADR-0003 and ADR-0007 stay exactly as decided.
- Con: `STATE_DISCONNECTED` remains practically unreachable and R19 AC1's dashboard
  requirement stays unmet for the disconnected case, on every installation, indefinitely.

## Decision

Option B. Option A avoids the Con Option B accepts — it would keep every unmatched state,
including a real charger error, surfacing as `Fault` rather than a wrong domain reading — but
its own Con is disqualifying: it leaves the exact symptom this ADR exists to fix (a real
disconnect reading as `Fault`) as the out-of-the-box default for every installation until a
household completes an additional, easy-to-skip config step, merely making the fix
*possible* rather than making the bug *impossible*. Option C simply accepts that symptom
permanently.

Option B's Con — a wrong `disconnected` reading (not just a slower failure signal) for any
unmatched state, including charger error states — is accepted for two reasons. First, its
scope is narrow: only `charger_status`, and only the "not connected and not charging" branch,
which per the `low_tariff` precedent is exactly the shape of vocabulary this integration
already treats as an open, default-to-negative set rather than an enumerable one — a
charger's "connected"/"charging" vocabularies are both config-flow-authored and small and
stable per charger, unlike its disconnected/idle/error vocabulary. Second, the mitigation
Option A would buy (charger error states still fault) is judged to matter less than closing
the structural, universal gap immediately; a cheaper partial mitigation for the same
regression — logging once per distinct unmatched raw state, so a household can notice and
correct an unanticipated string even though it no longer faults — is left to the
implementation spec (see Consequences) rather than adopted as a design change here.

This narrows [ADR-0003](0003-hardware-abstraction-adapters.md)'s Decision ("a raw state with
no entry in the translation table … is treated the same as an unavailable entity"),
[ADR-0007](0007-fault-handling.md)'s Decision ("for charger status specifically, a raw state
with no translation-table entry — is treated as a fault" — and, as a consequence, ADR-0007's
next sentence, "Grid voltage is the one documented exception, per NF4," is no longer a
complete enumeration of ADR-0007's exceptions to the general fault rule), and
[ADR-0009](0009-testing-strategy.md)'s Context (the same expectation, stated in passing) to the
case where the entity itself is present and reporting: that case now resolves to
`STATE_DISCONNECTED`, not `None`/`Fault`. None of the three ADRs is superseded outright — all
keep `Accepted` status and every other clause intact, per this project's precedent for a
narrowing that leaves the rest of an ADR standing (the same pattern ADR-0033 used against
ADR-0027). ADR-0034's Consequences description of a `None`-on-unmatched-state reading (which it
said the sensor must render as "unknown") is likewise narrowed: it applies from now on only to
the missing/unavailable-*entity* branch; ADR-0034's actual decision (a dedicated sensor) is
unaffected. A missing or unavailable `charger_status` *entity* (the adapter's `state is None`
branch) is untouched by this ADR: that case still returns `None` and still faults, per
ADR-0007's general rule for every required role.

## Consequences

- `StatusReadAdapter.read()` (`adapters/status.py`) changes so that when `state.state` has no
  entry in `self._translation`, it returns `STATE_DISCONNECTED` rather than `None`; the
  `state is None` (missing/unavailable entity) branch is unchanged.
- `docs/adl/README.md`'s rows for ADR-0003, ADR-0007, ADR-0009, and ADR-0034 gain a note that
  this ADR narrows the clause or premise each of them carries; all four ADRs' own Status lines
  and bodies stay unedited, per this project's ADR-immutability rule.
- Follow-up documentation pass (via the standard `write-requirement` flow, before any code
  change): `docs/analysis/entity-catalog.md`'s `charger_status` adapter-role row, and its
  `sensor.smart_charging_charger_status` row (whose Default/range/source cell currently says
  "unknown when that reading is absent — unmapped or unavailable raw state (ADR-0007
  semantics)", which becomes wrong for the unmapped-but-present case). `docs/analysis/
  system-overview.md`'s `charger status` glossary entry is the natural home for stating the
  new default-to-disconnected rule itself, mirroring how its `low-tariff flag` entry already
  documents that role's analogous "every other raw state" default. ADR-0034's own ADR body
  (like ADR-0003's, ADR-0007's, and ADR-0009's) is not edited by this documentation pass, per
  ADR-immutability — only `docs/adl/README.md`'s title cells (above) point at this ADR.
- Implementation (the `adapters/status.py` change; test coverage for "raw state matches
  neither list → disconnected, not fault"; and a decision on whether to log once per distinct
  unmatched raw state, so a household can discover an unanticipated firmware string even
  though it no longer faults) needs its own implementation-spec/TDD-plan follow-up via
  `write-impl-spec`, gated on the documentation pass above landing first, per this project's
  analysis-first methodology.
- A raw state that should have matched `connected_states` or `charging_states` but doesn't —
  a typo, an unanticipated firmware string, or a charger error/fault state never listed
  anywhere — now resolves to `disconnected` instead of `Fault`, for as long as it persists.
  Because `disconnected` drives every `CHARGEABLE_STATES`-gated behavior (non-exhaustively:
  the disconnect transition in `managers/vehicle_limit.py`, plug-in-reminder eligibility in
  `managers/notification_manager.py`, EV-SOC read gating and mode-state reset in
  `coordinator.py`, R8 solar step-up gating in `coordinator_cycle.py`, and Power mode's 0 A
  command in `modes/power.py`), this is a behavioral regression for that case on every cycle
  it persists, not just a slower failure signal — accepted per the Decision above.
