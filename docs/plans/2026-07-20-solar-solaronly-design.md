# Solar & SolarOnly charging modes — design

**Date:** 2026-07-20
**Status:** draft (issue #191, epic #189)
**Type:** implementation design (a slice of the approved architecture — not a new decision)

This document defines the next implementation slice after the Power-mode MVP
(`2026-07-18-power-mvp-design.md`): the **`Solar`** and **`SolarOnly`** charging modes, selectable
under the `Manual` profile, running end-to-end against a real grid connection.

It is a deliberate **subset** of the full architecture, built the same way the Power MVP was: every
component below is a slice of a service already named in
[`../design/system-design.md`](../design/system-design.md) and sequenced in
[`../design/project-plan.md`](../design/project-plan.md). Nothing here introduces a new service, call
direction, or structural decision, so no new ADR is required.

Behavior is owned by
[UC01](../analysis/use-cases/UC01-charge-from-solar-surplus.md) (`Solar`, R1) and
[UC02](../analysis/use-cases/UC02-charge-from-solar-only.md) (`SolarOnly`, R2); this document cites
their formulas/thresholds as test anchors and does not restate them as if it owns them. (CLAUDE.md's
doc-structure section still names the retired `docs/analysis/flows/01-solar-flow.md` /
`02-solar-only-flow.md` — see `docs/analysis/flows/README.md` for the supersession; fixing CLAUDE.md
itself is a separate, non-blocking cleanup.)

---

## 1. Why this slice is wider than "just the two mode engines"

`project-plan.md` files both modes under task **E1**, which on its own is "one self-contained module
per mode." But UC01/UC02's preconditions and set-point rules reach into three things the Power MVP
explicitly deferred:

| UC01/UC02 need | Power MVP status | This slice |
| --- | --- | --- |
| *Smoothed* net import (R10) — the trigger and set-point both key on smoothed surplus, not raw | `engines/signal_conditioning.py` (E7) does voltage (NF4) only; its own docstring defers R10 | **In scope** — add net-import smoothing to E7 |
| An active SOC limit to stop at (R7) | Doesn't exist; Power MVP charges regardless of SOC (documented v1 deviation) | **In scope** — add E3, scoped to what R7 actually reduces to under `Manual` (see §5) |
| A way to pick `Solar`/`SolarOnly` as the active mode | No selector; coordinator hardcodes `Power` | **In scope** — add a minimal `select.smart_charging_mode` |

Picking these up now (rather than re-deferring them again) is what makes this slice a **working**
mode instead of another set of pure functions nothing calls. §6 lists what is still explicitly
deferred — Auto/profiles, deadline, peak/billing beyond the existing grid ceiling, notifications,
vehicle-limit sync, capability gating — none of which UC01/UC02 need to run correctly under `Manual`.

---

## 2. Success criteria (what "works" means)

1. A `select.smart_charging_mode` entity appears with options `Off`, `Power`, `Solar`, `SolarOnly`
   (restore-state; `Off` if never set) and is adjustable from the HA UI.
2. A `number.smart_charging_soc_limit_override` entity appears (restore-state, 50–100%, default 80%,
   per R6) and is adjustable anytime.
3. With `Solar` active, a car connected, and SOC below the override: charging starts within one
   control cycle of smoothed surplus reaching the configurable start threshold (default 150 W),
   rounds **up** to the next whole ampere each cycle (fixed strategy), falls back to the minimum
   current on shortfall (grid fallback), rides out a dip below threshold for the configurable hold
   period (default 5 min) before stopping, and stops immediately and permanently at the SOC override
   until unplug/replug or the override changes (R7).
4. With `SolarOnly` active: same start/stop shape, but the amp-step strategy is configurable (default
   `round down`, net import ≤ 0 W), there is **no** grid fallback and **no** hold — surplus below the
   (higher, default 1300 W) threshold stops charging immediately.
5. Switching the mode selector resets the incoming mode's hold/cooldown state (R11); the C4 grid
   ceiling clamp (already shipped) still bounds the output every cycle, unconditionally.
6. `Power` mode's own behavior (Power MVP) is unchanged — including its existing v1 deviation of
   charging regardless of SOC (`2026-07-18-power-mvp-design.md` §6). The SOC gate added by this
   slice (§6 below) applies **only** to `Solar`/`SolarOnly`; `ev_soc` is read every cycle but is a
   required (fault-on-`None`) role only while one of those two modes is active.

---

## 3. Install-time / options additions

Extends the Power MVP's config/options flow (ADR-0005 split retained: role mappings in **data**,
thresholds/defaults in **options**).

| Field | Bucket | Role/Notes |
| --- | --- | --- |
| **EV state-of-charge entity** (r) | data — new adapter role `ev_soc`, **optional** at the factory level (mirrors `grid_voltage`'s pattern) | RA1 extension. Not configuring it leaves `ev_soc` absent from the built adapter set — harmless for `Off`/`Power` (unchanged), but selecting `Solar`/`SolarOnly` without it is a fault every cycle (missing role for a mode that needs it), surfaced via the existing status sensor. This also means an **existing Power-MVP config entry loads unchanged** without a migration (§9 note) — it simply has no `ev_soc` role until reconfigured. |
| **Smoothing window size** *N* | options | Default **4** samples (R10). Reused by any future smoothed input; this slice is its first consumer. |
| **Solar start threshold** | options | `Solar`'s start/resume threshold, default **150 W** (R1). |
| **SolarOnly start threshold** | options | `SolarOnly`'s start/resume threshold, default **1300 W** (R2). |
| **Post-surplus hold** | options | `Solar`-only ride-out period, default **5 min** (R1). |
| **Solar-mode cooldown** | options | Shared by `Solar`/`SolarOnly` after a stop, default **2 min** (R11). |
| **SolarOnly amp-step strategy** | options | `round_down` (default) / `round_up` / `round_nearest` (R2). `Solar`'s strategy is fixed `round_up`, not configurable (R1) — no field. |
| **SolarOnly rounding midpoint** | options | Only meaningful for `round_nearest`, default **50%** (R2). |
| **Default SOC limit** | seeds the owned entity | Initial value of `number.smart_charging_soc_limit_override`, default **80%**, range 50–100% (R6). |

No new **data**-bucket capability flag: R18 (capability gating) is deferred (§6) — `Solar`/`SolarOnly`
are unconditionally offered in the selector this slice.

---

## 4. Runtime surface (owned entities)

- **`select.smart_charging_mode`** — new (C2). Options `Off`, `Power`, `Solar`, `SolarOnly`
  (capability-gated option list is deferred — see §6; the list is static this slice). Restore-state.
  Replaces the coordinator's hardcoded Power dispatch.
- **`number.smart_charging_soc_limit_override`** — new (C2), mirrors the existing
  `number.smart_charging_target_current` pattern (restore-state, bounds 50–100, default from options).
- **`sensor.smart_charging_active_mode`** — new, read-only (C3-shaped; `control-cycle.md` step 4
  requires materializing it). Mirrors the existing `sensor.smart_charging_status` pattern.
- Existing `number.smart_charging_target_current` and `sensor.smart_charging_status` are unchanged.
- **Not built this slice:** `sensor.smart_charging_active_soc_limit` and the `ActiveSocLimitChanged`
  event (control-cycle.md step 4 also specifies these). Deferred because their only consumer,
  UC09 (vehicle-limit sync via M2/ADR-0011), is out of scope — materializing a sensor and an event
  with zero readers this slice would be speculative (YAGNI). The SOC-limit *value* is still fully
  functional internally (§5); only its own diagnostic sensor/event are deferred.

---

## 5. Active SOC limit for this slice (E3, scoped)

Full R7 has three priority rows: solar-reserve cap → solar step-up → default. Rows 1–2 are **not a
deferral of this slice's own correctness** — they are structurally inert without what this slice
doesn't build:

- Row 1 (solar-reserve cap) only ever applies "while the `Auto` profile is active" (R9); `Auto`/E2
  don't exist yet, so row 1 can never match, exactly as R7 itself states for `Manual` ("row 1 never
  matches ... the user's own mode choice is not second-guessed").
- Row 2 (solar step-up, R8) requires UC06's step-up mechanism, a separate `Should`-priority use case
  not in this epic.

So for the system as it exists after this slice (`Manual`-only, no step-up mechanism), **row 3 is the
entire resolution** — `resolve_active_soc_limit()` is a true, complete implementation of R7 for the
current system state, not a stub. Its only input is
`number.smart_charging_soc_limit_override`'s current value; there is no ADR-0010 gate concern (E3 was
never blocked by it in the first place — E1/E2 already had ADR-0002 homes — and per `project-plan.md`'s
corrected gate table, ADR-0010 is Accepted regardless). Rows 1–2 are added when UC06/UC07/E2 are
built, as a change to this one function, not a new service.

**Where the SOC gate itself lives.** R7's own framing — "whichever mode is active simply charges to
this resolved value ... it has no opinion on *why* the limit is where it is" — means the gate belongs
in the coordinator (M1), not inside `Solar`'s/`SolarOnly`'s own state machine. §6 reflects this: the
mode engines carry no SOC-related phase at all; M1 compares `ev_soc` against the resolved limit each
cycle and only calls a mode's `step()` when charging is actually permitted, forcing that mode's state
back to `idle()` for as long as the limit holds — which is also how both of R7's resume conditions
(the limit changing, or unplug/replug) end up satisfied for free: the very next cycle where the gate
no longer holds re-enters `step()` from `idle()`, re-checking the start threshold fresh.

---

## 6. Control cycle

Extends the Power MVP's cycle (`coordinator.py`, M1). New/changed steps in **bold**:

```text
read charger_status (raw) → translate to canonical
read net_power, charger_power, grid_voltage
**read ev_soc — only if active_mode ∈ {Solar, SolarOnly}; a None reading there is the ADR-0007
  fault signal for THIS cycle only (Off/Power never read it, so its absence never faults them)**
**smooth net_power over the last N raw samples (R10) → smoothed_net_w**
resolve voltage (grid_voltage None → nominal, NF4)
**resolve active SOC limit ← number.smart_charging_soc_limit_override (E3, §5)**
**surplus_w = charger_power (raw) − smoothed_net_w**   # per UC01/UC02: charger_w stays raw, only net_w is smoothed
**read active mode ← select.smart_charging_mode**

if canonical ∉ {connected, charging}:
    desired = 0
    **reset every mode's threaded state to idle() — disconnect ends any hold/cooldown (R7/R11)**
elif active_mode == Off:
    desired = 0                                                          # unchanged
elif active_mode == Power:
    desired = target_current                                            # unchanged (E1, Power MVP)
elif active_mode in (Solar, SolarOnly):
    **if ev_soc is None: desired = 0   # fault (this cycle's required-role check, above)**
    **elif ev_soc >= active_soc_limit:**
        **desired = 0**
        **state[active_mode] = idle()   # R7: don't resume until the gate clears -- see below**
    **else:**
        **desired, state[active_mode] = (solar if Solar else solar_only).step(surplus_w, state[active_mode], now)**  # E1, new — UC01/UC02

baseline_w = net_w (raw) − charger_w (raw)                              # unchanged
headroom_a = floor((ceiling − offset) − baseline_w / voltage)           # grid-safety, E6 — unchanged
desired = min(desired, headroom_a)
desired = clamp(desired, min, max)                                      # floor/cap invariant — E8, unchanged

write charger_current ← desired
materialize sensor.smart_charging_active_mode ← active_mode
```

**How this satisfies both of R7's resume conditions.** Forcing `state[active_mode] = idle()` every
cycle the SOC gate holds means the *next* cycle where it no longer holds — because the limit rose
(`number.smart_charging_soc_limit_override` changed) or because a disconnect/reconnect already reset
everything to `idle()` — re-enters `step()` fresh from `idle()`, re-checking the start threshold as
normal. Neither the mode engines nor a separate "SocReached" phase need to know why charging resumed;
the coordinator's own re-evaluation each cycle (`control-cycle.md`'s "every rule is re-evaluated every
control cycle" convention) is what R7 actually asks for. `Solar`/`SolarOnly`'s state machines
therefore have **no SOC-related phase at all** — only `idle`/`charging`/`hold` (`Solar`
only)/`cooldown`.

- **Smoothing (R10) applies only to `net_power`** this slice. `solar_power` is not read at all: the
  surplus formula is `charger_w − net_w` (both use-cases, and the entity-catalog note that
  `solar_power` "is not an operand of solar surplus"), so no `solar_power` adapter role is needed for
  `Solar`/`SolarOnly` to work correctly. `charger_power` stays **raw** in the surplus formula, per
  UC01/UC02's own wording ("*smoothed* solar surplus rides on the smoothed net import"). Smoothing
  `solar_power` itself is deferred to whichever later slice first consumes it (Auto's forecast/UC07).
- **Mode state is owned by the mode module, not by E7/E8.** `Solar`/`SolarOnly` each carry their own
  Idle/Charging/Hold(`Solar` only)/Cooldown/SocReached state machine (UC01/UC02 "State model"
  sections) as a small dataclass threaded by M1, the same pattern E7's smoothing window and E8's
  (future) cooldown timers use — state is a parameter, never HA-held (system-design §3). `E8` itself
  is **unchanged** from the Power MVP (floor/cap only); the mode-specific hold/cooldown durations and
  transitions live in `modes/solar.py` / `modes/solar_only.py`, not in a generic engine, because they
  differ per mode (`Solar` has a hold state `SolarOnly` doesn't; cooldown length will eventually differ
  again for `Captar`, R11).
- **Mode switch resets state (R11).** When `select.smart_charging_mode` changes, the coordinator
  discards the previous mode's state object and starts the newly active mode fresh — this is the one
  cross-mode R11 rule that isn't inside a mode module, because it's about the *transition itself*.
- **Grid ceiling (E6) and floor/cap (E8) are unchanged** and still apply unconditionally to whatever
  `Solar`/`SolarOnly` request, exactly as they do for `Power` — no safety behavior is weakened by this
  slice.
- **Amp-step rounding is a shared pure helper** (`modes/_amp_step.py`), not a new Engine: `Solar` calls
  it fixed to `round_up`; `SolarOnly` calls it with the configured strategy. Sharing the arithmetic
  doesn't couple the two modes' state machines (NF2 — each mode module is still independently
  testable and swappable).

---

## 7. Mapping to the full architecture

| Component | Full-design service | Test boundary (ADR-0009) |
| --- | --- | --- |
| `ev_soc` adapter role | Adapters — **RA1** (extension) | HA harness |
| net-import smoothing (R10) | Signal-Conditioning — **E7** (extension; voltage slice already shipped) | plain pytest |
| resolve active SOC limit (§5) | SOC-Target — **E3** (new, scoped to row 3) | plain pytest |
| `Solar` mode state machine (UC01) | Charging-Mode Engines — **E1** | plain pytest |
| `SolarOnly` mode state machine (UC02) | Charging-Mode Engines — **E1** | plain pytest |
| shared amp-step rounding helper | (utility inside E1's `modes/` home, not a separate service) | plain pytest |
| mode-switch state reset, active-mode dispatch, SOC gate | Coordinator — **M1** (extension) | HA harness |
| `select.smart_charging_mode`, `number.smart_charging_soc_limit_override` | Owned entities — **C2** (extension) | HA harness |
| `sensor.smart_charging_active_mode` | Owned entity — **C3**-shaped (see §4) | HA harness |
| `ev_soc` mapping, new options fields | **C4** (extension) | HA harness |

Grid-safety (E6, unchanged) and floor/cap (E8, unchanged) are reused as-is from the Power MVP — not
re-listed as new work.

---

## 8. Deliberately deferred

Out of scope for this slice, each a later slice of `project-plan.md` — none is a safety deferral
(the grid ceiling clamp is untouched and unconditional):

- **`Auto` profile (E2)** and everything that depends on it: the solar-reserve cap (R9), Auto
  mode-selection (R16), deadline escalation to `Captar` under `Auto`.
- **Solar step-up (R8, UC06)** — R7 rows 1–2 in general (§5 explains why row-3-only is not a hack
  given what else is/isn't built).
- **Deadline Engine (E4), R5** and the `Manual`-lever peak-limit raise — UC05.
- **Capability gating (E9, R18)** — the mode selector's option list is static; a solar-less
  installation still sees `Solar`/`SolarOnly` offered. Acceptable because R18 is `Should`, not `Must`,
  and the default installation has solar.
- **`Captar` mode and the peak/billing Engine (E5)** — its own epic, #190.
- **`sensor.smart_charging_active_soc_limit` and `ActiveSocLimitChanged`** (§4) — no consumer exists
  yet (UC09/M2 out of scope).
- **Vehicle-limit sync (M2, UC09), notifications (M3, UC08/UC10)**, the runtime dashboard (C5, UC11).
- **`solar_power` adapter role and its smoothing** — not consumed by anything built this slice (§6).
- **A formal config-entry migration (`async_migrate_entry`/`VERSION` bump).** Not needed: `ev_soc` is
  an **optional** adapter role (§3) exactly like `grid_voltage` already is, so an existing Power-MVP
  entry loads unchanged with `ev_soc` simply absent (Off/Power are unaffected; selecting `Solar`/
  `SolarOnly` without it faults every cycle until reconfigured). The eight new **options** keys are
  read with their `DEFAULT_*` fallback (`options.get(KEY, DEFAULT_...)`), the same pattern already
  used for every existing option — an old entry that predates these keys simply gets the defaults.

---

## 9. Testing

- **Plain pytest** (no HA) for the pure pieces: `Solar`'s and `SolarOnly`'s state-machine `step()`
  functions — a per-call determinism check (identical inputs → identical output) at this layer; the
  shared amp-step helper (all three strategies incl. the `round_nearest` "pendel" case); the
  net-import smoothing window (window-not-yet-full at startup; how a single-cycle spike moves the
  mean by `1/N` rather than tracking it fully — R10 dampens, it does not reject, a single-cycle spike);
  and `resolve_active_soc_limit`'s row-3 lookup.
- **HA harness** for the HA-coupled pieces: the `ev_soc` adapter's edge cases (missing/unavailable,
  and its absence being harmless for `Off`/`Power` but a fault for `Solar`/`SolarOnly`); an existing
  Power-MVP config entry loading unchanged with no `ev_soc` role configured; `select.smart_charging_mode`
  and `number.smart_charging_soc_limit_override` restore-state and bounds; the coordinator dispatching
  to each mode, gating on SOC (including both R7 resume paths — the limit rising, and unplug/replug —
  each re-entering `step()` from `idle()`), resetting state on a mode switch, and
  `sensor.smart_charging_active_mode` reflecting the resolved mode; **the genuine closed-loop
  no-oscillation regression** control-cycle.md/E1 calls for — a mode must hold steady, not oscillate,
  when its own charging draw is itself part of the `net_w` the surplus formula reads back — driven
  through a feedback model (commanded current → `charger_w` → `net_w` → next cycle's `surplus_w`),
  not just a repeated constant input; a full-cycle regression per UC01/UC02 (start /
  grid-fallback-or-immediate-stop / hold-where-applicable / cooldown / SOC-gated-stop-and-resume)
  against a mocked hardware state; the existing grid-ceiling and floor/cap tests continuing to pass
  unchanged.

---

## 10. Packaging

```text
custom_components/smart_charging/
  const.py              # + ev_soc CONF key, new options keys
  coordinator.py         # M1 — mode dispatch, SOC gate, state reset, smoothing wiring
  select.py              # C2 — select.smart_charging_mode (new platform file)
  number.py              # C2 — + soc_limit_override entity
  sensor.py               # C2/C3 — + active_mode sensor
  config_flow.py          # C4 — + ev_soc mapping, new options fields
  adapters/               # RA1 — + ev_soc role (no new file; factory extension)
  engines/
    signal_conditioning.py # E7 — + net_w smoothing (extends existing module)
    soc_target.py           # E3 — new module (row-3-only resolution)
  modes/
    solar.py               # E1 — new
    solar_only.py           # E1 — new
    _amp_step.py            # shared pure helper (not a mode; no public Engine of its own)
```

`tests/` mirrors 1:1 per ADR-0002/0009 (`tests/engines/test_soc_target.py`,
`tests/modes/test_solar.py`, `tests/modes/test_solar_only.py`, `tests/modes/test_amp_step.py`, plus
HA-harness additions to the existing `test_coordinator.py`, `test_config_flow.py`, and new
`test_select.py`).

---

## 11. Next step

This design feeds the `writing-plans` skill to produce the ordered, test-driven implementation plan
(`2026-07-20-solar-solaronly.md`). Build order follows `project-plan.md`'s layering: RA1 extension →
E7 extension + E3 (independent, pure) → E1 `Solar`/`SolarOnly` (pure, depend on E7/E3 only as data
shapes) → M1 extension (composes them) → C2/C4 extensions. No `custom_components/` code is written
until the paired plan exists and is approved.
