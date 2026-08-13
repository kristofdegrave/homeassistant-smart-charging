# ADR-0025: Table-driven linear step sequence for the capability-gated config flow

Date: 2026-08-13
Status: Proposed

## Context

[UC12](../analysis/use-cases/UC12-configure-installation-through-guided-flow.md) settled the
user-facing shape of the install, reconfigure and options flows: a first step that collects the core
mappings together with four enablement decisions, a fixed-order run of per-capability steps that
appear only when their enablement was answered "yes" (UC12 steps 3–6), then the two ungated steps
(UC12 steps 7 and 8), with the reconfigure and options variants (UC12 1a/1b) presenting
mapping-only and threshold-only subsets of that same step set. UC12 decides *what* the user sees.
This ADR decides *how* that branching is expressed against Home Assistant's config-flow API.

The implementation it replaces is flat. `config_flow.py` builds
`USER_SCHEMA = MAPPING_SCHEMA.extend(_threshold_schema().schema)` and shows the whole thing in a
single `async_step_user` form; `async_step_reconfigure` shows all of `MAPPING_SCHEMA` at once, and
the options flow shows all of `_threshold_schema()` plus the control interval at once. Because every
field is on one screen, the cross-field coupling a capability implies is enforced *after* the whole
form is submitted, by `_ev_soc_missing_error`, `_solar_forecast_missing_error` and
`_car_home_missing_error`, combined in `_mapping_errors`. `_split_data` and `OPTION_KEYS` then split
the one submitted dict into the two buckets at the single `async_create_entry` call site.

The forces at play:

- **Home Assistant offers two branching primitives, and they mean different things.** A
  `config_entries.ConfigFlow`/`OptionsFlow` subclass implements one `async_step_<name>` coroutine per
  step. `self.async_show_form(step_id=..., data_schema=...)` renders a step that *collects data*;
  `self.async_show_menu(step_id=..., menu_options=[...])` renders a screen whose *selection is a
  navigation act* — the chosen item becomes the next `step_id`, so every menu item must be a real
  step method. Which primitive fits depends on whether the branch condition is itself a value the
  integration has to persist.
- **The branch conditions here are persisted configuration, not navigation.** The solar, CapTar and
  deadline capabilities are R18 capability flags stored in the config-entry data bucket (ADR-0005);
  the vehicle-charge-limit decision determines whether a mapping is stored at all. They must be
  captured as answers on a form regardless of how the user is subsequently routed.
- **UC12 mandates a fixed order and complete traversal, not user-chosen navigation.** Steps 3–6 run
  in that order, every enabled one is visited, and only the last step submits. The user is never
  asked to pick which branch to enter.
- **Submission is now spread over several steps, but the storage boundary is not moving.** ADR-0005
  fixed the data/options split and explicitly deferred "the config flow's step layout, schema
  validation details, or how the reconfigure flow re-validates entity/role resolution" — i.e. to this
  ADR. Whatever shape is chosen has to accumulate answers across steps and still perform exactly one
  `async_create_entry` (install) or `async_update_reload_and_abort` (reconfigure) at the end, with
  the same bucket boundary. Flow-handler instance attributes persist for the duration of one flow
  run, so an accumulator is available; the question is whether one is needed and what it holds.
- **Extensibility is a stated postcondition, not a wish.** UC12 requires that a capability added in a
  later release adds exactly one step, appended after steps 3–5 and before step 6, with no change to
  any existing step. A structure that satisfies UC12 today but makes the *next* capability edit two
  existing steps has not met the use-case.
- **The three flows overlap but are not the same step set.** Install shows mappings and thresholds;
  reconfigure (UC12 1a) shows the same steps' mapping fields only and skips step 8; options (UC12 1b)
  skips steps 1–7 entirely, shows threshold-only per-capability steps gated on the *stored*
  capability flags, has no vehicle-charge-limit step at all, and asks one field — the control
  interval — that no other flow asks. Home Assistant also forces the options flow into a separate
  handler class, so whatever mechanism is chosen has to work in two classes.

## Considered options

### Option A — Do nothing: keep the flat single-step flow

Leave `async_step_user`, `async_step_reconfigure` and the options flow as single screens, and keep
the coupling in `_mapping_errors` as end-of-form validation.

- Pro: Zero cost, zero risk, and no new mechanism. The flat form does produce a correct config entry
  today — every guard that must hold is enforced before `async_create_entry` runs, so nothing invalid
  is ever persisted — and one screen means one `strings.json` step block and no traversal logic that
  can strand a user on an unreachable step.
- Con: It is the shape UC12 exists to replace. Users are asked for fields their installation does not
  need (contradicting UC12's postcondition that no disabled capability's field is ever presented) and
  are told about a missing field only through an error that names one entry in a form of ~45, which
  is exactly the "hunt through a flat form for the field a cryptic error refers to" UC12's stakeholder
  section calls out. Rejecting it here is not a live trade-off — R20's acceptance criteria are already
  approved — but it is the baseline every other option is paying its complexity against.

### Option B — Linear `async_step_*` sequence, each step naming its own successor

One `async_step_*` method per UC12 step. Step 1 stores the four enablement answers on the flow
instance; each step method ends by deciding, inline, which step comes next — e.g. the solar step
checks the CapTar flag, else the deadline flag, else the vehicle-limit flag, else step 7.

- Pro: Uses only the primitive the steps actually need (`async_show_form`), keeps each step's
  successor visible in the step that owns it, and needs no indirection at all to read: the traversal
  is literally the call graph. It is also the most conventional shape in the Home Assistant
  ecosystem, so a contributor recognises it immediately.
- Con: The gating logic is duplicated once per predecessor. Every step that can precede the solar
  step has to know solar's gate condition, so UC12's extensibility postcondition fails: inserting a
  new capability step between steps 5 and 6 requires editing the tail of *every* step that could
  precede it, which is precisely the "no change to any existing step" property the use-case demands.
  The duplication is also a silent-failure shape — a successor chain that forgets one branch skips a
  step the user needed rather than raising anything.

### Option C — Linear `async_step_*` sequence driven by one ordered, gated step table

One `async_step_*` method per UC12 step, plus a single ordered table of `(step_id, gate)` entries and
one shared "advance to the first later step whose gate passes" dispatcher. Every step method ends by
calling the dispatcher rather than naming a successor; the enablement answers and every submitted
field accumulate in one flow-instance dict.

- Pro: The fixed order and the gates become one declarative list, so UC12's extensibility
  postcondition holds by construction — a new capability is one table row plus one step method, with
  no existing step touched — and the three flows differ only in which table they walk and which
  half of each step's schema they render. It uses `async_show_form` throughout, matching what the
  steps do (collect data), and follows a shape the codebase already uses for exactly this kind of
  repetition (`coordinator.py`'s `simple_reads` table over `(platform, suffix, value_type, setter)`).
- Con: The traversal is hand-rolled control flow that Home Assistant does not provide and cannot
  check. A step method that exists but is absent from the table is silently unreachable, and reading
  any single step no longer tells you what follows it — the order lives one indirection away, which
  costs a contributor a lookup that Option B's inline chain does not. It also introduces
  flow-instance accumulator state whose lifetime and shape must be defined and respected by every
  step, where the flat flow had one dict handed to it by the framework.

### Option D — Home Assistant's native `async_show_menu` branching

Replace the gating with a menu: after (or instead of) the core-mapping step, `async_show_menu`
offers the per-capability steps as menu items, and the user selects which to enter; each menu
selection resolves to the step method of that name, and a "done" item leads on to steps 7 and 8.

- Pro: The branch mechanism is Home Assistant's own — no traversal code to write, test, or keep in
  sync, since the framework maps the selection to the next step id directly — and it gives the user
  free navigation, including revisiting a capability's step without restarting the flow, which
  neither linear option offers.
- Con: A menu selection is navigation, not an answer, and this flow's branch conditions are R18
  capability flags that must be persisted to the data bucket (ADR-0005) — so the enablement decisions
  would still have to be collected on a form somewhere, leaving the user to state the same fact
  twice, or leaving the flags inferred from which menu items were visited, which cannot distinguish
  "solar absent" from "solar step not visited yet". A menu also cannot be prefilled from an existing
  entry the way UC12 1a requires of step 1's fields, gives no guarantee that every enabled
  capability's step was completed before the user picks "done" (UC12 requires complete traversal, not
  free navigation), and cannot express UC12's fixed order at all.

### Option E — Hybrid: menu for capability selection, linear substeps within each capability

Use `async_show_menu` for the capability-selection screen, and a linear `async_step_*` chain for the
steps behind each selected capability.

- Pro: Confines the menu to the one screen that is genuinely a choice while keeping the per-capability
  content linear, and would pay off if any capability owned several steps — a plausible future for a
  capability with more configuration than a page holds.
- Con: It inherits every one of Option D's structural problems on the screen that matters (the
  capability flags still are not captured by a menu selection, still cannot be prefilled for
  reconfigure, still impose no completion or ordering guarantee) while adding a second branching
  mechanism to learn and maintain — and it buys nothing today, because no capability in UC12 has more
  than one step, so the linear substep chains it introduces are all of length one.

## Decision

**Option C.** The install/reconfigure flow and the options flow are each implemented as a linear
sequence of `async_show_form` steps, one `async_step_*` method per UC12 step, with the branching
expressed as a single ordered table of gated steps per flow and one shared dispatcher that advances
to the first later step whose gate passes.

The menu-based options are ruled out by what the branch conditions *are* rather than by ergonomics:
`async_show_menu` models a user's navigation choice, and this flow's branch conditions are persisted
R18 capability flags that ADR-0005 places in the data bucket and that UC12 1a requires to be
prefillable and re-answerable. Option D's saved traversal code is therefore paid for twice over — the
flags need a form anyway, and the guarantees UC12 states (fixed order, complete traversal of every
enabled step) are exactly the guarantees a menu declines to make. Option E confines that mismatch to
one screen but still lands it on the screen where it does the damage, and adds a second mechanism for
a per-capability multi-step case that does not exist yet; when one arises, a capability's table row
can expand into several without revisiting this decision.

Between the two linear shapes, C is chosen over B specifically for UC12's extensibility
postcondition, which B cannot satisfy without editing existing steps — the one property the
use-case singles out as structural. C's own cost is accepted and stated: traversal becomes hand-rolled
control flow that no framework check covers, and a step omitted from its table is unreachable in a
way nothing raises. That is discharged by test obligation, not by hope (see Consequences), and it is
the same table-over-repetition trade the codebase already accepted in `_read_owned_entities`.

Four points follow directly and are part of this decision rather than of its implementation:

1. **Validation becomes step-local.** Each of the coupling guards moves to the step that presents the
   field it protects and runs on that step's submission — the EV state-of-charge and solar-forecast
   requirements inside the solar and CapTar steps, the car-at-home requirement inside the
   vehicle-charge-limit step. Because a capability's step is shown only when that capability is
   enabled, the requirement is expressed as a plain `vol.Required` on a step that only appears when
   it applies, and the combined post-submit `_mapping_errors` call disappears rather than moving.
2. **Answers accumulate in flow-instance state; the storage boundary does not move.** Each step
   merges its validated `user_input` into one flow-instance dict, and the terminal step applies the
   existing `_split_data`/`OPTION_KEYS` bucket split to that accumulated dict at the single
   `async_create_entry` (install) or `async_update_reload_and_abort` (reconfigure) call. The
   accumulator holds only the current flow run's answers — abandoning the flow discards it, which is
   what UC12's abandonment exception flow requires — and ADR-0005's bucket boundary is untouched:
   this ADR changes when fields arrive at the split, not which side of it they land on. Prefilling
   the reconfigure path (UC12 1a) is a *rendering-only* concern and does not seed the accumulator:
   each step is rendered with `self.add_suggested_values_to_schema(<step schema>, entry.data)`, as
   the flat flow already does, so the existing entry supplies suggested values on the form while the
   accumulator still holds nothing but what the user submitted this run. This is what keeps R20 AC7
   honest — declaring a previously-present capability absent means that capability's step is never
   shown, so its stale mapping fields are never submitted, never enter the accumulator, and are
   therefore dropped by `_split_data` rather than carried forward.
3. **The options flow gets its own table, not a shared one.** Its gates read the *stored* capability
   flags rather than answers collected in this run, its steps carry threshold fields only, it has no
   vehicle-charge-limit step, and it writes only options (UC12 1b) — so it walks a separate table in
   its own handler class, reusing the same per-capability threshold sub-schemas as the install flow's
   steps. The install and reconfigure paths, in contrast, share one table and one set of step
   methods, with a flow-mode flag selecting the mapping-only or mapping-plus-threshold half of each
   step's schema, since UC12 1a differs from the install flow only in which half is rendered and in
   stopping before step 8.
4. **The three framework-mandated entry points survive and delegate.** Home Assistant fixes the
   method name of each flow's *first* step — `async_step_user` (install), `async_step_reconfigure`
   (reconfigure) and `async_step_init` (options), as ADR-0005's consequences already record — so "one
   `async_step_*` method per UC12 step" must not be read as one method for UC12 step 1. Step 1 keeps
   two entry methods, `async_step_user` and `async_step_reconfigure`, which set the flow mode and
   then delegate into a single shared step-1 implementation before both continue into the same table
   walk; the options flow's table walk likewise begins at `async_step_init` rather than at its first
   gated step. Only these three names are framework-imposed; every later step id is the integration's
   own.

This ADR supersedes nothing. ADR-0005's data/options boundary and ADR-0008's reload-on-change
behaviour both stand exactly as written; ADR-0004's owned-entity list is untouched, and the seed
values UC12 3a describes still initialise owned entities as they do today.

## Consequences

- **`config_flow.py` is restructured, not extended.** `USER_SCHEMA` (the flat
  `MAPPING_SCHEMA.extend(_threshold_schema().schema)`) has no remaining caller and goes away;
  `MAPPING_SCHEMA` and `_threshold_schema()` must be broken into per-step fragments — a core-mapping
  fragment, one mapping fragment and one threshold fragment per capability, an ungated-mapping
  fragment and an ungated-threshold fragment — since the mapping-only (UC12 1a) and threshold-only
  (UC12 1b) variants of each per-capability step are built from opposite halves of the same step.
  `_split_data` survives unchanged and moves to the terminal step — it is an exclusion filter, so a
  narrower accumulator simply yields a narrower data bucket. `OPTION_KEYS` survives as a constant but
  its *consumption* cannot: today the terminal call is `options = {k: user_input[k] for k in
  OPTION_KEYS}`, direct indexing over a tuple that includes capability-gated keys
  (`CONF_SOLAR_START_THRESHOLD_W`, `CONF_SOLAR_HOLD_MIN`, `CONF_SOLAR_RESERVE_SOC`,
  `CONF_CAPTAR_COOLDOWN_MIN` and friends). Once a solar-disabled install never renders the solar
  step, those keys are absent from the accumulator and that comprehension raises `KeyError`, so the
  terminal step must build the options bucket by *intersection* — only the `OPTION_KEYS` actually
  present in the accumulator — rather than by indexing every key.
- **The three guard helpers are split, not relocated wholesale.** `_ev_soc_missing_error`,
  `_solar_forecast_missing_error` and `_car_home_missing_error` are each invoked today against a dict
  containing every field; step-local, each becomes a guard on its owning step whose capability
  condition is already satisfied by the step being shown at all. `_mapping_errors` — whose only job is
  to combine the three — has no step that needs all three and is deleted. `_ev_soc_missing_error`
  needs particular care: UC12 requires the EV state-of-charge mapping to be asked exactly once even
  when both solar and CapTar are enabled, so the field is presented on whichever of the two steps runs
  first and its guard must not re-ask on the second.
- **The accumulator needs a defined shape and a documented lifetime.** A flow-instance dict of the
  fields submitted *in this run*, starting empty, merged per step, consumed once at the terminal
  step. It is never seeded from the existing entry: reconfigure prefill happens at render time via
  `add_suggested_values_to_schema`, so a capability the user has just switched off contributes
  nothing to the accumulator and its stale mapping fields cannot survive the save (R20 AC7). It is
  per-flow-run state on a `FlowHandler` instance and must never be read as a substitute for the
  config entry.
- **Every step needs its own `strings.json` and `translations/en.json`/`nl.json` block.** Today there
  are three step blocks — `config.step.user`, `config.step.reconfigure` and `options.step.init`.
  Those become one block per step id, in both the `config` and `options` sections (Home Assistant
  namespaces those two, so the config and options handlers may reuse step ids), each carrying the
  title, description and per-field labels for the fields that step now owns. That namespacing does
  *not* separate install from reconfigure — both live under `config.step.*` — so decision point 3's
  choice to share step methods and step ids between them necessarily collapses today's separate
  `config.step.reconfigure` block: the two flows will present the same per-step title and description
  text, which must therefore be worded to read correctly in both a first-install and an
  edit-my-mappings context. That is a real editorial cost of sharing the table, accepted here as the
  price of not maintaining two parallel step sets. The existing
  field labels can be redistributed; the parenthetical "(required if Solar installed)"-style
  qualifiers in them become redundant once the field only appears when it is required, and should be
  dropped in the same change rather than left to contradict the new structure.
- **The test obligation this decision creates.** Option C's Con — an unreachable step — must be
  pinned by tests over the table itself, not only over individual paths: every step method reachable
  from its table, and every enablement combination traversing exactly the steps UC12 prescribes in
  the prescribed order. Per ADR-0009 these are HA-harness tests. Step-local validation needs a case
  per moved guard asserting the error is raised on its own step (and that the flow does not advance),
  replacing the current end-of-form cases; and the accumulator needs a case pinning that an abandoned
  flow writes nothing.
- **No config-entry migration and no `VERSION` bump.** No key changes name, type or bucket, so an
  entry created by the flat flow is read identically by the new one. The key *set* does narrow,
  though: a disabled-capability install now persists an options bucket missing that capability's
  threshold keys entirely — a shape the flat flow never produced, since it always wrote every
  `OPTION_KEYS` entry. That is safe only because every consumer already reads defensively, via
  `opts.get(<key>, DEFAULT_...)` rather than direct indexing, so an absent key resolves to its
  default exactly as a never-configured one would; the property is pre-existing, and this decision
  now depends on it. Entries created before this change may lack fields a capability's step now presents
  as required; the reconfigure flow (UC12 1a) is the path that repairs them, and no automatic
  migration is introduced.
- **What becomes harder.** Adding a *field* is no longer a one-line schema edit — it now requires
  deciding which step owns it, which is the point, but it is a decision the flat schema never forced.
  And the fixed order lives in the table rather than in the step methods, so a contributor reading one
  step method cannot see what follows it.
- **What this forecloses.** With step gating carrying the capability coupling, a future required-field
  rule that spans two capabilities cannot be expressed as an end-of-form check; it must either be
  attached to whichever step runs last among those it constrains, or motivate a step of its own.
