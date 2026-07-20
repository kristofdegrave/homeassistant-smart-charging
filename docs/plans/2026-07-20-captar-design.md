# Captar charging mode — design

**Date:** 2026-07-20
**Status:** draft (issue #193, epic #190)
**Type:** implementation design (a slice of the approved architecture — not a new decision)

This document defines the **`Captar`** charging mode, selectable under the `Manual` profile,
running end-to-end against a real grid connection — the CapTar (capacity-tariff / peak-demand-aware)
grid-charging slice.

It is a deliberate **subset** of the full architecture, built the same way the Power MVP was: every
component below is a slice of a service already named in
[`../design/system-design.md`](../design/system-design.md) and sequenced in
[`../design/project-plan.md`](../design/project-plan.md). Nothing here introduces a new service, call
direction, or structural decision, so no new ADR is required.

Behavior is owned by
[UC03](../analysis/use-cases/UC03-charge-from-grid-within-captar-limit.md) (`Captar`, R4);
this document cites its formulas/thresholds, `control-cycle.md`'s R3/C4 clamp steps, and
`resolution-rules.md`'s effective-peak-limit rule as test anchors and does not restate them as if it
owns them. (CLAUDE.md's doc-structure section still names the retired
`docs/analysis/flows/03-captar-flow.md` — see `docs/analysis/flows/README.md` for the supersession;
fixing CLAUDE.md itself is a separate, non-blocking cleanup.)

---

## 0. Relationship to the Solar/SolarOnly slice (#189)

`project-plan.md` files `Captar`'s mode engine under the same task (**E1**) as `Solar`/`SolarOnly`,
and both slices need the same three pieces of coordinator scaffolding that don't exist in the shipped
Power MVP yet:

| Shared piece | Owned by (system-design service) |
| --- | --- |
| `select.smart_charging_mode` (the option list and restore-state entity) | C2 |
| `resolve_active_soc_limit` (SOC-Target Engine, row-3-only scope) | E3 |
| The coordinator's mode-dispatch/state-reset scaffolding (the `elif active_mode == ...` chain, per-mode state dict, mode-switch reset) | M1 |
| `ev_soc` adapter role (optional at the factory level) | RA1 |

As of this writing **neither slice has shipped code** — only Solar/SolarOnly has a written spec
(`2026-07-20-solar-solaronly-design.md` / `-solar-solaronly.md`), not yet implemented, and **not yet
merged to `main`** — it lives on the unmerged `feature/solar-solaronly` branch (issue #191). This
document is authored from `main`, so those files are not present in this branch's working tree; the
signatures cited below (`resolve_active_soc_limit`, `ModeSelect`/`MODE_OPTIONS`) were confirmed against
`feature/solar-solaronly`'s actual doc content at authoring time, not assumed. **If that branch's spec
changes before either epic is implemented, the two specs' shared signatures must be re-diffed** — this
document does not itself keep them in sync. Per the project's direction: **this design stays
independent of Solar/SolarOnly** (it does not assume that spec's tasks ran first, and does not block on
issue #191/#192) **but must not duplicate the shared pieces** — whichever epic's implementation
actually lands first creates them; the second reuses and extends what already exists rather than
re-authoring it.

Concretely, every task below that touches a shared piece is written as **"extend if it exists, create
if it doesn't"**:

- **`select.smart_charging_mode`** — if `select.py` already exists (Solar/SolarOnly landed first), add
  `"Captar"` to its existing `MODE_OPTIONS` list. If not, this slice creates the entity with
  `MODE_OPTIONS = ["Off", "Power", "Captar"]`, and Solar/SolarOnly's implementer extends the list
  later.
- **`resolve_active_soc_limit` (E3)** — if `engines/soc_target.py` already exists, this slice imports
  it unchanged (`Captar`'s SOC gate needs the identical row-3-only resolution UC03 §"State model"
  requires — no `Captar`-specific variant). If not, this slice creates it exactly as
  `2026-07-20-solar-solaronly-design.md` §5 specifies (same function signature, same row-3-only
  scope, same reasoning: rows 1–2 require `Auto`/UC06, neither of which exists yet regardless of
  which slice lands first) — Solar/SolarOnly's implementer then imports this slice's module instead
  of writing its own.
- **Coordinator dispatch/reset scaffolding (M1)** — if the `elif active_mode == "Solar" / "SolarOnly"`
  branches and the per-mode state dict / mode-switch reset already exist, this slice adds one more
  `elif active_mode == "Captar"` branch and one more entry to the state dict, following the existing
  pattern. If not, this slice adds the *general* dispatch/reset scaffolding itself (a dict keyed by
  mode name, cleared on mode switch and on disconnect) sized for just `Captar` today; Solar/SolarOnly's
  implementer then adds their branches and state-dict entries to the general scaffolding this slice
  built, instead of writing a parallel one.
- **`ev_soc` adapter role (RA1)** — same "optional at the factory level" extension either slice would
  add; whichever lands first adds the constant/factory wiring, the other reuses it unchanged.

**Whichever epic's implementation task is picked up first must post a comment on the other epic's
mode-engine implementation task** (issue #194 for Captar, #192 for Solar/SolarOnly) noting which
shared pieces now exist and pointing at the file(s) to extend, so the second implementer starts from
"extend X" rather than re-deriving it independently. This design records the obligation; it is
carried out at whichever implementation actually starts first (see §11).

Everything else in this document — the `Captar` mode engine itself (state machine), the
Billing-Protection Engine + Peak-Demand Tracker (E5), and the R17 `Power`-mode interaction — is
**this epic's own, non-shared work**; #189 has no equivalent.

---

## 1. Why this slice is wider than "just the mode engine"

| UC03 needs | Power MVP status | This slice |
| --- | --- | --- |
| A way to select `Captar` as the active mode | No selector; coordinator hardcodes `Power` | **In scope** — extend/create `select.smart_charging_mode` (§0) |
| An active SOC limit to stop at (R7) | Doesn't exist | **In scope** — extend/create E3, scoped as `2026-07-20-solar-solaronly-design.md` §5 describes (§0) |
| The R3 peak-protection clamp + effective peak limit (its own epic's core deliverable) | Doesn't exist — Power MVP has only the C4 grid-ceiling clamp (E6, shipped) | **In scope** — new Billing-Protection Engine (E5) |
| The monthly peak-demand tracker (`sensor.smart_charging_monthly_peak_kw`) | Doesn't exist | **In scope** — new Peak-Demand Tracker, bundled into E5 per `system-design.md` §3 |
| `Power`'s R17 peak-protection opt-out | Doesn't exist (Power MVP never had a peak clamp to opt out of) | **In scope** — E5's clamp becomes active for `Power` too, gated by the existing `sc_power_respect_peak` catalog entry (default on) — an intentional, R17-mandated behavior change to already-shipped `Power` mode, not a regression (§6) |

§9 lists what is still explicitly deferred — `Auto`/profiles, the Deadline Engine and deadline-urgency
peak-limit raise (R5/UC05), capability gating, notifications, vehicle-limit sync — none of which UC03
needs to run correctly under `Manual`.

---

## 2. Success criteria (what "works" means)

1. `select.smart_charging_mode` offers `Captar` (alongside whatever options already exist per §0) and
   is adjustable from the HA UI.
2. With `Captar` active, the car connected, and SOC below the active SOC limit, and no `Captar`
   cooldown in effect: charging starts within one control cycle, requesting the maximum charging
   current (C1) — not a surplus-derived amount.
3. The R3 peak-protection clamp (Billing-Protection Engine, E5) fits that request, on **raw**
   readings, to the peak headroom: the highest whole ampere that keeps net import at or below the
   effective peak limit minus the safety margin. A momentary breach only reduces the current; only a
   **sustained** breach at the minimum charging current (default grace period 2 minutes,
   `sc_peak_grace_min`) stops charging (0 A) and starts the `Captar` cooldown (default 10 minutes,
   `sc_captar_cooldown_min`).
4. `sensor.smart_charging_monthly_peak_kw` accumulates the highest 15-minute average net import seen
   so far this calendar month, resets at the start of each month, and survives an HA restart.
5. `sensor.smart_charging_effective_peak_limit` reflects `min(monthly_peak_demand, maximum_peak)`
   (the deadline-urgency raise, R5, is out of scope — §9 — so this slice's resolution is always row 2).
6. The C4 grid-ceiling clamp (E6, unchanged, shipped) still bounds the output every cycle,
   unconditionally, after E5's clamp.
7. `Power` mode's existing behavior changes exactly as R17 specifies: by default
   (`sc_power_respect_peak` on) it is now also bounded by the R3 peak clamp; setting that option off
   restores its pre-this-slice behavior (bounded only by C4). This is a deliberate, catalogued
   interaction (§6), not an unintended regression of the Power MVP.
8. Switching the mode selector away from `Captar` and back resets `Captar`'s cooldown state (R11).

---

## 3. Install-time / options additions

Extends the Power MVP's config/options flow (ADR-0005 split retained). Most of the *values* below are
**already catalogued** in `entity-catalog.md`'s "Peak protection" and "`Power` mode" groups (added when
UC03 was drafted) but **not yet wired into `const.py`/`config_flow.py`**, which only has the Power MVP's
fields today — that wiring is this slice's job, not new catalog entries.

| Field | Bucket | Role/Notes |
| --- | --- | --- |
| **Safety margin** (`sc_safety_margin_w`) | options | Default **250 W** (R3, glossary). |
| **Maximum peak** (`sc_max_peak_kw`) | options | Default **4 kW** (glossary "maximum peak"; upper operand of the effective peak limit). |
| **Peak-breach grace period** (`sc_peak_grace_min`) | options | Default **2 min** (R3). |
| **`Captar` cooldown** (`sc_captar_cooldown_min`) | options | Default **10 min** (R11). |
| **`Power` respects peak protection** (`sc_power_respect_peak`) | options | Default **on** (R17). Already catalogued but unused until this slice's E5 exists — wired here. |
| **`ev_soc` entity** (data, optional) | — see §0 — only added here if Solar/SolarOnly's implementation didn't already add it. |

No new **data**-bucket capability flag: R18 (capability gating) is deferred (§9) — `Captar` is
unconditionally offered in the selector (it always is, regardless of capabilities, per
`entity-catalog.md`'s note: "`Captar`, `Power`, and `Off` are always offered").

---

## 4. Runtime surface (owned entities)

- **`select.smart_charging_mode`** — extend/create per §0; adds the `"Captar"` option.
- **`sensor.smart_charging_monthly_peak_kw`** — new (C3-shaped: system-written, not user-set).
  Read-only, kW, the Peak-Demand Tracker's running value; must restore across a restart (§7).
- **`sensor.smart_charging_effective_peak_limit`** — new (C3-shaped), read-only, kW, `resolve_effective_peak_limit`'s
  output (row-2-only this slice — §9).
- **Not built this slice:** `sensor.smart_charging_active_soc_limit`, `sensor.smart_charging_active_mode`,
  `sensor.smart_charging_desired_current`, and `ActiveSocLimitChanged` — same deferral rationale as
  `2026-07-20-solar-solaronly-design.md` §4 (no consumer exists yet; whichever of the two mode slices
  lands first is free to add `sensor.smart_charging_active_mode` since both need it — another shared
  piece per §0's convention, added here as a candidate if Solar/SolarOnly hasn't already).
- Existing `number.smart_charging_target_current` and `sensor.smart_charging_status` are unchanged.

---

## 5. Active SOC limit and mode selection for this slice

Identical reasoning and scope to `2026-07-20-solar-solaronly-design.md` §5: full R7 has three priority
rows, of which only row 3 (the configured `number.smart_charging_soc_limit_override`) can ever match
without `Auto`/UC06 — this is the complete, correct R7 resolution for the system as it exists, not a
stub. Per §0, this slice reuses the identical `resolve_active_soc_limit` function Solar/SolarOnly's
design specifies rather than defining a `Captar`-specific variant; UC03's own "State model" section
confirms `Captar`'s SOC gate is the same resolved value every other mode reads ("the resolution is the
same to `Captar`").

**Where the SOC gate lives.** Same placement as Solar/SolarOnly (§5 of that design): the coordinator
(M1) compares `ev_soc` against the resolved active SOC limit and only calls `captar.step()` when
charging is actually permitted, forcing `Captar`'s state back to `idle()` for as long as the limit
holds. `Captar`'s own module carries no SOC-related phase, for the same reason UC01/UC02's modules
don't: "whichever mode is active simply charges to this resolved value... it has no opinion on *why*
the limit is where it is" (R7).

---

## 6. Billing-Protection Engine + Peak-Demand Tracker (E5)

The core, non-shared deliverable of this epic. Two pieces, **two sibling modules** — ADR-0010's
Decision is explicit that "the V6 pair (Billing-Protection + Peak-Demand Tracker) stays two sibling
modules in `engines/`; their relationship is recorded by project-plan task E5 bundling them, not by a
directory": `engines/billing_protection.py` (the effective-peak-limit resolution and the R3 clamp,
§6.1–§6.2) and `engines/peak_demand_tracker.py` (§6.4), both named directly in ADR-0010's file list.

### 6.1 Effective peak limit (`resolve_effective_peak_limit`)

`resolution-rules.md`'s "Effective peak limit" rule has two priority rows: deadline urgency raises the
limit to the maximum peak; otherwise `min(monthly_peak_demand, maximum_peak)`. Row 1 (urgency) is
structurally inert without the Deadline Engine (E4, R5/UC05 — its own epic, out of scope, §9) — exactly
the same "rows N are inert without engine X" reasoning `2026-07-20-solar-solaronly-design.md` §5 uses
for R7's rows 1–2. **Row 2 is therefore this slice's complete, correct resolution** — not a stub — and
`resolve_effective_peak_limit(monthly_peak_kw, max_peak_kw)` takes no urgency input at all this slice;
E4 adds the row-1 branch as a change to this one function when it lands, not a new service.

### 6.2 The R3 peak clamp (`apply_peak_clamp`)

Mirrors E6's `clamp_to_ceiling` shape (same baseline-solved math: `net_w (raw) − charger_w (raw)`,
floored to a whole ampere, per `control-cycle.md` step 5/ADR-0006), but adds the R3 grace-period
distinction step 5/UC03's exception flow requires and E6 (C4, no grace period, ADR-0006) does not have:

```python
def apply_peak_clamp(
    desired_current: float,
    net_w: float,
    charger_w: float,
    voltage: float,
    effective_peak_limit_kw: float,
    safety_margin_w: float,
    min_a: float,
    grace_period_s: float,
    tracker: "PeakBreachTracker",
    now: float,
) -> tuple[float, "PeakBreachTracker", bool]:
    """Return (clamped_current, new_tracker, force_stop).

    `force_stop=True` only once the MODE'S OWN REQUEST has been at least `min_a`
    (it is actually trying to charge) while the available headroom stayed below
    `min_a` continuously for `grace_period_s` (R3's grace period) -- the coordinator
    then commands 0 A and drives Captar's own state to cooldown (see 6.3). A `desired_current`
    already below `min_a` (Off, an idle/cooldown/SOC-gated mode, or a disconnect --
    all of which request 0 A) never starts or extends the grace timer, regardless of
    headroom -- R3's own wording is explicit that the stop condition requires the
    charger to be "already at the minimum charging current," not merely idle.
    """
```

`PeakBreachTracker` is a small frozen dataclass (`breached_since: float | None`), threaded by M1
exactly like `Solar`'s/`SolarOnly`'s per-mode state and E7's smoothing window — never HA-held. This is
the `PeakBreachTracker` the pre-existing scaffolding plan already named and `project-plan.md` §6 folded
into E5 ("the R3 grace-period `PeakBreachTracker`").

**Clamp math**, per `control-cycle.md` step 5 / R3's acceptance criteria:

```text
headroom_a = floor(((effective_peak_limit_kw * 1000) - safety_margin_w - baseline_w) / voltage)
clamped    = min(desired_current, headroom_a)
```

where `baseline_w = net_w - charger_w` (the same raw baseline E6 already solves from). The breach
timer is gated on the **request**, not the clamped result: only when `desired_current >= min_a` (the
mode wants to charge, not merely idling) **and** `headroom_a < min_a` (there isn't room to honor even
the minimum) does a breach start/continue —

- if `tracker.breached_since is None` → start the grace timer (`breached_since = now`); this cycle
  still returns `clamped` (E8 downstream floors it to 0 A this cycle regardless — the *grace period*
  only governs whether the *cooldown* engages, not whether this cycle's current is reduced, per R3's
  own "momentary breach does not stop charging" wording — a reduction is not a stop).
- if `now - tracker.breached_since >= grace_period_s` → `force_stop=True`, `clamped=0.0`, tracker
  resets (`breached_since=None`) — the coordinator forces `Captar`'s own state to `cooldown(now)`.

Otherwise (the mode isn't requesting at least `min_a`, or headroom is sufficient) the tracker resets
(`breached_since=None`). This request-gated framing is also what keeps a disconnect or an SOC-gated
stop from ever tripping `force_stop`: both branches set `desired_current = 0` before this clamp runs, so
the breach condition's first half (`desired_current >= min_a`) never holds — the coordinator's own
`idle()`/disconnect reset (§8) is never fought by a stray breach timer left over from a prior charging
cycle.

### 6.3 `Captar` mode engine (E1 — UC03)

Simplest of the mode state machines: `Idle → Charging → Cooldown` (no `Hold` — `Captar` has no
surplus-threshold concept to ride out; UC03's exception flows put the stop/cooldown decision entirely
in E5, not in the mode's own logic, matching UC03's own framing: "the clamp decides the set-point this
cycle, not the mode"). No SOC-related phase either, for the reason §5 gives.

```python
@dataclass(frozen=True)
class CaptarState:
    phase: str  # "idle" | "charging" | "cooldown"
    phase_started_at: float = 0.0

    @classmethod
    def idle(cls) -> "CaptarState":
        return cls(phase="idle")


def step(
    state: CaptarState, now: float, max_a: float, cooldown_minutes: float
) -> tuple[float, CaptarState]:
    """Return (desired_current, next_state) for one control cycle (UC03).

    Captar always requests the maximum charging current while charging -- unlike
    Solar/SolarOnly, it has no surplus input to derive an ideal current from (R4);
    E5's peak clamp and E6's grid-ceiling clamp are what actually bound the request
    each cycle. There is no in-module transition into cooldown: a sustained R3 breach
    at the minimum current is detected by E5 (6.2), and the coordinator -- not this
    function -- forces `state` to `cooldown(now)` when that happens, the same
    externally-driven-transition pattern the SOC gate uses (see 5): the mode "has no
    opinion on" why it stopped, only on whether cooldown has elapsed.
    """
    if state.phase in ("idle", "cooldown"):
        elapsed = now - state.phase_started_at
        cooldown_done = state.phase == "idle" or elapsed >= cooldown_minutes * 60
        if cooldown_done:
            return max_a, CaptarState("charging", now)
        return 0.0, state
    return max_a, state  # "charging" -- coordinator overrides to cooldown on a forced stop
```

### 6.4 Peak-Demand Tracker (`engines/peak_demand_tracker.py`)

The glossary is explicit that `monthly peak demand` is "the highest **15-minute average** net import,"
not an instantaneous raw reading — a materially larger, differently-purposed rolling window than R10's
smoothing window (default *N*=4 cycles, ≈40 s, for charging-rate responsiveness).

**No engine calls another engine** (`system-design.md` §4 rule 4; ADR-0010: "no engine imports …
another Engine"), so this module does **not** import E7's `smooth_net_power` itself. Instead the
coordinator (M1) — which already owns and threads E7's smoothing window as a parameter — calls
`smooth_net_power` a **second time**, with its own, much larger `size` (≈`900 / control_interval_s`
samples, e.g. 90 at the default 10 s interval) and its **own** window parameter, distinct from R10's
short window, and passes the already-smoothed kilowatt value into the tracker below. Reusing the E7
*helper function* across two Manager-owned call sites (one per window size) is not an engine→engine
call — it is M1 calling E7 twice, exactly as it already calls E7 once for R10; per §0, this reuses
`smooth_net_power` if Solar/SolarOnly's implementation already added it to
`engines/signal_conditioning.py`, or this slice adds it there if not.

```python
def update_monthly_peak_demand(
    smoothed_kw: float,
    current_month: tuple[int, int],
    tracked_kw: float,
    tracked_month: tuple[int, int] | None,
) -> tuple[float, tuple[int, int]]:
    """Return (monthly_peak_kw, new_tracked_month).

    Takes the ALREADY-SMOOTHED (15-minute-average) net import in kW -- the
    coordinator (M1) is responsible for calling `signal_conditioning.smooth_net_power`
    with its own dedicated window before calling this function (see above); this
    module never touches a raw watt reading or a smoothing window itself, keeping
    it a trivial, engine-purity-respecting running-max. `current_month` is
    `(year, month)`, computed by the coordinator from real wall-clock time (this
    function stays pure -- it never calls `datetime.now()` itself, per the
    project's "now is injected" convention). A month change resets the running
    peak to this cycle's own smoothed value (not to 0), since a fresh month starts
    accumulating immediately, not from an artificial floor.
    """
    if tracked_month != current_month:
        return smoothed_kw, current_month
    return max(tracked_kw, smoothed_kw), current_month
```

**Month rollover also resets the smoothing window, not just the tracked value.** Because the 15-minute
window is threaded by the coordinator (not this module), M1 is responsible for resetting its dedicated
peak-tracking window to `()` in the same cycle it detects `current_month != tracked_month`, **before**
calling `smooth_net_power` — otherwise the "reset" would still be a 15-minute average partly built from
the *previous* month's raw samples, contradicting the "resets at the start of each month" glossary
wording. §8's control-cycle sketch and the paired plan's Task 5.1 both call this out explicitly at the
coordinator call site, since it is a coordinator responsibility, not something this pure function can
enforce on its own.

**Bootstrap edge case, named rather than hidden:** on a brand-new install (or the first cycle of a new
month), `monthly_peak_demand` starts at that cycle's own smoothed reading rather than an arbitrary
floor — closer to the glossary's "peak demand" framing (the *first* sample already establishes a peak)
than initializing at 0 kW would be. This is **not** the same as guaranteeing charging starts
immediately on a fresh install: with a flat household baseline, `effective_peak_limit ≈ baseline`, and
subtracting the safety margin can still leave zero or negative headroom until either a genuinely higher
peak accrues (from a household appliance, not from clamped charging — see below) or the baseline itself
dips. Guaranteeing the "starts within one cycle" UC03 success criterion under a cold-start,
already-at-baseline peak is what the deadline-urgency raise to `maximum_peak` would provide (R5/UC05,
deferred, §9) — this slice does not claim to solve that bootstrap case, only to avoid the strictly worse
0 kW floor. Because the R3 clamp itself always keeps charging at or below
`effective_peak_limit − safety_margin`, controlled charging structurally cannot be the cause of a new
recorded peak except when household baseline load alone already exceeds the previous one — the tracker
needs no charging-aware special-casing to keep this invariant (R3's own acceptance criteria,
§"Requirements satisfied").

**Persistence.** `sensor.smart_charging_monthly_peak_kw` must survive an HA restart mid-month (§2.4).
Per the `RestoreSensor` pattern the other owned entities already use, the sensor restores its last
native value **and** a `period_month` extra-state-attribute (`"YYYY-MM"`) on `async_added_to_hass`,
feeding both back into the coordinator's tracker state as the initial `(tracked_kw, tracked_month)` —
the same "state is a parameter, never HA-held" rule E7's smoothing window and the per-mode state
dataclasses already follow, just seeded from restore-state instead of a hardcoded initial value. The
15-minute smoothing *window* itself is **not** persisted (the same known limitation R10's own window
already has after a restart — `2026-07-20-solar-solaronly-design.md` §6's "smoothing window not yet
full" edge case): a post-restart cycle rebuilds it from scratch, so a spike in the first ~15 minutes
after a restart is under-smoothed relative to steady-state — an accepted, pre-existing limitation of
the rolling-mean approach, not a new gap this slice introduces.

---

## 7. `Power` mode's R17 opt-out interaction

Before this slice, `Power` mode (shipped) is bounded only by E6 (C4, grid ceiling) — there is no R3
clamp to opt out of yet. This slice's E5 addition is the coordinator's **first** R3 clamp of any kind,
and per `control-cycle.md` step 5 / R17, it applies to **every** mode except `Power` with its own
`sc_power_respect_peak` option explicitly turned off. Concretely, in the coordinator:

```python
if not (self.active_mode == "Power" and not self._config["power_respect_peak"]):
    desired, self._peak_tracker, force_stop = apply_peak_clamp(desired, ..., tracker=self._peak_tracker, now=now)
    if force_stop and self.active_mode == "Captar":
        desired = 0.0
        self._mode_state["Captar"] = captar.CaptarState("cooldown", now)
# E6 (C4, unchanged) always runs next, regardless of the branch above -- ADR-0006's
# "step 7/step 8 must remain separate methods/call sites" rule: Captar/Power's R17
# opt-out can only ever skip E5, never E6.
desired = clamp_to_ceiling(desired, ...)  # E6, unchanged
```

**This is an intentional, R17-mandated behavior change to the shipped Power MVP**, not a slice-scope
creep: `sc_power_respect_peak` defaults **on** (already catalogued), so an existing Power-MVP
installation that upgrades to this slice starts having its `Power`-mode charging bounded by the R3
peak clamp by default, exactly as R17's acceptance criteria require ("A configurable option determines
whether `Power` mode respects CapTar peak protection... when enabled (default)..."). An installer who
wants the pre-this-slice behavior back sets the option off. The existing Power-MVP regression suite
must be updated to reflect this (§8) — not treated as a bug.

`force_stop`'s cooldown-override only applies to `Captar` (the `if force_stop and active_mode ==
"Captar"` guard above): `Power`'s own R11 cooldown handling is out of this slice's scope (Power's
existing behavior — charging regardless of SOC, no cooldown state machine yet — is otherwise
untouched; a sustained R3 breach in `Power` mode this slice simply holds the clamped/floored current at
whatever E8 resolves it to, without a cooldown transition, since `Power` has no cooldown state to
transition into yet).

---

## 8. Control cycle

Extends the Power MVP's cycle (`coordinator.py`, M1). New/changed steps in **bold** (assuming the
Solar/SolarOnly scaffolding described in §0 does not exist yet — if it does, these steps compose with,
rather than duplicate, its equivalent additions):

```text
read charger_status (raw) → translate to canonical
read net_power, charger_power, grid_voltage
**read ev_soc — only if active_mode == Captar (or a solar mode, if that scaffolding exists);
  a None reading there is the ADR-0007 fault signal for THIS cycle only**
resolve voltage (grid_voltage None → nominal, NF4)
**resolve active SOC limit ← number.smart_charging_soc_limit_override (E3, §5)**
**current_month = (now.year, now.month); if current_month != peak_tracked_month:
  reset the dedicated 15-min peak window to () (§6.4's month-rollover reset)**
**smooth net_power into the dedicated 15-min peak window (E7's smooth_net_power, its
  own window/size -- distinct from R10's short window) → smoothed_peak_kw**
**update the Peak-Demand Tracker ← smoothed_peak_kw, current_month (E5 §6.4);
  materialize sensor.smart_charging_monthly_peak_kw**
**resolve effective peak limit ← monthly_peak_kw, sc_max_peak_kw (E5 §6.1);
  materialize sensor.smart_charging_effective_peak_limit**
**read active mode ← select.smart_charging_mode**

if canonical ∉ {connected, charging}:
    desired = 0
    **reset Captar's threaded state to idle() — disconnect ends any cooldown (R7/R11)**
elif active_mode == Off:
    desired = 0                                                          # unchanged
elif active_mode == Power:
    desired = target_current                                            # unchanged (E1, Power MVP)
elif active_mode == Captar:
    **if ev_soc is None: desired = 0   # fault (this cycle's required-role check)**
    **elif ev_soc >= active_soc_limit:**
        **desired = 0; state["Captar"] = CaptarState.idle()   # R7, same pattern as §5**
    **else:**
        **desired, state["Captar"] = captar.step(state["Captar"], now, max_current, captar_cooldown_min)**

**if not (active_mode == "Power" and not power_respect_peak):                 # §7, R17**
    **desired, peak_tracker, force_stop = apply_peak_clamp(desired, ..., peak_tracker, now)   # E5 §6.2**
    **# force_stop can only be True when `desired` (the mode's own request, above) was**
    **# already >= min_a -- Off/idle/cooldown/SOC-gated/disconnected branches all set**
    **# desired = 0 before this point, so they can never trip force_stop (§6.2's**
    **# request-gated framing) -- no extra guard needed here beyond the mode check below.**
    **if force_stop and active_mode == "Captar":**
        **desired = 0.0; state["Captar"] = CaptarState("cooldown", now)**

baseline_w = net_w (raw) − charger_w (raw)                              # unchanged
headroom_a = floor((ceiling − offset) − baseline_w / voltage)           # grid-safety, E6 — unchanged
desired = min(desired, headroom_a)
desired = clamp(desired, min, max)                                      # floor/cap invariant — E8, unchanged

write charger_current ← desired
```

- **The Peak-Demand Tracker and effective-peak-limit resolution run every cycle, regardless of active
  mode** — R3's monthly-peak bookkeeping is not `Captar`-specific (it also gates `Power`'s clamp, §7,
  and would gate any future mode that doesn't opt out). This mirrors `control-cycle.md`'s own step
  ordering: the tracker/resolution precede mode dispatch.
- **E5 runs after mode dispatch, before E6** — exactly `control-cycle.md` steps 5→6 and ADR-0006's
  "two distinct clamp methods" rule: the R17 opt-out can only ever skip E5's call, never E6's.
- **`Captar`'s cooldown is entered two ways**, both ending at the same `CaptarState("cooldown", now)`:
  a sustained R3 breach (E5's `force_stop`, §6.2/§7) or a disconnect (R7/R11, resets to `idle()` instead
  — a disconnect does not "cool down," it simply exits the use-case's scope, per UC03's state model
  note). There is no mode-switch-away-and-back test needed beyond the existing per-mode state-dict
  pattern (§0) — switching away from `Captar` and back finds `CaptarState.idle()` if the dict was
  reset, same as `Solar`/`SolarOnly`.
- **A disconnect can never be spuriously overridden back into cooldown by the peak clamp.** The
  disconnect branch sets `desired = 0` before E5 runs; per §6.2's request-gated breach condition
  (`desired_current >= min_a`), a request of `0` can never start or extend the grace timer, so
  `force_stop` cannot fire on the same cycle a disconnect already reset `Captar` to `idle()` — the two
  branches cannot fight each other. The same reasoning covers the SOC-gated-stop branch, which also
  sets `desired = 0` before E5 runs.

---

## 9. Deliberately deferred

Out of scope for this slice, each a later slice of `project-plan.md` — none is a safety deferral (the
grid ceiling clamp, E6, is untouched and unconditional; the R3 peak clamp this slice adds is itself the
opposite of a deferral — it is the safety behavior UC03/R3 mandate):

- **`Auto` profile (E2)** and everything that depends on it: Auto mode-selection's escalation to
  `Captar` under deadline urgency or the low-tariff overnight row (`resolution-rules.md` rows 2/4) —
  `Captar` is reachable only via `Manual` this slice, exactly like `SolarOnly`/`Power`.
- **Deadline Engine (E4), R5** and the effective-peak-limit's row-1 urgency raise (§6.1) — its own
  epic; `resolve_effective_peak_limit` is row-2-only until E4 exists.
- **Capability gating (E9, R18)** — `Captar` is always offered regardless of capabilities per
  `entity-catalog.md`, so this changes nothing about the selector's option list this slice adds.
- **`Solar`/`SolarOnly` modes** — their own epic, #189; §0 records the shared-scaffolding obligation
  between the two epics.
- **`sensor.smart_charging_active_soc_limit`, `ActiveSocLimitChanged`, vehicle-limit sync (M2, UC09),
  notifications (M3, UC08/UC10)**, the runtime dashboard (C5, UC11) — no consumer exists yet.
- **A formal config-entry migration.** Not needed: the five new **options** keys (§3) are read with
  their `DEFAULT_*` fallback, the same pattern Solar/SolarOnly's design and the Power MVP already use —
  an entry that predates them simply gets the defaults (`sc_power_respect_peak` defaulting **on**, per
  §7, is the one default whose *effect* is a deliberate behavior change, not its *mechanism*, which is
  the same fallback-default pattern as every other option). `ev_soc` (data, optional) needs no
  migration either, per the identical reasoning `2026-07-20-solar-solaronly-design.md` §8 gives.

---

## 10. Testing

- **Plain pytest** (no HA) for the pure pieces: `resolve_effective_peak_limit` (row-2-only lookup);
  `apply_peak_clamp` — the baseline-solved clamp math with worked examples (mirroring E6's existing
  worked-example tests), the grace-period tracker (momentary breach reduces but does not stop;
  a sustained breach at the minimum current for the full grace period returns `force_stop=True`; a
  breach that clears before the grace period elapses resets the tracker); `update_monthly_peak_demand`
  (window-not-yet-full at startup, sliding max within a month, reset on a month change, seeded from a
  restored value); `Captar`'s `step()` state machine (idle→charging, cooldown blocks restart until
  elapsed, deterministic given identical inputs) — same shape as `Solar`'s/`SolarOnly`'s Task 1.4/1.5
  tests; `resolve_active_soc_limit` only if this slice creates it (§0 — skip if Solar/SolarOnly's
  module already exists and is reused unchanged).
- **HA harness** for the HA-coupled pieces: `select.smart_charging_mode` offering `Captar` (extend or
  create per §0); the coordinator dispatching to `Captar`, gating on SOC (both R7 resume paths — the
  limit rising, and unplug/replug); the R17 opt-out — `Power` mode clamped by E5 when
  `sc_power_respect_peak` is on, unclamped by E5 (but still C4-clamped) when off; E5 running before E6
  with the two clamps as **distinct call sites** (ADR-0006 assertion: opting `Power` out of E5 must
  never also skip E6); `sensor.smart_charging_monthly_peak_kw` and
  `sensor.smart_charging_effective_peak_limit` materializing and restoring across a simulated restart;
  a sustained R3 breach forcing `Captar` to 0 A and into cooldown, and the cooldown blocking a restart
  until it elapses; a mode switch away from and back to `Captar` resetting its cooldown state; the
  existing Power-MVP regression suite updated for the R17-mandated default-on peak clamp (§7) and
  otherwise passing unchanged; a full-cycle regression per UC03's main-success/alternate/exception
  flows (start / cooldown-block / peak-clamp-reduces / sustained-breach-stop-and-cooldown /
  SOC-gated-stop-and-resume) against a mocked hardware state.

---

## 11. Packaging

```text
custom_components/smart_charging/
  const.py              # + peak-protection/Captar-cooldown/power-respect-peak CONF keys
  coordinator.py         # M1 — Captar dispatch, peak-clamp wiring, R17 opt-out, tracker wiring
  select.py              # C2 — extend MODE_OPTIONS with "Captar" (create if it doesn't exist, §0)
  sensor.py              # C3 — + monthly_peak_kw, effective_peak_limit sensors (RestoreSensor)
  config_flow.py         # C4 — + peak-protection options, power_respect_peak, ev_soc (if needed)
  engines/
    signal_conditioning.py # E7 — + smooth_net_power if it doesn't already exist (§6.4; shared with R10)
    soc_target.py           # E3 — reuse if it exists, else create per §0/§5
    billing_protection.py   # E5 (part 1/2) — new: resolve_effective_peak_limit, apply_peak_clamp,
                             #      PeakBreachTracker (ADR-0010 names this module directly)
    peak_demand_tracker.py  # E5 (part 2/2) — new: update_monthly_peak_demand (ADR-0010: a
                             #      sibling module, not folded into billing_protection.py)
  modes/
    captar.py              # E1 — new: CaptarState, step()
```

`tests/` mirrors 1:1 per ADR-0002/0009 (`tests/engines/test_billing_protection.py`,
`tests/engines/test_peak_demand_tracker.py`, `tests/modes/test_captar.py`, plus HA-harness additions to
`test_coordinator.py`, `test_config_flow.py`, `test_select.py`/`test_sensor.py`).

---

## 12. Next step

This design feeds the `writing-plans` skill to produce the ordered, test-driven implementation plan
(`2026-07-20-captar.md`). Build order follows `project-plan.md`'s layering: the shared pieces (§0,
extend-or-create) → E5 (pure, independent of the shared pieces) → `Captar` mode engine (pure, depends
on E5/E3 only as data shapes) → M1 extension (composes them, wires the R17 opt-out) → C2/C3/C4
extensions. No `custom_components/` code is written until the paired plan exists and is approved.
