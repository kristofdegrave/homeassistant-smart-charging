# Integration Architecture Design — Smart Charging HACS Integration

*Date: 2026-07-04*

## Context

The analysis layer is complete for the modes and flows built so far (system-overview,
requirements, control-cycle, resolution-rules, entity-catalog, UC01–UC04). This document
is the bridge between that behavioural spec and code: it decides the technical shape of
the Home Assistant custom integration before any scaffolding happens, per the project's
analysis-first methodology.

Scope is architecture only. Dev tooling (skills/agents, GitHub Actions workflows, issue
labels) is a deliberately separate follow-up design, since it depends on decisions made
here (testing strategy, config-entry structure).

**Target:** current stable Home Assistant core. Support for older minimum HA versions is
explicit future scope, not designed for yet.

---

## Decision 1 — Domain and package layout

- Domain/slug: `smart_charging`
- Package: `custom_components/smart_charging/`
- Repo layout addition:

```text
custom_components/
  smart_charging/
    __init__.py
    manifest.json
    config_flow.py
    coordinator.py
    const.py
    adapters/
    modes/
    profiles/
    entity.py            # base entity classes for owned entities
    select.py / number.py / time.py / sensor.py / switch.py / binary_sensor.py
tests/
  ...                     # mirrors custom_components/smart_charging/ structure
hacs.json
```

`docs/` is unaffected; `docs/analysis/` remains the source of truth for behaviour.

---

## Decision 2 — Hardware abstraction: config-flow entity mapping + Python adapters

Rejected alternative: synthetic `sc_`-prefixed proxy entities kept in sync via
automations/templates. That adds an extra state hop, is fragile, and isn't idiomatic
for a Python integration — HA integrations that sit on top of arbitrary hardware
(e.g. Versatile Thermostat, Better Thermostat) resolve this in code, not via automations.

**Decision:** the "sc_ wrapper" described in `system-overview.md` (NF3) is a **Python-side
adapter layer**, not new HA entities.

**Known conflict, tracked in [issue #29](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/29).**
NF3 (Must) currently reads literally — "every sensor value ... read from an `sc_`-prefixed
**wrapper entity**" — and `entity-catalog.md` operationalizes that literally as concrete HA
entities (`sensor.sc_net_power_w`, `number.sc_charger_current`, etc.), explicitly stating raw
upstream entities are "never catalog rows." This decision conflicts with that committed text.
**Until NF3 and `entity-catalog.md` are actually reworded** (via the standard
write-requirement flow — 6Cs self-check, fresh-agent review, human approval — tracked in
issue #29), **they remain the authoritative source of truth**, per this project's
methodology. This design should not be treated as implementable ahead of that reword landing.

This design is scoped to the roles UC01–UC04 actually need — the mapped roles enumerated
below, plus the four control-cycle inputs already wired into Decision 5's pipeline (grid
voltage, monthly peak demand, in addition to net/solar/charger power and charger status).
Everything else in `entity-catalog.md` (low-tariff flag, solar forecast, home-day/departure
entities, battery-capacity sensor, vehicle charge-limit write-back, car-home presence, and
the ~20 remaining config thresholds outside this scope) is **out of scope for this design**
and deferred to the follow-up design that lands once UC05–UC10 exist — it is not modeled,
not forgotten.

- Each required role (charger current, EV SOC, solar power, charger power, grid voltage,
  monthly peak demand, and — when the solar capability is present — solar power; charger
  status as an enum role) is mapped once, during config flow, to the user's real `entity_id`.
- Config flow validates the mapped entity exists and is the expected platform (e.g. the
  charger-current role must resolve to a `number` entity).
- Numeric roles read/write the entity's native value directly.
- Enum/status roles (charger status) additionally capture a **state-translation table**
  during config flow: the user maps each of their hardware's actual state strings to the
  three canonical charger states already defined in `system-overview.md`'s glossary and
  `entity-catalog.md` — `disconnected`, `connected`, `charging` (not a new vocabulary).
  The adapter translates in one direction, raw → canonical; the coordinator never writes
  charger status back to the hardware.
- A raw state with no entry in the translation table (e.g. an unmapped firmware state) is
  treated the same as an unavailable entity — the adapter returns `None`, which Decision 6's
  fault handling picks up (a mapping the user never provided is treated as missing data,
  the same as a sensor that's actually offline).
- Adapters live in `adapters/`, one class per role, sharing a common `Adapter` protocol
  (`async def read()`, `async def write(value)`).

---

## Decision 3 — Owned entities vs mapped entities

Two distinct entity populations:

1. **Mapped hardware entities** — the user's existing charger/EV/solar/grid entities,
   referenced by `entity_id`, never modified or renamed by this integration.
2. **Owned control/diagnostic entities** — new entities created by `smart_charging`,
   grouped under one HA device (e.g. "Smart Charging"):
   - `select.smart_charging_profile` (Manual / Auto)
   - `select.smart_charging_mode` (Manual profile's mode override: Solar / SolarOnly /
     Captar / Power / Off)
   - `number.smart_charging_soc_limit_override`
   - `time.smart_charging_departure_*`
   - `switch.smart_charging_wfh`
   - `sensor.smart_charging_desired_current`, `sensor.smart_charging_effective_peak_limit`,
     `sensor.smart_charging_active_mode`, `sensor.smart_charging_status` (Fault/OK)
   - `binary_sensor.smart_charging_plug_in_reminder`

State for owned entities persists via HA's normal entity-registry restore-state; no
custom storage is needed for them.

---

## Decision 4 — Config entry structure and control-cycle interval

- **Config entry `data`** (set at initial setup, changed via a reconfigure flow, not
  live-editable): entity-role mappings, state-translation tables, declared capabilities
  (R18, e.g. solar present).
- **Config entry `options`** (changeable any time via Settings → Integrations →
  Configure): thresholds and defaults (start thresholds, safety margin, grace periods,
  smoothing window N), and the **control-cycle interval**.
- The control-cycle interval is a fixed options-flow setting, not an entity — consistent
  with how most HA polling coordinators expose their update interval. Changing it in
  options reloads the config entry.

---

## Decision 5 — Coordinator and data flow

A single `DataUpdateCoordinator` subclass drives the control cycle at the configured
interval:

1. Read raw values through adapters: net power, charger power, EV SOC, charger status,
   monthly peak demand, and — when solar is present — solar power; grid voltage is read
   when mapped, otherwise treated as absent (not a fault — see step 3).
2. Smooth net power and solar power per R10 (rolling mean over N cycles); charger power is
   used raw (`entity-catalog.md`'s note on `sc_charger_power_w` is explicit it is not an
   operand of solar surplus via the smoothed channel). Keep the raw net-power reading too —
   the R3/C4 clamps in steps 6–7 use raw readings so a breach can't hide behind the
   smoothing window.
3. Resolve the supply voltage (NF4): the measured grid-voltage reading when healthy,
   otherwise the configured nominal voltage. This is the one input where "missing" is
   expected, normal behavior, not a Decision-6 fault — NF4 explicitly requires the
   fallback.
4. Resolve the active SOC limit (`resolution_rules.active_soc_limit`, scoped in this
   implementation to the default row only — see the scaffolding plan).
5. Resolve the active profile → active mode (`profiles/manual.py` uses the user's
   `select.smart_charging_mode`; `profiles/auto.py`, once it exists, runs the
   flow-selection logic).
6. Dispatch smoothed readings + resolved SOC limit + config to the active mode module
   (`modes/*.py`) → desired current.
7. Apply the R3 peak-protection clamp on raw readings (skippable only in `Power` mode with
   its peak-protection option disabled).
8. Apply the C4 grid-supply-ceiling clamp on raw readings — **a distinct, always-active
   step from step 7**, per `control-cycle.md`'s explicit two-clamp structure: C4 is "the
   one clamp `Power` mode cannot switch off," so it runs even when step 7 was skipped.
9. Apply rapid-cycling prevention (R11) and the C1 floor/cap invariant.
10. Write the result through the charger-current adapter (skip the write if unchanged),
    update the owned diagnostic entities, and evaluate notification triggers (R12/R13,
    once those use-cases exist).

Mode modules (`solar.py`, `solar_only.py`, `captar.py`, `power.py`, `off.py`) are pure
functions/classes: smoothed readings + config in, desired current out — no direct HA
or adapter access, per NF2 (one self-contained unit per mode). This is what makes them
unit-testable without a running Home Assistant instance.

---

## Decision 6 — Error handling

- An adapter returning `None` for a **required** role (mapped entity missing, unavailable,
  or — for charger status — reporting a raw state with no translation-table entry) is
  treated as a fault: the coordinator sets `sensor.smart_charging_status` to `Fault`,
  forces 0 A through the same C1/R11 invariants as any other stop (no bypassing the
  cooldown machinery on the fault path), and never guesses a substitute value.
- **Grid voltage is the one documented exception**: a missing/unavailable reading there is
  NF4's normal fallback path (resolve to the nominal voltage), not a fault.
- An uncaught exception anywhere in a coordinator cycle is treated the same as the fault
  path above (force 0 A, set `Fault`) rather than leaving the charger at its last set
  current — `DataUpdateCoordinator`'s default backoff/retry behavior is not sufficient on
  its own for a loop with a safety-critical clamp, since it does not guarantee the charger
  current gets re-evaluated on the library's own schedule.
- Each outage logs once at `warning` level, not once per cycle (avoid log spam); a
  recovery logs at `info` level.
- Changing entity mappings via the reconfigure flow, or a threshold change via the options
  flow, triggers a full config-entry reload — which recreates the coordinator and its mode
  instances, resetting any in-progress hold/cooldown timer. This is an accepted trade-off
  (thresholds change rarely, and R11's "runs to completion" concern is about normal
  operation, not about the user actively reconfiguring the integration) rather than an
  oversight; call it out explicitly if a future revision finds it surprising in practice.
- R6 (vehicle charge-limit write-back) and its C2 "never while away from home" guard are
  out of scope for this design — see the "Explicitly deferred" section.

---

## Decision 7 — Testing strategy

- `pytest-homeassistant-custom-component` provides the HA test harness; `MockConfigEntry`
  drives config-flow and coordinator integration tests.
- Mode modules, profile modules, peak protection, SOC management, and deadline escalation
  are pure logic — unit-tested directly with plain pytest, no HA dependency required.
  Test names reference the requirement they verify (e.g.
  `test_r1_solar_first_holds_at_minimum_during_grid_fallback`) for traceability back to
  `requirements.md` / the UC acceptance criteria.
- Adapter classes are tested against mocked HA state objects (entity present, absent,
  unavailable, and — for enum roles — an unmapped raw state).
- CI enforcement (pytest, ruff, hassfest, HACS validation) is scoped to the dev-tooling
  follow-up design, not this document.

---

## Explicitly deferred

- **NF3's wording and `entity-catalog.md`'s entity-model framing** — tracked in
  [issue #29](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/29);
  this design's Decision 2 is provisional until that lands.
- **Everything behind UC05–UC10**, matching the scaffolding plan's scope decision: the
  departure-deadline guarantee (R5) and its effect on the effective peak limit, vehicle
  charge-limit write-back and its C2 guard (R6), solar SOC step-up (R8), the solar-reserve
  cap (R9), notifications (R12/R13), and the `Auto` profile's flow-selection logic (R16) —
  none of these have a role, owned entity, or pipeline step in this design yet. The
  low-tariff flag, solar-forecast sensor, home-day/departure entities, and battery-capacity
  sensor are likewise unmapped. Each is additive once its use-case doc exists, not a
  rewrite of what's here.
- Multi-minimum-HA-version support (targeting current stable only for now).
- Three-phase support (already deferred at the analysis layer).
- Dev tooling: skills/agents, GitHub Actions workflows, issue labels — separate design.
