# ADR-0034: Dedicated diagnostic sensor for the `charger_status` role (extends ADR-0021)

Date: 2026-09-01
Status: Accepted

## Context

[ADR-0021](0021-adapter-readings-diagnostic-sensor.md) surfaces every currently-wired *read*
adapter role as an attribute of one owned diagnostic sensor,
`sensor.smart_charging_adapter_readings`, rather than as one entity per role. Its Decision
accepted the resulting loss of per-role recorder history explicitly and conditionally: nothing in
scope at the time asked for history or graphing of an individual role, and "if a future dashboard
need requires that for one specific role, applying Option A's mechanism to just that one role (a
dedicated first-class sensor for it) is the appropriate follow-up then, not a blanket decision
now." This ADR is that follow-up, for exactly one role.

Three forces have since made `charger_status` the one role that clears that bar:

- **`charger_status` is synthesized here, not passed through.** Most wired read roles mirror a
  number or state the household already owns as an HA entity (`net_power`, `charger_power`,
  `grid_voltage`, `ev_soc`, `ev_battery_capacity`, `solar_forecast`, `departure_external`).
  `charger_status` is instead the output of a mapping this integration performs:
  `adapters/status.py` applies the user-supplied state-translation table
  (`CONF_STATUS_TRANSLATION`, built in the config flow from `CONF_CONNECTED_STATES` /
  `CONF_CHARGING_STATES`) to the raw charger entity's state, yielding the canonical
  `disconnected`/`connected`/`charging` vocabulary `system-overview.md`'s glossary and
  `entity-catalog.md`'s `charger_status` row define, or `None` when the raw state is unmapped or
  unavailable (ADR-0007's fault signal). That canonical value exists nowhere in the household's own
  entity set — only inside this integration's process. It is not the *only* role whose adapter
  normalizes: `adapters/tariff.py` resolves `low_tariff` through a user-supplied raw-state list
  (`CONF_LOW_TARIFF_STATES`) and `adapters/presence.py` maps `car_home`'s state to a boolean. What
  separates `charger_status` from those is not the presence of a translation but its shape and its
  audience — a three-valued domain vocabulary the analysis documents name and that a requirement
  asks to be *shown*, where the other two collapse to a boolean that a template can re-derive from
  the raw entity in one line.
- **R19 AC1 asks for the canonical value and does not currently get it.** R19's first acceptance
  criterion requires the dashboard show "charger status (connected/charging/disconnected)". The
  shipped dashboard (`dashboard.py`'s `_charging_status_cards`, per
  `2026-08-11-runtime-dashboard-design.md`'s entity table) binds that tile to
  `entry.data[CONF_CHARGER_STATUS_ENTITY]` — the household's **raw** charger entity, in whatever
  hardware-specific vocabulary that entity speaks (`B2`, `Charging`, `ready_to_charge`, …). The
  design doc justifies that binding on the grounds that the role is "a **required** role, always
  mapped" — i.e. the raw entity is reliably *present*, not that its vocabulary is the right one to
  show; the same document separately notes that `adapter_readings` is "a timestamp-plus-attributes
  diagnostic blob, not a tileable single value," so no tileable carrier of the canonical value
  existed to bind instead. Reading those two together, the shipped tile is a raw-upstream-entity
  binding of exactly the kind ADR-0021's own Option B was rejected for — that inference is this
  ADR's, not a conclusion the design doc draws.
- **Recorder history and `state_changed` triggering are only available to a state, not an
  attribute.** A household automation that should fire when the charger becomes `connected`, or a
  history view of when the car was plugged in, cannot be written against
  `adapter_readings`' attribute blob: HA's recorder does not index attributes as independently
  queryable series, and `state_changed` on `adapter_readings` fires every control cycle (its state
  is the read timestamp), so it carries no usable signal about this one role.

Whatever this decision adds must stay inside the frame ADR-0021 set, not reopen it. That frame is
the "no new HA entities for hardware inputs" reading of NF3 — NF3's own text says only that all
charging-logic I/O goes through adapter roles rather than raw device entities; the
no-new-entities gloss is ADR-0003's, deliberately preserved by ADR-0021, and it is a constraint on
*mirroring hardware inputs*, which is not obviously what a value this integration computes is. A
counterweight has also appeared since: ADR-0031 added a diagnostic sensor per config-entry value
(35 of them, disabled by default) after reasoning explicitly about when ADR-0021's attribute-bundle
shape does and does not carry over — so the "each new entity is expensive clutter" premise
ADR-0021's Option A was rejected on has already been revisited once, for a category of value that,
unlike this one, no requirement asks to display.

There is also a naming hazard to weigh: `sensor.smart_charging_status` already exists and means
something entirely different — ADR-0007's integration-health Fault/OK readout — a confusion the
runtime-dashboard design doc already had to call out in prose.

The other wired read roles were reviewed against the same three forces and none clears them.
`net_power`, `charger_power`, `grid_voltage`, `ev_soc`, `ev_battery_capacity`, `solar_forecast`,
`low_tariff`, `departure_external` and `sun` are bundled in `adapter_readings` today and are
either passthroughs or boolean/scalar reductions the household can already graph, trigger on, and
put on a card via the upstream entity. `charger_current`, `car_home`, `vehicle_charge_limit` and
`home_day_external` are in `const.py`'s `ROLES_ADAPTER_READINGS_EXCLUDED` — they have no bundled
attribute form at all, deliberately (write-only from the control cycle's perspective, or read by a
Manager outside it), so promoting one would be a new decision about *that* exclusion rather than an
application of ADR-0021's exception clause, and nothing asks for one. Two roles have no reading to
promote either way: `solar_power`, listed in `entity-catalog.md` but not yet wired by
`adapters/factory.py`, and `monthly_peak_external`, decided by ADR-0030 (as
`ROLE_MONTHLY_PEAK_EXTERNAL`) but likewise not yet wired there.

## Considered options

### Option A — Status quo: leave the dashboard bound to the raw charger-status entity

Change nothing. `charger_status` stays an `adapter_readings` attribute only; the dashboard tile
keeps showing the household's raw charger entity, and an automation wanting the canonical value
re-implements the translation table itself in a template.

- Pro: Zero cost, no new entity, no further bend of ADR-0003's no-new-entities gloss, and the tile
  does show *a* charger status — a household that recognizes its own charger's vocabulary can read
  it fine.
- Con: Leaves R19 AC1 satisfied only in the loosest reading (the value shown is not the
  canonical vocabulary the criterion names), keeps the shipped dashboard non-portable across
  installations with different charger hardware — the exact regression ADR-0021's Option B was
  rejected for — and forces any automation on charger status to duplicate the translation table
  the integration already owns, where it will silently drift when the household reconfigures the
  mapping.

### Option B — Derive the value in the dashboard/automation layer from the attribute

Keep the attribute as the only carrier and read it where needed: a `state_attr(...)` template in
the tile card, and a household-authored template sensor for anyone needing history or a trigger.

- Pro: No new owned entity at all, and it does put the canonical vocabulary on the tile — the
  attribute is already the translated value, so nothing has to be re-derived.
- Con: Pushes the integration's own domain vocabulary into dashboard templates and household YAML,
  where `adapter_readings`' attribute-key set is an implicit public contract nothing tests; a
  household still cannot get history or a `state_changed` trigger without hand-writing a template
  sensor per install, which is precisely the per-install work an integration-owned entity exists
  to remove. It also makes the tile depend on the attribute blob whose state changes every control
  cycle, so the card re-renders at the control interval regardless of whether the status changed.

### Option C — One dedicated first-class diagnostic sensor for `charger_status` only

Add a single owned entity, `sensor.smart_charging_charger_status` (ADR-0004's owned population,
`entity_category: diagnostic`, `object_id` pinned per ADR-0013), whose state is the canonical
`disconnected`/`connected`/`charging` value the status adapter produced on the most recent read,
sourced from the same per-cycle reading the coordinator already performs and written through RA3's
Store (ADR-0018) alongside the other owned diagnostic entities in ADR-0006 step 10 — the same path
ADR-0021 uses for `adapter_readings`. Every other role stays bundled in `adapter_readings` exactly
as ADR-0021 decided — this invokes ADR-0021's own single-role exception clause rather than amending
its mechanism.

Two `object_id`s are available for it, and the choice is part of this option rather than an
implementation detail, because it is what decides whether Option C's naming Con below actually
bites:

- `charger_status` (→ `sensor.smart_charging_charger_status`) — the name the role already carries
  in `const.py`, `entity-catalog.md` and the glossary, at the cost of sitting one word from
  `sensor.smart_charging_status`.
- `diag_charger_status` (→ `sensor.smart_charging_diag_charger_status`) — the
  `sensor.smart_charging_diag_<role>` shape ADR-0021's own rejected Option A proposed, which
  removes the collision outright, at the cost of introducing a `diag_` prefix no owned entity uses
  today (`entity_category: diagnostic` already carries that information in the UI) and of naming
  the entity differently from the role every other document calls `charger_status`.

- Pro: Gives the canonical value a tileable state with recorder history and `state_changed`
  triggering, closes R19 AC1 against the integration's own vocabulary instead of a specific
  charger's, restores hardware-agnosticism for the one dashboard tile that lost it, and costs one
  entity — one `strings.json` entry, one pinned `object_id`, one set of tests — that does not grow
  as more roles are wired.
- Con: Adds one entity mirroring an adapter-role value, which is the direction ADR-0003's
  no-new-entities gloss points away from even if this value is computed rather than a raw hardware
  input. Under the first `object_id` above it also introduces a sensor whose name is one word away
  from `sensor.smart_charging_status` (ADR-0007's Fault/OK health readout) — a confusion the
  runtime-dashboard design already had to warn about in prose, and one the code makes concrete:
  `sensor.py` already has `ChargingStatusSensor` with `_object_id_suffix = "status"`, and
  `dashboard.py` already has a `_charging_status_cards` function that means the *section*, not this
  value. And it creates a value that exists in two places at once (state and `adapter_readings`
  attribute), so any future change to the value's semantics has two writers to keep consistent.

### Option D — Promote every wired read role to its own sensor (ADR-0021's Option A, wholesale)

Rather than singling out one role, give every wired read role its own diagnostic sensor and reduce
or retire `adapter_readings`.

- Pro: Uniform and predictable — no per-role judgment call about which value deserves an entity,
  and every role gets history and triggering, not just this one.
- Con: Re-litigates a decision ADR-0021 took on its merits, at the cost it named: one entity per
  wired role (double digits today, growing), each with its own translation entry, pinned
  `object_id`, and tests, for values that are overwhelmingly passthroughs of entities the household
  already owns — a maintenance cost disproportionate to an observational need, and a much larger
  reversal of ADR-0003's no-new-entities gloss than the one identified gap requires. ADR-0031
  softens but does not remove this: the sensors it added are disabled by default precisely so 35
  new entities cost the household nothing until asked for, whereas the roles here would be
  enabled-by-default dashboard-facing entities.

## Decision

Option C. Option A's Con is a real, already-diagnosed gap: R19 AC1 names the canonical vocabulary,
and the shipped tile does not show it — with the portability loss ADR-0021 explicitly refused to
accept as permanent. Option B addresses the tile but not the history/trigger half of the need, and
pays for it by promoting `adapter_readings`' attribute-key set into an untested public contract
that household YAML depends on. Option D's Con is the ADR-0021 trade-off itself, unchanged and
still valid — this decision deliberately does **not** disturb it. Option C's own Cons are accepted:
the one-entity move away from ADR-0003's no-new-entities gloss is confined to a single role whose
value this integration computes and that a requirement asks to display, which is a narrower step
than the one ADR-0031 already took for values no requirement displays at all.

Of Option C's two `object_id` candidates, `charger_status` is chosen. The `diag_` form removes the
naming collision, but at the price of being the only owned entity with such a prefix and of
diverging from the name `const.py`, `entity-catalog.md` and the glossary already use for this
value — a permanent, every-reader cost to avoid a one-time confusion that a catalog row, distinct
translated display names, and the `entity_category` shown in the UI address directly. The collision
is therefore mitigated by documentation rather than by renaming; the concrete code-level traps it
creates are listed in the Consequences below so the implementation does not walk into them.

ADR-0021 is **extended, not superseded**: its Decision already anticipated exactly this
single-role follow-up, and its mechanism (one diagnostic sensor whose attributes cover whichever
read roles are wired) remains in force for every other role. Accordingly, `charger_status` also
stays in `adapter_readings`' attributes: removing it was considered and rejected, because the
attribute set is derived from whichever read roles are wired rather than from a curated list, so
carving out one key would add a special case to ADR-0021's mechanism — and would break any
consumer already reading that attribute — in exchange for cosmetic de-duplication. The duplication
is accepted, with the constraint that both surfaces are fed from the same cached reading so they
can never disagree.

This ADR records the decision only; the sensor itself is implementation work tracked separately,
per ADR-0021's own precedent.

## Consequences

- `entity-catalog.md` needs a new row under the owned control/diagnostic entities section for
  `sensor.smart_charging_charger_status`, describing it as the canonical translated charger state
  (`disconnected`/`connected`/`charging`) and distinguishing it from the existing
  `charger_status` **adapter role** row (the mapping input) and from
  `sensor.smart_charging_status` (ADR-0007 health) — tracked as follow-up via the standard
  `write-requirement` flow, not done in this ADR.
- `object_id` for this entity (`charger_status`) must be pinned per ADR-0013 from the start, via
  the same `_object_id_suffix` mechanism `sensor.py`'s existing owned sensors use, with a new
  `OWNED_SUFFIX_*` constant alongside the others in `const.py` — not left to
  translated-name-derived naming.
- Two existing names in the code mean something else and must not be reused or shadowed:
  `sensor.py`'s `ChargingStatusSensor` (`_object_id_suffix = "status"`) is ADR-0007's health
  readout, and `dashboard.py`'s `_charging_status_cards` names the dashboard *section*, not this
  value. The new class and its translation strings need names that keep those three apart at a
  glance.
- ADR-0004's owned-entity list gains this one entity; ADR-0004 itself is not edited (it is
  `Accepted` and immutable) — its Consequences already allow the owned-entity inventory to grow
  without a new ADR unless the two-population boundary changes, and this addition does not change
  that boundary.
- The entity is a diagnostic readout, not runtime configuration: it must **not** carry
  `LABEL_SC_RUNTIME` (no owned sensor does today), so it never appears in the dashboard's
  label-driven "Runtime settings" section, and R19's "no install-time configuration on the
  dashboard" rule is untouched.
- Implementation follow-up (via the normal `write-impl-spec`/task-plan flow, not this ADR): the
  runtime dashboard's charger-status tile — `dashboard.py`'s `_charging_status_cards`, currently
  `_tile(entry.data[CONF_CHARGER_STATUS_ENTITY])` — should bind to the new sensor instead, closing
  the R19 AC1 gap this ADR's Context describes. The raw entity remains the *mapping* input either
  way; only the tile's binding changes. The new binding is recorded in whichever impl spec makes
  the change, not by rewriting `2026-08-11-runtime-dashboard-design.md`'s entity table — that
  document is a dated record of a completed slice, and at most gains a pointer forward.
- The new sensor's state and `adapter_readings`' `charger_status` attribute must be fed from the
  same cached reading, so the two can never report different values for the same cycle. This is
  cheap for this role specifically: `coordinator.py`'s required-role read already assigns
  `self._role_readings[ROLE_CHARGER_STATUS]` on every cycle that reaches that assignment,
  including when the reading is `None` because the raw state is unmapped or the entity is
  unavailable, so no new read, cache entry, or retain-last special case is introduced (ADR-0021's
  retain-last behaviour applies to *optional* roles that may go unread on a cycle, e.g. `ev_soc`
  while disconnected — not to this one). The one case that does not reach the assignment is the
  adapter's own `read()` raising outright: the cache then keeps the prior cycle's value rather
  than advancing to `None`, same as any other unhandled exception funneling to `_async_update_data`'s
  fault path — a pre-existing, narrow staleness window this decision does not change or need to
  close, since both surfaces still read the one shared cache either way.
- What the implementation spec must settle explicitly is how a `None` reading presents. The adapter
  returns `None` both when the raw entity is missing/unavailable/unknown and when its raw state has
  no entry in the translation table, and this role's `None` also faults the cycle (ADR-0007). The
  sensor must map that to an unknown state rather than inventing a canonical value, and must not
  make the entity itself `unavailable` — UC11's exception flow requires the rest of the dashboard to
  keep rendering. Note the resulting, deliberate asymmetry with the bundle: on a faulted cycle
  `adapter_readings`' `charger_status` attribute is already this cycle's `None` while its own state
  (`_role_readings_at`) intentionally does not advance, so the bundle's timestamp refers to an
  earlier successful cycle than its attribute values — the new sensor has no such split and should
  not try to reproduce one.
- Choosing HA's `enum` device class for this sensor (with the three canonical states as its
  `options`) is the natural fit and would give translated state names, but it also constrains the
  state to exactly those options — the implementation spec owns that call together with the
  unknown-state semantics above. Long-term statistics are not available for a non-numeric sensor
  either way; recorder history and `state_changed` triggering, which are what this decision is
  for, are.
- This decision sets the bar for any *future* single-role promotion rather than opening the door
  generally. Both halves must hold: the role's value is **not** obtainable from an entity the
  household already owns (a translated domain vocabulary, not a boolean or scalar a one-line
  template could re-derive from the raw entity), **and** a requirement or use-case asks for that
  value to be displayed, historised, or triggered on. The second half is what does the work: no
  other role wired today meets it, including `low_tariff` and `car_home`, whose adapters also
  normalize. Wiring `solar_power` or `ROLE_MONTHLY_PEAK_EXTERNAL` does not by itself earn either
  one a sensor.
