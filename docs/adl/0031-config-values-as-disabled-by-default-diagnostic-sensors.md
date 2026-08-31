# ADR-0031: Config-entry values also exposed as disabled-by-default diagnostic sensors

Date: 2026-08-31
Status: Proposed

## Context

Per [ADR-0005](0005-config-entry-structure-and-interval.md), every install-time threshold,
default, and declared capability (R18) lives only in the config entry — as **data** (entity-role
mappings, state-translation tables, capabilities) or **options** (thresholds/defaults, the control
interval) — with **no entity id at all**. `entity-catalog.md` is explicit about this: a
`config-data`/`config-options` row is reached only through the Configure/reconfigure flow (R20),
never presented on the runtime dashboard (R19). ADR-0005's Context notes that "a setting could in
principle be both a config-entry value and mirrored as an entity ([ADR-0004](0004-owned-vs-mapped-entities.md)
rejected that duplication for the settings in scope here)" — but that line is ADR-0005 describing
ADR-0004's reasoning as background, not itself an ADR-0004 Decision statement, and ADR-0004's own
Decision only enumerates the owned-entity population and its examples (mode/profile selectors, SoC
override, departure times, diagnostic readouts of *computed* cycle outputs) — it does not state
that no further owned entity may ever mirror a config-entry value. ADR-0004's Consequences say the
owned-entity list "will grow... new owned entities don't need a new ADR unless they change the
two-population boundary itself," which this decision does not: every sensor this ADR adds is still
an owned, integration-created entity, squarely inside ADR-0004's existing "owned control/diagnostic
entities" population.

What has actually changed is the motivating need. ADR-0004/0005 were written before any use-case
asked a household to check a config value without opening Configure. The household now wants to
*see* values like the grid supply ceiling or max charging current in the HA UI — on the dashboard,
in Developer Tools, or from an automation/template — without navigating to
Settings → Integrations → Smart Charging → Configure each time. `entity-catalog.md`'s Diagnostic
outputs section already establishes the precedent that a **computed** value earns a read-only
diagnostic sensor purely for observability (R19) — `sensor.smart_charging_effective_peak_limit`,
`sensor.smart_charging_solar_surplus_w`, etc. — without becoming a control input. The question this
ADR resolves is whether a **static, config-entry-sourced** value can earn the same treatment.

Two Home Assistant mechanisms are directly relevant here (developer docs, fetched 2026-08-31):

- `EntityCategory.DIAGNOSTIC` is defined for an entity that "exposes some configuration
  parameter or diagnostics... but does not allow changing it" (the docs' own examples are RSSI and
  MAC address) — a config value surfaced read-only is exactly this case, and this integration
  already uses the category this way for the computed diagnostics above.
  `EntityCategory.CONFIG` is the wrong category here since none of these values become
  user-editable through the new entity — the config flow remains the only way to change them
  (ADR-0005 is untouched by this decision).
- HA's device model represents "a physical device that has its own control unit, or a service" —
  not a mechanism for grouping entities by topic. `via_device` covers connectivity (hub and the
  devices behind it) and child devices cover physical composition (a power strip's outlets); neither
  fits splitting one logical charging installation into per-topic devices (Installation/EV/Solar/...).
  Splitting the existing single "Smart Charging" device by config area was raised and discounted on
  this basis before this ADR was drafted — it is not one of the options below because it fails HA's
  own device-modeling guidance outright, not because of a project-specific trade-off worth recording
  as Pro/Con.

The forces at play:

- **Visibility the household actually wants** vs. **entity-registry clutter**: `entity-catalog.md`
  currently lists roughly two dozen `config-options` rows plus four boolean capabilities in
  `config-data`; mirroring all of them as always-enabled sensors would roughly double the
  integration's entity count for every installation, most of whose households will never look at
  most of them.
- **Precedent already in this codebase**: `SolarSurplusSensor` (capability-gated) and
  [ADR-0028](0028-registry-level-disabling-for-capability-gated-entities.md)'s
  `sync_disabled_by` already establish disabled-by-default as this integration's answer to "this
  entity is not universally relevant, but some installations want it."
- **Which config-entry values are in scope.** Entity-role mappings and state-translation tables
  (also `config-data`) are per-installation hardware bindings, not simple scalar values — a sensor
  mirroring "which entity plays the `net_power` role" is a different, less clearly useful kind of
  diagnostic than "what is the grid supply ceiling," and is out of scope for this decision.

## Considered options

### Option A — Status quo: no entities for config-entry values

- Pro: Zero new entities, zero new maintenance surface; consistent with ADR-0004/0005's original
  scope, which never anticipated this need.
- Con: Does not meet the stated need at all — a household must still open Configure to check a
  single value, with no dashboard/automation/template access to it.

### Option B — HA's built-in diagnostics download (`diagnostics.py`)

- Pro: Zero entity footprint — a JSON snapshot of the full config entry (`data` + `options`),
  reachable from Settings → Devices & Services → Smart Charging → Download diagnostics; a standard,
  low-maintenance HA mechanism purpose-built for "let a user inspect the full config."
  Straightforward to add and keep in sync (one file, reads the same `SmartChargingConfig` these
  sensors would read).
- Con: Not a live, in-UI value — it's a manual, one-shot file download, not something the dashboard
  can show, an automation can trigger on, or a template can read. Does not satisfy the household's
  actual ask ("see it in the UI").

### Option C — One disabled-by-default diagnostic sensor per config-options value and per config-data capability boolean

- Pro: Matches `EntityCategory.DIAGNOSTIC`'s own definition exactly; each value becomes
  individually enable-able, graphable (state history), and usable from a dashboard, automation, or
  template — none of which Option B offers. Disabled-by-default (mirroring ADR-0028's existing
  pattern) means the clutter Option A avoids is opt-in per household, not automatic for everyone.
- Con: Roughly two dozen new sensor classes/tests to add and maintain, and every future
  `config-options` addition now also needs an explicit "does this get a sensor" call — the same
  kind of ongoing classification burden ADR-0005's own Consequences already named for the
  data/options split, now duplicated for this second axis.

### Option D — One (or a few) attribute-bundle sensor(s), values as attributes rather than separate entities

- Pro: A single new entity (or one per config area) instead of two dozen, avoiding both the
  clutter Option C's Con raises and the need for disabled-by-default at all.
- Con: Forfeits per-value enable/disable, per-value state history/graphing, and direct
  automation/template access by entity id — exactly what the household is asking for is to *see*
  individual values, not read them out of one entity's attribute dict. Unlike
  [ADR-0021](0021-adapter-readings-diagnostic-sensor.md)'s adapter-readings sensor — which chose
  the attribute-bundle shape specifically because its value set is dynamic and grows as adapter
  roles are wired, so no fixed list of columns could be enumerated in `entity-catalog.md` without
  drifting — the config-options/capability list here is fixed and known at code-time, so the
  argument that justified ADR-0021's shape does not carry over.

## Decision

Option C. Add one read-only diagnostic sensor (`entity_category=DIAGNOSTIC`), disabled by default
in the entity registry, per `config-options` value and per boolean capability currently in
`config-data`, joining the existing single "Smart Charging" device — no device split. Entity-role
mappings and state-translation tables stay out of scope (Context, above); this decision covers only
scalar `config-options` values and capability booleans.

Option C is chosen over Option A because Option A does not meet the household's stated need at all.
It is chosen over Option B because a diagnostics download cannot power a dashboard tile,
automation trigger, or template — the household explicitly wants in-UI visibility, not a one-shot
export. It is chosen over Option D because Option D forfeits the same
per-value enable/disable, history, and automation-usability that ADR-0028's disabled-by-default
precedent already shows this project values, and because — unlike ADR-0021's adapter-readings case
— the value set here is fixed and enumerable, so the attribute-bundle shape buys nothing that Option
C's per-value sensors don't already offer at the cost this ADR accepts (Option C's Con).

This does not supersede ADR-0004 or ADR-0005: ADR-0004's Decision already anticipates the
owned-entity list growing without a new ADR "unless [a change] change[s] the two-population
boundary itself," and every sensor this decision adds remains inside that same owned population.
ADR-0005's data/options placement of these values is untouched — they still live only in the
config entry as the authoritative value; the new sensors are read-only mirrors, never a second
place a value can be set. What this ADR does resolve is the specific question ADR-0005's Context
left as background reasoning rather than a formal Decision: whether a config-entry value may also
be mirrored as a diagnostic sensor. It may, under the scope and defaults (disabled-by-default, no
device split) this ADR decides.

## Consequences

- `entity-catalog.md`'s Diagnostic outputs section gains one row per new sensor (id, default
  registry-enabled state, unit, which `config-options`/`config-data` key it mirrors) — tracked as a
  follow-up `requirement`-labeled issue per `write-requirement`, once this ADR is Accepted; not
  part of this ADR's own PR.
- An implementation spec (`write-impl-spec`) is needed before any code lands: the concrete sensor
  list (every `config-options` row plus the four `config-data` capability booleans currently in
  `entity-catalog.md`), object-id/`unique_id` scheme, and how each sensor's `_attr_entity_registry_enabled_default = False`
  is wired — most likely a `_ConfigMirrorSensor` base in `sensor.py` reading from the entry's
  already-resolved `SmartChargingConfig` (`config.py`), analogous to `_CoordinatorFieldSensor`'s
  existing shape but sourced from config instead of the coordinator's per-cycle `CycleResult`.
- Every future `config-options` (or capability) addition must now also decide whether it gets a
  mirrored sensor — the same kind of per-setting classification call ADR-0005's Consequences
  already named for the data/options split, now duplicated for this second axis. Worth calling out
  explicitly in `write-requirement`/`write-adr` guidance so a new setting isn't silently skipped.
- Makes it easier for a household to answer "what is this installation currently configured to"
  from the dashboard or an automation, without opening Configure — the concrete goal this ADR
  exists to satisfy.
- Forecloses the attribute-bundle (Option D) and device-split alternatives for this specific need;
  either could still be revisited by a future ADR if the sensor count or maintenance burden Option
  C accepts turns out to be a real problem in practice.
