# ADR-0027: Table-driven linear step sequence for the nine-step, topic-grouped config flow

Date: 2026-08-21
Status: Accepted

## Context

[ADR-0025](0025-config-flow-branching-structure.md) decided *how* the config flow's branching is
expressed against Home Assistant's config-flow API, and chose a single ordered table of gated steps
per flow plus one shared dispatcher. It decided that against the step model
[UC12](../analysis/use-cases/UC12-configure-installation-through-guided-flow.md) held at the time:
seven steps — a `core` step carrying the mappings and four enablement decisions, capability-gated
`solar`, `captar` and `deadline` steps, an election-gated `vehicle_limit` step, and two ungated
catch-all steps (`mappings`, `thresholds`) that absorbed every field no capability owned.

UC12 has since been rewritten around a different organising principle, and that rewrite is what
motivates revisiting the decision:

- **The step set is now nine steps, grouped by installation topic rather than by capability.** In
  fixed order: `core`, `grid`, `ev_charger`, `vehicle`, `power`, `captar`, `solar`, `deadline`,
  `notifications`. The first five are ungated and shown on every install path; the last four are
  gated on their capability. `captar` now precedes `solar`, reversing their previous relative order.
- **The two ungated catch-all steps are gone.** Every field `mappings` and `thresholds` held has
  been redistributed onto a topic step — grid fields to `grid`, charger fields to `ev_charger`,
  EV/battery fields to `vehicle`, `Power`-mode fields to `power`, notification fields to the new
  `notifications` step, and the smoothing window into `core`. There is no longer any step whose
  membership rule is "whatever did not fit elsewhere". Two fields land on a step for the first time
  rather than moving onto one — the solar-production mapping and the `Power`-mode cooldown, which
  the seven-step model never presented at all (UC12's postconditions name both).
- **`vehicle_limit` is gone as a step.** UC12 4a turns the vehicle-charge-limit question from a
  step-level election asked on the first step into a plain field on the always-shown `vehicle`
  step, with the car-at-home mapping becoming required by a *field-level* rule on that same step
  (when a charge limit is mapped, or when the deadline capability is declared present). The one
  step-level gate that was not a capability flag therefore disappears.
- **A fourth capability, `notifications`, exists**, and unlike the other three it defaults to
  *absent* (UC12's "Requirements satisfied" section explains why). It owns step 9.
- **The EV state-of-charge mapping is now asked unconditionally on `vehicle`.** ADR-0025 had to
  carry a special mechanism for it — present it on whichever of `solar`/`captar` ran first and
  suppress it on the second. With the field on an ungated step, that mechanism has nothing to do.
- **Peak-protection fields moved under the CapTar gate** (UC12 5b), and the external home-day
  mapping under the deadline gate (UC12 5c) — both fields that the previous model presented
  ungated. This is a behaviour change UC12 owns; the consequence for *this* ADR is only that the
  gated tables carry more fields than they did.
- **The three flows' relationship to the table changed shape.** ADR-0025 could express "reconfigure
  stops before the last step" as a single gate on the `thresholds` row. Now two steps — `power` and
  `captar` — are threshold-only and so must be absent from the reconfigure walk, while every other
  step has both halves; and the options flow walks threshold halves of all five ungated steps plus
  the four gated ones, where before it walked three gated steps plus one catch-all.

The forces that shaped ADR-0025 are otherwise unchanged and are not re-derived here: Home Assistant
still offers exactly two branching primitives (`async_show_form` collects data, `async_show_menu`
turns a selection into a navigation act); the branch conditions are still persisted R18 capability
flags living in the config-entry data bucket ([ADR-0005](0005-config-entry-structure-and-interval.md));
UC12 still mandates a fixed order and complete traversal rather than user-chosen navigation; the
storage boundary still does not move, so answers must still accumulate across steps and be split
once at a single terminal call; UC12 still states extensibility as a postcondition; and Home
Assistant still forces the options flow into a separate handler class.

Two things make this a supersede rather than an edit. First, ADR-0025's reasoning is written in
terms of the old step identities, not merely illustrated by them — its extensibility argument turns
on inserting a step "after steps 3–5 and before step 6", and its validation-locality consequence
names "the vehicle-charge-limit step" as a guard's owner. Neither anchor exists any more. Second,
ADR-0001's immutability rule forbids editing an Accepted ADR's Context/Decision/Consequences to
reflect a change of fact. So the question this ADR answers is: **given the nine-step topic-grouped
model, is the table-driven linear sequence still the right structure, and what does its
implementation now owe?**

## Considered options

### Option A — Keep ADR-0025's decision and its seven-step table

Leave the structure and the tables as ADR-0025 specified and as
`custom_components/smart_charging/config_flow.py` already implements them, and treat UC12's rewrite
as unimplemented.

- Pro: Zero change; the implemented flow works, is tested, and produces a correct config entry.
  It is the baseline every other option pays its cost against.
- Con: It is the model UC12's rewrite exists to replace, so it fails the postconditions UC12 now
  states — most concretely, `mappings` and `thresholds` still ask for peak-protection and home-day
  fields UC12 now gates, and still ask the user for fields grouped by "leftover" rather than by
  topic. It also leaves the ADL asserting a step model no analysis document describes, which is the
  documentation failure the supersede mechanism exists to prevent.

### Option B — Linear `async_step_*` sequence, each step naming its own successor

One `async_step_*` method per UC12 step, with each method deciding inline which step comes next —
e.g. `power` checks the CapTar flag, else solar, else deadline, else notifications, else finish.

- Pro: Uses only `async_show_form`, keeps each step's successor visible in the step that owns it,
  needs no indirection to read (the traversal is the call graph), and is the most conventional shape
  in the Home Assistant ecosystem.
- Con: The gating logic is duplicated once per possible predecessor. The nine-step model does not
  make this *larger* — the seven-step model already had four consecutive gated steps
  (`solar`, `captar`, `deadline`, `vehicle_limit`), and the count of gate tests a hand-chained
  version must spell out is the same ten in both models (`power`, `captar`, `solar` and `deadline`
  must each know every later gate, exactly as `core`, `solar`, `captar` and `deadline` had to
  before). What changes is the *failure mode*, and it changes for the worse. In the seven-step
  model the gated block was followed by the always-reachable `mappings` and `thresholds` steps, so a
  forgotten branch meant a capability's fields silently never rendered while the flow still ran to
  completion and created a correct-shaped entry. In the nine-step model the gated block
  (`captar`, `solar`, `deadline`, `notifications`) is the tail, with nothing always-reachable behind
  it: a forgotten branch has no later step to fall through to, so the worst case is a chain that
  terminates early rather than one that merely skips a screen. Either way the duplication is what
  makes UC12's extensibility postcondition — a new capability appended after steps 6–9 with no
  change to any other step — unsatisfiable, since the new step's gate would have to be added to each
  of its four possible predecessors. And in both models the shape fails silently: nothing raises
  when a successor condition is missing.

### Option C — Linear `async_step_*` sequence driven by one ordered, gated step table

One `async_step_*` method per UC12 step, plus a single ordered table of `(step_id, gate)` entries
per flow and one shared "advance to the first later step whose gate passes" dispatcher. Every step
method ends by calling the dispatcher; answers accumulate in one flow-instance dict.

- Pro: The fixed order and the gates are one declarative list, so UC12's extensibility postcondition
  holds by construction — a new capability is one table row plus one step method, appended after the
  existing gated rows, with no existing step touched. The ungated steps are simply rows whose gate is
  a constant, so the five-ungated/four-gated split needs no second mechanism. It uses
  `async_show_form` throughout, matching what the steps do; the three flows differ only in which
  table they walk and which half of each step's schema they render; and it is the shape the codebase
  already uses for this kind of repetition (`coordinator.py`'s `simple_reads` table). It is also
  already implemented and under test, so this ADR's change reduces to the tables' contents and the
  step methods, not the mechanism.
- Con: The traversal is hand-rolled control flow Home Assistant neither provides nor checks. A step
  method absent from its table is silently unreachable — a risk that grows with nine steps rather
  than seven — and reading one step method no longer tells you what follows it. It also keeps
  flow-instance accumulator state whose lifetime and shape every step must respect.

### Option D — Home Assistant's native `async_show_menu` branching

After the ungated steps, `async_show_menu` offers the capability steps as menu items; each selection
resolves to that step's method, and a "done" item finishes the flow.

- Pro: The branch mechanism is the framework's own — no traversal code to write, test, or keep in
  sync — and it gives the user free navigation, including revisiting a step without restarting.
- Con: A menu selection is navigation, not an answer, and the branch conditions are R18 capability
  flags that must be persisted to the data bucket (ADR-0005). The flags would still need a form,
  leaving the user to state the same fact twice, or be inferred from which items were visited, which
  cannot distinguish "solar absent" from "solar not visited yet". The `notifications` capability
  sharpens this: defaulting to absent is a *stored* fact about a household that never engaged with
  the question, and a menu cannot record a decision the user did not make. A menu also cannot be
  prefilled from an existing entry as UC12 1a requires of `core`'s declarations, gives no guarantee
  every enabled step was completed before "done", and cannot express the fixed order at all. This
  assessment is unchanged from ADR-0025's; the nine-step model only strengthens it, since five of
  the nine steps are ungated and would sit outside the menu entirely.

### Option E — Hybrid: menu for capability selection, linear substeps within each capability

`async_show_menu` for the capability-selection screen; a linear `async_step_*` chain behind each
selection.

- Pro: Confines the menu to the one screen that is arguably a choice while keeping per-capability
  content linear, and would pay off if a capability ever owned several steps — more plausible now
  that `captar` carries the cooldown, the peak-protection switch and four peak-protection thresholds,
  and `solar` carries a dozen fields.
- Con: It inherits every one of Option D's structural problems on the screen that matters (the flags
  still are not captured by a selection, still cannot be prefilled, still impose no completion or
  ordering guarantee) while adding a second branching mechanism. And it still buys nothing today: no
  capability in UC12's nine-step model owns more than one step, so every substep chain it introduces
  has length one — `captar`'s and `solar`'s field counts argue for splitting a step, which Option C
  does with an extra table row, not for a second branching primitive.

### Option F — Derive the traversal from the schema fragments instead of a step table

Drop the explicit table and compute the step order and gates from the per-step schema fragments —
e.g. a registry mapping each step id to its mapping-half and threshold-half schema, from which
"which steps does this flow show" falls out (a step with no mapping half is absent from reconfigure,
a step whose capability flag is false is absent everywhere).

- Pro: Removes the duplication the nine-step model introduces, where a step's existence is asserted
  once in the table and again in its schema fragments — and it makes UC12's two new derived rules
  ("`power` and `captar` never appear in reconfigure because they have no mapping half"; "the
  options flow shows threshold halves only") true by construction rather than by a hand-written gate
  that could disagree with the schemas.
- Con: It conflates two things UC12 keeps separate: *whether* a step runs (a capability decision)
  and *what* it renders (a schema decision) — and it only actually eliminates the table for the
  second. The four capability gates (`captar`, `solar`, `deadline`, `notifications`) are not
  derivable from schema shape at all: a capability flag is a value in the config-entry data bucket
  (ADR-0005), not a property of a schema fragment, so no amount of inspecting fragments can tell you
  whether step 7 runs for *this* entry. Only the mapping-half-presence question ("which fields does
  this step's schema happen to include", which decides reconfigure's subset) falls out of the
  schemas. Option F would therefore still need a per-step capability declaration sitting alongside
  the schema-derived part — the harder half of the duplication it promises to remove survives it,
  and with it the premise of the option. It also makes the fixed order
  implicit in a registry's declaration order, which is a weaker guarantee than an ordered table the
  tests can assert against directly, and it discards a working, tested mechanism for a speculative
  gain.

## Decision

**Option C, unchanged in mechanism.** The install/reconfigure flow and the options flow remain
linear sequences of `async_show_form` steps — one `async_step_*` method per UC12 step, one ordered
table of gated steps per flow, one shared dispatcher advancing to the first later step whose gate
passes, one flow-instance accumulator, one terminal split. What this ADR changes is the *content* of
that structure: the nine-step topic-grouped model replaces the seven-step model ADR-0025 was written
against.

The menu-based options remain ruled out by what the branch conditions *are* rather than by
ergonomics, exactly as ADR-0025 found — and the `notifications` capability, whose absent-by-default
value must be stored for a household that never touched the question, makes Option D's
infer-from-navigation fallback less viable than before, not more. Option E still lands that mismatch
on the screen where it does damage.

Between the linear shapes, C is still preferred to B for the same reason ADR-0025 preferred it, and
the new model does not change the size of B's per-predecessor duplication — the seven-step model had
the same four consecutive gated steps and the same ten gate tests. What the new model changes is
where a mistake lands: the gated block is now the tail of the flow, with no always-reachable step
behind it to absorb a forgotten branch. UC12's restated extensibility postcondition ("appended after
the existing capability-gated steps (6–9), with no change to the fields or order of any other step")
remains the decisive point, and it is exactly what B cannot deliver. Option F is rejected as the more
interesting alternative it is: it would make two of UC12's derived rules structural, but it leaves
the capability gates — the half of the duplication that actually costs something — undelivered, and
it trades a tested mechanism for a speculative one. The duplication it does remove is cheap to pin
with the table tests this decision already requires.

Option C's own cost is accepted and restated, now larger: traversal is hand-rolled control flow no
framework check covers, and at nine steps a row omitted from a table is unreachable in a way nothing
raises. That is discharged by test obligation (see Consequences).

Five points follow directly and are part of this decision rather than of its implementation:

1. **Validation is step-local, and one guard becomes field-local.** Each coupling guard belongs to
   the step presenting the field it protects and runs on that step's submission. Two of them are now
   *unconditional required fields* rather than guards at all: the EV state-of-charge mapping is a
   plain `vol.Required` on the ungated `vehicle` step (asked always, UC12 postcondition), and the
   solar-forecast mapping is a plain `vol.Required` on the capability-gated `solar` step. The
   car-at-home mapping is the one genuine guard that survives: it is required on the `vehicle` step
   when a vehicle charge-limit mapping is filled in **or** the deadline capability was declared
   present on `core` (UC12 4a) — a rule that reads one field submitted on this step and one answer
   already in the accumulator from step 1, and reports its error on the `vehicle` step, never at the
   end of the flow.
2. **Answers accumulate in flow-instance state; the storage boundary does not move.** Unchanged from
   ADR-0025: each step merges its validated `user_input` into one flow-instance dict; the terminal
   step applies the data/options split to that accumulated dict at the single `async_create_entry`
   (install) or `async_update_reload_and_abort` (reconfigure) call; the accumulator holds only this
   run's answers, so abandoning discards them (UC12's abandonment exception); reconfigure prefill is
   rendering-only, via `add_suggested_values_to_schema`, and never seeds the accumulator — which is
   what keeps a just-disabled capability's stale mapping fields from surviving the save.
3. **Reconfigure's step subset is a per-step gate, not a stop condition.** ADR-0025 could express
   "reconfigure stops before the threshold step" as one gate on one row. It cannot now: `power` and
   `captar` are threshold-only and must be skipped in reconfigure mode, while every other step has a
   mapping half and must be shown (subject to its capability gate). Each such row therefore carries a
   gate conjoining its capability condition with "this flow mode renders a half this step has". The
   install and reconfigure paths still share one table and one set of step methods, with the flow
   mode selecting which half of each step's schema is rendered.
4. **The options flow keeps its own table.** Its gates read the *stored* capability flags rather than
   answers collected this run, its steps carry threshold halves only, and it writes only options
   (UC12 1b) — so it walks a separate table in its own handler class, reusing the same per-step
   threshold sub-schemas. It now walks the threshold halves of all five ungated steps plus the four
   gated ones, and it is the only flow that presents the control interval, which UC12 1b places on
   the `core` step's threshold half (install defaults it; reconfigure touches no options).
5. **The three framework-mandated entry points survive and delegate.** `async_step_user` (install),
   `async_step_reconfigure` (reconfigure) and `async_step_init` (options) are fixed by Home
   Assistant, so "one `async_step_*` method per UC12 step" still does not mean one method for step 1:
   the two config-flow entry points set the flow mode and delegate into a shared `core`
   implementation, and the options flow's table walk begins at `async_step_init`. Every later step id
   is the integration's own.

This ADR **supersedes ADR-0025**, whose Status is updated accordingly. ADR-0005's data/options
boundary and ADR-0008's reload-on-change behaviour both stand exactly as written, and ADR-0004's
owned-entity list is untouched — the seed-value fields UC12 4b describes still only initialise owned
entities.

## Consequences

- **ADR-0025 is superseded in full.** Its Status becomes `Superseded by ADR-0027` and its ADL row is
  updated to match, in this same change; its Context, Decision and Consequences are left exactly as
  written, per ADR-0001's immutability rule. No other *ADR* cites ADR-0025, but the approved
  implementation spec `docs/plans/2026-08-13-guided-config-flow-design.md` does, and makes
  "ADR-0025 reaching Accepted" its slice gate, barring any task from being committed against a
  superseded ADR-0025 — so merging this change puts that spec's own gate condition on a superseded
  record. Re-pointing that gate (and the spec's ADR-0025 citations) at ADR-0027 is a small follow-up
  update the spec owes once this ADR is Accepted; it is named here, not attempted here. Where this
  ADR restates ADR-0025's reasoning unchanged (the menu options, the accumulator,
  the framework-mandated entry points), the restatement — not the superseded record — is what
  applies from here.
- **The implementation has not caught up, and this ADR does not pretend otherwise.**
  `custom_components/smart_charging/config_flow.py` on `main` implements ADR-0025's *seven*-step
  model: `_TableWalkMixin` with `INSTALL_STEP_TABLE` and `OPTIONS_STEP_TABLE`, step methods
  `async_step_core`/`solar`/`captar`/`deadline`/`vehicle_limit`/`mappings`/`thresholds`, and
  `UC12_FIXED_STEP_ORDER` spelling out the old order. `const.py` correspondingly defines
  `STEP_CORE`, `STEP_SOLAR`, `STEP_CAPTAR`, `STEP_DEADLINE`, `STEP_VEHICLE_LIMIT`, `STEP_MAPPINGS`
  and `STEP_THRESHOLDS`, and no `notifications` capability flag exists (`const.py` has
  `CONF_SOLAR_AVAILABLE`, `CONF_CAPTAR_AVAILABLE` and `CONF_DEADLINE_AVAILABLE` only). Migrating the
  flow onto the nine-step model is therefore **outstanding implementation work**, to be planned and
  tracked as its own task set; until it lands, the shipped flow follows ADR-0025's superseded model.
  The mechanism this ADR re-affirms is already built, so that work is confined to the tables, the
  step methods and the schema fragments — plus a mechanical re-citation pass: roughly fifty
  docstring and comment references to "ADR-0025" live in `config_flow.py`, `const.py`,
  `tests/test_config_flow.py` and `tests/test_config_flow_translations.py`, including a test named
  `test_adr0025_every_config_table_step_has_a_step_method`, and all of them must come to name
  ADR-0027 instead.
- **The step constants and the fixed-order constant change.** `STEP_VEHICLE_LIMIT`, `STEP_MAPPINGS`
  and `STEP_THRESHOLDS` lose their steps; `STEP_GRID`, `STEP_EV_CHARGER`, `STEP_VEHICLE`,
  `STEP_POWER` and `STEP_NOTIFICATIONS` are added; `UC12_FIXED_STEP_ORDER` becomes the nine-step
  order with `captar` before `solar`. A `notifications` capability flag and its default (absent,
  unlike the other three) must be added alongside `CONF_SOLAR_AVAILABLE` and friends.
- **The schema fragments are re-cut along topic lines.** Today's fragments are cut per capability
  plus two catch-alls (`_solar_mapping_schema`, `_solar_threshold_schema`,
  `_captar_mapping_schema`, `_captar_threshold_schema`, `_deadline_threshold_schema`,
  `_ungated_threshold_schema`). The nine-step model needs one mapping fragment and one threshold
  fragment per step that has each half — with `power` and `captar` threshold-only and no step
  mapping-only — so `_ungated_threshold_schema`'s contents disperse across `core`, `grid`,
  `ev_charger`, `vehicle` and `power`, and new `notifications` fragments appear. Two fragments get
  simpler: `_solar_mapping_schema` and `_captar_mapping_schema` lose their `include_ev_soc`
  parameter entirely, since the EV state-of-charge field moves to `vehicle`. One new mapping
  fragment is not a flat field list: UC12 2 puts the low-tariff mapping's own state-translation
  table on the `grid` step beside the mapping itself, presented only when the mapped entity does not
  already report on/off — the single place where a step's mapping half is conditionally shaped by
  another field submitted on that same step, and therefore the one fragment whose construction is
  not a straight per-topic re-cut.
- **Two guard helpers dissolve; one moves and gains a condition.** `_ev_soc_missing_error` and
  `_solar_forecast_missing_error` have no remaining job — each becomes a plain `vol.Required` on a
  step that is always shown, respectively always shown when it applies — and the once-only-across-
  two-steps bookkeeping around the EV state-of-charge field disappears with them.
  `_car_home_missing_error` survives on the `vehicle` step but must now fire on the deadline
  capability as well as on a filled-in charge-limit mapping (UC12 4a), reading the former from the
  accumulator.
- **The options-bucket intersection rule still holds, over a larger key set.** `OPTION_KEYS` must
  continue to be consumed by *intersection* with the accumulator, never by indexing every key: with
  four gated steps rather than three, more threshold keys can legitimately be absent from a given
  install. `_split_data` survives unchanged as an exclusion filter at the terminal step.
- **Translations are re-cut, and grow.** `strings.json` and `translations/en.json`/`nl.json` need one
  step block per step id in both the `config` and `options` sections — nine ids rather than seven,
  with `vehicle_limit`, `mappings` and `thresholds` blocks removed and `grid`, `ev_charger`,
  `vehicle`, `power` and `notifications` blocks added. Install and reconfigure continue to share
  `config.step.*` blocks, so each step's title and description must still read correctly in both a
  first-install and an edit-my-mappings context.
- **The test obligation grows with the table.** Every step method must be pinned reachable from its
  table, and every capability combination — now sixteen, since `notifications` is a fourth
  independent flag — must be shown to traverse exactly the steps UC12 prescribes, in order, for each
  of the three flows. Per [ADR-0009](0009-testing-strategy.md) these are HA-harness tests. Cases must
  also cover the reconfigure subset explicitly (that `power` and `captar` never appear), the
  field-level car-at-home rule in both of its triggering conditions, and that the control interval
  appears on the options flow only.
- **No config-entry migration and no `VERSION` bump from the step restructuring itself.** No key
  changes name, type or bucket because a field moved between steps; the key *set* narrows further
  than before, which is safe only because every consumer reads options defensively via
  `opts.get(<key>, DEFAULT_...)`. Two changes do have data effects and are UC12's, not this ADR's:
  the new `notifications` flag is a key entries created before it will not have (defaulting absent
  on read), and CapTar-gating the peak-protection fields means an existing non-CapTar entry keeps
  stored values no flow can reach any more (UC12 5b). Entries created before this change may lack
  fields a step now presents as required; the reconfigure flow repairs them, and no automatic
  migration is introduced.
- **What becomes easier.** Adding a field is now a question with an obvious answer — which topic does
  it belong to — where the seven-step model routinely answered "the catch-all step", and the
  catch-alls' disappearance removes the only steps whose membership rule was not stateable.
- **What becomes harder.** The tail of the table is four gated steps deep, so a contributor reading
  one step method is further than ever from seeing what follows it, and the reconfigure gate now
  conjoins two conditions per row rather than testing one. `captar` and `solar` are large steps, and
  nothing in this structure prevents them from growing further; splitting one later is an extra table
  row, but the decision of when to split is not made here.
- **What this forecloses.** With step gating carrying the capability coupling, a required-field rule
  spanning two capabilities still cannot be an end-of-form check; it must attach to whichever step
  runs last among those it constrains, or motivate a step of its own. UC12 4a is the boundary case
  already in the model — a rule that reads an earlier step's answer but reports on its own step —
  and it is the pattern any future cross-step rule should follow.
