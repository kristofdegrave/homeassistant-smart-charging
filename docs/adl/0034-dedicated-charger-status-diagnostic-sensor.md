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

- **`charger_status` is synthesized here, not passed through.** Every other wired read role
  mirrors a number or state the household already owns as an HA entity (`net_power`,
  `charger_power`, `grid_voltage`, `ev_soc`, `ev_battery_capacity`, `vehicle_charge_limit`,
  `solar_forecast`, `low_tariff`, `car_home`). `charger_status` is the output of a mapping this
  integration performs: `adapters/status.py` applies the user-supplied state-translation table
  (`CONF_STATUS_TRANSLATION`, built in the config flow from `CONF_CONNECTED_STATES` /
  `CONF_CHARGING_STATES`) to the raw charger entity's state, yielding the canonical
  `disconnected`/`connected`/`charging` vocabulary `system-overview.md`'s glossary and
  `entity-catalog.md`'s `charger_status` row define, or `None` when the raw state is unmapped or
  unavailable (ADR-0007's fault signal). That canonical value exists nowhere in the household's own
  entity set — only inside this integration's process.
- **R19 AC1 asks for the canonical value and does not currently get it.** R19's first acceptance
  criterion requires the dashboard show "charger status (connected/charging/disconnected)". The
  shipped dashboard (`dashboard.py`'s `_charging_status_cards`, per
  `2026-08-11-runtime-dashboard-design.md`'s entity table) binds that tile to
  `entry.data[CONF_CHARGER_STATUS_ENTITY]` — the household's **raw** charger entity, in whatever
  hardware-specific vocabulary that entity speaks (`B2`, `Charging`, `ready_to_charge`, …). The
  design doc chose that binding explicitly, on the grounds that `adapter_readings` "is a
  timestamp-plus-attributes diagnostic blob, not a tileable single value" — i.e. because no
  tileable carrier of the canonical value existed, not because the raw entity was the right
  value. The same document also records that binding dashboard tiles to raw upstream entities is
  the hardware-agnosticism regression ADR-0021's own Option B was rejected for.
- **Recorder history and `state_changed` triggering are only available to a state, not an
  attribute.** A household automation that should fire when the charger becomes `connected`, or a
  history view of when the car was plugged in, cannot be written against
  `adapter_readings`' attribute blob: HA's recorder does not index attributes as independently
  queryable series, and `state_changed` on `adapter_readings` fires every control cycle (its state
  is the read timestamp), so it carries no usable signal about this one role.

Whatever this decision adds must stay inside the frame ADR-0021 set, not reopen it: NF3's "no new
HA entities for hardware inputs" framing (established by ADR-0003, deliberately preserved by
ADR-0021) is only tolerable to bend where the value is genuinely this integration's own output.
There is also a naming hazard to weigh: `sensor.smart_charging_status` already exists and means
something entirely different — ADR-0007's integration-health Fault/OK readout — a confusion the
runtime-dashboard design doc already had to call out in prose.

The other wired read roles were reviewed against the same three forces and none clears them: each
is a passthrough the household can already graph, trigger on, and put on a card directly, with no
demonstrated need beyond the bundled attribute form. `solar_power` is listed in
`entity-catalog.md` but not yet wired by `adapters/factory.py`, so it has no reading to promote
either way.

## Considered options

### Option A — Status quo: leave the dashboard bound to the raw charger-status entity

Change nothing. `charger_status` stays an `adapter_readings` attribute only; the dashboard tile
keeps showing the household's raw charger entity, and an automation wanting the canonical value
re-implements the translation table itself in a template.

- Pro: Zero cost, no new entity, no further bend of NF3's framing, and the tile does show *a*
  charger status — a household that recognizes its own charger's vocabulary can read it fine.
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
sourced from the same per-cycle reading the coordinator already performs and written through the
same path as the other owned diagnostic sensors. Every other role stays bundled in
`adapter_readings` exactly as ADR-0021 decided — this invokes ADR-0021's own single-role exception
clause rather than amending its mechanism.

- Pro: Gives the canonical value a tileable state with recorder history and `state_changed`
  triggering, closes R19 AC1 against the integration's own vocabulary instead of a specific
  charger's, restores hardware-agnosticism for the one dashboard tile that lost it, and costs one
  entity — one `strings.json` entry, one pinned `object_id`, one set of tests — that does not grow
  as more roles are wired.
- Con: Bends NF3's "no new entities for hardware inputs" framing one entity further than ADR-0021
  did, and introduces a second sensor whose name is one word away from
  `sensor.smart_charging_status` (ADR-0007's Fault/OK health readout), a confusion the
  runtime-dashboard design already had to warn about in prose and which this entity makes easier
  to hit. It also creates a value that exists in two places at once (state and
  `adapter_readings` attribute), so any future change to the value's semantics has two writers to
  keep consistent.

### Option D — Promote every wired read role to its own sensor (ADR-0021's Option A, wholesale)

Rather than singling out one role, give every wired read role its own diagnostic sensor and reduce
or retire `adapter_readings`.

- Pro: Uniform and predictable — no per-role judgment call about which value deserves an entity,
  and every role gets history and triggering, not just this one.
- Con: Re-litigates a decision ADR-0021 took on its merits barely a month earlier, at the cost it
  named: one entity per wired role (double digits today, growing), each with its own translation
  entry, pinned `object_id`, and tests, for values that are overwhelmingly passthroughs of entities
  the household already owns — a maintenance cost disproportionate to an observational need, and a
  much larger reversal of NF3's framing than the one identified gap requires.

## Decision

Option C. Option A's Con is a real, already-diagnosed gap: R19 AC1 names the canonical vocabulary,
and the shipped tile does not show it — with the portability loss ADR-0021 explicitly refused to
accept as permanent. Option B addresses the tile but not the history/trigger half of the need, and
pays for it by promoting `adapter_readings`' attribute-key set into an untested public contract
that household YAML depends on. Option D's Con is the ADR-0021 trade-off itself, unchanged and
still valid — this decision deliberately does **not** disturb it. Option C's own Cons are accepted:
the one-entity bend of NF3's framing is confined to the single role whose value this integration
actually synthesizes rather than passes through, and the naming hazard against
`sensor.smart_charging_status` is mitigated by documentation and translated names, not by picking a
worse `entity_id` than the one `charger_status` is already called everywhere else in the analysis
docs.

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
  `_tile(entry.data[CONF_CHARGER_STATUS_ENTITY])` — should bind to the new sensor instead, and
  `2026-08-11-runtime-dashboard-design.md`'s entity table updated to match, closing the R19 AC1
  gap this ADR's Context describes. The raw entity remains the *mapping* input either way; only
  the tile's binding changes.
- The new sensor's state and `adapter_readings`' `charger_status` attribute must be fed from the
  same cached reading, so the two can never report different values for the same cycle.
- That shared cache carries a semantic the implementation spec must settle explicitly: ADR-0021's
  role-readings cache deliberately retains each role's **last known** value across cycles, so a
  charger entity that goes unavailable would leave the new sensor showing a stale state rather than
  an unknown one — acceptable for a bundled diagnostic attribute, more questionable for a dashboard
  tile and an automation trigger. Whichever behaviour is chosen (retain-last vs. resolve to
  unknown on an unreadable role), it applies to both surfaces identically, per the point above, and
  must not make the entity itself `unavailable` — UC11's exception flow requires the rest of the
  dashboard to keep rendering.
- Choosing HA's `enum` device class for this sensor (with the three canonical states as its
  `options`) is the natural fit and would give translated state names, but it also constrains the
  state to exactly those options — the implementation spec owns that call together with the
  unknown-state semantics above. Long-term statistics are not available for a non-numeric sensor
  either way; recorder history and `state_changed` triggering, which are what this decision is
  for, are.
- This decision sets the bar for any *future* single-role promotion rather than opening the door
  generally: a role earns its own sensor only when its value is synthesized by this integration
  rather than passed through from an entity the household already owns, and a requirement or
  use-case actually asks for it. No other role wired today meets that bar; `solar_power` will not
  meet it merely by being wired.
