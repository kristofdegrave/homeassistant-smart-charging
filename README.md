# homeassistant-smart-charging

<img src="custom_components/smart_charging/brand/logo@2x.png" alt="Smart Charging logo" width="96" height="96" align="right" />

Smart EV charging integration for Home Assistant — solar-first and
capacity-tariff-aware. Hardware-agnostic; targets single-phase grids for now
(three-phase later).

> **Status: Power/Solar/SolarOnly/Captar modes.** This project follows an analysis-first,
> spec-driven methodology — the documents under [`docs/analysis/`](docs/analysis/)
> are the source of truth for the full design. The current code implements the
> **Power**, **Solar**, **SolarOnly**, and **Captar** modes, selected manually via
> `select.smart_charging_mode`: a target-current control loop with grid-safety
> clamping (never exceed the configured grid ceiling), solar-surplus-driven
> charging with start/hold/cooldown behaviour, and capacity-tariff (CapTar) peak
> protection — a monthly-peak-aware charging mode with its own grace/cooldown
> behaviour, plus an opt-in peak-respecting clamp available to `Power` mode too.
> The `Auto` profile, deadline management, and notifications are **not
> implemented yet** — see [Deferred](#deferred-not-in-this-mvp) below. See
> [CLAUDE.md](CLAUDE.md) for the working method.

## Installation (HACS custom repository)

1. In Home Assistant, open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add this repository's URL with category **Integration**.
3. Install **Smart Charging**, then restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Smart Charging**
   and complete the setup form (see below).

## Configuration

The setup form maps the entities that represent your charger and grid, and
sets the initial thresholds:

| Field | Role |
| --- | --- |
| Charger current control entity | `number` entity that sets the charger's output current (A) |
| Charger status entity | `sensor`/`binary_sensor` reporting the charger's connection/charging state |
| States meaning "connected" / "charging" | Comma-separated raw state values from the status entity, mapped to the integration's canonical states |
| Net grid power entity | `sensor` for net grid import/export power |
| Charger power entity | `sensor` for the charger's current power draw |
| Grid voltage entity (optional) | `sensor` for live grid voltage; falls back to the configured nominal voltage when unset |
| Solar installed | Toggle that offers `Solar`/`SolarOnly` in the mode selector; requires the EV SOC entity to be mapped |
| CapTar available | Toggle (default on) that offers `Captar` in the mode selector; requires the EV SOC entity to be mapped |
| EV state-of-charge entity (required if Solar installed or CapTar available) | `sensor` for the EV's state of charge (%) |
| Nominal grid voltage, min/max current, grid ceiling, grid safety offset, default target current | Thresholds, editable anytime afterwards via **Configure** |
| Smoothing window | Rolling-window sample count for surplus smoothing (R10) |
| Solar start threshold, SolarOnly start threshold | Surplus power (W) required to start charging in each mode |
| Solar post-surplus hold duration, cooldown duration | Minutes charging holds after surplus drops, and before a mode may restart |
| SolarOnly amp-step rounding strategy, round-nearest midpoint fraction | How SolarOnly rounds ideal current to a whole amp |
| Default charge limit | Config-time default (%) for `number.smart_charging_soc_limit_override` |
| CapTar peak safety margin (W) | Margin subtracted below the effective peak limit before Captar clamps the target current |
| CapTar maximum peak (kW) | Configurable ceiling on the billed monthly peak; the effective peak limit never exceeds this |
| CapTar peak grace period (min) | How long a peak breach must persist before Captar force-stops charging (the headroom clamp itself applies every cycle; avoids stopping on brief spikes) |
| Captar cooldown duration (min) | Minutes Captar must wait after a sustained-breach stop before it may restart |
| Power mode respects the peak limit | Opt-out (default on, R17): when enabled, `Power` mode also clamps to the effective peak limit instead of only the grid ceiling |

Entity-role mappings can be changed later via **Reconfigure** (this re-validates
and reloads the integration). Thresholds and the control interval can be changed
anytime via **Configure**; this also reloads the integration, but does not
re-validate the entity mappings.

`select.smart_charging_mode` chooses the active mode: `Off`/`Power` always
available, `Solar`/`SolarOnly` offered only when Solar installed is enabled,
`Captar` offered only when CapTar available is enabled (on by default). In
`Power` mode, `number.smart_charging_target_current` sets the desired charging
current; the control loop clamps it to the configured min/max and to the
grid-safety ceiling — and, when "Power mode respects the peak limit" is
enabled, to the effective peak limit too — and writes 0 A whenever the charger
is disconnected or faulted. In `Solar`/`SolarOnly` mode, the control loop
derives the target current from solar surplus instead. In `Captar` mode, the
control loop tracks the rolling monthly peak and clamps the target current to
stay a safety margin below the effective peak limit (`min(monthly peak, CapTar
maximum peak)`); a sustained breach past the configured grace period forces a
stop, with its own cooldown before restarting.
`sensor.smart_charging_status` reports `Fault`/`OK`;
`sensor.smart_charging_active_mode` reports the mode in effect;
`sensor.smart_charging_monthly_peak_kw` reports the tracked rolling monthly
peak (kW); `sensor.smart_charging_effective_peak_limit` reports the peak limit
currently in force (kW).

## Deferred (not in this MVP)

The `Auto` profile; SOC-target/deadline management; notifications; vehicle
charge-limit sync; the runtime dashboard. These are later slices of
[`docs/design/project-plan.md`](docs/design/project-plan.md).

## What it does

The integration charges an EV intelligently rather than at full power on plug-in,
pursuing four goals in priority order (bounded by the last):

1. **Maximise solar self-consumption** — use solar surplus before any grid power.
2. **Keep the monthly capacity-tariff (CapTar) peak under control** — never raise
   the billed peak through avoidable charging spikes.
3. **Charge cost-efficiently from the grid** — prefer low-tariff periods.
4. **Meet the departure deadline** whenever physically possible — escalating
   charging (and cost) only as far as a configurable maximum peak allows.

## Key concepts

A few terms recur throughout the documentation (all defined authoritatively in the
[Ubiquitous Language glossary](docs/analysis/system-overview.md#ubiquitous-language)):

- **Mode vs profile** — a *mode* (`Solar`, `SolarOnly`, `Captar`, `Power`, `Off`)
  is the concrete behaviour the coordinator executes; a *profile* (`Manual`, `Auto`)
  is the higher-level strategy that selects which mode is active over time. The
  coordinator never decides the mode itself — a profile does.
- **Effective peak limit & safety margin** — charging stays a configurable margin
  below `min(monthly peak demand, maximum peak)`; deadline urgency may raise the
  limit up to the configurable maximum peak.
- **Active SOC limit** — the charge target in force, resolved from the configured
  default, an optional solar step-up, and the solar-reserve overnight cap.
- **Configurable & sensor-driven** — values are configurable with sensible defaults,
  and inputs/outputs flow through the integration's own native `smart_charging_`-prefixed
  entities, so any charger, EV, or solar setup can be swapped in.

## Documentation

| Document                                                         | Purpose                                                                                                                       |
|------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| [Methodology](docs/plans/2026-06-24-analysis-approach-design.md) | The analysis-first, spec-driven approach this project follows.                                                                |
| [System overview](docs/analysis/system-overview.md)              | Stakeholders, problem, goals, hardware context, and the authoritative Ubiquitous Language glossary.                           |
| [Requirements](docs/analysis/requirements.md)                    | Functional (R1–R17), non-functional (NF1–NF4), and constraints (C1–C3), with MoSCoW priorities and SMART acceptance criteria. |
| [Flows](docs/analysis/flows/)                                    | Per-behaviour flow documents (control cycle, each mode, SOC management, deadline override, etc.) — *in progress*.             |

Reading order: **system overview → requirements → flows**. Every domain term used
anywhere must be defined in the glossary first.

> A previous iteration is kept under [`docs/archive/`](docs/archive/) for reference
> only — it is **not** a source of truth.
