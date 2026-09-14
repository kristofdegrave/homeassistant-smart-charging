# TDD plan: R5's pursued occurrence, and the escalated rate's smoothed forecast (#1154)

Derived from [2026-09-14-r5-pursued-occurrence-design.md](2026-09-14-r5-pursued-occurrence-design.md).
Decisions are cited as `D-n`; behaviour is cited to the analysis doc that owns it and never restated
here.

Every task is failing test → minimal implementation → green → commit, and **every commit is green**
(D-8). Each task names its ADR-0009 tier and its exact file.

## T1 — The pursued occurrence, added alongside the boolean

**Tier:** plain pytest · `tests/engines/test_deadline.py`

**Failing test.** `resolve_required_current(..., pursued_occurrence=None)` on a cycle whose slack
test holds returns `RequiredCurrentResult.pursued_occurrence == deadline_at`; on a cycle whose slack
test does not hold, `None`. A second test threads a non-`None` occurrence in across a cycle the
handback clears and asserts `None` comes back out.

**Implementation.** Add `pursued_occurrence: datetime | None` as a parameter and a result field,
**both defaulting to `None`** — the result field's default is what keeps the other three
construction sites compiling on this commit (D-1, D-8): `coordinator.py:225` and
`coordinator_cycle.py:613` outside the engine, and `engines/deadline.py:226` — the `deadline_at is
None` early return — inside it. Only `engines/deadline.py:257`, the normal return, sets the field. **Keep `urgency_latched` accepted** and derive the effective
latch as `pursued_occurrence is not None or urgency_latched`, so `coordinator_cycle.py:663` keeps
working untouched and the HA suite stays green. The slack test, the handback and their precedence are
otherwise unchanged.

**Also assert**, two things:

- `urgent == (result.pursued_occurrence is not None)` on every branch the existing `SLACK_KWARGS`
  cases cover — the glossary's invariant, and the guard against the two drifting.
- **The occurrence is not re-anchored.** Thread an occurrence in, advance `now` past it, and pass a
  freshly resolved `deadline_at` for the *next* occurrence: the result must still carry the
  **original** occurrence. This is the rule that makes a hold reachable at all — since
  `resolve_next_occurrence` always yields a future occurrence, an implementation of "pursued =
  deadline_at while urgent" makes a hold **impossible**, and every other engine test still passes
  because T2 and T3 inject a past occurrence directly.

**Mutation check.** Re-anchor the occurrence to `deadline_at` every cycle: this test and T2's case 1
must both fail.

**Anchors:** `requirements.md` R5; `resolution-rules.md`, the R5 lookup; `control-cycle.md` step 4
for the preservation rule ("once an occurrence is pursued it stays pursued until released").

## T2 — The hold, in the order the releases require

**Tier:** plain pytest · `tests/engines/test_deadline.py`

**Failing tests**, five, and the order is the point (D-2):

1. `pursued_occurrence` at or before `now`, energy still needed → `urgent=True`,
   `unreachable=True`, `required_a is None`, *whatever* `baseline_desired_a` and
   `escalated_maximum_permitted_rate_a` say, including values that would fire the handback.
2. **`pursued_occurrence` in the past and SOC at or above the active SOC limit → released** (D-2).
3. **`pursued_occurrence` in the past and `deadline_at is None` → still held.** `resolution-rules.md`
   and R5's AC both say a later occurrence resolving to "no deadline" cannot end a hold, and
   `deadline.py:225-226` returns `urgent=False` on that input today. The hold branch sits **above**
   that early return.
4. The occurrence strictly after `now` → the ordinary path, unchanged.
5. **Pursued occurrence in the *future*, `deadline_at is None` → released.** The ordinary "no
   deadline" release (`requirements.md` R5, `resolution-rules.md`), which is *not* the case case 3
   protects. The early return yields it for free through the new field's default — pin it anyway,
   because an implementation that threaded the parameter through that return would keep a future
   occurrence pursued for ever and every other case here would still pass.

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

**Implementation.** Rename and retype the field, initialised at `coordinator.py:213`; assign from
`deadline_urgency.required.pursued_occurrence` at the same line the boolean was assigned; pass it in
at the same call site; retype `DeadlineUrgencyInputs.urgency_latched`. **In the same commit**, drop
the `urgency_latched` parameter T1 kept, now that nothing passes it (D-8).

`coordinator_cycle.py:613`'s `not deadline_resolvable` early return **splits its two halves**
(D-5): disconnected returns `pursued_occurrence=None`, SOC-unavailable returns the occurrence
threaded in.

**Do not move the assignment.** It stays below both fault early-returns (D-5). Re-point, don't
rewrite, the existing fault tests, and keep the one asserting a fault cycle holds the value it
entered with.

**Add the test that pins the split — and set it up in `Power`, not a solar mode.** A SOC-unavailable
cycle must hold the occurrence, a disconnected cycle must release it. `is_soc_gated` is False for
`Off` and `Power` (`coordinator_cycle.py:233,:254`), so those are the modes where a missing SOC
reading reaches this line at all instead of faulting upstream. Written with a solar mode active the
test passes on the fault path and proves nothing.

**Anchors:** `control-cycle.md`'s Trigger section; ADR-0024 for the fault-cycle reasoning;
`resolution-rules.md`'s release list for the disconnect.

## T5 — The unreachable block survives a hold, and the notice carries a value

**Tier:** HA harness · `tests/test_coordinator.py`, `tests/test_notifications_end_to_end.py`

**Failing test.** A held cycle reaches the unreachable block with `required_a is None` and does not
raise, and the `DeadlineUnreachableNotified` it fires carries `self._config.max_current` (D-6). A
second test asserts the notice fires **once** per occasion while held, and re-arms on release.

**A third test, for the deviation** (see *Deliberate deferrals*): a SOC-unavailable cycle mid-hold
on `Power` must **not** re-arm the notice, so no second `DeadlineUnreachableNotified` fires when the
reading returns and the hold is still in effect. It asserts R5's AC directly — *"A control cycle on
which state of charge is unavailable ends no occasion"* — and fails against the shipped behaviour,
where the non-resolvable early return's `unreachable=False` fires `DeadlineUnreachableCleared`.

Land it `@pytest.mark.xfail(strict=True, reason="#1178")`. **Strict is the point**: `xfail_strict`
is not set in `pyproject.toml` and no other `xfail` exists under `tests/`, so a plain `xfail` would
XPASS silently once #1178's fix lands and nothing would signal that the deviation had closed. Strict
turns it red instead, which is what makes this a guard rather than a note.

**Implementation.** Guard `math.isinf(required.required_a)` against `None`
(`coordinator.py:706-724`) and supply the payload. Without this, T2's own case 1 crashes the cycle
the moment it reaches the coordinator.

**Anchors:** `system-overview.md`'s `escalated maximum permitted rate` entry (the notice fires once
the pursued occurrence lies in the past); ADR-0024 for the re-arm.

## T6 — R14's "no deadline" does not release a hold, and R18's absence needs no code

**Tier:** HA harness · `tests/test_coordinator_cycle.py`

**Failing test**, one: held, the deadline **resolves to "no deadline"** (R14) → **still held**. This
is T2 case 3 asserted end to end, and it is the direction the coordinator can get wrong on its own.

**No implementation for R18** — D-7 says why. What this task adds is the assertion: a reload
mid-hold, and the occurrence does not survive it. That is also T11's restart case, covered here
once.

**Anchors:** `requirements.md` R18 and R5's AC on restart; `resolution-rules.md`'s release list;
`UC05`'s `Unreachable` row.

## T7 — The following occurrence, relative to the pursued one

**Tier:** HA harness · `tests/test_coordinator_cycle.py`

**Failing tests**, two:

1. While held, `following_occurrence` is the occurrence for the day **after the pursued
   occurrence** — and the test is set up so that occurrence has **already elapsed**, which is the
   case that fails outright if `resolve_next_occurrence`'s output is used instead (D-4). Without
   this, T3's case 2 passes in the engine and is unreachable in production.
2. An installation whose following day resolves to "no deadline" passes `None`, making T3's case 3
   reachable end to end.

**Implementation.** Build it from `resolve_deadline_for` (defined at `coordinator.py:395`, returned
at `:418`) for the day after the pursued occurrence — the same R14 table both existing occurrence
resolutions use. Carry it as a new `DeadlineUrgencyInputs` field (`coordinator_cycle.py:538-565`)
and forward it at `:645-664`.

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

**Implementation.** Add the sixth argument to `resolve_solar_reserve_gate`
(`coordinator_cycle.py:496`) **and pass it at its call site**, `coordinator.py:410-417` inside
`_resolve_deadline_and_reserve` — the parameter alone leaves the task half-built. It is read from
the **threaded-in** occurrence (D-2); the ordering that needs is free, since `:410` runs well before
the urgency call at `:661`.

**Anchors:** `resolution-rules.md`'s R9 condition; `system-design.md` §5.1's opening note.

## T10 — Both escalated bounds on smoothed readings

**Tier:** HA harness · `tests/test_coordinator.py`, `tests/test_captar_end_to_end.py`,
`tests/test_deadline_soc_management_end_to_end.py` (the UC05 path the split changes)

**Failing test.** A cycle where the smoothed and raw readings *differ* — a single-cycle spike, so
the smoothing window and the debounced raw value disagree — asserts, in one test:

- the escalated rate's **peak** bound is computed from the smoothed baseline;
- its **C4 ceiling** bound is computed from the smoothed net reading (D-3, and #1167);
- the R3 clamp and the C4 clamp both still compute from raw;
- `sensor.smart_charging_peak_headroom_a` is still the raw-based readout.

One test, because the defect it guards against is the operands collapsing back onto one, and a test
per consumer would still pass with them collapsed. **Size the spike so a run with only the peak
bound moved still fails** — otherwise the C4 half is untested.

**The fixture must declare the CapTar capability and must not be `Power` with the R17 opt-out set.**
The peak bound is appended only when `_peak_clamp_would_run()` (`coordinator.py:1233`), so on any
other fixture that bound is never composed, the peak assertion is vacuous, and the sizing
instruction above has no reachable state to describe. **Add a second, smaller case** on a
CapTar-absent fixture: the rate is C1/C4 only, and its C4 bound is still smoothed.

**Implementation.** **One** new `CycleContext` field, `smoothed_net_w` — not two.
`_escalated_maximum_permitted_rate_a` takes only `ctx` and `peak_operand_kw`, so it derives the peak
operand itself: `peak_headroom_a(baseline_w=ctx.smoothed_net_w - ctx.charger_w)` and
`ceiling_headroom_a(net_w=ctx.smoothed_net_w)`, with `charger_w` unchanged since R10 smooths net
grid power alone. Both reads are the helper's and no other caller's. Do not derive either from
`ctx.surplus_w`, which is the peak operand's exact negation (D-3).

**Both construction sites, and no default.** `CycleContext` is built twice in
`custom_components/`: `coordinator.py:579` and `:1382`, the baseline dry-run, whose docstring warns
that a placeholder there is the `#990` hazard. `smoothed_net_w` is added as a **required** field —
no default — for the reason that docstring gives: a permissive default lets a forgotten construction
site fail open silently, and this field decides a forecast. That makes the test constructions in
`tests/test_coordinator_cycle.py` part of this commit; move them here rather than in a follow-up,
and say in the test which of the two production sites is exercised.

The dry-run site passes `0.0`, with the comment its `baseline_w=0.0` neighbour already carries: a
placeholder is sound there **only** because that ctx never reaches `_apply_peak_clamp` or
`_escalated_maximum_permitted_rate_a`. State the guarantee at the site rather than leaving the
reader to infer it from the neighbour.

**Mutation checks**, two — point the peak bound back at `ctx.baseline_w`, then the C4 bound back at
`ctx.net_w`, and confirm the test fails each time on its own.

**Anchors:** `requirements.md` R5 and R10; `system-overview.md`'s `escalated maximum permitted rate`
and `maximum permitted rate` entries. **ADR-0012** governs the `CycleContext` field. D-3 records why
no R3 deferral is applied (#1164) and why both bounds move rather than one (#1167) — both are asks
against the analysis layer, and if either lands the other way, the source wins.

## T11 — The two ACs that rot silently

**Tier:** HA harness · `tests/test_coordinator.py`

**Failing test**: a car connecting **after** the deadline elapsed is never held — it never pursued
that occurrence. It follows from `_pursued_occurrence` starting `None`, which makes it cheap now and
the kind of AC that silently rots later.

The sibling AC — a hold not preserved across a restart spanning the elapsed moment — is asserted in
T6, where it does double duty as the evidence for D-7.

**Anchors:** `requirements.md` R5's AC; `UC05`'s State model ("scoped to the current connected
session and never preserved across a restart").

## T12 — Integration checkpoint

**Tier:** HA harness · full suite

- **ADR-0006**'s call-order spy test passes **unchanged** — no step added, removed or reordered.
- `grep` `custom_components/` for `urgency_latched`: none. (E3's `missed_deadline_hold` parameter
  is expected and is not urgency state — success criterion 1 says why.)
- `grep` `_escalated_maximum_permitted_rate_a`'s body for `ctx.net_w` and `ctx.baseline_w`: neither
  reaches it any more — the raw readings belong to the clamps and the readout.
- **The prose this slice falsifies is updated, not just the code.** `engines/deadline.py:121-123`
  and `:196-223` (the `urgency_latched` explanation, and "a missed-deadline hold clearing (issue
  #1006)"), `deadline.py:140-142` (the result field comments — `required_a`'s "None when no
  deadline is resolved" is false while held, and `urgent`'s "a latch not yet cleared"),
  `coordinator.py:731-738` (the latch comment block, which also states the fault-cycle rule the new
  field inherits), `coordinator_cycle.py:62` (`net_w`'s "coordinator.py's separate `smoothed_net_w`"
  — no longer separate), `const.py:22-26` (which enumerates one saturated-and-capped case and gains
  a second at T5), and `project-plan.md`'s Phase-2 status row (`:101`) alongside its E4 and M1 status
  lines, all describe a model this slice replaces. A grep for `urgency_latched` catches none of them,
  which is why this bullet is a list and not a grep.
- The UC05 end-to-end tests pass on **probed** values — assert the actual `required_a`, `urgent` and
  pursued occurrence, never infer from a green run; the accidental-latch-from-a-setup-cycle failure
  is the reason this line is here.
- `ruff format --check` and the full suite green.

## Follow-up (not this plan)

- **#1006 closes into this slice.** Its premise — a missed-deadline hold to build — no longer holds:
  T2 makes it a comparison. Close it referencing this plan rather than working it.
- **#1164**, asking R5 or the glossary to state the undeferred smoothed operand in one line, and
  **#1167**, asking it to state which reading each of the escalated rate's bounds is fitted to. Both
  non-blocking; if either lands contradicting D-3, the source wins.
- **#1141** brings `docs/design/` into line with the smoothed/raw split this slice builds. Not a
  dependency — this spec derives from the analysis layer, which already states it.
