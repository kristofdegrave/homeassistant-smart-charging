# C4 — Topic-grouped nine-step config flow (implementation design)

**Slice:** C4 — Install-time config flow / options flow, `docs/design/project-plan.md`, Phase 4.
Verbatim from that slice's entry:

> **Service:** Client, V14 (ADR-0003/0005). **Builds:** maps adapter roles, declares capabilities,
> sets install-time thresholds (data); tunes options anytime; triggers reload on change (ADR-0008).
> Holds no orchestration — writes only through the Store.
> **Depends on:** RA3 (Store data/options write), RA1 factory (role list to map). **ADR gate:** none
> new (its owned-entity *creation* is C2's concern; C4 writes config buckets).
> **Testable on its own:** HA harness — a full flow produces a valid config entry; an options change
> reloads the entry (ADR-0008).
> **Integration checkpoint:** ⎔ the entry C4 writes drives RA1's factory and the Store's data/options
> reads on setup.

**Issue:** #821 (epic #760).
**Model:** this document and its plan are authored on Opus (CLAUDE.md); the implementation
([`2026-08-25-topic-step-config-flow.md`](2026-08-25-topic-step-config-flow.md)) is executed on
Sonnet.

**Supersedes** [`2026-08-13-guided-config-flow-design.md`](2026-08-13-guided-config-flow-design.md)
and its plan [`2026-08-13-guided-config-flow.md`](2026-08-13-guided-config-flow.md), which describe
the **seven**-step, capability-grouped model of
[ADR-0025](../adl/0025-config-flow-branching-structure.md) (`_TableWalkMixin` with
`INSTALL_STEP_TABLE`/`OPTIONS_STEP_TABLE`, the `vehicle_limit`/`mappings`/`thresholds` steps, three
capability flags). ADR-0025 is itself superseded by
[ADR-0027](../adl/0027-config-flow-topic-step-structure.md) (Accepted). Neither superseded plan
document is edited; both stay as the record of what shipped.

**What this slice is.** The flow already exists as a *guided, table-driven* flow. This slice changes
neither the service, the call direction, nor any stored key's bucket: it re-cuts one existing Client
(`custom_components/smart_charging/config_flow.py`) from ADR-0025's seven capability-grouped steps
onto the nine **topic-grouped** steps
[UC12](../analysis/use-cases/UC12-configure-installation-through-guided-flow.md) and
[R20](../analysis/requirements.md#r20--guided-installation-configuration) now settle, keeping the
mechanism [ADR-0027](../adl/0027-config-flow-topic-step-structure.md) re-affirms (Option C —
one ordered gated table per flow, one shared dispatcher). Every behavioural fact below is cited;
none is decided here.

**ADR gate:** none outstanding. ADR-0027 is **Accepted** (#820, merged). Unlike the superseded
design, this slice has no ADR waiting on it, so project-plan C4's "ADR gate: none new" line is
accurate again as of ADR-0027's acceptance.

**Sources of truth (cited, never restated as this document's own):**

| Source | Owns |
| --- | --- |
| [UC12](../analysis/use-cases/UC12-configure-installation-through-guided-flow.md) | the nine steps, their contents, their fixed order, the three flows' variants (1a/1b), the alternate flows (4a/4b/5a/5b/5c), the exception flows, the postconditions |
| [R20](../analysis/requirements.md#r20--guided-installation-configuration) AC1–AC9 | the acceptance criteria this slice must satisfy |
| [R18](../analysis/requirements.md#r18--configurable-installation-capabilities) AC1–AC13 | the four capabilities, each capability's default (including notifications' default-**absent** exception), and the three per-notification enable toggles' conjunctive gating (AC11) |
| [ADR-0027](../adl/0027-config-flow-topic-step-structure.md) | Option C — the table-driven linear step sequence, its five decision points, its Consequences |
| [ADR-0005](../adl/0005-config-entry-structure-and-interval.md) | the data/options bucket boundary (unchanged by this slice) |
| [ADR-0008](../adl/0008-reconfigure-reload-behavior.md) | reload-on-change (unchanged by this slice) |
| [ADR-0009](../adl/0009-testing-strategy.md) | the test boundary — the config flow is HA-harness territory |
| [`entity-catalog.md`](../analysis/entity-catalog.md) | the key, bucket, unit and default of every configuration value the flow presents, and every adapter role it maps |

**A note on epic #760's own field list.** The epic body records the step model as first decided.
Where it and UC12 disagree, **UC12 wins** (the skill's "if a spec and its source disagree, the source
wins", and UC12 is the later, reviewed artifact). The five places they differ, each resolved in
UC12's favour below and listed here so the divergence is visible rather than silent:

| # | Epic #760 says | UC12 says (adopted) |
| --- | --- | --- |
| 1 | `control_interval_s` on step 1 | step 1 presents it on the **options flow only**; install defaults it (UC12 1b) |
| 2 | `nominal_voltage` on step 3 (`ev_charger`) | on step 2 (`grid`), beside the grid-voltage mapping it substitutes for (UC12 2, NF4) |
| 3 | `power_respect_peak` on step 5 (`power`) | on step 6 (`captar`), with the thresholds it switches (UC12 5b, R18 AC5) |
| 4 | step 6 omits `peak_floor_kw` | step 6 presents the **peak floor** too (UC12 6, R3) |
| 5 | step 9 "ungated" | step 9 is gated on the notifications capability (UC12 step table, R18 AC10) |

UC12 also names two solar thresholds the epic's step-7 list omits (`solar_only_hold_min`,
`solar_restart_debounce_min` — "the `Solar` and `SolarOnly` post-surplus hold durations … the
restart debounce duration"); both already exist as keys and both stay on the solar step.
`prompt_timeout_h` appears nowhere in this slice: it was reverted from the analysis documents
(#813) and from the code (#818), both merged.

---

## Success criteria

The slice is done when all of the following hold, each pinned by a named test in the paired plan:

1. **R20 AC1** — the first step (`core`) presents the **four** capability declarations and nothing
   else but the smoothing window; solar/CapTar/deadline default present, notifications defaults
   absent (R18 AC1/AC4/AC6/AC9). UC12 step 1.
2. **R20 AC2** — each capability declared present contributes exactly one further step, in UC12's
   fixed nine-step order (`captar` **before** `solar`); a capability declared absent contributes no
   step. Each amendment path counts only the steps its own half populates. UC12 step table, 5a.
3. **R20 AC3** — no field of an absent capability is ever presented, and the one optional mapping no
   capability gates (the vehicle charge limit) sits on the always-shown `vehicle` step and may be
   left blank. UC12 4a, 5a.
4. **R20 AC4** — the EV state-of-charge mapping is presented exactly once, on the always-shown
   `vehicle` step, **whatever the capability declarations** — including when neither solar nor CapTar
   is present. No field appears on two steps. UC12 postconditions.
5. **R20 AC5** — every ungated field sits on the step of its own concern, the external home-day
   mapping being the single named carve-out (deadline-gated, UC12 5c). The peak-protection fields are
   now on the CapTar-gated step and nowhere else (UC12 5b, R18 AC5).
6. **R20 AC6** — a domain-mismatched or blank required field is reported on the step that presents
   it and that step is re-shown; the car-at-home rule (UC12 4a) reports on the `vehicle` step in both
   of its triggering conditions, never at the end of the flow.
7. **R20 AC7** — reconfigure (UC12 1a) amends mappings and capability declarations, leaves the
   options bucket untouched, and never shows `power` or `captar` (neither has a mapping half); the
   options flow (UC12 1b) amends thresholds only, and is the only flow presenting the control
   interval. Withdrawing a capability drops that capability's mapping fields from data and leaves its
   stored options values untouched.
8. **R20 AC8** — abandoning any flow before its final step creates nothing and amends nothing.
   UC12 exception flows.
9. **R20 AC9** — a capability added later is one table row plus one step method, appended after rows
   6–9, changing no existing step. UC12 postconditions. Pinned by the extensibility test, the only
   way a closed capability set (R18 AC13) can exercise this criterion.
10. **R18 AC11** — the `notifications` step presents all three per-notification enable toggles,
    each defaulting **on**, stored in the options bucket, presented whatever the deadline capability
    declares (UC12 9). What each toggle *suppresses* is out of this slice (Deferrals).
11. The entry the flow produces is still ADR-0005-shaped: mappings, capability flags and the derived
    state-translation table in **data**; thresholds, defaults and seed values in **options** (UC12
    step 10); an options change still reloads the entry (ADR-0008).

---

## Structure

### Step ids and the two tables

Install and reconfigure **share one table and one set of step methods** (ADR-0027 point 3, point 5);
the options flow walks **its own table** in its own handler class (ADR-0027 point 4). Home Assistant
namespaces `config.step.*` and `options.step.*`, so the two tables reuse step ids freely.

`core` is the shared entry point both config-flow entry points delegate into (ADR-0027 point 5), so
it is deliberately **not** a `CONFIG_TABLE` row — exactly as today. It *is* an `OPTIONS_TABLE` row,
because the options flow's own entry point is `async_step_init`, which renders no form of its own.

Config table (`SmartChargingConfigFlow`), in UC12's fixed order:

| UC12 # | Step id | Gate | Install renders | Reconfigure renders |
| --- | --- | --- | --- | --- |
| 1 | `core` | entry point, always | mapping + threshold half | mapping half (prefilled) |
| 2 | `grid` | always | mapping + threshold half | mapping half |
| 3 | `ev_charger` | always | mapping + threshold half | mapping half |
| 4 | `vehicle` | always | mapping + threshold half | mapping half |
| 5 | `power` | flow mode is **not** reconfigure | threshold half | *skipped* — no mapping half (UC12 1a) |
| 6 | `captar` | `captar_available` answered this run **and** mode is not reconfigure | threshold half | *skipped* — no mapping half (UC12 1a) |
| 7 | `solar` | `solar_available` answered this run | mapping + threshold half | mapping half |
| 8 | `deadline` | `deadline_available` answered this run | mapping + threshold half | mapping half |
| 9 | `notifications` | `notifications_available` answered this run | mapping + threshold half | mapping half |

The two conjoined gates (`power`, `captar`) are exactly what ADR-0027 point 3 calls for: reconfigure's
subset is a per-step gate, not a stop condition, because the threshold-only steps sit in the *middle*
of the order rather than at its end.

Options table (`SmartChargingOptionsFlow`), gated on the **stored** capability flags (ADR-0027
point 4); threshold halves only:

| UC12 # | Step id | Gate | Rendered |
| --- | --- | --- | --- |
| 1 | `core` | always | smoothing window **+ the control interval** (UC12 1b) |
| 2 | `grid` | always | threshold half |
| 3 | `ev_charger` | always | threshold half |
| 4 | `vehicle` | always | threshold half |
| 5 | `power` | always | threshold half |
| 6 | `captar` | `entry.data.get(CONF_CAPTAR_AVAILABLE, DEFAULT_CAPTAR_AVAILABLE)` (`True`) | threshold half |
| 7 | `solar` | `entry.data.get(CONF_SOLAR_AVAILABLE, DEFAULT_SOLAR_AVAILABLE)` (`False`) | threshold half |
| 8 | `deadline` | `entry.data.get(CONF_DEADLINE_AVAILABLE, DEFAULT_DEADLINE_AVAILABLE)` (`True`) | threshold half |
| 9 | `notifications` | `entry.data.get(CONF_NOTIFICATIONS_AVAILABLE, DEFAULT_NOTIFICATIONS_AVAILABLE)` (`False`) | threshold half |

**Every options-flow gate reads defensively, with the named default spelled out above — never
`entry.data[<key>]`.** `notifications_available` is a *new* key (D-1), absent from every entry
written before this change, so bracket indexing would raise `KeyError` the first time an upgraded
installation opens Configure and a bare `.get(key)` would gate on `None`. The fallbacks are the
module `DEFAULT_*` constants, so an entry that predates a key behaves exactly as a never-declared one
would (ADR-0027, Consequences: "the new `notifications` flag is a key entries created before it will
not have (defaulting absent on read)").

Only `async_step_user`, `async_step_reconfigure` and `async_step_init` are framework-imposed names
(ADR-0027 point 5); every other step id is the integration's own and is a `STEP_*` constant in
`const.py` (CLAUDE.md: no magic strings), consumed by `config_flow.py`, both tables, and the
translation-parity test.

`STEP_VEHICLE_LIMIT`, `STEP_MAPPINGS` and `STEP_THRESHOLDS` are **deleted**; `STEP_GRID`,
`STEP_EV_CHARGER`, `STEP_VEHICLE`, `STEP_POWER` and `STEP_NOTIFICATIONS` are added.
`UC12_FIXED_STEP_ORDER` (in `config_flow.py`) becomes the nine-id order above, with `captar` before
`solar` (ADR-0027, Consequences).

### The dispatcher, the accumulator, and the terminal split — all unchanged

ADR-0027's Decision is "**Option C, unchanged in mechanism** … What this ADR changes is the *content*
of that structure". This slice therefore keeps, byte-for-byte in shape:

- `FlowMode`, `FlowStep`, and `_TableWalkMixin._async_advance`/`_async_finish` — the dispatcher
  already implemented (ADR-0027, Consequences: "The mechanism this ADR re-affirms is already built,
  so that work is confined to the tables, the step methods and the schema fragments").
- The per-run accumulator `self._answers`: a plain `dict[str, Any]`, empty at each entry point, never
  seeded from the existing entry, merged into by each step's validated `user_input`, consumed exactly
  once at `_async_finish`, discarded on abandonment (ADR-0027 point 2; UC12's abandonment exception,
  R20 AC8). Reconfigure prefill stays **rendering-only**, via
  `add_suggested_values_to_schema(<fragment>, entry.data)` in `_maybe_prefill` — which is what keeps a
  just-withdrawn capability's stale mapping fields from surviving the save (R20 AC7).
- `_split_data` — an exclusion filter, so a narrower accumulator simply yields a narrower data
  bucket (ADR-0027, Consequences: "`_split_data` survives unchanged as an exclusion filter").
- The **intersection-based** consumption of `OPTION_KEYS`
  (`{k: self._answers[k] for k in OPTION_KEYS if k in self._answers}`), which ADR-0027's Consequences
  reaffirm over a larger key set: "with four gated steps rather than three, more threshold keys can
  legitimately be absent from a given install."
- The options flow's **merge-not-replace** terminal write
  (`{**self.config_entry.options, **intersection}`), which is what leaves a withdrawn capability's
  stored options values untouched (UC12 1a/5b).

Two things do disappear from `_maybe_prefill`'s call sites and `_async_finish`: the transient
`CONF_VEHICLE_LIMIT_MAPPED` key and its `extra_from` augmentation on the core step, and the
`self._answers.pop(CONF_VEHICLE_LIMIT_MAPPED, None)` line — the election is gone as a concept
(ADR-0027, Context: "`vehicle_limit` is gone as a step"; UC12 4a). `_maybe_prefill`'s `extra_from`
parameter has no remaining caller and is removed with it; every step now prefills from `entry.data`
directly, because every mapping field it presents *is* a stored key.

### Field-to-step assignment

Every field below is placed by UC12's own step text and bound by `entity-catalog.md`'s row; **none is
added, moved, or renamed by this document.** "Half" is ADR-0005's bucket: mapping half → config-entry
**data**, threshold half → config-entry **options**.

| UC12 # | Step | Mapping half (data) | Threshold half (options) |
| --- | --- | --- | --- |
| 1 | `core` | `solar_available`, `captar_available`, `deadline_available`, `notifications_available` (catalog *Capabilities*) | `smoothing_window`; `control_interval_s` **options flow only** (catalog *Core & coordinator*; UC12 1b) |
| 2 | `grid` | `net_power_entity` (req), `grid_voltage_entity` (opt), `low_tariff_entity` (opt) + its state-translation table (D-4) | `nominal_voltage`, `grid_ceiling_a`, `grid_safety_offset_a` (catalog *Installation*) |
| 3 | `ev_charger` | `charger_current_entity`, `charger_status_entity`, `connected_states`, `charging_states`, `charger_power_entity` (all req) | `min_current`, `max_current` (catalog *Charger*, C1) |
| 4 | `vehicle` | `ev_soc_entity` (**req**, D-2), `ev_battery_capacity_entity` (opt), `vehicle_charge_limit_entity` (opt), `car_home_entity` (opt + the 4a guard, D-3) | `ev_battery_capacity_kwh`, `default_soc_limit` (seed, UC12 4b) (catalog *SOC & battery*) |
| 5 | `power` | — (threshold-only) | `default_target_current` (seed, UC12 4b), `power_cooldown_min` (**new key**, D-1) (catalog *`Power` mode*) |
| 6 | `captar` | — (threshold-only) | `captar_cooldown_min`, `power_respect_peak`, `safety_margin_w`, `max_peak_kw`, `peak_floor_kw`, `peak_grace_min` (catalog *Peak protection* + *`Power` mode*; UC12 5b, R18 AC5) |
| 7 | `solar` | `solar_power_entity` (**new key**, opt, D-1/D-2), `solar_forecast_entity` (**req**, D-2) | `solar_start_threshold_w`, `solar_only_start_threshold_w`, `solar_only_strategy`, `solar_only_midpoint`, `solar_hold_min`, `solar_only_hold_min`, `solar_cooldown_min`, `solar_restart_debounce_min`, `solar_step_pp`, `solar_step_threshold_pp`, `max_solar_soc`, `solar_reserve_soc` (seed, UC12 4b), `solar_forecast_threshold_kwh` (catalog *Solar configuration*) |
| 8 | `deadline` | `departure_external_entity` (opt), `home_day_external_entity` (opt — the named carve-out, UC12 5c / R20 AC5) | `reminder_lead_h` (catalog *Departure times*, *Home day*, *Reminders & prompts*) |
| 9 | `notifications` | `notification_target_entity` (opt, D-2) | `deadline_notice_enabled` (**new key**), `plug_in_reminder_enabled` (**new key**), `evening_prompt_enabled`, `evening_prompt_time` (catalog *Reminders & prompts*; R18 AC11) |

Every catalogued `config-options` key and every catalogued **mapped** adapter role now has exactly one
home, which is UC12's own postcondition ("Two gaps the previous step model named as out of scope are
closed by **this** step model"). `sun` is the one role with no field, deliberately (catalog Notes:
`sun.sun` is a core platform entity, not a device).

**No field appears in two fragments.** ADR-0027 removed the only exception the previous model had:
`_solar_mapping_schema`/`_captar_mapping_schema` lose their `include_ev_soc` parameter entirely, and
the once-only-across-two-steps bookkeeping disappears with them, because `ev_soc_entity` now lives on
the always-shown `vehicle` step (R20 AC4). The fragment-disjointness test therefore needs **no**
carve-out any more — its `ev_soc_entity` exemption is deleted.

### Schema fragments

One mapping fragment and one threshold fragment per step that has each half (ADR-0027,
Consequences). Threshold fragments keep today's `defaults: Mapping | None = None` parameter (the
superseded design's D-4, unchanged in substance): the options flow builds each schema with the
**stored** values as voluptuous defaults, so an untouched field re-submits its stored value rather
than the module default. Mapping fragments carry no stored-value defaults and use
`add_suggested_values_to_schema(entry.data)` instead (ADR-0027 point 2).

| Step | Mapping fragment | Threshold fragment |
| --- | --- | --- |
| `core` | `CORE_MAPPING_SCHEMA` | `_core_threshold_schema(defaults, *, include_interval=False)` |
| `grid` | `GRID_MAPPING_SCHEMA` | `_grid_threshold_schema(defaults)` |
| `ev_charger` | `EV_CHARGER_MAPPING_SCHEMA` | `_ev_charger_threshold_schema(defaults)` |
| `vehicle` | `VEHICLE_MAPPING_SCHEMA` | `_vehicle_threshold_schema(defaults)` |
| `power` | — | `_power_threshold_schema(defaults)` |
| `captar` | — | `_captar_threshold_schema(defaults)` (extended: +5 fields) |
| `solar` | `SOLAR_MAPPING_SCHEMA` (no parameter) | `_solar_threshold_schema(defaults)` (unchanged contents) |
| `deadline` | `DEADLINE_MAPPING_SCHEMA` (+ `home_day_external_entity`) | `_deadline_threshold_schema(defaults)` (unchanged) |
| `notifications` | `NOTIFICATIONS_MAPPING_SCHEMA` | `_notifications_threshold_schema(defaults)` |

Deleted outright: `UNGATED_MAPPING_SCHEMA`, `_ungated_threshold_schema`,
`VEHICLE_LIMIT_MAPPING_SCHEMA`, `_solar_mapping_schema`, `_captar_mapping_schema`
(`_ungated_threshold_schema`'s contents disperse across `core`, `grid`, `ev_charger`, `vehicle`,
`power` and `captar` exactly as ADR-0027's Consequences describe).

`include_interval` migrates from `_ungated_threshold_schema` to `_core_threshold_schema`, since UC12
1b places the control interval on the `core` step's threshold half and the options flow is the only
flow that renders it.

### Guards and required fields (ADR-0027 point 1)

ADR-0027 point 1 settles this directly: two of the three guards become plain required fields, one
survives and gains a condition.

| Field | Before (ADR-0025) | After (ADR-0027 point 1) |
| --- | --- | --- |
| `ev_soc_entity` | `_ev_soc_missing_error`, a cross-step guard on `solar`/`captar` | plain `vol.Required` on the ungated `vehicle` step |
| `solar_forecast_entity` | `_solar_forecast_missing_error` on `solar` | plain `vol.Required` on the capability-gated `solar` step |
| `car_home_entity` | `_car_home_missing_error` on `vehicle_limit`, firing on a filled-in charge limit | `_car_home_missing_error` on `vehicle`, firing on a filled-in charge limit **or** a present deadline capability (UC12 4a) |

`_ev_soc_missing_error` and `_solar_forecast_missing_error` are **deleted**, and with them their two
error codes: `ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE` and `ERROR_REQUIRED_WHEN_CAPTAR_AVAILABLE` lose
their only emitters, so the constants and their `config.error` translation entries go too.
`tests/test_config_flow_translations.py` discovers emitted codes from `const.py`'s `ERROR_*`
constants, so removing constant and translation together keeps that parity test green (and its
non-vacuity test still passes on the two surviving codes).

`_car_home_missing_error` changes signature semantics: it now reads a merged
`{**self._answers, **user_input}` mapping, because one of its two triggers
(`deadline_available`) was answered on step 1 and the other (`vehicle_charge_limit_entity`) on this
step. This is exactly the boundary case ADR-0027 point 1 and its "What this forecloses" note describe
— a rule that reads an earlier step's answer but reports on its own step, never at the end of the
flow (R20 AC6).

### The terminal step

| Mode | Terminal action | UC12 |
| --- | --- | --- |
| install | `async_create_entry(title="Smart Charging", data=_split_data(answers), options=<intersection> \| {control_interval_s: DEFAULT_CONTROL_INTERVAL_S})` | step 10 |
| reconfigure | `async_update_reload_and_abort(entry, data=_split_data(answers))` — data bucket only, entry reloaded (ADR-0008) | 1a |
| options | `async_create_entry(title="", data={**self.config_entry.options, **<intersection, incl. control_interval_s>})` — options bucket only, **merged**, never replacing | 1b |

Unchanged from what is implemented today, minus the `CONF_VEHICLE_LIMIT_MAPPED` pop.

---

## Concrete decisions this document makes

These are implementation choices inside already-settled behaviour — the only kind of decision this
document is entitled to make. Each states the source that constrains it.

**D-1 — New `const.py` constants.** UC12 presents five values whose catalog row exists but whose
`const.py` constant does not. Keys, buckets and defaults are taken from `entity-catalog.md`, not
invented:

| Constant | Value | Bucket | Catalog row / source |
| --- | --- | --- | --- |
| `CONF_NOTIFICATIONS_AVAILABLE` | `"notifications_available"` | data | catalog *Capabilities*; R18 AC9; UC12 step 1 |
| `DEFAULT_NOTIFICATIONS_AVAILABLE` | `False` | — | catalog "off (absent)"; R18 AC9's named default-**absent** exception |
| `CONF_POWER_COOLDOWN_MIN` | `"power_cooldown_min"` | options | catalog *`Power` mode*; R11; UC12 step 5 |
| `DEFAULT_POWER_COOLDOWN_MIN` | `10.0` | — | catalog default 10 min |
| `CONF_DEADLINE_NOTICE_ENABLED` | `"deadline_notice_enabled"` | options | catalog *Reminders & prompts*; R18 AC11 |
| `DEFAULT_DEADLINE_NOTICE_ENABLED` | `True` | — | catalog "on"; R18 AC11 "defaults to **on**" |
| `CONF_PLUG_IN_REMINDER_ENABLED` | `"plug_in_reminder_enabled"` | options | catalog *Reminders & prompts*; R18 AC11 |
| `DEFAULT_PLUG_IN_REMINDER_ENABLED` | `True` | — | catalog "on"; R18 AC11 |
| `CONF_SOLAR_POWER_ENTITY` | `"solar_power_entity"` | data | catalog *`Solar` mode*, the `solar_power` **adapter role**; UC12 step 7 |
| `ERROR_REQUIRED_WHEN_DEADLINE_AVAILABLE` | `"required_when_deadline_available"` | — | UC12 4a's second trigger (D-3) |

`CONF_POWER_COOLDOWN_MIN`, `CONF_DEADLINE_NOTICE_ENABLED` and `CONF_PLUG_IN_REMINDER_ENABLED` are
appended to `OPTION_KEYS`. The two data keys need no list membership: `_split_data` is an exclusion
filter and routes them to data automatically.

`CONF_SOLAR_POWER_ENTITY` is the one name not spelled literally in a source. The catalog names the
**role** `solar_power`; the `CONF_<ROLE>_ENTITY = "<role>_entity"` convention is uniform across every
other mapping key in `const.py` (`net_power` → `net_power_entity`, `solar_forecast` →
`solar_forecast_entity`, …), and epic #760 step 7 spells `solar_power_entity` explicitly. No
`ROLE_SOLAR_POWER` constant and no `adapters/factory.py` wiring is added here — building the role is
RA1's, not C4's (project-plan C4: "Depends on: RA1 factory (role list to map)"). See Deferrals.

**No consumer wiring is in this slice.** Neither `power_cooldown_min`, `solar_power_entity`,
`deadline_notice_enabled` nor `plug_in_reminder_enabled` is read by any `custom_components/` module
today. Capturing them now is the contract-first move for a forward dependency: the key, bucket and
default are pinned here so the slice implementing R11's `Power` cooldown, RA1's solar-production role
and R5/R12's notification gating reads an already-populated entry. **This is deliberately distinct
from the reverted `prompt_timeout_h` case** (#813/#818): that field had *no documented consumer at
all* — the notifications design had decided against it — whereas each of these four has a named
reader in `entity-catalog.md`'s own `Read by` column (`UC04`, `control-cycle`, `(UC05)`, `UC10`) and
a requirement that mandates it (R11, R10/NF3, R18 AC11). Their runtime *effect* is explicitly out of
this slice (Deferrals).

**D-2 — Requiredness of the three mappings no source marks required.** ADR-0027 point 1 names exactly
two mappings that become unconditional `vol.Required` (`ev_soc_entity`, `solar_forecast_entity`) and
one that stays a guard (`car_home_entity`). Three further mappings this slice presents are marked
`vol.Optional`, matching what they are today and adding no requiredness no source states:

- `solar_power_entity` — new, and nothing reads it yet (D-1); the catalog's row carries no
  "optional" qualifier but no source marks it required either, and requiredness would be an
  analysis-level claim this document may not make.
- `notification_target_entity` — R18 AC10 states the *consequence* of leaving it unmapped
  ("the notifications themselves are undeliverable"), which is a behavioural fact, not a form
  constraint; today's schema has it optional and UC12 step 9 names no requiredness.
- `low_tariff_entity`, `grid_voltage_entity`, `ev_battery_capacity_entity`,
  `vehicle_charge_limit_entity`, `departure_external_entity`, `home_day_external_entity` — each
  explicitly optional in the catalog and optional today.

If a reviewer reads R18 AC10 as making the notification target required on a step the household
opted into, that is an analysis-level change to UC12/R18 and belongs in its own issue, not here.

**D-3 — The car-at-home rule's two triggers get two error codes.** UC12 4a gives the rule two
*independent* reasons (a mapped vehicle charge limit; a present deadline capability). The existing
`ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED` names only the first, and reporting it when the trigger
was the deadline capability would render a message that contradicts the form the user is looking at.
`ERROR_REQUIRED_WHEN_DEADLINE_AVAILABLE` is added for the second trigger (D-1); the guard returns
whichever applies, checking the charge-limit trigger first so a user who triggered both sees the
message about the field they just filled in. Both codes get `config.error` entries in
`strings.json`/`en.json`/`nl.json`, which the parity test enforces.

**D-4 — The low-tariff state-translation table is an always-present optional field, not a
dynamically reshaped form.** UC12 step 2 presents the low-tariff mapping "with its own
state-translation table when the mapped entity does not already report on/off", and ADR-0027's
Consequences flag this as "the one fragment whose construction is not a straight per-topic re-cut".
The sibling slice that **owns** this field —
[`2026-08-17-low-tariff-state-translation-design.md`](2026-08-17-low-tariff-state-translation-design.md)
(issue #746) — already settled its shape: a `vol.Optional(CONF_LOW_TARIFF_STATES): str`
comma-separated field rendered beside the mapping, inert when the mapped entity already reports
on/off. UC12's "when" is a condition on when the table is *consulted*, not a mandate to reshape a
form mid-step (which HA's flow API can only do by re-showing the step). This slice adopts that shape
unchanged and adds nothing of its own.

**Landing order with #746 — whichever lands second re-homes the field.** That slice targets
`UNGATED_MAPPING_SCHEMA`/`STEP_MAPPINGS`, which this slice deletes. Concretely:

- If #746 lands **first**, `GRID_MAPPING_SCHEMA` here carries both `CONF_LOW_TARIFF_ENTITY` (with its
  widened `sensor`/`select`/`input_select` domains) and `CONF_LOW_TARIFF_STATES`, and its
  `strings.json` label moves from the `mappings` block to the `grid` block.
- If this slice lands **first**, `GRID_MAPPING_SCHEMA` carries only `CONF_LOW_TARIFF_ENTITY` as it
  exists today, and #746's own plan re-points its "add the field to `UNGATED_MAPPING_SCHEMA`" step at
  `GRID_MAPPING_SCHEMA`/`STEP_GRID` — a one-line change to that plan, not a redesign.

The paired plan's first task checks which case holds and says so in its commit message; nothing else
in either slice depends on the order.

**D-5 — The solar capability's form default stays `True` while `DEFAULT_SOLAR_AVAILABLE` stays
`False`.** Inherited verbatim from the superseded design, not re-decided: R18 AC1 and R20 AC1 say the
declaration defaults to present, so the *form* renders `default=True`; `DEFAULT_SOLAR_AVAILABLE`
remains `False` because it is now used only as the absent-key read fallback, and changing it would
retroactively grant the solar capability to an entry that predates the key. The new
`notifications_available` has **no such divergence**: R18 AC9's default-absent and the read fallback
agree, so the form renders `default=DEFAULT_NOTIFICATIONS_AVAILABLE` (`False`) directly. The plan
marks both explicitly so the asymmetry stays visible.

**D-6 — Step ids stay `STEP_*` constants in `const.py`**, consumed by `config_flow.py`, both tables
and the translation-parity test (CLAUDE.md: no magic strings). Unchanged in kind from the superseded
design's D-5; only the id set changes.

---

## Forks

**None.** Every fork this slice could plausibly have raised is already answered by a cited source:

- **Config-entry migration / `VERSION` bump** — answered directly by ADR-0027's Consequences: "**No
  config-entry migration and no `VERSION` bump from the step restructuring itself.** No key changes
  name, type or bucket because a field moved between steps; the key *set* narrows further than
  before, which is safe only because every consumer reads options defensively via
  `opts.get(<key>, DEFAULT_...)`." `SmartChargingConfigFlow.VERSION` stays `1`. The ADR-0025 "no
  migration" precedent therefore holds unchanged, for the reason it always held: bucket membership
  does not move. See Packaging and migration for the two data effects ADR-0027 attributes to UC12
  rather than to the restructuring.
- **The capability set, the step set, the order, each field's step and bucket** — UC12, R18, R20 and
  `entity-catalog.md`.
- **The branching mechanism** — ADR-0027's Decision (Option C, unchanged in mechanism).

The three judgement calls that remained (D-2's requiredness, D-3's second error code, D-4's landing
order) are implementation choices inside settled behaviour, not behavioural forks; each is recorded
above with the source that constrains it and the alternative it declined.

---

## Mapping to `system-design.md` services

| Piece | Service | Source |
| --- | --- | --- |
| `SmartChargingConfigFlow` (install + reconfigure), `SmartChargingOptionsFlow` | **Client**, V14 | project-plan C4: "Service: Client, V14 (ADR-0003/0005)" |
| The role list the flow maps (including the new `solar_power_entity` key) | **RA1** factory | project-plan C4 "Depends on: RA1 factory (role list to map)" |
| The config-entry data/options buckets the flow writes | **RA3** Store's data/options side | project-plan C4 "Depends on: RA3 (Store data/options write)"; ADR-0005 |
| Reload on options change | ADR-0008 behaviour in `__init__.py` | project-plan C4 "triggers reload on change (ADR-0008)" |
| The four capability flags the `core` step declares | read by **E9**/`capability_gate.py` and `select.py` (R18) — **not written to by them** | catalog *Capabilities* "Written by: user (reconfigure flow), UC12" |

No orchestration is added to the flow (project-plan C4: "Holds no orchestration"). No new service, no
new call direction, no new volatility: this slice changes only how one existing Client groups the
fields it already owns, plus five keys it newly captures for consumers other slices own.

---

## Testing approach (ADR-0009)

**HA harness for the flow itself.** The config flow is HA-coupled — `hass.config_entries.flow`,
`FlowResultType`, `EntitySelector`, `MockConfigEntry` — so per ADR-0009, and per project-plan C4's own
"Testable on its own: HA harness" line, every *behavioural* test in this slice lives in
`tests/test_config_flow.py`. Two test modules are touched:

- `tests/test_config_flow.py` — **HA harness.** Restructured in place. Its existing per-step drivers
  (`_run_install_flow(hass, *, capabilities, per_step_input)` and friends) are re-cut for nine steps
  and four capabilities; `tests/helpers.py`'s `entry_data_base`/`entry_options_base` stay the
  fixtures for every non-flow module, so no other test file changes.
- `tests/test_config_flow_translations.py` — **plain pytest** (it imports only `json`, `pathlib`,
  `config_flow` and `const`), the correct boundary per ADR-0009 for a data-file parity check. Its
  `CONFIG_STEP_FIELDS`/`OPTIONS_STEP_FIELDS` maps are rebuilt from the new fragments; its module-level
  `assert set(CONFIG_STEP_FIELDS) == CONFIG_STEP_IDS` self-check keeps a step added to a table without
  a fields entry from passing vacuously.

`tests/test_translations.py` is **not** touched: the previous slice already removed its config-flow
import and its flat-block parity test, leaving only entity-translation and file-identity checks.

A handful of pure assertions (fragment key sets, table order, fragment disjointness) need no `hass`
fixture; they live in the harness module for cohesion with the flow they describe, since the
fragments have no meaning outside it.

Five obligations come from ADR-0027's Consequences ("The test obligation grows with the table") and
are explicit tasks rather than incidental coverage:

1. **Table reachability** — every step method is reachable from its table and every table row has a
   method. The named discharge of Option C's stated Con, now over nine rows.
2. **Traversal matrix — sixteen combinations**, since `notifications` is a fourth independent flag:
   each must traverse exactly the steps UC12 prescribes, in order, for **each of the three flows**.
3. **The reconfigure subset explicitly** — `power` and `captar` never appear, whatever the CapTar
   declaration.
4. **The field-level car-at-home rule in both of its triggering conditions** (UC12 4a), plus the case
   where neither holds and the field stays optional.
5. **The control interval appears on the options flow only** — never on install, never on
   reconfigure.

Test names stay anchored to their criterion —
`test_r20_ac4_ev_soc_asked_on_vehicle_step_with_no_capabilities`,
`test_uc12_5a_notifications_absent_skips_the_notifications_step`,
`test_uc12_1a_reconfigure_never_shows_power_or_captar` — following the traceability convention the
existing suite uses. Every renamed test carries its ADR citation forward: ADR-0027's Consequences
require the mechanical re-citation pass described under Packaging.

---

## Packaging and migration

- **No config-entry `VERSION` bump and no migration** (ADR-0027, Consequences, quoted under Forks).
  `SmartChargingConfigFlow.VERSION` stays `1`.
- **Both key sets narrow further, and that stays safe only because consumers read defensively.** A
  notifications-absent install writes no `notification_target_entity`, no enable toggles and no
  `evening_prompt_time`; a CapTar-absent install writes none of the five peak-protection values. The
  plan's completion check re-verifies by grep that `adapters/factory.py`, `__init__.py`,
  `coordinator.py`, `dashboard.py` and the notification manager all read
  `entry.data.get(...)`/`opts.get(<key>, DEFAULT_...)` rather than indexing — which is exactly what
  project-plan C4's integration checkpoint ("the entry C4 writes drives RA1's factory and the Store's
  data/options reads on setup") asks to be true.
- **Two data effects belong to UC12, not to the restructuring** (ADR-0027, Consequences): the new
  `notifications_available` key is absent from every pre-existing entry and defaults absent on read;
  and CapTar-gating the peak-protection fields means an existing non-CapTar entry keeps stored values
  no flow can reach any more (UC12 5b) — dormant, and resumed exactly as stored if the capability is
  declared present again.
- **Entries created before this change may lack fields a step now presents as required**
  (`ev_soc_entity` on a pre-guided entry, `notifications_available`). The reconfigure flow (UC12 1a)
  is the repair path; no automatic migration is introduced.
- **`manifest.json` is untouched** — no new dependency, no version-gated HA API.
- **`strings.json`, `translations/en.json`, `translations/nl.json`** each carry one block per step id
  under both `config.step.*` and `options.step.*`: **nine** ids rather than seven, with the
  `vehicle_limit`, `mappings` and `thresholds` blocks removed and `grid`, `ev_charger`, `vehicle`,
  `power`, `notifications` blocks added. Install and reconfigure continue to share `config.step.*`, so
  each title/description must read correctly in both a first-install and an edit-my-mappings context
  (ADR-0027, Consequences). Two `config.error` entries are removed and one added (D-3).
- **A mechanical re-citation pass is part of this slice, not a follow-up.** ADR-0027's Consequences
  name it: "roughly fifty docstring and comment references to 'ADR-0025' live in `config_flow.py`,
  `const.py`, `tests/test_config_flow.py` and `tests/test_config_flow_translations.py`, including a
  test named `test_adr0025_every_config_table_step_has_a_step_method`, and all of them must come to
  name ADR-0027 instead." The plan gives it its own task so it cannot be lost between the others.

---

## Deliberate deferrals

**None of UC12's or R20's mandated flow behaviour is deferred.** This slice is a pure re-cut of a
surface that is already fully specified. What is *outside* it, each with its owner:

| Not in this slice | Why | Owner |
| --- | --- | --- |
| Building the `solar_power` **adapter role** from `CONF_SOLAR_POWER_ENTITY` (`ROLE_SOLAR_POWER`, the factory branch, smoothing per R10) | Role construction is RA1's, not C4's (project-plan C4 "Depends on: RA1 factory (role list to map)"); `engines/signal_conditioning.py`'s own docstring already records `solar_power` smoothing as deferred to a later slice | the RA1 solar-production-role slice |
| Runtime *effect* of `power_cooldown_min` (R11's `Power`-mode cooldown) | R11 behaviour, not the flow's surface | the R11 `Power`-cooldown slice |
| Runtime *effect* of `deadline_notice_enabled` / `plug_in_reminder_enabled` (R18 AC11's conjunctive gating of R5/R12) | R5/R12/R18 behaviour; `evening_prompt_enabled`'s own reader (UC08) already exists, its two siblings' do not | the R5 notice and R12 reminder slices |
| Runtime *effect* of `notifications_available` (gating M3's delivery at all) | R18 AC10 behaviour; the flow only captures the flag | the R18 capability-gating slice |
| `CONF_LOW_TARIFF_STATES` and the widened low-tariff selector | owned by the #746 slice (D-4); this slice only re-homes the field onto `grid` if that slice landed first | issue #746 |
| Any change to the data/options boundary | ADR-0005 stands as written (ADR-0027: "ADR-0005's data/options boundary and ADR-0008's reload-on-change behaviour both stand exactly as written") | — |
| Splitting the large `captar`/`solar` steps | ADR-0027, "What becomes harder": "splitting one later is an extra table row, but the decision of when to split is not made here" | a future issue, if ever |

**Safety caveat, stated out loud.** This slice moves a safety-relevant field group and a
safety-relevant *gate*:

- The grid-connection group (`grid_ceiling_a`, `grid_safety_offset_a`, `nominal_voltage`) moves onto
  the **ungated** `grid` step and the current bounds (`min_current`, `max_current`) onto the
  **ungated** `ev_charger` step, so neither can ever be skipped by a capability gate. The
  traversal-matrix test asserts exactly that for all sixteen combinations.
- The peak-protection group (`safety_margin_w`, `max_peak_kw`, `peak_floor_kw`, `peak_grace_min`,
  `power_respect_peak`) moves **behind** the CapTar gate. That is a deliberate behaviour change owned
  by UC12 5b and R18 AC5, not by this slice, and its real-world consequence is stated there and in
  the catalog's *Captar-dependent rows* note: on a non-CapTar installation the R3 clamp does not run
  at all, net import is bounded only by the grid supply ceiling (C4), and no path through the flow
  reaches those five values while the capability is absent. This slice implements that gating
  faithfully; it does not soften it, and it does not introduce it.
- Nothing here touches the ADR-0007 fault path.
