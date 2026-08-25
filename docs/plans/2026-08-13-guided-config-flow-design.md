# C4 — Guided config flow / options flow (implementation design)

**Slice:** C4 — Install-time config flow / options flow, `docs/design/project-plan.md`, Phase 4.
Verbatim from that slice's entry:

> **Service:** Client, V14 (ADR-0003/0005). **Builds:** maps adapter roles, declares capabilities,
> sets install-time thresholds (data); tunes options anytime; triggers reload on change (ADR-0008).
> Holds no orchestration — writes only through the Store.
> **Depends on:** RA3 (Store data/options write), RA1 factory (role list to map). **ADR gate:** none
> new (its owned-entity *creation* is C2's concern; C4 writes config buckets).
> **Testable on its own:** HA harness — a full flow produces a valid config entry; an options change
> reloads the entry (ADR-0008).

**Issue:** #677 (epic #656).
**Model:** this document and its plan are authored on Opus (CLAUDE.md); the implementation
([`2026-08-13-guided-config-flow.md`](2026-08-13-guided-config-flow.md)) is executed on Sonnet.

**What this slice is.** C4 already exists as a *flat* flow. This slice does not add a service, a
call direction, or a stored key's home; it restructures the one existing Client
(`custom_components/smart_charging/config_flow.py`) from one screen per flow into the capability-gated
step sequence [UC12](../analysis/use-cases/UC12-configure-installation-through-guided-flow.md) and
[R20](../analysis/requirements.md#r20--guided-installation-configuration) settled, using the
mechanism [ADR-0025](../adl/0025-config-flow-branching-structure.md) proposes. Every behavioural fact
below is cited; none is decided here.

**ADR gate.** The project-plan C4 entry quoted above says "**ADR gate:** none new" — that line is now
**stale**, and this document is where the staleness is recorded rather than silently carried.
Restructuring the flow *did* surface a structural decision, and it was opened as
[ADR-0025](../adl/0025-config-flow-branching-structure.md), whose Status is still **Proposed**. So
everywhere this document and its plan say "the mechanism ADR-0025 chose", read it as *the mechanism
ADR-0025 proposes*: **ADR-0025 reaching Accepted is this slice's gate**, and no task below may be
committed against a superseded or rejected ADR-0025. Correcting project-plan.md's own C4 line is a
separate change to `docs/design/project-plan.md` and is deliberately not made here (this slice edits
no design doc).

**Sources of truth (cited, never restated as this document's own):**

| Source | Owns |
| --- | --- |
| [UC12](../analysis/use-cases/UC12-configure-installation-through-guided-flow.md) | the step list, their contents, their fixed order, the three flows' variants (1a/1b), the four exception flows, the postconditions |
| [R20](../analysis/requirements.md#r20--guided-installation-configuration) AC1–AC9 | the acceptance criteria this slice must satisfy |
| [R18](../analysis/requirements.md#r18--configurable-installation-capabilities) | the capability set and each capability's default |
| [ADR-0025](../adl/0025-config-flow-branching-structure.md) | Option C — the table-driven linear step sequence, its four decision points, its consequences |
| [ADR-0005](../adl/0005-config-entry-structure-and-interval.md) | the data/options bucket boundary (unchanged by this slice) |
| [ADR-0008](../adl/0008-reconfigure-reload-behavior.md) | reload-on-change (unchanged by this slice) |
| [ADR-0009](../adl/0009-testing-strategy.md) | the test boundary — the config flow is HA-harness territory |
| [`entity-catalog.md`](../analysis/entity-catalog.md) | the id, bucket, unit and default of every configuration key the flow presents |

---

## Success criteria

The slice is done when all of the following hold, each pinned by a named test in the paired plan:

1. **R20 AC1** — the first step presents only the four core mappings (charger current, charger status
   with its two state lists, net power, charger power) plus the four enablement decisions (solar,
   CapTar, deadline capabilities; the vehicle-charge-limit election). UC12 step 1.
2. **R20 AC2** — each declared capability contributes exactly one further step, in UC12's fixed order
   (solar → CapTar → deadline), followed by the vehicle-charge-limit step when elected; a capability
   declared absent contributes no step. UC12 step 2 / 2a.
3. **R20 AC3** — no field of an absent capability or a declined election is ever presented. UC12
   postcondition 2.
4. **R20 AC4** — the EV state-of-charge mapping is presented exactly once (on the first of the solar
   and CapTar steps that runs) and not at all when neither capability is declared. UC12 step 3/4 and
   postcondition 3.
5. **R20 AC5** — every ungated mapping appears on UC12 step 7 and every ungated threshold on UC12
   step 8, regardless of the declared capabilities — including the peak-protection fields (UC12 8a).
6. **R20 AC6** — a domain-mismatched or missing required field is reported on the step that presents
   it and that step is re-shown; no cross-field requiredness is reported only after the final step.
   UC12 exception flows 1 and 2; UC12 postcondition 4.
7. **R20 AC7** — reconfigure (UC12 1a) amends mappings and capability declarations without
   re-presenting thresholds and leaves the options bucket untouched; the options flow (UC12 1b)
   amends thresholds without re-presenting mappings and leaves the data bucket untouched. Declaring a
   previously present capability absent drops that capability's own mapping fields.
8. **R20 AC8** — abandoning any flow before its final step creates nothing (install) and amends
   nothing (reconfigure/options). UC12 exception flow 3.
9. **R20 AC9** — a capability added later adds one table row plus one step method and changes no
   existing step. UC12 postcondition 5. Pinned by the extensibility test (plan T13), which is the
   only way a closed capability set (R18) can exercise this criterion.
10. The entry the flow produces is still ADR-0005-shaped: mappings, capability flags and the derived
    state-translation table in **data**, thresholds/defaults/seed values in **options** (UC12 step 9),
    and an options change still reloads the entry (ADR-0008).

---

## Structure

### Step ids

Install and reconfigure **share one table and one set of step methods** (ADR-0025 point 3); the
options flow walks **its own table** in its own handler class (ADR-0025 point 3). Home Assistant
namespaces `config.step.*` and `options.step.*`, so the two tables reuse step ids freely (ADR-0025,
Consequences).

Config table (`SmartChargingConfigFlow`), in UC12's fixed order:

| # | Step id | UC12 | Gate | Rendered in install | Rendered in reconfigure |
| --- | --- | --- | --- | --- | --- |
| — | `core` | step 1 | entry point, always | mappings + decisions | mappings + decisions (prefilled) |
| 1 | `solar` | step 3 | `solar_available` answered this run | mapping half + threshold half | mapping half only (UC12 1a) |
| 2 | `captar` | step 4 | `captar_available` answered this run | mapping half + threshold half | mapping half only |
| 3 | `deadline` | step 5 | `deadline_available` answered this run | mapping half + threshold half | mapping half only |
| 4 | `vehicle_limit` | step 6 | the vehicle-limit election answered this run | mapping half (no thresholds exist) | mapping half |
| 5 | `mappings` | step 7 | always | ungated mappings | ungated mappings |
| 6 | `thresholds` | step 8 | flow mode is **not** reconfigure | ungated thresholds | *skipped* (UC12 1a) |

Reconfigure's "skips step 8 entirely" (UC12 1a) is therefore expressed as the `thresholds` row's own
gate, not as a second table — which is what keeps ADR-0025 point 3's "one shared table" literal.

Options table (`SmartChargingOptionsFlow`), gated on the **stored** capability flags (ADR-0025
point 3):

| # | Step id | UC12 | Gate | Rendered |
| --- | --- | --- | --- | --- |
| — | `init` | — | framework entry point; renders no form of its own, dispatches into the table | — |
| 1 | `solar` | step 3, threshold half | `entry.data.get(CONF_SOLAR_AVAILABLE, DEFAULT_SOLAR_AVAILABLE)` (`False`) | threshold half only |
| 2 | `captar` | step 4, threshold half | `entry.data.get(CONF_CAPTAR_AVAILABLE, DEFAULT_CAPTAR_AVAILABLE)` (`True`) | threshold half only |
| 3 | `deadline` | step 5, threshold half | `entry.data.get(CONF_DEADLINE_AVAILABLE, DEFAULT_DEADLINE_AVAILABLE)` (`True`) | threshold half only |
| 4 | `thresholds` | step 8 | always | ungated thresholds **+ the control interval** (UC12 1b) |

**Every options-flow gate reads defensively, with the named default spelled out above — never
`entry.data[<key>]`.** `deadline_available` is a *new* key this slice introduces (D-1), so every
config entry written before this change lacks it entirely; bracket indexing would raise `KeyError`
the first time an upgraded installation opens Configure, and a bare `.get(key)` would silently gate
on `None`. The fallbacks are the module `DEFAULT_*` constants, so an entry that predates a key
behaves exactly as a never-configured one would (Packaging and migration). Note that
`DEFAULT_SOLAR_AVAILABLE` stays `False` here deliberately — see "Decisions on two forks" §2: the
`True` default belongs to the *form*, the `False` constant to the *absent-key read*.

There is deliberately **no** `vehicle_limit` row here: that step has no threshold fields of its own
(UC12 1b).

Only `async_step_user`, `async_step_reconfigure` and `async_step_init` are framework-imposed names
(ADR-0025 point 4); every other step id above is the integration's own. Each is a `STEP_*` constant in
`const.py` (CLAUDE.md: no magic strings), consumed by `config_flow.py`, the tables, and the
translation-parity test.

### The dispatcher

One shared mixin, `_TableWalkMixin`, used by both handler classes:

```python
# config_flow.py

class FlowMode(StrEnum):
    INSTALL = "install"
    RECONFIGURE = "reconfigure"
    OPTIONS = "options"


@dataclass(frozen=True)
class FlowStep:
    """One row of a flow's ordered, gated step table (ADR-0025, Option C)."""

    step_id: str
    gate: Callable[[Any], bool]   # the flow handler: a config flow or an options flow


class _TableWalkMixin:
    _mode: FlowMode
    _answers: dict[str, Any] | None = None      # per-run accumulator (ADR-0025 point 2)
    _table: ClassVar[tuple[FlowStep, ...]]

    async def _async_advance(self, after: str | None) -> ConfigFlowResult:
        """Show the first step after `after` whose gate passes; finish when none remain."""

    async def _async_finish(self) -> ConfigFlowResult:
        """Terminal: create / update the entry. Implemented per handler."""
```

`gate` takes the flow handler rather than a dict so that one signature serves both tables: the config
gates read `self._answers` and `self._mode`, the options gates read `self.config_entry.data`. The
annotation is deliberately *not* `Callable[[_TableWalkMixin], bool]`: `config_entry` lives on
`OptionsFlow`, not on the mixin, so the narrower hint would make every options gate a type error.
The handler is the union of "a config flow" and "an options flow", each of which also mixes in
`_TableWalkMixin`; annotating the parameter as that permissive is the honest description.
`_async_advance` scans the table from the row after `after` (or from the first row when `after is
None`) and calls `getattr(self, f"async_step_{row.step_id}")()` with no `user_input`, which renders
that step's form; when the table is exhausted it calls `self._async_finish()`. Every step method's
success path ends in `await self._async_advance(after=<its own step id>)` — no step method names its
successor (that is exactly the Option B shape ADR-0025 rejected).

ADR-0025 states this dispatcher's own cost out loud: a step method absent from its table is silently
unreachable. That is discharged by the table-reachability test (plan T2), not by inspection.

### The accumulator

Concrete shape: **a plain `dict[str, Any]` on the flow instance**, `self._answers`, declared as a
class attribute defaulting to `None` and assigned `{}` by each flow's entry point. It is not a typed
dataclass or `TypedDict`: its key set is *by construction* variable (that is the whole point of
capability gating), it is consumed only by `_split_data`/`OPTION_KEYS`, both of which already take a
flat `dict`, and a fixed-shape type would have to declare every capability's keys optional anyway.
A `dict` is also what lets `_split_data` survive **unchanged** (ADR-0025, Consequences).

It is declared as a class attribute rather than initialised in `__init__` because
`SmartChargingOptionsFlow` deliberately defines no `__init__` (its `self.config_entry` is not
resolvable there — see the class docstring in `config_flow.py` today).

Lifetime and rules, per ADR-0025 point 2 and its Consequences:

- Starts **empty** on every run. It is **never seeded from the existing entry** — reconfigure
  prefill is a *rendering-only* concern, done with
  `self.add_suggested_values_to_schema(<fragment>, entry.data)` at form-render time.
  **The `core` step is the one exception to passing `entry.data` directly**: its fragment carries
  `vehicle_limit_mapped`, which is transient (D-2) and therefore has no key in `entry.data` at all,
  so passing `entry.data` unchanged would render that election unset on every reconfigure regardless
  of whether a limit entity is in fact mapped. The core step's render passes an **augmented mapping**
  instead:

  ```python
  self.add_suggested_values_to_schema(
      CORE_MAPPING_SCHEMA,
      entry.data | {CONF_VEHICLE_LIMIT_MAPPED: bool(entry.data.get(CONF_VEHICLE_CHARGE_LIMIT_ENTITY))},
  )
  ```

  Every other step passes `entry.data` as-is, because every field it presents *is* a stored key.
- Each step merges its validated `user_input` into it and nothing else reads it mid-flow except the
  gates and the EV-SOC once-only rule.
- Consumed exactly once, at `_async_finish`.
- Abandoning the flow discards it (UC12 exception flow 3 / R20 AC8) — no persistence, no
  `hass.data` stash.
- It is per-flow-run state on a `FlowHandler` and must never be read as a substitute for the config
  entry.

This is what keeps R20 AC7 honest without any explicit "drop stale keys" code: a capability the user
has just switched off never renders its step, so its mapping fields are never submitted, never enter
the accumulator, and are therefore absent from `_split_data`'s output.

### Schema fragments

`USER_SCHEMA` (the flat `MAPPING_SCHEMA.extend(_threshold_schema().schema)`) has no remaining caller
and is deleted; `MAPPING_SCHEMA` and `_threshold_schema()` are broken into the fragments below
(ADR-0025, Consequences). Threshold fragments keep today's `defaults: Mapping | None = None`
parameter — this preserves the current options-flow behaviour exactly, where an untouched field
re-submits its **stored** value rather than the module default.

| Step | Mapping fragment | Threshold fragment | Step-local guard |
| --- | --- | --- | --- |
| `core` (UC12 1) | `CORE_MAPPING_SCHEMA` — `charger_current_entity`, `charger_status_entity`, `connected_states`, `charging_states`, `net_power_entity`, `charger_power_entity`, `solar_available`, `captar_available`, `deadline_available`, `vehicle_limit_mapped` | — | none (all fields `vol.Required`; domain mismatch is rejected by `EntitySelector` itself, UC12 exception flow 1) |
| `solar` (UC12 3) | `_solar_mapping_schema(include_ev_soc: bool)` — `ev_soc_entity` (when included), `solar_forecast_entity` | `_solar_threshold_schema(defaults)` — `solar_start_threshold_w`, `solar_only_start_threshold_w`, `solar_only_strategy`, `solar_only_midpoint`, `solar_hold_min`, `solar_cooldown_min`, `solar_step_pp`, `solar_step_threshold_pp`, `max_solar_soc`, `solar_reserve_soc`, `solar_forecast_threshold_kwh` | `_ev_soc_missing_error` (→ `ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE`), `_solar_forecast_missing_error` |
| `captar` (UC12 4) | `_captar_mapping_schema(include_ev_soc: bool)` — `ev_soc_entity` (when included) | `_captar_threshold_schema(defaults)` — `captar_cooldown_min` | `_ev_soc_missing_error` (→ `ERROR_REQUIRED_WHEN_CAPTAR_AVAILABLE`) |
| `deadline` (UC12 5) | `DEADLINE_MAPPING_SCHEMA` — `departure_external_entity` (optional) | `_deadline_threshold_schema(defaults)` — `reminder_lead_h` | none |
| `vehicle_limit` (UC12 6) | `VEHICLE_LIMIT_MAPPING_SCHEMA` — `vehicle_charge_limit_entity` (`vol.Required`), `car_home_entity` | — | `_car_home_missing_error` |
| `mappings` (UC12 7) | `UNGATED_MAPPING_SCHEMA` — `grid_voltage_entity`, `low_tariff_entity`, `notification_target_entity`, `ev_battery_capacity_entity`, `home_day_external_entity` (all optional) | — | none |
| `thresholds` (UC12 8) | — | `_ungated_threshold_schema(defaults, include_interval: bool)` — `nominal_voltage`, `min_current`, `max_current`, `grid_ceiling_a`, `grid_safety_offset_a`, `smoothing_window`, `default_soc_limit`, `default_target_current`, `safety_margin_w`, `max_peak_kw`, `peak_grace_min`, `ev_battery_capacity_kwh`, `power_respect_peak`, `evening_prompt_enabled`, `evening_prompt_time`, and `control_interval_s` **only when `include_interval`** (UC12 1b) | none |

Every field above is placed by UC12's own step text; none is added or moved by this document. Note in
particular that `grid_voltage_entity` moves from step 1's fragment to the ungated-mappings step (UC12
step 7 lists it there) and that the peak-protection thresholds sit on the ungated step regardless of
the CapTar capability (UC12 8a / R18 AC5 / R20 AC5).

**The once-only EV-SOC rule (R20 AC4, UC12 postcondition 3)** is one expression, evaluated when each
step renders: `include_ev_soc = CONF_EV_SOC_ENTITY not in self._answers`. Because the solar step
always precedes the CapTar step in the table, this presents the field on the solar step when solar is
declared and on the CapTar step otherwise, and never when neither is — exactly UC12 steps 3 and 4.

`ev_soc_entity` is consequently the **one** field that is a member of two fragments
(`_solar_mapping_schema(include_ev_soc=True)` and `_captar_mapping_schema(include_ev_soc=True)`),
and that is deliberate: the once-only rule is enforced at **render time** by the `include_ev_soc`
argument, not by fragment disjointness. Every other field belongs to exactly one fragment. The
fragment-disjointness test (plan T1) carries an explicit `ev_soc_entity` carve-out for this reason.

### Guards (ADR-0025 point 1 and its Consequences)

`_mapping_errors` — whose only job is to combine the three guards — has no step that needs all three
and is **deleted** (ADR-0025, Consequences). The three guard helpers are kept and become step-local:
each is invoked by exactly one step, on that step's submission, and its capability condition is
already satisfied by the step being shown at all, so each drops its `if capability` prefix and
becomes a plain presence check.

ADR-0025 point 1 phrases this as "a plain `vol.Required` on a step that only appears when it
applies". Keeping a step-local guard that returns the existing `ERROR_REQUIRED_WHEN_*` code, rather
than relying on voluptuous alone, is the reading adopted here, for two cited reasons:

- the guard produces a **field-local, translated** error and re-shows the same step, which is
  literally what UC12's exception flow ("an error local to the missing field") and R20 AC6 ask for,
  whereas a bare `vol.Required` surfaces as `data_entry_flow.InvalidData`;
- `tests/test_config_flow_translations.py` (issue #508) discovers error codes from `const.py`'s
  `ERROR_*` constants and asserts each has a `config.error` translation, with an explicit
  non-vacuity test; deleting all three codes would break that guard rather than satisfy it.

`vehicle_charge_limit_entity` on the `vehicle_limit` step is the one exception: it is the reason that
step is shown at all, so it is `vol.Required` and needs no new error code (UC12 names none).

### The terminal step and the bucket split

`_split_data` **survives unchanged** (ADR-0025, Consequences) — it is an exclusion filter, so a
narrower accumulator simply yields a narrower data bucket.

`OPTION_KEYS` survives as a constant, but its *consumption* becomes **intersection-based**:

```python
# today, at the single async_create_entry call site:
options = {k: user_input[k] for k in OPTION_KEYS}          # KeyError once a step is skipped
# after this slice:
options = {k: self._answers[k] for k in OPTION_KEYS if k in self._answers}
```

Direct indexing raises `KeyError` the moment a solar-disabled install never renders the solar step and
`CONF_SOLAR_START_THRESHOLD_W` and friends are absent (ADR-0025, Consequences). The intersection is
the whole fix; nothing else about the split moves.

**In the options flow the intersection is *merged*, not written as the whole bucket.**
`OptionsFlow.async_create_entry(data=...)` replaces `entry.options` wholesale, and after this slice
the accumulator is deliberately narrower than the stored options: a capability withdrawn through
reconfigure (UC12 1a) leaves its thresholds sitting in the options bucket by design — 1a changes only
the data bucket — but its options step is then gated off by the stored flag, so none of its keys
enter the next options run's accumulator. A replace-the-bucket write would silently delete the user's
solar thresholds the first time they open Configure after withdrawing solar, and re-enabling solar
later would seed from module defaults instead of their prior values. The terminal step therefore
writes `{**self.config_entry.options, **intersection}`: this run's answers win for the keys it
actually presented, and every key it did not present survives untouched. Pinned by a named test
(plan T10).

The transient `vehicle_limit_mapped` decision (see D-2) is popped from the accumulator immediately
before the split, so `_split_data`'s exclusion tuple needs no new member and stays literally
unchanged.

Per flow mode, `_async_finish` does:

| Mode | Terminal action | UC12 |
| --- | --- | --- |
| install | `async_create_entry(title="Smart Charging", data=_split_data(answers), options=<intersection> \| {control_interval_s: DEFAULT})` | step 9 |
| reconfigure | `async_update_reload_and_abort(entry, data=_split_data(answers))` — data bucket only, entry reloaded (ADR-0008) | 1a |
| options | `async_create_entry(title="", data={**self.config_entry.options, **<intersection, incl. control_interval_s>})` — options bucket only, **merged** into the stored options, never replacing them | 1b |

---

## Concrete decisions this document makes

These are implementation choices inside already-settled behaviour — the only kind of decision this
document is entitled to make. Each states the source that constrains it.

**D-1 — New `const.py` constants.** UC12 presents two fields that have a row in
`entity-catalog.md` but no constant in `const.py` today. Names and defaults are taken from the
catalog, not invented:

| Constant | Value | Bucket | Catalog row / source |
| --- | --- | --- | --- |
| `CONF_DEADLINE_AVAILABLE` | `"deadline_available"` | data | catalog *Capabilities*; R18 AC6; UC12 step 1 |
| `DEFAULT_DEADLINE_AVAILABLE` | `True` | — | catalog "on (present)"; R18 AC6 "defaulting to present" |
| `CONF_REMINDER_LEAD_H` | `"reminder_lead_h"` | options | catalog *Reminders & prompts*; R12; UC12 step 5 |
| `DEFAULT_REMINDER_LEAD_H` | `8.0` | — | catalog default 8 h; R12 |

Four further `DEFAULT_*` constants are added at the same time — not because a field is new, but
because four existing ungated thresholds are the only ones in `_threshold_schema()` whose fallback is
a **bare numeric literal** rather than a named constant, and this slice is the one change that
rewrites those very lines into `_ungated_threshold_schema()`. Leaving them as literals while moving
them would carry a CLAUDE.md "no magic strings" violation across a rewrite. Names follow `const.py`'s
existing `DEFAULT_<CONF suffix>` convention (`CONF_GRID_SAFETY_OFFSET_A` →
`DEFAULT_GRID_SAFETY_OFFSET_A`); values are today's literals, unchanged, so this is a pure extraction
with no behavioural effect:

| Constant | Value | Extracted from |
| --- | --- | --- |
| `DEFAULT_MIN_CURRENT` | `6.0` | `_threshold_schema()`'s `d.get(CONF_MIN_CURRENT, 6.0)` |
| `DEFAULT_MAX_CURRENT` | `16.0` | `d.get(CONF_MAX_CURRENT, 16.0)` |
| `DEFAULT_GRID_CEILING_A` | `25.0` | `d.get(CONF_GRID_CEILING_A, 25.0)` |
| `DEFAULT_DEFAULT_TARGET_CURRENT` | `10.0` | `d.get(CONF_DEFAULT_TARGET_CURRENT, 10.0)` |

`CONF_REMINDER_LEAD_H` is appended to `OPTION_KEYS`;
`CONF_DEADLINE_AVAILABLE` needs no list membership, since `_split_data` is an exclusion filter and
routes it to data automatically.

**No consumer wiring is in this slice.** `deadline_available` has documented readers
(resolution-rules, UC05/UC07/UC10/UC11) and `reminder_lead_h` has one (UC10), but neither is built
yet — grep confirms no `custom_components/` code reads either today. Capturing them now is the
contract-first move for a forward dependency: the key, bucket and default are pinned here so the
slice that implements R12/R18's runtime behaviour reads an already-populated entry. Their runtime
*effect* is explicitly out of this slice (see Deferrals).

**D-2 — The vehicle-charge-limit election is transient, not persisted.** UC12 calls it "a plain
optional-mapping decision, not an R18 capability", and `entity-catalog.md` has **no** row for it —
the catalog is authoritative for stored configuration ids, so persisting one would be an analysis
change this document is not entitled to make. It is therefore a form field on step 1
(`CONF_VEHICLE_LIMIT_MAPPED = "vehicle_limit_mapped"`, a transient key), gating the
`vehicle_limit` row, popped from the accumulator before `_split_data` runs. On reconfigure it is
prefilled by deriving from the entry: `bool(entry.data.get(CONF_VEHICLE_CHARGE_LIMIT_ENTITY))` — the
persisted mapping *is* the stored form of that answer, which is why no second key is needed.

**D-3 — Guard mechanism.** See "Guards" above: step-local guards returning the existing `ERROR_*`
codes for `ev_soc_entity`, `solar_forecast_entity` and `car_home_entity`; `vol.Required` for
`vehicle_charge_limit_entity`.

**D-4 — Threshold fragments keep their `defaults` parameter** rather than becoming bare constants
rendered through `add_suggested_values_to_schema`. Rationale: today's options flow builds the schema
with the stored values as voluptuous *defaults*, so a submission that omits a field re-submits the
stored value. Suggested values do not have that property, so switching mechanism would let a partial
submission silently reset a customised threshold to its module default. Mapping fragments, which
carry no stored-value defaults today, do use `add_suggested_values_to_schema(entry.data)` — exactly
as the flat reconfigure step already does, and as ADR-0025 point 2 requires.

**D-5 — Step ids live in `const.py` as `STEP_*` constants**, consumed by `config_flow.py`, both
tables and the translation-parity test (CLAUDE.md: no magic strings).

---

## Decisions on two forks (settled by the human partner)

Two fields in this slice's surface had no single citable answer across the existing docs/code, so
each was raised as an explicit fork rather than resolved by guessing. One is decided and stands; the
other was decided, implemented, and has since been reverted.

**The evening prompt's timeout field — reverted (2026-08-24); the flow presents no such field.**
This slice originally decided to present a `prompt_timeout_h` option, on the grounds that
`entity-catalog.md` then carried a config-options row for it (default 2 h) and that UC12/R20 are the
later authority over this flow's surface. It was implemented that way (T3/T10) even though nothing
read the stored value — `docs/plans/2026-07-21-notifications-design.md` §3/§9 had deliberately not
wired it, because UC08 has no separate timeout and midnight is the only answer deadline. **The human
partner has since reverted that decision:** collecting a value no component consumes was judged a
mistake, so the field was removed from both the analysis documents (#813 — catalog row, R18 AC10,
the `capability` and `notifications capability` glossary entries, UC12's steps) and the code (#818 —
`CONF_PROMPT_TIMEOUT_H` / `DEFAULT_PROMPT_TIMEOUT_H` and the schema field they backed). Both have
merged; the earlier notifications-design decision stands unchanged.

**The solar capability's default — form defaults `True`, constant stays `False`.** R18 AC1 and R20
AC1 both say the capability declarations default to **present**; the glossary's `solar_available`
entry says "default present"; `entity-catalog.md`'s Capabilities table says "on (present)". `const.py`
has `DEFAULT_SOLAR_AVAILABLE = False`, and `MAPPING_SCHEMA` renders the field with `default=False` —
a pre-existing divergence this slice inherits rather than introduces. **Decision:** render step 1's
solar decision with `default=True` per R20 AC1 (the form default is squarely inside this slice's
remit — it is what the flow presents), and leave `DEFAULT_SOLAR_AVAILABLE` itself untouched at
`False`. That constant is now used only as the *absent-key read fallback* by consumers reading
`entry.data.get(...)`; changing it would retroactively grant the solar capability to an existing
entry that predates the key, which is a behavioural change to running installations and belongs in
its own issue against R18, not here. The plan marks this explicitly (T3) so the divergence stays
visible rather than silently carried.

---

## Mapping to `system-design.md` services

| Piece | Service | Source |
| --- | --- | --- |
| `SmartChargingConfigFlow` (install + reconfigure), `SmartChargingOptionsFlow` | **Client**, V14 | project-plan C4: "Service: Client, V14 (ADR-0003/0005)" |
| The role list the flow maps | **RA1** factory | project-plan C4 "Depends on: RA1 factory (role list to map)" |
| The config-entry data/options buckets the flow writes | **RA3** Store's data/options side | project-plan C4 "Depends on: RA3 (Store data/options write)"; ADR-0005 |
| Reload on options change | ADR-0008 behaviour in `__init__.py` | project-plan C4 "triggers reload on change (ADR-0008)" |

No orchestration is added to the flow (project-plan C4: "Holds no orchestration"). No new service, no
new call direction, no new volatility: this slice changes only how one existing Client presents the
fields it already owns.

---

## Testing approach (ADR-0009)

**HA harness for the flow itself.** The config flow is HA-coupled — `hass.config_entries.flow`,
`FlowResultType`, `EntitySelector`, `MockConfigEntry` — so per ADR-0009 (and project-plan C4's own
"Testable on its own: HA harness" line) every *behavioural* test in this slice lives in the harness
module. Three test modules are touched:

- `tests/test_config_flow.py` — **HA harness.** Restructured in place, keeping its existing shape
  (`USER_INPUT` dict, `_run_user_flow`/`_create_entry` helpers, `tests/helpers.py`'s
  `entry_data_base` / `entry_options_base`) but per-step. The existing single-submission helpers
  become a `_run_install_flow(hass, *, capabilities, per_step_input)` driver that walks the steps.
- `tests/test_config_flow_translations.py` — **plain pytest** (it imports only `json`, `pathlib` and
  `const`), which is the correct boundary per ADR-0009 for a pure data-file parity check. Extended
  from error-code parity to **step and field** parity (see plan T12).
- `tests/test_translations.py` — **plain pytest**, and a module this slice *breaks* rather than
  extends. It imports `USER_SCHEMA`, `MAPPING_SCHEMA` and `OPTION_KEYS` from `config_flow.py` and
  asserts label parity against `config.step.user`, `config.step.reconfigure` and `options.step.init`
   — the three blocks T12 deletes and the two schemas T13 deletes. Its
  `test_every_config_flow_field_has_a_label` is therefore **superseded** by T12's dynamic step/field
  parity test and is removed there; its `test_strings_json_and_en_json_are_identical`,
  `test_nl_json_has_the_same_keys_as_en_json` and `test_every_entity_translation_key_has_a_name`
  are unrelated to `config_flow.py` and are **kept unchanged**.

A handful of assertions in T1 (schema fragments have exactly the keys UC12 lists) are pure and need
no `hass` fixture; they live in the same harness module for cohesion with the flow they describe,
since the fragments have no meaning outside it.

Four obligations come from ADR-0025's Consequences and are explicit tasks rather than incidental
coverage:

1. **Table reachability** — every step method is reachable from its table and every table row has a
   method (plan T2). This is the named discharge of Option C's stated Con.
2. **Traversal matrix** — every enablement combination visits exactly the steps UC12 prescribes, in
   the prescribed order (plan T8).
3. **Step-local validation** — one case per moved guard, asserting the error is field-local *and*
   that the flow did not advance (plan T4/T5/T7), replacing the current end-of-form cases.
4. **Abandonment writes nothing** (plan T11).

Test names are anchored to their criterion — `test_r20_ac4_ev_soc_asked_once_when_solar_and_captar`,
`test_uc12_2a_solar_disabled_skips_solar_step`, and so on — following the traceability convention the
existing suite uses (`test_adr0005_user_flow_builds_translation_and_splits_buckets`).

---

## Packaging and migration

- **No config-entry `VERSION` bump and no migration.** Confirmed against ADR-0025's Consequences: no
  key changes name, type or bucket, so an entry written by the flat flow is read identically by the
  restructured one. `SmartChargingConfigFlow.VERSION` stays `1`.
- **Both key *sets* narrow, and that is safe only because consumers read defensively.** A
  solar-disabled install now writes an options bucket with no solar threshold keys at all — a shape
  the flat flow never produced. **The data bucket narrows too**, which is the half easiest to
  overlook: `ev_soc_entity`, `solar_forecast_entity`, `departure_external_entity`, `car_home_entity`
  and `vehicle_charge_limit_entity` are each absent whenever the capability or election that carries
  them was declared off, so `adapters/factory.py`, `dashboard.py` and `__init__.py` must all read
  `entry.data.get(<key>)`/`entry.data.get(<key>, DEFAULT_...)` rather than indexing. Every consumer
  already reads that way, so an absent key resolves to its default exactly as a never-configured one
  would. This property is pre-existing; this slice now *depends* on it for **both** buckets, so the
  plan's completion check re-verifies both by grep before the final commit. This is exactly what
  project-plan C4's integration checkpoint — "the entry C4 writes drives RA1's factory and the
  Store's data/options reads on setup" — asks to be true.
- **Entries created before this change may lack fields a step now presents as required**
  (`deadline_available`, `reminder_lead_h`). The reconfigure flow (UC12 1a) is the repair path; no
  automatic migration is introduced (ADR-0025, Consequences).
- **`manifest.json` is untouched** — no new dependency, no version-gated HA API. `FlowStep` uses
  `dataclasses` and `StrEnum` from the stdlib (Python ≥3.12, already the project floor).
- **`strings.json`, `translations/en.json`, `translations/nl.json`** each gain one block per step id
  under both `config.step.*` and `options.step.*`, replacing today's `config.step.user`,
  `config.step.reconfigure` and `options.step.init`. Per ADR-0025's Consequences: install and
  reconfigure share `config.step.*`, so their titles/descriptions must be worded to read correctly in
  both a first-install and an edit-my-mappings context, and the parenthetical "(required if Solar
  installed)"-style qualifiers are dropped in the same change, since a field now only appears when it
  is required.

---

## Deliberate deferrals

**None of UC12's or R20's mandated behaviour is deferred.** This slice is a pure restructuring of
behaviour that is already fully specified, so there is no MVP-vs-later line to draw inside it. What
is *outside* it, each with its owner:

| Not in this slice | Why | Owner |
| --- | --- | --- |
| Runtime *effect* of `deadline_available` (gating modes, deadline resolution, the reminder) | R18/R14/R12 behaviour, not the flow's surface; the flow only captures the flag (D-1) | the R18 capability-gating slice |
| Runtime *effect* of `reminder_lead_h` | R12/UC10 behaviour; no component reads it yet | the R12 plug-in-reminder slice |
| `entity-catalog.md`'s `solar_power` adapter role and `power_cooldown_min` option | UC12's own postcondition names both as pre-existing gaps it "does not introduce and is out of scope to close" | their own issues |
| The `Power`-mode cooldown and the control interval on the install path | R20 AC5 explicitly puts a value the flow never presents on a path outside its scope; the control interval is asked only in the options flow (UC12 1b) and defaulted otherwise | — |
| Any change to the data/options boundary | ADR-0005 stands as written (ADR-0025: "This ADR supersedes nothing") | — |

**Safety caveat:** none of the above touches a clamp, the peak protection, or the ADR-0007 fault
path. The one safety-adjacent surface this slice moves is the grid-safety threshold group
(`grid_ceiling_a`, `grid_safety_offset_a`, `min_current`, `max_current`, `nominal_voltage`), which
UC12 step 8 puts on an **ungated** step — so it is presented on every install path regardless of any
capability answer, and can never be skipped by a gate. The traversal-matrix test (plan T8) asserts
exactly that for all enablement combinations.
