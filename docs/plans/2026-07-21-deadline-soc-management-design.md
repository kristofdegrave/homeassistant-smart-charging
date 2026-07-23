# Deadline & SOC Management — design

**Date:** 2026-07-21
**Status:** draft (issue #309, epic #306)
**Type:** implementation design (a slice of the approved architecture — not a new decision)

This document defines the **Deadline & SOC Management** slice: the full three-row active-SOC-limit
resolution (R7, rows 1–2 new; row 3 already ships), the Deadline Engine (R5/R14/R15, new), the
Capability-Gate Engine (R18, new), and the `Auto` profile (R16, new) — the pieces
[UC05](../analysis/use-cases/UC05-guarantee-ready-by-departure.md),
[UC06](../analysis/use-cases/UC06-store-abundant-solar.md), and
[UC07](../analysis/use-cases/UC07-reserve-capacity-for-tomorrow.md) need to exist at all.

It is a deliberate **subset** of the full architecture, built the same way the Captar and
Solar/SolarOnly slices were: every component below is a slice of a service already named in
[`../design/system-design.md`](../design/system-design.md) and sequenced in
[`../design/project-plan.md`](../design/project-plan.md) (tasks E2, E3, E4, E9). Nothing here
introduces a new service, call direction, or structural decision, so no new ADR is required.

Behavior is owned by [`resolution-rules.md`](../analysis/resolution-rules.md) (the shared lookups)
and the three use-cases above; this document cites their tables/formulas as test anchors and does
not restate them as if it owns them. Entity ids, adapter roles, and config defaults are already
fixed by [`entity-catalog.md`](../analysis/entity-catalog.md) — this document derives files and
tasks from that catalog, it does not re-decide it.

---

## 0. Relationship to prior slices

This slice reuses, unchanged, everything the Captar and Solar/SolarOnly slices already built:

| Existing piece | Where | This slice's relationship |
| --- | --- | --- |
| `resolve_active_soc_limit(soc_limit_override)` — row-3-only | `engines/soc_target.py` | **Extended**, not replaced — becomes the "otherwise" branch of the new three-row function (§5). Its existing docstring already names rows 1–2 as pending exactly this epic. |
| `resolve_effective_peak_limit(monthly_peak_kw, max_peak_kw)` — row-2-only | `engines/billing_protection.py` | **Extended** — row 1 (deadline-urgency raise) is added as a new parameter (§9). Its existing docstring already names this dependency on E4. |
| `select.smart_charging_mode` (`ModeSelect`) | `select.py` | **Unchanged.** Still the `Manual` profile's own mode override (C2); `Auto` never writes to it (§8's note). |
| Coordinator mode-dispatch/state-reset scaffolding, per-mode state dict | `coordinator.py` | **Extended** — the resolved active mode driving that dispatch now comes from `select.smart_charging_profile` (`Manual` → the selector; `Auto` → E2's own selection, §10), not the selector unconditionally. |
| `ev_soc` adapter role | `adapters/factory.py` | **Unchanged**, reused for R7 row 2's SOC-proximity check and R5's required-current computation. |

Nothing above is re-derived; each engine/task cites which existing file it extends.

---

## 1. Why this slice is wide

Unlike Captar or Solar/SolarOnly, this slice adds no charging mode of its own — all three use-cases
say so explicitly ("this document has no charging mode of its own" / "never charges the car
itself"). Instead it adds four small cross-cutting engines (E2/E3/E4/E9) that several existing
modes and the coordinator already need to consult (`resolution-rules.md`'s five tables). Shipping
only the engines as isolated pytest units would leave them unreachable — nothing would call them —
so, per the scoping decision for issue #309, this slice bundles the full stack in one TDD plan:
config keys → entities (already specified in `entity-catalog.md`, not re-designed here) → the four
engines → coordinator (M1) wiring. This mirrors how Captar and Solar/SolarOnly each shipped
config→entity→engine→coordinator in one slice.

---

## 2. Success criteria (what "works" means)

- The active SOC limit resolves through the full three-row table (solar-reserve cap → solar
  step-up → default, R7) instead of always returning the configured override.
- A solar step-up applies and clears per R8/UC06's state model, surviving a `Solar`↔`SolarOnly`
  switch and resetting on a non-solar mode or disconnect.
- The solar-reserve cap engages/lifts per R9/UC07's state model, is `Auto`-only, and is mutually
  exclusive with a departure deadline resolved for tomorrow.
- The departure deadline resolves per R14's four-row table (external sensor → holiday → home-day
  override → day-of-week default), including the one-day-ahead evaluation R9 needs.
- Deadline urgency (R5) is detected from the required-current formula against the **baseline**
  mode's own desired current, raises the effective peak limit to the maximum peak, and — under
  `Auto` only — escalates mode-selection to `Captar` (or `Power` when CapTar is absent, R18), with
  the deadline-unreachable notification path represented (delivery itself is M3's, deferred, §11).
- The available-mode set (R18) reflects the solar/CapTar capability toggles and gates both the
  manual selector (already true today) and `Auto`'s own mode-selection.
- `select.smart_charging_profile` (`Manual`/`Auto`) exists; under `Auto`, the resolved active mode
  comes from Auto mode-selection (R16) instead of the manual selector.
- `ruff check . && ruff format --check . && pytest -q` green; the HA harness (WSL, per project
  convention) passes; no engine imports another engine or `homeassistant.*`.

---

## 3. Install-time / options additions

New `const.py` keys, derived directly from `entity-catalog.md`'s "Deadline / urgency configuration"
and "Solar-reserve cap" sections and `requirements.md` R8/R9/R14/R15's stated defaults. `CONF_*`
naming and DATA-vs-OPTIONS split follow ADR-0005 exactly as the existing keys do.

**DATA** (entity-role mappings, changed only via reconfigure — ADR-0005):

```python
CONF_EV_BATTERY_CAPACITY_ENTITY = "ev_battery_capacity_entity"   # optional (NF3) — ev_battery_capacity role
CONF_DEPARTURE_EXTERNAL_ENTITY = "departure_external_entity"  # optional (NF3) — departure_external role
CONF_HOME_DAY_EXTERNAL_ENTITY = "home_day_external_entity"  # optional (NF3) — home_day_external role
CONF_SOLAR_FORECAST_ENTITY = "solar_forecast_entity"  # required when CONF_SOLAR_INSTALLED (R9 needs it)
```

`ev_battery_capacity`, `departure_external`, and `home_day_external` are all-optional adapter roles
(same "optional at the factory level" pattern `grid_voltage`/`ev_soc` already use — entity-catalog.md
marks each "mapped ... when available" / NF3). `solar_forecast` is required only when
`CONF_SOLAR_INSTALLED` is `True` (R9's precondition is inert without the solar capability, per R18's
"solar-specific inputs ... not required to be configured" when solar is absent) — same
`required_when_solar_installed`-style guard the flow already uses for `ev_soc`.

**OPTIONS** (thresholds/defaults, editable anytime — ADR-0005):

```python
CONF_EV_BATTERY_CAPACITY_KWH = "ev_battery_capacity_kwh"           # R15, default 75
CONF_MAX_SOLAR_SOC = "max_solar_soc"                         # R8 ceiling, default 100
CONF_SOLAR_STEP_PP = "solar_step_pp"                         # R8 step size, default 5
CONF_SOLAR_STEP_THRESHOLD_PP = "solar_step_threshold_pp"     # R8 trigger gap, default 2
CONF_SOLAR_RESERVE_SOC = "solar_reserve_soc"                 # R9 cap, default 60 (runtime, R7-priority-1)
CONF_SOLAR_FORECAST_THRESHOLD_KWH = "solar_forecast_threshold_kwh"  # R9, default 12

DEFAULT_EV_BATTERY_CAPACITY_KWH = 75.0
DEFAULT_MAX_SOLAR_SOC = 100.0
DEFAULT_SOLAR_STEP_PP = 5.0
DEFAULT_SOLAR_STEP_THRESHOLD_PP = 2.0
DEFAULT_SOLAR_RESERVE_SOC = 60.0
DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH = 12.0
```

`sc_solar_reserve_soc` is catalogued as **runtime** (a target the household adjusts, mirrors
`number.smart_charging_soc_limit_override`'s own runtime classification) — per the catalog's own
"Notes" judgment call, it stays an install-time **options** field like every other Solar threshold in
this slice; the catalog's ADR-0005-reconciliation follow-up (not this slice) is what would migrate it
to an owned entity later, exactly as the catalog's Notes section already says for
`sc_power_target_current_a`.

`time.smart_charging_departure_<dow>` (×7), `time.smart_charging_departure_holiday`,
`time.smart_charging_departure_home_day`, and `switch.smart_charging_home_day` are **owned runtime
entities** per `entity-catalog.md`, not config-flow fields — seeded at setup with their catalog
defaults (§4), editable afterward through the entity itself (mirrors
`number.smart_charging_soc_limit_override`'s pattern, not the options flow).

`select.smart_charging_profile` needs one new **DATA** field: none — it is an owned runtime entity
(§4) like `select.smart_charging_mode`, seeded `Manual` by default (R16's own default),
config-flow-free.

---

## 4. Runtime surface (owned entities)

All ids, defaults, and read/write behavior below are exactly `entity-catalog.md`'s rows — no new
entity is invented here; this section only assigns each to its owning platform file and states its
restore-state behavior (ADR-0004 native naming throughout).

| Entity | Platform file | Behavior |
| --- | --- | --- |
| `select.smart_charging_profile` | `select.py` (new class, alongside `ModeSelect`) | `Manual`/`Auto`, restore-state, default `Manual` (R16). Pushes to `coordinator.active_profile` and requests a refresh, mirroring `ModeSelect`. |
| `sensor.smart_charging_active_soc_limit` | `sensor.py` | Read-only diagnostic (like `EffectivePeakLimitSensor`): the coordinator's resolved R7 value each cycle. No restore needed — recomputed every cycle from its own inputs. |
| `time.smart_charging_departure_mon` … `_sun` (×7) | `time.py` (new platform) | Defaults 06:00 Mon–Fri, none Sat–Sun (R14); user-editable, no restore needed (a `time` entity's state persists natively via HA's own entity-registry state, not `RestoreEntity`). |
| `time.smart_charging_departure_holiday` | `time.py` | Default none (R14). |
| `time.smart_charging_departure_home_day` | `time.py` | Default none (R14). |
| `switch.smart_charging_home_day` | `switch.py` (new platform) | Default off; resets to off at local midnight (R13) — a small coordinator-driven or `homeassistant.helpers.event.async_track_time_change` reset, not a config option. |

New adapter roles (`adapters/factory.py`, all optional/conditional per §3): `ev_battery_capacity`,
`departure_external`, `home_day_external`, `solar_forecast`.

The midnight reset for `switch.smart_charging_home_day` is the one piece of behavior not already
fully pinned by the catalog; `entity-catalog.md`'s R13 acceptance criterion ("resets each day at
midnight") is the test anchor. It is implemented as a small scheduled callback in the switch
entity's `async_added_to_hass` (`homeassistant.helpers.event.async_track_time_change(hour=0,
minute=0, second=0)`), the same category of HA-harness-tested, non-coordinator behavior
`RestoreSensor`'s restore hook already is for `MonthlyPeakSensor` — not a new architectural piece.

---

## 5. SOC-Target Engine (E3) — full three-row resolution

Extends `engines/soc_target.py`. Two additions, both pure (no HA imports):

```python
@dataclass(frozen=True)
class SolarStepUpState:
    """R8's lifecycle state: whether a step-up is currently applied, and its value."""
    stepped_pct: float | None = None  # None = no step-up in effect (Baseline, UC06 §State model)


def resolve_solar_step_up(
    state: SolarStepUpState,
    is_solar_mode_charging: bool,
    soc: float,
    default_limit: float,
    step_threshold_pp: float,
    step_pp: float,
    max_solar_soc: float,
) -> tuple[float, SolarStepUpState]:
    """Return (row-2 value if in effect else default_limit, new_state) — R8/UC06.

    Mirrors E8's "stateful engine, state threaded by the caller" shape. Clears
    (returns to Baseline) the moment `is_solar_mode_charging` is False (UC06's
    exception flow: leaving solar charging, or a disconnect the coordinator
    represents the same way) — the caller passes False for both cases, so this
    function has one clearing rule, not two. Applies a fresh step (or a further
    step) whenever charging in a solar mode and SOC is within `step_threshold_pp`
    of the currently-effective limit (the state's own stepped value, or
    `default_limit` if none yet), clamped to `max_solar_soc` (UC06 step 3/2a).
    """


def resolve_solar_reserve_active(
    profile: str,
    home_day_flag: bool,
    sun_is_down: bool,
    forecast_kwh: float,
    forecast_threshold_kwh: float,
    deadline_tomorrow_resolved: bool,
) -> bool:
    """R9/UC07's cap-activation condition — shared by resolve_active_soc_limit's row 1
    below and Auto mode-selection's row 4 (E2, §8), per resolution-rules.md's note that
    both are "two separate effects of the same Auto decision." Lives here (not in E2)
    because it is R9/R7's own trigger condition, cited by name from the mode-selection
    table rather than restated there.
    """
    return (
        profile == PROFILE_AUTO
        and home_day_flag
        and sun_is_down
        and forecast_kwh > forecast_threshold_kwh
        and not deadline_tomorrow_resolved
    )


def resolve_active_soc_limit(
    soc_limit_override: float,
    solar_reserve_active: bool,
    solar_reserve_soc: float,
    step_up_state: SolarStepUpState,
) -> float:
    """R7's three-row table: solar-reserve cap -> solar step-up -> default.
    `step_up_state` reflects whatever resolve_solar_step_up already computed
    this cycle (row 2's current value, if any) -- this function only applies
    the priority order, it does not itself run the step-up lifecycle.
    """
    if solar_reserve_active:
        return solar_reserve_soc
    if step_up_state.stepped_pct is not None:
        return step_up_state.stepped_pct
    return soc_limit_override
```

**Testable on its own:** plain pytest — the three-row priority order; step-up applies/clamps/persists
across `Solar`↔`SolarOnly`/clears on non-solar-mode or disconnect (R8, UC06 state table); the reserve
condition's five-way AND (R9, UC07 state table) including the mutual-exclusivity clause with
tomorrow's deadline.

---

## 6. Deadline Engine (E4) — new module `engines/deadline.py`

```python
def resolve_departure_deadline(
    external_configured: bool,
    external: time | None,
    is_holiday: bool,
    holiday_override: time | None,
    home_day_flag: bool,
    home_day_override: time | None,
    day_of_week_default: time | None,
) -> time | None:
    """R14's four-row table: external sensor -> holiday -> home-day -> day-of-week
    default. Any row, including the terminal default, may resolve to None ("no
    deadline"). Public-holiday wins over home-day when both apply (requirements.md
    R14, second bullet).

    `external_configured` is distinct from `external` being None: the
    `departure_external` adapter role is optional (NF3) -- when it is not mapped
    at all, row 1 must never match, falling through to row 2, exactly like every
    other optional role in this system. When it IS mapped, its current reading
    (including None, "sensor currently reports no deadline") wins outright, per
    R14's "external sensor ... takes precedence over all configured values." The
    coordinator (not this function) knows whether the role was configured (§10).
    """


@dataclass(frozen=True)
class RequiredCurrentResult:
    required_a: float | None  # None when no deadline is resolved (urgency never applies)
    urgent: bool              # required_a > baseline_desired_a
    unreachable: bool         # required_a > maximum_permitted_rate


def resolve_required_current(
    deadline: time | None,
    now: datetime,
    soc: float,
    active_soc_limit: float,
    ev_battery_capacity_kwh: float,
    voltage: float,
    baseline_desired_a: float,
    maximum_permitted_rate_a: float,
) -> RequiredCurrentResult:
    """R5/R15's required-current formula (resolution-rules.md 'Required current for
    the departure deadline'): energy_needed = capacity * (limit - soc) / 100;
    time_remaining = deadline - now; required_a = energy_needed / time_remaining,
    W->A via `voltage`. urgent = required_a > baseline_desired_a (the mode rows
    3-5 of Auto mode-selection would otherwise pick, or the Manual mode itself --
    the caller resolves `baseline_desired_a`, this function only compares).
    unreachable = required_a > maximum_permitted_rate_a even so."""
```

`deadline - now <= 0` (the deadline has already passed today) is treated the same as urgency already
being maximal — `required_a` saturates rather than raising a `ZeroDivisionError` (a same-day
deadline in the past is not one of R14's documented "no deadline" cases, so this function must still
return a defined value); the exact edge is a test anchor to write down, not a new rule (control-cycle
never lets `now` outrun the deadline by more than one control interval before the next resolution
runs).

**Testable on its own:** plain pytest — R14's four rows incl. holiday-over-home-day precedence and
every "no deadline" path; R5/R15's formula against worked examples; the urgent/unreachable
boundaries: `required_a` at/below baseline (Normal), between baseline and max rate (Urgent), above
max rate (Unreachable) — the exact three-state table UC05's state model specifies.

---

## 7. Capability-Gate Engine (E9) — new module `engines/capability_gate.py`

```python
def resolve_available_modes(solar_available: bool, captar_available: bool) -> frozenset[str]:
    """R18's runtime available-mode set. Power and Off are always available;
    Solar/SolarOnly require solar_available; Captar requires captar_available."""
    modes = {MODE_OFF, MODE_POWER}
    if solar_available:
        modes |= {MODE_SOLAR, MODE_SOLAR_ONLY}
    if captar_available:
        modes.add(MODE_CAPTAR)
    return frozenset(modes)
```

This is the **runtime** counterpart to `select.py`'s existing entity-definition-time option list
(project-plan.md E9's own distinction) — `ModeSelect` keeps building its options directly from the
same two config booleans (unchanged, §0); this function exists so `Auto` mode-selection (E2, §8) can
ask the identical question without a config-flow dependency, per project-plan's "C2 reuses the same
facts" integration note.

**Testable on its own:** plain pytest — the four capability combinations (project-plan.md E9's own
acceptance).

---

## 8. `Auto` profile (E2) — new module `profiles/auto.py`

```python
def select_mode(
    soc: float,
    active_soc_limit: float,
    available_modes: frozenset[str],
    urgent: bool,  # resolution-rules.md row 2's own condition; UC05's Unreachable state is still
                   # `urgent=True` from this function's point of view (the caller's `unreachable`
                   # flag only changes what the delivered current clamps to and whether M1 notifies,
                   # §11 -- it never changes which mode row 2 selects, so this function needs no
                   # separate `unreachable` parameter)
    solar_capability_present: bool,
    sun_is_up: bool,  # mutually exclusive with sun_is_down by construction (both derived from the
                      # same sun.sun reading) -- the caller passes one boolean pair, not two
                      # independent sources of truth
    solar_surplus_sufficient: bool,  # UC01's own start condition, evaluated by the caller
    sun_is_down: bool,
    low_tariff_active: bool,
    solar_reserve_active: bool,  # E3's resolve_solar_reserve_active output (§5), reused verbatim
) -> str:
    """resolution-rules.md's Auto mode-selection table, rows 1-5, first match wins:
    1. soc >= active_soc_limit -> Off
    2. urgent -> Captar if MODE_CAPTAR in available_modes else Power
    3. solar_capability_present and sun_is_up and solar_surplus_sufficient -> Solar
    4. sun_is_down and low_tariff_active and not solar_reserve_active -> Captar
       (only reachable when MODE_CAPTAR in available_modes -- R18: absent CapTar,
       row 4 simply never matches, falling through to row 5, NOT a Power fallback --
       this is the row-2-only carve-out, resolution-rules.md's own distinction)
    5. otherwise -> Off
    """
```

Row 4's `MODE_CAPTAR in available_modes` guard, not a `captar_available` bool, keeps this function's
only capability dependency going through E9's output (project-plan.md E2: "the set of available
modes passed in as an input ... not a Capability-Gate call") — `Auto` never calls E9 itself; the
coordinator does (§10) and passes the result in.

`Manual` needs no module here (resolution-rules.md: "`Manual` needs no table"); the coordinator
already reads `select.smart_charging_mode` directly for that case (unchanged).

**Testable on its own:** plain pytest — every row incl. the two urgency-escalation branches (`Captar`
present/absent, R18), the solar-reserve withholding of row 4 (R9, UC07), and that row 1 compares
against the resolved (already-row-1/2/3'd) `active_soc_limit`, not the default (UC01's step-up-aware
note in the resolution-rules table).

---

## 9. Effective-peak-limit row 1 (extends `engines/billing_protection.py`)

```python
def resolve_effective_peak_limit(monthly_peak_kw: float, max_peak_kw: float, urgent: bool) -> float:
    """Row 1: urgent -> max_peak_kw (R5/C3). Row 2 (unchanged): min(monthly, max)."""
    if urgent:
        return max_peak_kw
    return min(monthly_peak_kw, max_peak_kw)
```

A new required keyword parameter on an existing pure function — every existing call site (only
`coordinator.py`, §10) is updated in the same task. No new module; this is the row-1 completion the
existing docstring already flags as blocked on E4.

---

## 10. Control cycle (M1 wiring)

Extends `_run_cycle`, inserted into the existing step order per `control-cycle.md` (step numbers
below match that doc):

1. **(step 1, unchanged)** Read sensors — plus the new optional roles (`ev_battery_capacity`,
   `departure_external`, `home_day_external`, `solar_forecast`) when configured, defaulting to the
   configured fallback (`ev_battery_capacity`: `CONF_EV_BATTERY_CAPACITY_KWH`) or `None`/`False` otherwise.
2. **(new, before step 4)** Resolve tomorrow's departure deadline (E4, one-day-ahead inputs — R14's
   own note) to get `solar_reserve_active` (E3, §5) — needed before step 4's SOC-limit resolution.
3. **(step 4, extended)** Resolve the active SOC limit via the full three-row table (E3, §5) instead
   of row-3-only; resolve today's departure deadline and the required-current/urgency result (E4,
   §6) using the **baseline** mode — computed by evaluating Auto mode-selection rows 3–5 (or the
   `Manual` selection) with `urgent=False` first, exactly as resolution-rules.md specifies ("the
   comparison ... always uses the baseline mode"); resolve available modes (E9, §7); then resolve the
   actual active mode — `Manual`: the selector; `Auto`: `select_mode` (E2, §8) with the real `urgent`
   result. Dispatch to that mode module as today.
4. **(step 5, extended)** Resolve the effective peak limit with the new `urgent` parameter (§9)
   before applying the R3 clamp — unchanged clamp call otherwise.
5. **(steps 6–8, unchanged)** Grid ceiling, invariants, write.

New coordinator state threaded across cycles: `self._step_up_state: SolarStepUpState` (E3). Its
clearing is **not** wired to the coordinator's generic per-mode-switch reset (that reset also fires
on a `Solar`↔`SolarOnly` switch, which R7/UC06 alternate-flow 4a requires to *preserve* an in-effect
step-up). Instead, `resolve_solar_step_up` (§5) is called every cycle with
`is_solar_mode_charging = active_profile == PROFILE_AUTO and active_mode in (MODE_SOLAR,
MODE_SOLAR_ONLY)` (R8 is `Auto`-only, like R9's reserve cap) computed fresh from the
**resolved** active mode this cycle (under `Auto`, this is necessarily the *prior* cycle's resolved
mode, since step 3 below resolves the step-up before selecting this cycle's mode — one cycle of lag,
matching R8's own "next control cycle" framing); its own `False`-when-not-solar branch is what clears
`self._step_up_state`, on both a non-solar mode *and* a disconnect (the coordinator passes
`is_solar_mode_charging=False` whenever `charger_status` is not in `CHARGEABLE_STATES` too). No
separate reset call is added to the mode-switch/disconnect branches. `self.active_profile: str`
(seeded `Manual`, written by `select.smart_charging_profile`, mirrors `self.active_mode`).

`sensor.smart_charging_active_soc_limit` and `ActiveSocLimitChanged`'s emission (change-detected
against the prior cycle's resolved value, per `control-cycle.md` step 4) are added here — the
`ActiveSocLimitChanged`-driven vehicle sync itself is M2's job (deferred, §11); this slice only emits
the event and surfaces the sensor, per ADR-0011's publish-step gate, which already covers this event
name (no new ADR gate).

`DeadlineUnreachableNotified` is also emitted here (same ADR-0011 publish-step gate), fired every
cycle `resolve_required_current`'s (E4, §6) `unreachable` flag is `True` (UC05: "re-fires while
remaining in Unreachable," not only on the transition edge) — delivery to the user is M3's job
(deferred, §11); this slice only publishes the event.

---

## 11. Deliberately deferred

- **M2 (Vehicle-Limit Manager) and M3 (Notification Manager)** — separate epics (#256, #257).
  `ActiveSocLimitChanged`/`DeadlineUnreachableNotified` are emitted by this slice (§10, per
  ADR-0011's already-accepted publish-step gate) but have no subscriber yet; this is the same
  "publish now, subscribe later" pattern the project-plan already prescribes for M1's other domain
  events.
- **The evening home-day prompt (UC08)** — M3's job. `switch.smart_charging_home_day` exists and is
  user-settable directly (its own acceptance criterion, R13: "at least one configured mechanism");
  the automated prompt is simply a second way to set the same switch, added later without changing
  this slice's entity.
- **The plug-in reminder (UC10/R12)** — M3's job; unrelated to this slice's engines.
- **A materialized "resolved departure deadline" entity** — `entity-catalog.md`'s own note: computed
  fresh each cycle, no entity today; if a future use-case needs one, it adds the row then.

---

## 12. Testing

Pure logic (`engines/soc_target.py`, `engines/deadline.py`, `engines/capability_gate.py`,
`engines/billing_protection.py`, `profiles/auto.py`) → plain pytest, no HA harness (ADR-0009).
Adapters, entities (`select.py`, `sensor.py`, new `time.py`/`switch.py`), config flow, and
`coordinator.py` → HA harness. One end-to-end HA-harness regression per UC05/UC06/UC07's main
success scenario + each alternate/exception flow, mirroring Captar's Task 6.2 shape.

---

## 13. Packaging

No new top-level package: `engines/deadline.py` and `engines/capability_gate.py` join the existing
`engines/` package (ADR-0010, already accepted — homes every one of E3/E4/E9); `profiles/auto.py`
joins the existing (currently empty) `profiles/` package (ADR-0002). Two new platform files,
`time.py` and `switch.py`, at the package root alongside `select.py`/`sensor.py`/`number.py`
(ADR-0002's existing pattern).

---

## 14. Next step

Derive the task-by-task TDD plan (`2026-07-21-deadline-soc-management.md`) from this design with the
`writing-plans` skill, then route both through `impl-spec-reviewer` before either is committed to the
PR, per the `write-impl-spec` skill's cycle.
