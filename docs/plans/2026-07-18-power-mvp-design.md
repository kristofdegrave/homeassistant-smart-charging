# Power-mode MVP — design

**Date:** 2026-07-18
**Status:** approved (design); implementation plan to follow via `writing-plans`
**Type:** implementation design (a first slice of the approved architecture — not a new decision)

This document defines the **minimum viable product** for the Smart Charging integration: an
HACS-installable Home Assistant integration that supports a **single charging mode (`Power`)** with
**minimal configuration**, and is safe to run against a real grid connection.

It is a deliberate **subset** of the full architecture. Every component below is a slice of a service
already named in [`../design/system-design.md`](../design/system-design.md) and sequenced in
[`../design/project-plan.md`](../design/project-plan.md). Nothing here introduces a new service, call
direction, or structural decision — so no new ADR is required, and none of this work is throwaway.

---

## 1. Success criteria (what "works" means)

A successful MVP is an integration the user can **install and use**:

1. Installable via HACS as a custom repository.
2. A single config flow completes and creates the integration.
3. A `number.smart_charging_target_current` entity appears and is adjustable from the HA UI.
4. With a car connected, adjusting the target current changes the charger's commanded current.
5. Disconnecting the car (or a fault) writes **0 A**.
6. The commanded current **never** breaches the configured grid-supply ceiling.

That is the entire acceptance bar for v1. Everything else is a later slice.

---

## 2. Install-time configuration

The config flow collects only what `Power` mode + grid safety require. Every field is load-bearing.

| Field | Role | Notes |
| --- | --- | --- |
| **Charger current entity** (r/w) | `charger_current` adapter | The HA entity that sets charge current. |
| **Charger status entity** (r) | `charger_status` adapter | Raw charger state. |
| **Status translation map** | `charger_status` raw→canonical | Many raw values → one canonical state (`"Charging"`,`"SuspendedEV"`→`charging`; `"Connected"`,`"Cable"`→`connected`; everything else→`disconnected`). |
| **Net power entity** (r) | `net_power` adapter | Whole-home import/export. |
| **Charger power entity** (r) | `charger_power` adapter | To isolate the non-charger baseline for the clamp. |
| **Grid voltage entity** (r, *optional*) | `grid_voltage` adapter | NF4: if missing/unavailable, fall back to nominal voltage — voltage `None` does **not** trigger the fault path. |
| **Nominal voltage** | config value | Default **230 V**. Used for the NF4 fallback and power↔current conversion. |
| **Min / max current** | floor/cap bounds | Explicit A. Clamp bounds for the commanded current. |
| **Grid supply ceiling** | C4 limit | Max current/power importable from the grid — enforced by the grid-safety clamp. |
| **Default target current** | seeds the owned entity | Initial value of `number.smart_charging_target_current`. |

**Control interval** is not asked at install: it defaults to **30 s** and is tunable later in the
options flow (ADR-0005).

The config surface is intentionally small; if implementation reveals a genuinely required field, it
is added then — not speculatively now (YAGNI).

---

## 3. Runtime surface (owned entities)

- **`number.smart_charging_target_current`** — restore-state, bounds = configured min/max, initial
  value = configured default. Adjustable anytime from the UI/dashboard/automations.

Single mode ⇒ **no mode selector**. This one number entity is the entire owned surface (the C2
pattern, ADR-0004 native naming).

---

## 4. Control cycle

Runs every control interval (fired by the interval timer):

```text
read charger_status (raw) → translate to canonical
read net_power, charger_power, grid_voltage (grid_voltage None → nominal, NF4)
read target_current (number entity)

if canonical ∈ {connected, charging}:
    desired = clamp(target_current, min, max)          # floor/cap — E8
    baseline_w = net_w − charger_w                     # non-charger household load
    headroom_a = (ceiling − baseline_w) / voltage
    desired = min(desired, headroom_a)                 # grid-safety ceiling — E6, no opt-out
else:
    desired = 0

write charger_current ← desired
```

Notes:

- The grid-safety clamp solves from the **actual baseline flowing** (`net_w − charger_w`), not from
  the requested current — matching the clamp math in `project-plan.md` §6 / system-design.
- The clamp has **no opt-out** and runs **every cycle** (ADR-0006). In `Power` mode the peak clamp
  (E5) is skipped by design (R17), but grid-safety (E6) is not skippable.
- An adapter returning `None` (except `grid_voltage`, per NF4) is the ADR-0007 fault signal → the
  cycle writes **0 A**.

---

## 5. Mapping to the full architecture

Every MVP component is a subset of a named service — built on-architecture, not as a detour:

| MVP component | Full-design service | Test boundary (ADR-0009) |
| --- | --- | --- |
| `charger_current` r/w, `charger_status` + translation, `net_power`, `charger_power`, `grid_voltage` | Adapters — **RA1** | HA harness |
| config/options read + owned-entity read/write | Store — **RA3** | HA harness |
| `desired = target` (pure fn) | Power mode — **E1** | plain pytest |
| floor/cap clamp | Cycle-Invariant — **E8** | plain pytest |
| grid-supply ceiling clamp | Grid-Safety — **E6** | plain pytest |
| voltage NF4 fallback | Signal-Conditioning — **E7** (voltage slice only; R10 smoothing deferred) | plain pytest |
| the ordered cycle (`DataUpdateCoordinator`) | Coordinator — **M1** | HA harness |
| interval timer | **C1** | HA harness |
| `number.smart_charging_target_current` | Owned entities — **C2** | HA harness |
| config / options flow | **C4** | HA harness |

Package layout per ADR-0002 (`adapters/`, `modes/`, `coordinator.py`, `entity.py`, platform files);
native naming per ADR-0004; fault-on-`None` per ADR-0007; two-distinct-clamp-sites discipline per
ADR-0006 (E6 is a structurally separate call site even though E5 is absent in the MVP).

---

## 6. Deliberately deferred

Out of scope for v1, each a later slice of `project-plan.md`:

- Other charging modes (`Off`, `Solar`, `SolarOnly`, `Captar`) and the `Auto` profile — E1 (rest), E2.
- Solar sensing, peak clamp / peak-demand tracker (E5), SOC-target & deadline logic (E3/E4).
- Notifications & prompting (M3), vehicle charge-limit sync (M2).
- R10 signal smoothing, R11 cooldown/hold gating.
- Runtime dashboard (UC11 / C5).

The **grid-safety ceiling clamp is included** (not deferred): with it, the MVP cannot command a
current that breaches the configured supply, so v1 is safe as a real HACS release rather than a
test-only install.

---

## 7. Testing

- **Plain pytest** (no HA) for the pure pieces: the `Power` engine (`desired = target`), the floor/cap
  clamp, the grid-safety headroom solve (with worked examples), and the NF4 voltage fallback.
- **HA harness** (`pytest-homeassistant-custom-component`) for the HA-coupled pieces: config flow
  produces a valid entry; the coordinator runs one full cycle and writes `charger_current`; the number
  entity restores state; the status translation resolves raw→canonical including the many-to-one case;
  the fault path writes 0 A.

---

## 8. Packaging

```text
custom_components/smart_charging/
  manifest.json
  __init__.py          # setup/unload the config entry, create the coordinator + timer
  const.py
  config_flow.py       # C4 (install + options)
  coordinator.py       # M1 (DataUpdateCoordinator)
  number.py            # C2 (target-current entity)
  entity.py            # owned-entity base (ADR-0002)
  adapters/            # RA1 (protocol + factory + roles)
  modes/               # E1 (Power)
hacs.json              # repo root — custom-repo install metadata
```

---

## 9. Next step

This design feeds the `writing-plans` skill to produce the ordered, test-driven implementation plan.
Build order follows `project-plan.md`: adapters (RA1 subset) → engines (E1/E6/E7/E8 subset) →
coordinator (M1) → clients (C1/C2/C4). No `custom_components/` code is written until that plan exists
and is approved.
