# Control cycle

The coordinator spine that every use-case plugs into. This is the loop the integration runs
on a timer; each use-case supplies a **mode module** that the loop dispatches to, and each
resolution rule supplies a lookup the loop or a mode consumes. This document is authoritative
for the order of operations in one control cycle and for the invariants that hold regardless of
which mode is active.

Follows the flow-document standard: **Purpose → Trigger → Domain events → Mermaid diagram →
Steps → Edge cases → Requirements satisfied**.

---

## Purpose

Run the [coordinator](system-overview.md#ubiquitous-language) once per [control
interval](system-overview.md#ubiquitous-language): read the sensors, smooth the power readings,
ask the [active mode](system-overview.md#ubiquitous-language) module for a desired charger
current, clamp that current with peak protection, and set it. The coordinator executes the
active mode and never chooses it (NF1); mode choice belongs to the [profile](system-overview.md#ubiquitous-language)
(see `resolution-rules.md`, Auto mode-selection). All inputs and outputs cross an adapter role
(NF3); see `entity-catalog.md` for their bindings.

## Trigger

A timer firing every control interval (configurable via `input_number.sc_control_interval_s`,
default 10 s). The cycle is otherwise stateless between firings except for the rolling
smoothing window and the rapid-cycling timers, which persist across cycles.

## Domain events produced

- `SensorsRead` — past-tense — the cycle has captured a fresh raw reading through every input
  adapter role; signals the start of one cycle's processing.
- `ActiveSocLimitChanged` — the resolved [active SOC limit](system-overview.md#ubiquitous-language)
  (`resolution-rules.md`, Active SOC limit table) differs from the value resolved on the prior
  cycle; the coordinator materializes the resolved value read-only as
  `sensor.smart_charging_active_soc_limit` and emits this event when it changes. Consumed by
  [UC09](use-cases/UC09-sync-charge-limit-with-car.md) as the single trigger to sync the vehicle's
  own charge limit; it subsumes the cause-specific step-up / solar-reserve transitions into one
  consumer contract (ADR-0011).
- `PeakLimitClamped` — the peak-protection step reduced the mode's desired current to keep
  net import at or below the [effective peak limit](system-overview.md#ubiquitous-language)
  minus the [safety margin](system-overview.md#ubiquitous-language); signals that peak
  protection, not the mode, decided the set-point this cycle.
- `SupplyCeilingClamped` — the grid-supply-ceiling step reduced the current to keep net grid
  import below the [grid supply ceiling](system-overview.md#ubiquitous-language) minus the
  [grid safety offset](system-overview.md#ubiquitous-language); signals that the hard
  fuse-protection limit (C4), not the mode or peak protection, decided the set-point.
- `ChargerCurrentSet` — the cycle has written the final charger current through the charger
  current adapter role; signals the end of one cycle and the value applied.

## Diagram

```mermaid
flowchart TD
    Timer(["Control interval timer fires"]) --> Read["Read sensors (raw)<br/>net_w, solar_w, charger_w,<br/>grid voltage, charger status, SOC"]
    Read --> Smooth["Smooth net_w & solar_w<br/>(rolling mean, N cycles — R10)"]
    Smooth --> Volt["Resolve supply voltage<br/>(measured if healthy, else nominal — NF4)"]
    Volt --> SocLimit["Resolve & materialize active SOC limit<br/>(resolution-rules.md; sensor.smart_charging_active_soc_limit;<br/>ActiveSocLimitChanged on change)"]
    SocLimit --> Dispatch["Dispatch to active mode module<br/>(coordinator reads active mode — NF1)"]
    Dispatch --> Desired["Desired charger current<br/>(mode's set-point rule, smoothed inputs)"]
    Desired --> Peak{"Would net import exceed<br/>effective peak limit − safety margin?<br/>(raw readings — R3;<br/>skipped if Power disables it, R17)"}
    Peak -->|yes| Clamp["Clamp to highest whole ampere<br/>that holds the target<br/>(PeakLimitClamped)"]
    Peak -->|no| Ceiling
    Clamp --> Ceiling{"Would net import exceed<br/>grid supply ceiling − safety offset?<br/>(raw readings — C4, always)"}
    Ceiling -->|yes| CeilingClamp["Clamp so net import stays below<br/>ceiling − safety offset<br/>(SupplyCeilingClamped)"]
    Ceiling -->|no| Invariant
    CeilingClamp --> Invariant["Enforce invariants:<br/>0 A or ≥ minimum current (C1);<br/>cooldown gating (R11)"]
    Invariant --> Set["Set charger current<br/>(ChargerCurrentSet)"]
    Set --> Wait(["Wait for next interval"])
```

## Steps

1. **Read sensors (raw).** The coordinator reads each input through its adapter role (NF3):
   net grid import, solar power, charger power, the measured grid voltage, charger status, and
   state of charge. These are [raw values](system-overview.md#ubiquitous-language) — the most
   recent, unsmoothed readings (the measured grid voltage is resolved into the
   [supply voltage](system-overview.md#ubiquitous-language) in step 3). Produces `SensorsRead`.
2. **Smooth the power readings (R10).** The coordinator pushes this cycle's raw `net_w` and
   `solar_w` into a rolling window of the last *N* samples (configurable, default 4) and
   recomputes the [smoothed value](system-overview.md#ubiquitous-language) of each. Smoothed
   values feed charging-rate decisions; the raw values are retained for peak protection. A
   spike lasting a single cycle does not move the smoothed value; a change sustained across the
   full window does, within the following cycle.
3. **Resolve the supply voltage (NF4).** The coordinator selects the [supply
   voltage](system-overview.md#ubiquitous-language) used for all amperes↔watts conversions this
   cycle: the measured grid voltage when a healthy reading is available, otherwise the
   configurable nominal voltage (default 230 V). Using the live value keeps current-derived
   thresholds (e.g. the minimum charging current) correct as grid voltage drifts.
4. **Resolve the active SOC limit, then dispatch to the active mode module (R7, NF1).** First the
   coordinator resolves the [active SOC limit](system-overview.md#ubiquitous-language) in force
   this cycle via `resolution-rules.md`'s Active SOC limit table (solar-reserve cap → solar
   step-up → default), composing that resolution with the active profile and the step-up/reserve
   context it threads across cycles (UC06/UC07); it surfaces the resolved value read-only as
   `sensor.smart_charging_active_soc_limit` and emits `ActiveSocLimitChanged` when it differs from
   the prior cycle's (consumed by [UC09](use-cases/UC09-sync-charge-limit-with-car.md)). That
   resolution is homed in `resolution-rules.md` (R7); this step only fixes *when* in the cycle it
   is resolved, materialized, and change-detected. Then the coordinator determines the resolved
   active mode — the `select.smart_charging_mode` selection under `Manual`, or `Auto`'s selection
   (`resolution-rules.md`, whose row 1 compares against this resolved active SOC limit) under
   `Auto` — calls the matching module, passing the smoothed readings and the resolved voltage, and
   surfaces the resolved value read-only as `sensor.smart_charging_active_mode`. The module returns
   a **desired charger current** using its own set-point rule (defined in the mode use-case —
   UC01–UC04; e.g. the `Off` module returns 0 A). The coordinator contains no logic that chooses
   or changes the mode — this includes deadline urgency (R5): under `Auto`, escalating to `Captar`
   is Auto mode-selection's own decision (`resolution-rules.md`), made before this step reads the
   active mode; under `Manual` the active mode never changes, and this step never adjusts what a
   mode requests either (NF2) — see step 5.
5. **Apply the peak-protection clamp (R3).** Using the **raw** readings (not the smoothed
   ones, to avoid lag), the coordinator checks whether the desired current would push net
   import above the effective peak limit minus the safety margin. If so, it reduces the current
   to the highest whole ampere that keeps net import at or below that target, within the same
   cycle, and emits `PeakLimitClamped`. The effective peak limit itself is resolved by
   `resolution-rules.md` (it rises to the maximum peak only under deadline urgency, R5/C3) —
   this is the *only* lever deadline urgency has under `Manual`: raising the ceiling lets a
   mode whose own request was previously clamped (e.g. `Captar`, `Power`) draw more, up to
   whatever it already requests; it never raises what a mode requests in the first place. This
   clamp is active in every mode except when `Power` mode has its peak-protection option
   disabled (R17); the grid supply ceiling clamp in step 6 still applies in that case.
6. **Apply the grid supply ceiling clamp (C4).** Regardless of mode — and even when the step 5
   peak clamp was skipped — the coordinator reduces the current, using **raw** readings (not
   smoothed, to avoid lag), so that net grid import stays below the
   [grid supply ceiling](system-overview.md#ubiquitous-language) minus the
   [grid safety offset](system-overview.md#ubiquitous-language) (converted to amperes via the
   resolved supply voltage). This is the hard fuse-protection limit and the one clamp `Power`
   mode cannot switch off; it emits `SupplyCeilingClamped` when it engages.
7. **Enforce the invariants.** The final current obeys C1 — it is either 0 A or at least the
   [minimum charging current](system-overview.md#ubiquitous-language), never in between — and
   the rapid-cycling invariant (R11): once charging has stopped it does not restart until the
   mode-specific cooldown has fully elapsed, and a cooldown in progress always runs to
   completion. (Start/stop and cooldown durations are mode-specific and defined in each mode
   use-case; the coordinator only upholds the invariant.)
8. **Set the charger current.** The coordinator writes the final current to the charger
   through its adapter role (NF3) and emits `ChargerCurrentSet`, then waits for the next
   interval.

## Edge cases

- **No healthy supply-voltage reading.** Conversions fall back to the configurable nominal
  voltage (default 230 V) for the cycle (NF4); the cycle still completes.
- **Peak breach persists.** A momentary breach only triggers a clamp, not a stop. The charger
  drops to 0 A only when it is already at the minimum charging current *and* net import has
  exceeded the target continuously for a configurable grace period (default 2 minutes, R3); the
  rapid-cycling cooldown then governs any restart (R11).
- **Mode switched mid-operation.** Switching the active mode resets all hold and cooldown
  timers so the incoming mode starts fresh (R11); the next cycle dispatches to the new module.
- **Smoothing window not yet full.** At start-up or after a restart the rolling mean is taken
  over the samples available so far until the window fills.
- **Mode requests a current below the minimum.** The invariant in step 7 resolves it to 0 A or
  the minimum per the mode's own rule (C1); the coordinator never emits an in-between value.
- **Grid supply ceiling reached.** The charger is clamped down — to 0 A if necessary — so net
  grid import stays below the grid supply ceiling minus the grid safety offset and the main fuse
  cannot trip (C4). This applies even in `Power` mode with peak protection disabled, where it is
  the only active clamp.

## Requirements satisfied

- **R3** — CapTar peak protection (the clamp in step 5, on raw readings).
- **R10** — Sensor smoothing (the rolling mean in step 2; peak protection exempt, step 5).
- **R11** — Rapid-cycling prevention (the cooldown/min-current invariant in step 7).
- **NF4** — Voltage-aware power conversion (voltage resolution in step 3).

Upholds but does not home: **NF1** (coordinator executes, never chooses the mode — homed in
`requirements.md`; mode choice, including deadline urgency's `Auto` escalation, in
`resolution-rules.md`), **NF2** (the coordinator never adjusts what a mode requests; deadline
urgency's `Manual` lever only widens the peak clamp in step 5 — homed in `requirements.md`), and
**NF3** (all I/O via adapter roles — bindings in `entity-catalog.md`). **C1**, **C3**, and **C4**
(grid supply ceiling clamp, step 6) are enforced as invariants in steps 5–7. **R7** (active SOC
limit) is homed in `resolution-rules.md` (the resolution table) and applied by
[UC09](use-cases/UC09-sync-charge-limit-with-car.md); this document only fixes *when* in the cycle
the resolved value is materialized (`sensor.smart_charging_active_soc_limit`, step 4) and
change-detected to emit `ActiveSocLimitChanged`. **R5** (departure deadline guarantee) is homed in
`resolution-rules.md` and [UC05](use-cases/UC05-guarantee-ready-by-departure.md); this document
supplies the peak clamp (step 5) that realizes its `Manual` lever, unchanged from normal operation.
