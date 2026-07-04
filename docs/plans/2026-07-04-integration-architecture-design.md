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
adapter layer**, not new HA entities. `NF3` will be reworded during the next requirements
pass to say "all device I/O goes through an internal adapter abstraction" rather than
implying wrapper entities exist in HA.

- Each required role (charger current, EV SOC, solar power, grid power, plug status,
  charger status, EV status, ...) is mapped once, during config flow, to the user's real
  `entity_id`.
- Config flow validates the mapped entity exists and is the expected platform (e.g. the
  charger-current role must resolve to a `number` entity).
- Numeric roles read/write the entity's native value directly.
- Enum/status roles (charger status, plug status, EV status) additionally capture a
  **state-translation table** during config flow: the user maps each of their hardware's
  actual state strings to the integration's canonical states (`Idle`, `Plugged`,
  `Charging`, `Fault`, `Unavailable`, ...). The adapter translates in both directions.
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

1. Read raw values through adapters (grid power, solar power, EV SOC, charger status,
   plug status, ...).
2. Smooth per R10 (rolling mean over N cycles); keep the raw values too — CapTar breach
   checking (R3) uses raw readings so a breach can't hide behind the smoothing window.
3. Resolve the active profile → active mode (`profiles/manual.py` uses the user's
   `select.smart_charging_mode`; `profiles/auto.py` runs the flow-selection logic).
4. Dispatch smoothed readings + config to the active mode module (`modes/*.py`) →
   desired current.
5. Clamp the desired current with peak protection, using raw readings.
6. Apply rapid-cycling prevention (R11).
7. Write the result through the charger-current adapter (skip the write if unchanged).
8. Update the owned diagnostic entities.
9. Evaluate notification triggers (R12 plug-in reminder, R13 home-day evening prompt).

Mode modules (`solar.py`, `solar_only.py`, `captar.py`, `power.py`, `off.py`) are pure
functions/classes: smoothed readings + config in, desired current out — no direct HA
or adapter access, per NF2 (one self-contained unit per mode). This is what makes them
unit-testable without a running Home Assistant instance.

---

## Decision 6 — Error handling

- An adapter returning `None` (mapped entity missing/unavailable) is treated as a fault:
  the coordinator sets `sensor.smart_charging_status` to `Fault` and holds/stops charging
  safely rather than guessing a value. It never silently substitutes a default for a
  role that's supposed to be live hardware data.
- Each outage logs once at `warning` level, not once per cycle (avoid log spam); a
  recovery logs at `info` level.
- Changing entity mappings via the reconfigure flow triggers a full config-entry reload.

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

- Multi-minimum-HA-version support (targeting current stable only for now).
- Three-phase support (already deferred at the analysis layer).
- Dev tooling: skills/agents, GitHub Actions workflows, issue labels — separate design.
