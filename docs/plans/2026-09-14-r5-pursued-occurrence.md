# TDD plan: R5's pursued occurrence, and the escalated rate's smoothed forecast (#1154)

Derived from [2026-09-14-r5-pursued-occurrence-design.md](2026-09-14-r5-pursued-occurrence-design.md).
Decisions are cited as `D-n`; behaviour is cited to the analysis doc that owns it and never restated
here.

Every task is failing test → minimal implementation → green → commit. **Every commit is green**: the
engine's new parameter is additive in T1 and the old boolean is removed in T4, once nothing passes
it (D-8). Each task names its ADR-0009 tier and its exact file.

## T1 — The pursued occurrence, added alongside the boolean

**Tier:** plain pytest · `tests/engines/test_deadline.py`

**Failing test.** `resolve_required_current(..., pursued_occurrence=None)` on a cycle whose slack
test holds returns `RequiredCurrentResult.pursued_occurrence == deadline_at`; on a cycle whose slack
test does not hold, `None`. A second test threads a non-`None` occurrence in across a cycle the
handback clears and asserts `None` comes back out.

**Implementation.** Add `pursued_occurrence: datetime | None` as a parameter and a result field
(D-1). **Keep `urgency_latched` accepted** and derive the effective latch as
`pursued_occurrence is not None or urgency_latched`, so `coordinator_cycle.py:663` keeps working
untouched and the HA suite stays green (D-8). The slack test, the handback and their precedence are
otherwise unchanged.

**Also assert.** `urgent == (result.pursued_occurrence is not None)` on every branch the existing
`SLACK_KWARGS` cases cover — D-1's invariant, and the guard against the two drifting.

**Anchors:** `requirements.md` R5; `resolution-rules.md`, the R5 lookup.

## T2 — The hold, in the order the releases require

**Tier:** plain pytest · `tests/engines/test_deadline.py`

**Failing tests**, four, and the order is the point (D-2):

1. `pursued_occurrence` at or before `now`, energy still needed → `urgent=True`,
   `unreachable=True`, `required_a is None`, *whatever* `baseline_desired_a` and
   `escalated_maximum_permitted_rate_a` say, including values that would fire the handback.
2. **`pursued_occurrence` in the past and SOC at or above the active SOC limit → released.** This is
   the release the naive short-circuit destroys: today it is produced inside the ordinary path
   (`energy_needed_kwh <= 0` → `required_a = 0.0` → handback). A car that finishes charging after a
   missed deadline must not stay pinned until the backstop.
3. **`pursued_occurrence` in the past and `deadline_at is None` → still held.** `resolution-rules.md`
   and R5's AC both say a later occurrence resolving to "no deadline" cannot end a hold, and
   `deadline.py:225-226` returns `urgent=False` on that input today. The hold branch sits **above**
   that early return.
4. The occurrence strictly after `now` → the ordinary path, unchanged.

**Implementation.** The energy computation first, then the hold branch, then the early return
(D-2). No field, no flag.

**Mutation checks**, three — one per ordering the tests exist to pin: move the hold branch above the
energy computation (case 2 must fail); move it below the `deadline_at is None` early return (case 3
must fail); drop `unreachable=True` (the notification edge's only input — case 1 must fail).

**Anchors:** `UC05`'s Exception flow and its `Unreachable` state-table row; `resolution-rules.md`'s
release list; `requirements.md` R5's missed-deadline-hold AC.

## T3 — The backstop, including the arm that always exists

**Tier:** plain pytest · `tests/engines/test_deadline.py`

**Failing tests**, four:

1. Held, `following_occurrence` strictly after `now` and less than 24 h past the pursued one →
   still held.
2. Held, `following_occurrence` at or before `now` → released (`pursued_occurrence is None`,
   `urgent=False`).
3. Held, `following_occurrence is None`, 24 h elapsed since the pursued occurrence → **released**.
   The case R14's "no deadline" makes reachable, and the one an implementation without the second
   arm gets wrong.
4. Held, `following_occurrence` later than 24 h past the pursued occurrence, 24 h elapsed →
   released on the 24-hour arm, not the occurrence arm.

**Implementation.** `following_occurrence: datetime | None` as a parameter (D-4), and the release per
the bound `resolution-rules.md` states. Use `_absolute_hours_between` — the 24-hour arm spans
midnight by construction and so straddles both DST transitions, the exact hazard that function
exists for.

**Also add.** A DST case for the 24-hour arm, mirroring the existing spring-forward case for
`required_a`.

**Anchors:** `resolution-rules.md`'s release list; `requirements.md` R5's missed-deadline-hold AC;
`UC05`'s state diagram.

## T4 — The coordinator threads one occurrence, and the boolean goes

**Tier:** HA harness · `tests/test_coordinator.py`, `tests/test_coordinator_cycle.py`

**Failing test.** Across three cycles — engage, hold, release — `coordinator._pursued_occurrence`
holds the expected datetime or `None`, and `_urgency_latched` no longer exists.

**Implementation.** Rename and retype the field, initialised at `coordinator.py:225`; assign from
`deadline_urgency.required.pursued_occurrence` at the same line the boolean was assigned; pass it in
at the same call site; retype `DeadlineUrgencyInputs.urgency_latched`. **In the same commit**, drop
the `urgency_latched` parameter T1 kept, now that nothing passes it (D-8).

`coordinator_cycle.py:613`'s `not deadline_resolvable` early return returns
`pursued_occurrence=None` (D-5): what reaches that line is a disconnect, which *is* a release
condition — the SOC-unavailable half never gets there.

**Do not move the assignment.** It stays below both fault early-returns (D-5). Re-point, don't
rewrite, the existing fault tests, and keep the one asserting a fault cycle holds the value it
entered with. **Add** the test that pins the two apart: a SOC-unavailable cycle holds the occurrence
(fault, upstream), a disconnected cycle releases it.

**Anchors:** `control-cycle.md`'s Trigger section; ADR-0024 for the fault-cycle reasoning;
`resolution-rules.md`'s release list for the disconnect.

## T5 — The unreachable block survives a hold, and the notice carries a value

**Tier:** HA harness · `tests/test_coordinator.py`, `tests/test_notifications_end_to_end.py`

**Failing test.** A held cycle reaches the unreachable block with `required_a is None` and does not
raise, and the `DeadlineUnreachableNotified` it fires carries the **maximum permitted rate** — the
same value the existing `float('inf')` saturation resolves to, for the same reason (D-6). A second
test asserts the notice fires **once** per occasion while held, and re-arms on release.

**Implementation.** Guard `math.isinf(required.required_a)` against `None`
(`coordinator.py:706-724`) and supply the payload. Without this, T2's own case 1 crashes the cycle
the moment it reaches the coordinator.

**Anchors:** `system-overview.md`'s `escalated maximum permitted rate` entry (the notice fires once
the pursued occurrence lies in the past); ADR-0024 for the re-arm.

## T6 — R18's release, which the engine cannot make

**Tier:** HA harness · `tests/test_coordinator_cycle.py`

**Failing tests**, two, in opposite directions (D-7):

1. Held, the **deadline capability becomes absent** (R18) → released.
2. Held, the deadline **resolves to "no deadline"** (R14, capability still present) → still held.

Both arrive at the engine as `deadline_at is None`, so neither is expressible in a pure-engine test
and the distinction has to live with the caller.

**Implementation.** Apply the R18 release in `coordinator_cycle.py` ahead of the engine call, from
the declared capabilities M1 already reads every cycle.

**Anchors:** `requirements.md` R18; `resolution-rules.md`'s release list; `UC05`'s `Unreachable` row.

## T7 — The following occurrence, relative to the pursued one

**Tier:** HA harness · `tests/test_coordinator_cycle.py`

**Failing tests**, two:

1. While held, `following_occurrence` is the occurrence for the day **after the pursued
   occurrence** — and the test is set up so that occurrence has **already elapsed**, which is the
   case that fails outright if `resolve_next_occurrence`'s output is used instead (D-4). Without
   this, T3's case 2 passes in the engine and is unreachable in production.
2. An installation whose following day resolves to "no deadline" passes `None`, making T3's case 3
   reachable end to end.

**Implementation.** Build it from `resolve_deadline_for` (`coordinator.py:408/418`) for the day after
the pursued occurrence — the same R14 table both existing occurrence resolutions use — and pass it
through.

**Anchors:** `requirements.md` R14; `resolution-rules.md`'s departure-deadline lookup.

## T8 — R9's sixth precondition

**Tier:** plain pytest · `tests/engines/test_soc_target.py`

**Failing test.** `resolve_solar_reserve_active(..., missed_deadline_hold=True)` returns `False` with
all five existing conditions met; `False` for the hold and the five met returns `True`. The five
existing cases stay as they are.

**Implementation.** The sixth parameter on `resolve_solar_reserve_active`
(`engines/soc_target.py:51`) — a pure function, so this is a plain-pytest task, not an HA one.

**Anchors:** `resolution-rules.md`'s R9 six-part reserve condition; `requirements.md` R9.

## T9 — R9 reads the hold as it stood entering the cycle

**Tier:** HA harness · `tests/test_coordinator_cycle.py`, `tests/test_coordinator.py`

**Failing test.** One cycle on which the pursued occurrence is in the past *entering* the cycle but
released by the urgency call: the reserve cap must read *held* for that cycle and *not held* on the
next. That assertion pins the ordering, not the value.

**Implementation.** Wire the sixth argument through `resolve_solar_reserve_gate`
(`coordinator_cycle.py:496`) from the **threaded-in** occurrence, read before the urgency call
updates it (D-2).

**Anchors:** `resolution-rules.md`'s R9 condition; `system-design.md` §5.1's opening note.

## T10 — Both escalated bounds on smoothed readings

**Tier:** HA harness · `tests/test_coordinator.py`, `tests/test_captar_end_to_end.py`

**Failing test.** A cycle where the smoothed and raw readings *differ* — a single-cycle spike, so
the smoothing window and the debounced raw value disagree — asserts, in one test:

- the escalated rate's **peak** bound is computed from the smoothed baseline;
- its **C4 ceiling** bound is computed from the smoothed net reading — R5 puts the whole rate on the
  smoothed reading, and it has two bounds, not one (D-3);
- the R3 clamp and the C4 clamp both still compute from raw;
- `sensor.smart_charging_peak_headroom_a` is still the raw-based readout.

One test, because the defect it guards against is the operands collapsing back onto one, and a test
per consumer would still pass with them collapsed. **Size the spike so a run with only the peak
bound moved still fails** — otherwise the C4 half is untested.

**Implementation.** `smoothed_net_w` carried on `CycleContext`, with
`smoothed_baseline_w = smoothed_net_w - charger_w` beside it, both read by
`_escalated_maximum_permitted_rate_a` only: `peak_headroom_a(baseline_w=smoothed_baseline_w)` and
`ceiling_headroom_a(net_w=smoothed_net_w)`, `charger_w` unchanged since R10 smooths net grid power
alone. Do not derive either from `ctx.surplus_w`.

**Both construction sites.** `CycleContext` is built twice. The second, at `coordinator.py:1382`
(the baseline dry-run), has a docstring warning that a placeholder there is exactly the `#990`
hazard — give the field the same treatment that docstring prescribes for its neighbours, and say in
the test which one is exercised.

**Mutation checks**, two — point the peak bound back at `ctx.baseline_w`, then the C4 bound back at
`ctx.net_w`, and confirm the test fails each time on its own.

**Anchors:** `requirements.md` R5 and R10; `system-overview.md`'s `escalated maximum permitted rate`
and `maximum permitted rate` entries. D-3 records why no R3 deferral is applied, and #1164 asks for
that to be stated in the source.

## T11 — The two ACs that rot silently

**Tier:** HA harness · `tests/test_coordinator.py`

**Failing tests**, two, both from `requirements.md` R5's AC:

1. A hold is **not** preserved across a restart spanning the elapsed moment.
2. A car connecting **after** the deadline elapsed is never held — it never pursued that occurrence.

Both follow from `_pursued_occurrence` starting `None`, which makes them cheap now and the kind of
AC that silently rots later.

**Anchors:** `requirements.md` R5's AC; `UC05`'s State model ("scoped to the current connected
session and never preserved across a restart").

## T12 — Integration checkpoint

**Tier:** HA harness · full suite

- ADR-0006's call-order spy test passes **unchanged** — no step added, removed or reordered.
- `grep` `custom_components/` for `urgency_latched` and for any hold-named boolean: none.
- `grep` `_escalated_maximum_permitted_rate_a`'s body for `ctx.net_w` and `ctx.baseline_w`: neither
  reaches it any more — the raw readings belong to the clamps and the readout.
- The UC05 end-to-end tests pass on **probed** values — assert the actual `required_a`, `urgent` and
  pursued occurrence, never infer from a green run; the accidental-latch-from-a-setup-cycle failure
  is the reason this line is here.
- `ruff format --check` and the full suite green.

## Follow-up (not this plan)

- **#1006 closes into this slice.** Its premise — a missed-deadline hold to build — no longer holds:
  T2 makes it a comparison. Close it referencing this plan rather than working it.
- **#1164**, asking R5 or the glossary to state the undeferred smoothed operand in one line.
  Non-blocking; if it lands contradicting D-3, the source wins.
- **#1141** brings `docs/design/` into line with the smoothed/raw split this slice builds. Not a
  dependency — this spec derives from the analysis layer, which already states it.
