# Design: R5's pursued occurrence, and the escalated rate's smoothed forecast (#1154)

The analysis layer changed under the code. `requirements.md` R5 now specifies urgency state as a
single **pursued occurrence** — the departure occurrence being chased — from which the
**missed-deadline hold** is *read* rather than separately tracked, and specifies the **escalated
maximum permitted rate** as a forecast fitted to a **smoothed** household baseline while delivery
stays clamped on raw. The code carries a boolean and reads raw for every bound.

This slice closes that gap. It writes no new behaviour: every rule it implements is already stated
in `requirements.md` (R3, R5, R9, R10, R14), `resolution-rules.md` and `UC05`, and is cited here as
a test anchor rather than restated.

## Scope

| In | Out |
| --- | --- |
| `engines/deadline.py` — the urgency-state parameter and return, the hold, the backstop | The required-current formula itself (R5/R15, unchanged) |
| `engines/soc_target.py` — R9's sixth precondition | R9's cap rule itself; only its precondition set grows |
| `coordinator.py` / `coordinator_cycle.py` — threading one occurrence where a boolean is threaded, and one further fact out of the same early return for the clear edge (D-9) | ADR-0006's step order — no step added, removed or reordered |
| Both of the escalated rate's bounds moved to smoothed readings | The R3 clamp, the C4 clamp, and the `peak_headroom` readout — all stay raw |
| Closing #1006 (there is no separate hold left to build) | `debounce_baseline_w` (ADR-0039) — R3's deferral, which R5 `:92` keeps off the smoothed operand; see D-3 |

## Project-plan slice this derives from

`docs/design/project-plan.md`: **E4** (Deadline Engine — "R5's pursued occurrence, threaded in and
out by M1"), **E3** (SOC-Target — R9's cap activation), **E5**/**E6** (the peak and C4 headrooms as
values), and **M1** (Coordinator — "Owns and threads every Engine's cross-cycle state, the Deadline
Engine's included").

**Where each rule is owned.** The smoothed operand is stated by `requirements.md` R5 `:90-92`
and by `system-overview.md`'s `escalated maximum permitted rate` and `maximum permitted rate`
entries, which is where this spec cites it. The design layer now says the same in its own terms —
`project-plan.md` E5 ("the readout to a raw one, R5's to the smoothed baseline") and
`system-design.md` §5.1 (`:450`, `:452`), both of which fit the escalated rate's peak and C4
headrooms to the smoothed baseline. `system-design.md:160` (Billing Protection) carries the
in-force-versus-raised limit contrast.

`system-design.md` §5.1's sequence is unchanged by this slice: no step is added, removed or
reordered, and smoothing (`:438`) already precedes the escalated-headroom call (`:450`), so the
smoothed operands are available where they are needed. ADR-0006's call-order spy test should pass
untouched — a success criterion below.

## Success criteria

1. `resolve_required_current` takes and returns a `datetime | None`, and `urgency_latched` is gone
   from `custom_components/`. Two booleans deliberately remain and are **not** what this criterion
   is about: `urgent` on the result (D-1 says why), and E3's `missed_deadline_hold` parameter, which
   carries the *reading* of an occurrence across a service boundary that has no business holding a
   datetime. What the criterion forbids is a boolean that is urgency state — something a cycle
   writes and the next cycle reads.
2. A missed-deadline hold is nowhere a stored field — it is `pursued is not None and pursued <= now`
   at every site that needs it.
3. Every release condition `resolution-rules.md` lists for a hold is reachable, including the two
   the engine's current control flow would swallow (D-2).
4. The backstop releases per `resolution-rules.md`'s bound, including on an installation where the
   following occurrence never resolves — the 24-hour arm is what makes the release reachable
   without one. It is evaluated on every cycle that reaches the engine; the deferral below bounds
   the one case that does not.
5. Every **baseline-dependent** bound of the escalated rate is computed from smoothed readings —
   the C4 ceiling headroom always, and the peak headroom wherever it is composed at all (it is
   absent under R18 and R17, exactly as the clamp is). The R3 clamp, the C4 clamp and
   `sensor.smart_charging_peak_headroom_a` still compute from raw, and a test pins that the two can
   differ.
6. ADR-0006's call-order spy test passes unchanged.
7. **Every commit is green.** T1's parameter is additive and the boolean is removed in T4, so the HA
   suite never goes red between commits (D-8).
8. Mutation check: each new test is shown to fail against a deliberately broken implementation
   before the slice is called done — the standard this strand has been held to since #1101.

## No ADR is opened by this slice

The rules driving it — which occurrence is pursued, when it is released, which reading each bound is
fitted to, R9's sixth precondition — are **domain rules**, which `CLAUDE.md`'s second carve-out
places in `requirements.md`/`resolution-rules.md`, where they already are, and explicitly not in an
ADR.

The slice does touch more than one module's signature (E4's entry point, E3's, `CycleContext`,
`DeadlineUrgencyInputs`), so it does not pass the calibration test on reach alone — but reach is not
the only question the test asks. ADR-0010's Decision (package placement) does not move; ADR-0012
already covers `CycleContext`'s shape; `system-design.md` §3's two-kind split already says M1 owns
and threads Engine state. Nothing structural is being decided, only applied.

Five existing ADRs are *honoured* rather than changed: **ADR-0006** (two clamp call sites, cycle
order), **ADR-0009** (test tiers, named per task), **ADR-0012** (`CycleContext`), **ADR-0024**
(`DeadlineUnreachableCleared` pairing — D-6 explains why it needs no new arm), and **ADR-0042**
(that pairing's `ev_soc`-becomes-`None` row, narrowed — D-9 states the structure, T13 builds it).

**ADR-0042 is not a counter-example to this section's title.** It was opened and merged on its own
issue, against a contradiction that predates this slice; this slice consumes it. What would falsify
the title is a structural decision taken *here*, and D-9 takes none — it records where an
already-decided rule lands.

## Concrete decisions

### D-1 — the urgency parameter becomes the pursued occurrence

`resolve_required_current`'s `urgency_latched: bool` becomes `pursued_occurrence: datetime | None`,
and `RequiredCurrentResult` gains `pursued_occurrence: datetime | None` as the successor value the
Manager threads back in.

`urgent` stays on the result. Every downstream consumer already reads it — the effective peak
limit's `urgent` parameter, `Auto`'s escalation row, the notification edge — and re-deriving it at
each of those sites would spread R5's precedence rule across the coordinator.

The relation is the glossary's, not this slice's — `system-overview.md`'s `urgency` and `pursued
occurrence` entries define urgency as being in effect exactly when there is a pursued occurrence. It
is rendered once, in the engine, as `urgent == (pursued_occurrence is not None)`, and a test asserts
it on every branch, which is what stops the two drifting.

### D-2 — the hold's release order inside the engine

The hold is `pursued is not None and pursued <= now`, evaluated where it is needed — no field, no
setter, no clear path of its own. But a short-circuit placed naively destroys two releases the
analysis requires, so the **order** is a decision, not an implementation detail.

`UC05`'s state table (the `Unreachable` row) and `resolution-rules.md` agree on what may end a hold:
state of charge reaching the active SOC limit, a disconnect, the deadline capability becoming absent
(R18), or the backstop — and on what may **not**: the required-current exit, and the deadline
resolving to "no deadline". The engine must therefore evaluate, in this order:

1. **SOC at or above the active SOC limit → release.** Today this release is produced *inside* the
   ordinary path: `energy_needed_kwh <= 0` → `required_a = 0.0` → the handback fires
   (`deadline.py:231-255`). A hold short-circuit placed above that computation removes it, and a car
   that finishes charging after a missed deadline would stay pinned until the 24-hour backstop —
   max-peak raise held, `Auto` escalated, R9's cap suppressed. So the energy computation runs first,
   and a non-positive energy need releases whether or not the occurrence has passed.
2. **The backstop → release** (D-4).
3. **Otherwise, held**: `urgent=True`, `unreachable=True`, no required current computed.

And **`deadline_at is None` must not release a hold.** `deadline.py:225-226` returns `urgent=False`
on that input today. R5's AC and `resolution-rules.md` say the opposite while held: *a later
occurrence resolving to "no deadline" cannot end it.* So the hold branch sits **above** that early
return, not below it. The engine cannot distinguish R14's "no deadline" from R18's absent
capability, which release in opposite directions — that distinction is the caller's, D-7.

### D-3 — both bounds read smoothed; the operand carries no R3 deferral

**Both questions this decision once argued are now stated outright by the source, and are cited
here as test anchors rather than re-derived.** `requirements.md` R5:

- `:90` — the escalated maximum permitted rate is computed from a **smoothed** household
  baseline, not the instantaneous reading, while urgency's own delivery stays clamped on raw.
- `:91` — **every** bound of that rate which depends on a household reading is fitted to that
  same smoothed baseline: both the peak headroom R3 would leave and the headroom the grid supply
  ceiling (C4) leaves. C1's maximum charging current depends on no reading and is unaffected, and
  the peak bound is a bound at all only where the peak clamp is composed — so not with the CapTar
  capability absent (R18), nor under `Power`'s R17 opt-out.
- `:92` — that smoothed baseline carries **no** R3 deferral.

The two clamps and the `sensor.smart_charging_peak_headroom_a` readout all stay raw, per the same
criteria.

**Where it lands.** `_run_cycle` already computes `smoothed_net_w`; it is carried on `CycleContext`
as its own field. `_escalated_maximum_permitted_rate_a` takes only `ctx` and `peak_operand_kw`, so
it derives the peak bound's operand itself — `ctx.smoothed_net_w - ctx.charger_w` — rather than
reading a `_run_cycle` local it cannot see. The C4 bound takes `net_w=ctx.smoothed_net_w` with
`charger_w` unchanged, since R10 smooths net grid power alone. Deliberately *not* derived from
`ctx.surplus_w`, which is that operand's exact negation: one refactor of either would silently
change the other.

### D-4 — the backstop's operands, and where the following occurrence comes from

`resolution-rules.md`'s release needs the occurrence *following* the pursued one, and 24 hours since
the pursued one. The second is arithmetic on a value the engine already holds.

The first is **not** `resolve_next_occurrence`'s output. That yields an occurrence strictly after
`now` (`deadline.py:127`), whereas the backstop's operand is relative to the *pursued* occurrence,
which while held has already elapsed. Fed the existing call's output, `following_occurrence <= now`
would be unreachable in production and only the 24-hour arm could ever fire. It must be built from
the per-day resolution for the day after the pursued occurrence — `resolve_deadline_for` (defined at
`coordinator.py:395`, returned at `:418` and in scope at the urgency call site), the same R14 table
both existing occurrence resolutions use — and passed in as `following_occurrence: datetime | None`.

`None` is a normal value here, not an error: R14 lets any day resolve to "no deadline". That is
precisely why the 24-hour arm exists.

### D-5 — the fault-cycle rule is unchanged, and must be shown to be

Both fault early-returns sit upstream of the assignment, so a fault cycle holds the occurrence it
entered with rather than releasing it — the same reasoning `_role_readings_at` and
`_unreachable_edge` already carry (ADR-0024). Swapping the field's type must not move that line; the
existing fault tests are re-pointed at the new field rather than rewritten.

**`coordinator_cycle.py:613`'s early return must split its two halves.** The new field forces a
value onto it, and `deadline_resolvable` is `status in CHARGEABLE_STATES and ev_soc is not None` —
two conditions with **opposite** answers:

- **Disconnected** — a release condition R5 names. Returns `pursued_occurrence=None`.
- **SOC unavailable** — explicitly *not* an exit: *"State of charge becoming unavailable is
  deliberately not one of those exits … the System holds whichever state it was already in"*
  (`UC05`). Returns the occurrence **threaded in**, unchanged.

It is tempting to assume the SOC half never gets here because the fault early-return fires first. It
does not. That return is gated on `is_soc_gated` (`coordinator.py:534-538`), and `is_soc_gated` is
**False** on `_OffModeHandler` and `_PowerModeHandler` (`coordinator_cycle.py:233`, `:254`). The
coordinator states the consequence without enumerating the modes: *"outside that gate a missing
reading just means deadline urgency can't be computed this cycle (below), not a fault."* So `Manual`+`Off`, and `Auto`
without the CapTar capability whose urgency row escalates to `Power`, both reach this line with a
missing SOC reading and a live hold. Collapsing the two halves releases it on a cycle that
established nothing.

### D-6 — `unreachable` while held, and what the notification carries

While the hold is in effect no required current is computed (`UC05`), so `unreachable` cannot come
from the comparison. The engine sets it directly: a pursued occurrence in the past is unreachable by
definition, time having run out on it.

`_unreachable_edge` keeps working untouched on every path that *releases* the occurrence, because
each flips `unreachable` back to False through the same flag it already reads — ADR-0024's own
argument for keying the edge on the flag rather than on any one upstream guard.

**One path is not a release and still flips the flag**, and this slice is what makes it matter: see
the deviation on the `DeadlineUnreachableCleared` re-arm under *Deliberate deferrals*.

**But `required_a is None` with `unreachable=True` is a combination the coordinator cannot take
today.** `coordinator.py:706-724` enters the unreachable block and evaluates
`math.isinf(required.required_a)` — a `TypeError` on `None` — and
`managers/notification_manager.py:280-291` would drop a notification with no value to format, while the
glossary says the notice fires *"likewise once the pursued occurrence lies in the past"*.

The notification carries `self._config.max_current` — C1's configured maximum charging current,
which is precisely what the existing `float('inf')` saturation caps to (`coordinator.py:722-724`),
and **not** the [maximum permitted rate], which the glossary defines as the clamped delivered value.
The `None` case is the same statement as the saturated one, about a deadline that has run out
entirely rather than one needing more than the hardware can give.

No analysis escalation is owed for the value: `notification_manager.py` already records message
content as M3's own presentation detail. A task pins both the guard and the payload.

### D-7 — R18's release needs no code, and this slice adds none

Two inputs reach the engine as "no deadline resolved" and release in opposite directions while a
hold is in effect: the **deadline capability becoming absent** (R18) *releases*; the deadline
**resolving to "no deadline"** (R14) does *not*. The engine sees `deadline_at is None` for both, so
the obvious move is to have the caller distinguish them.

It cannot, and does not need to. `resolve_deadline_urgency` receives two capabilities,
`solar_available` and `captar_available`; `SmartChargingConfig` carries no `deadline_available`
field at all, and `CONF_DEADLINE_AVAILABLE` is read off `entry.data` by `time.py`, `sensor.py` and
`config_flow.py`'s own step gate — never by the control cycle. The coordinator is in exactly the
engine's position.

**The release already happens, by reload.** `__init__.py` registers
`entry.add_update_listener(_async_reload_entry)`, which calls `hass.config_entries.async_reload`.
Withdrawing the capability is a reconfigure that updates `entry.data`, so the entry reloads, the
coordinator is re-created, and `_pursued_occurrence` starts at `None` — the *"scoped to the current
connected session and never preserved across a restart"* rule (`system-overview.md`'s `pursued
occurrence` entry, restated in `UC05`; R5's AC says the same in its own words) producing exactly the
release R5 asks for.

The reload has two triggers, not one: the reconfigure branch calls
`async_update_reload_and_abort(entry, data=…)` directly, *and* the data update reaches the listener.

So this slice adds no plumbing for R18, and the engine's `deadline_at is None` path keeps meaning
R14's case only, which is what D-2 already requires. Specifying a capability parameter here would
build a second mechanism for a release the entry lifecycle already makes.

### D-8 — the parameter is additive first, so no commit is red

Swapping `urgency_latched` for `pursued_occurrence` in one commit breaks every HA-harness test from
T1 until T4, because `coordinator_cycle.py:663` passes a keyword the engine no longer accepts. The
Definition of Done's green-suite bar is per commit, not per slice.

So T1 **adds** `pursued_occurrence` alongside `urgency_latched`, with a default on both the
parameter and the result field, and derives the boolean internally; T4 moves the coordinator onto
the new parameter and removes the old one in the same commit that stops passing it. Every commit in
between is green.

### D-9 — the clear edge is told whether the cycle established anything (ADR-0042)

[ADR-0042](../adl/0042-soc-unavailable-cycle-holds-the-unreachable-clear.md) decides the rule and
owns it; in brief, `DeadlineUnreachableCleared` fires only on a cycle that **established** the
deadline is no longer unreachable, and the two halves of `deadline_resolvable` answer that question
differently — a disconnect is a genuine exit, a missing state of charge establishes nothing. This
decision records only the structure that lands in, which is D-5's split extended from the pursued
occurrence to the event.

`DeadlineUnreachableEdge.resolve` takes a second argument and holds its prior flag when the cycle
established no outcome — the behaviour it already has across both fault early-returns, now owed to
every such cycle rather than only the two that also fault:

```python
def resolve(self, unreachable: bool, *, outcome_established: bool = True) -> tuple[bool, bool]:
    """Return (this cycle's `unreachable`, whether it just cleared from True to False).

    `outcome_established=False` means no required current could be computed this cycle, so the
    prior flag is held and no clear is reported (ADR-0042).
    """
```

The keyword's default is `True` for the same reason D-8 gives for `pursued_occurrence`'s. There is
one production call site (`coordinator.py`, off the single `DeadlineUnreachableEdge()` at `:203`),
but **seven existing tests** in `tests/test_coordinator_cycle.py` call `resolve` with `unreachable`
positionally and nothing else. A required second argument turns all seven red in the commit that
adds it; a defaulted keyword leaves every one of them asserting exactly what it asserts today, which
is correct — a cycle that establishes an outcome is the case they cover.

**Where the fact comes from.** `resolve_deadline_urgency`'s non-resolvable early return already
distinguishes the two halves for the occurrence (D-5). It carries the same distinction out for the
event rather than the coordinator re-deriving it: re-deriving `status in CHARGEABLE_STATES` on the
coordinator side would be a second, separately written copy of the predicate the module boundary
exists to keep single — the hazard `resolve_deadline_urgency`'s own docstring names.

**What does not change.** The edge still reads `RequiredCurrentResult.unreachable` for *which* exit
occurred; ADR-0042 narrows only the claim that the flag alone is sufficient. Every release path
D-6 relies on keeps clearing for free.

## Structure

| Piece | File | `system-design.md` service |
| --- | --- | --- |
| `resolve_required_current` signature and return | `custom_components/smart_charging/engines/deadline.py` | **E4** Deadline Engine |
| The hold's release order and the backstop | same | **E4** |
| R9's sixth precondition | `custom_components/smart_charging/engines/soc_target.py` | **E3** SOC-Target Engine |
| `self._pursued_occurrence`, threaded in and out (init at `coordinator.py:213`) | `coordinator.py` | **M1** Coordinator |
| `smoothed_net_w` on `CycleContext`, **both** construction sites | `coordinator.py`, `coordinator_cycle.py` | **M1** |
| `_escalated_maximum_permitted_rate_a` reads both smoothed operands | `coordinator.py` | **M1** calling **E5** and **E6** |
| `following_occurrence` from the pursued occurrence's following day | `coordinator.py`, `coordinator_cycle.py` | **M1** calling **E4** |
| R18's release | — **no code**; the entry reload already makes it (D-7) | — |
| The unreachable-block guard and the notification payload | `coordinator.py` | **M1** calling **M3** |
| `DeadlineUnreachableEdge.resolve`'s `outcome_established` argument and its hold (D-9) | `coordinator_cycle.py` | **M1** |
| The non-resolvable early return carrying that fact out, and the fire site consuming it (D-9) | `coordinator_cycle.py`, `coordinator.py` | **M1** calling **M3** |
| R9's precondition wired from the threaded-in value | `coordinator_cycle.py` | **M1** calling **E3** |

Signatures after the slice:

```python
def resolve_required_current(
    deadline_at: datetime | None,
    following_occurrence: datetime | None,
    now: datetime,
    soc: float,
    active_soc_limit: float,
    ev_battery_capacity_kwh: float,
    voltage: float,
    baseline_desired_a: float,
    escalated_maximum_permitted_rate_a: float,
    pursued_occurrence: datetime | None,
) -> RequiredCurrentResult: ...


@dataclass(frozen=True)
class RequiredCurrentResult:
    required_a: float | None
    urgent: bool
    unreachable: bool
    pursued_occurrence: datetime | None = None  # the successor M1 threads back in
    # The default is load-bearing, not decoration. `RequiredCurrentResult` is constructed at four
    # sites: two OUTSIDE the engine (`coordinator.py:225`, `coordinator_cycle.py:613`) and two
    # inside it (`engines/deadline.py:226`, the `deadline_at is None` early return, and `:257`, the
    # normal return). Only the normal return sets the field; without the default the other three
    # stop compiling and T1's commit turns the HA suite red (D-8).


def resolve_solar_reserve_active(
    profile: str,
    home_day_flag: bool,
    sun_is_down: bool,
    forecast_kwh: float,
    forecast_threshold_kwh: float,
    deadline_tomorrow_resolved: bool,
    missed_deadline_hold: bool,  # as it stood ENTERING the cycle
) -> bool: ...
```

## Testing approach (ADR-0009)

`engines/deadline.py` and `engines/soc_target.py` are pure — **plain pytest**, in
`tests/engines/test_deadline.py` and `tests/engines/test_soc_target.py`, no HA harness. The
coordinator threading, the `CycleContext` field, the R18 release, the notification payload and the
two-baseline split are HA-coupled — **HA harness**, in `tests/test_coordinator.py`,
`tests/test_deadline_soc_management_end_to_end.py`, `tests/test_notifications_end_to_end.py` (T5)
and `tests/test_captar_end_to_end.py` (T10). Each task names its tier and its exact file.

`tests/test_coordinator_cycle.py` is a **third** placement and belongs to the first group, not the
second: it is plain pytest over `coordinator_cycle.py`'s pure units — its own module docstring says
so, and it imports no harness. The clear-edge detector D-9 adds (T13) is one of those units and is
tested there; only T13's *cycle* half needs the harness. Where an earlier draft of this document put
that file on the HA-harness list, the list was wrong and the file has not moved.

## Deliberate deferrals, and the known deviations

- **No entity surfaces the pursued occurrence.** `entity-catalog.md` lists none; adding one is a
  `requirement` change, not this slice's.
- **Closed, was a known deviation — a SOC-unavailable cycle re-arms the unreachable notification.**
  `coordinator_cycle.py`'s non-resolvable early return yields `unreachable=False`, which reaches
  `_unreachable_edge` and fires `DeadlineUnreachableCleared`, re-arming M3. D-5 has that same
  cycle *preserve* the pursued occurrence, so the next healthy cycle is held again,
  `unreachable` goes True, and a **second notification fires for the same occasion** — which R5 and
  `UC05` both forbid.

  It was newly reachable because of this slice, not newly wrong. On the tree before it, that cycle
  also clears `_urgency_latched`, so urgency ends outright and a later notice is a legitimately new
  occasion; the slice keeps the urgency state and not the notification latch.

  It was deferred for one reason — ADR-0024 was Accepted and a spec must not silently contradict an
  Accepted ADR. **ADR-0042 has since narrowed the row that disagreed**, so the reason is spent and
  the fix is in scope: **D-9** states the structure it lands in and **T13** builds it, un-xfailing
  T5's guard in the same commit.
- **Known deviation — a sustained SOC-role outage suspends the backstop.** The backstop is the
  engine's (D-4), and the engine is reached only when `deadline_resolvable` is True. D-5 has the
  SOC-unavailable half of that gate preserve the occurrence, which is what `UC05` requires — but it
  means a `Power`/`Off` cycle with the SOC role unavailable evaluates neither the SOC release nor
  the backstop, so a *sustained* outage holds the occurrence beyond the 24-hour bound and, through
  R9's precondition, suppresses the solar-reserve cap for its duration.

  Bounded, and in the safe direction: those cycles resolve `urgent=False`, so nothing is delivered
  at the raised peak limit and both clamps run normally — suppressing R9's cap leaves the active SOC
  limit *higher* than it would otherwise be, which is a cost and solar-optimisation regression, never
  an over-current or a peak breach. The backstop fires on the first cycle that reaches the engine
  again.

  The alternative is not merely "R5's release logic in two places". On a SOC-unavailable cycle the
  SOC release **cannot be evaluated by anyone** — the input does not exist — so a coordinator-side
  backstop would be releasing on a cycle that established nothing about the deadline, which `UC05`
  prohibits in terms. The deviation is the analysis layer's own answer. What is imprecise is
  `resolution-rules.md`'s unconditional "a hold never outlives one deadline cycle", which does not
  carry `UC05`'s fault-cycle qualifier — a defect there rather than here, raised in #1201.
- **The baseline calls are not skipped while held.** `system-design.md` §5.1's note says the two
  R5 tests "and the baseline calls that exist only to feed them" are skipped under a hold. T2 does
  the engine half; the Coordinator will still call `mode_desired_current`. It is a query that
  advances no mode state (`control-cycle.md` step 4), so the only cost is a wasted call — deferred
  deliberately rather than left unmentioned.
- **The `following_occurrence` resolution lag.** Like the escalated rate's own mode-lag caveat
  already recorded in `coordinator.py`, it is resolved once per cycle before dispatch. No case is
  known where that matters within a single cycle; recorded rather than left silent.
- **Known deviation — the C4 *clamp* stays raw while its *headroom* moves.** E6 will answer headroom
  under two readings while clamping on one. That is deliberate and matches R5: C4 is a hard physical
  clamp on this instant (`system-design.md` §2's V6/V7 split), and only the forecast is a forecast.
  Stated here because a reader could otherwise take it for an oversight.
- **No safety behaviour is deferred *silently*.** Every clamp, the fault path and the notification
  gating are decided above or deferred by name here, never assumed: D-2 pins the release order the
  current control flow would swallow, D-5 the fault cycle *and* the two halves of the non-resolvable
  early return, D-6 the crash and the payload, D-7 the R18 release. Each is a place where the
  obvious implementation drops a release R5 requires. Two bullets above still carry a **Known
  deviation** label. One is *deferred* and carries a test — the suspended backstop. The other, the
  C4 clamp staying raw while its headroom moves, is a deliberate difference rather than a deferral,
  and T10 pins it. A third deviation, the notification re-arm, was deferred pending an ADR and is
  now closed: D-9 and T13 build the fix, and T5's guard turns green with it.
