# TDD plan: R5's pursued occurrence, and the escalated rate's smoothed forecast (#1154)

Derived from [2026-09-14-r5-pursued-occurrence-design.md](2026-09-14-r5-pursued-occurrence-design.md).
Decisions are cited as `D-n`; behaviour is cited to the analysis doc that owns it and never restated
here.

Build order matters: **T1–T3 are the engine** (pure, plain pytest) and leave the coordinator
compiling against the old signature only until T4, so T1–T3 land as one branch's consecutive
commits rather than being merged apart.

Every task is failing test → minimal implementation → green → commit. Each names its ADR-0009 tier.

## T1 — The urgency parameter becomes an occurrence

**Tier:** plain pytest · `tests/engines/test_deadline.py`

**Failing test.** `resolve_required_current(..., pursued_occurrence=None)` on a cycle whose slack
test holds returns `RequiredCurrentResult.pursued_occurrence == deadline_at`, and on a cycle whose
slack test does not hold returns `None`. A second test threads a non-`None` occurrence in across a
cycle the handback clears and asserts `None` comes back out.

**Implementation.** Swap the parameter and add the result field (D-1). The slack test, the handback
and their precedence are untouched — this task changes what the function *carries*, not what it
decides.

**Also assert.** `urgent == (result.pursued_occurrence is not None)` on every branch the existing
`SLACK_KWARGS` cases already cover — D-1's invariant, and the guard against the two drifting.

**Anchors:** `requirements.md` R5; `resolution-rules.md`, the R5 lookup.

## T2 — The hold is read from the occurrence

**Tier:** plain pytest · `tests/engines/test_deadline.py`

**Failing test.** With `pursued_occurrence` set to a datetime at or before `now`, the function
returns `urgent=True`, `unreachable=True` and `required_a is None`, *whatever* `baseline_desired_a`
and `escalated_maximum_permitted_rate_a` say — including values that would otherwise fire the
handback. A companion test with the occurrence strictly after `now` takes the ordinary path.

**Implementation.** The short-circuit, before the two R5 tests (D-2, D-6). No field, no flag.

**Mutation check.** Delete the `unreachable=True` half and confirm the test fails; the notification
edge is the consumer that would otherwise silently stop firing.

**Anchors:** `UC05`, Exception flow and the `Unreachable` state-table row; `resolution-rules.md` R5.

## T3 — The backstop, including the arm that always exists

**Tier:** plain pytest · `tests/engines/test_deadline.py`

**Failing tests**, four:

1. Held, `following_occurrence` strictly after `now` and less than 24 h past the pursued one →
   still held.
2. Held, `following_occurrence` at or before `now` → released (`pursued_occurrence is None`,
   `urgent=False`).
3. Held, `following_occurrence is None`, 24 h elapsed since the pursued occurrence → **released**.
   This is the case R14's "no deadline" makes reachable and the one an implementation without the
   second arm gets wrong.
4. Held, `following_occurrence` later than 24 h past the pursued occurrence, 24 h elapsed →
   released on the 24-hour arm, not the occurrence arm.

**Implementation.** `following_occurrence: datetime | None` as a parameter (D-4), and the release
per the bound `resolution-rules.md` states. Use the same absolute-duration arithmetic
`_absolute_hours_between` already applies — the 24-hour arm spans midnight by construction and so
straddles both DST transitions, which is the exact hazard that function exists for.

**Also add.** A DST case for the 24-hour arm, mirroring the existing spring-forward case for
`required_a`.

**Anchors:** `resolution-rules.md`'s release list; `requirements.md` R5's missed-deadline-hold AC;
`UC05`'s state diagram.

## T4 — The coordinator threads one occurrence

**Tier:** HA harness · `tests/test_coordinator_deadline*.py` (WSL)

**Failing test.** Across three cycles — engage, hold, release — `coordinator._pursued_occurrence`
holds the expected datetime or `None`, and the field `_urgency_latched` no longer exists.

**Implementation.** Rename and retype the field (D-2); assign from
`deadline_urgency.required.pursued_occurrence` at the same line the boolean was assigned, and pass
it in at the same call site. Update `coordinator_cycle.py`'s `urgency_latched` input field to match.

**Do not move the assignment.** It stays below both fault early-returns (D-5). Re-point, don't
rewrite, the existing fault tests, and confirm one of them still asserts a fault cycle holds the
value it entered with.

**Anchors:** `control-cycle.md`'s Trigger section (per-cycle carried state); ADR-0024 for the
fault-cycle reasoning.

## T5 — R9's reserve precondition reads the entering value

**Tier:** HA harness · `tests/test_coordinator_reserve*.py` (WSL)

**Failing test.** One cycle on which the pursued occurrence is in the past entering the cycle but
released by the urgency call: the reserve cap must read *held* for that cycle, and *not held* on the
next. That is the assertion that pins the ordering rather than the value.

**Implementation.** Read the hold from the threaded-in value at the existing precondition site
(D-2).

**Anchors:** `resolution-rules.md`'s R9 six-part reserve condition; `system-design.md` §5.1's
opening note.

## T6 — The following occurrence reaches the engine

**Tier:** HA harness · `tests/test_coordinator_deadline*.py` (WSL)

**Failing test.** The coordinator passes a `following_occurrence` that is the occurrence after the
pursued one, and passes `None` on an installation whose next day resolves to "no deadline" — the
configuration T3's case 3 needs to be reachable end to end.

**Implementation.** Resolve it beside the existing `resolve_next_occurrence` call in
`coordinator_cycle.py` and pass it through (D-4).

**Anchors:** `requirements.md` R14; `resolution-rules.md`'s departure-deadline lookup.

## T7 — The smoothed baseline, and that it can differ from the raw one

**Tier:** HA harness · `tests/test_coordinator_peak*.py` (WSL)

**Failing test.** A cycle where the smoothed and raw baselines *differ* — a single-cycle spike, so
the smoothing window and the debounced raw value disagree — asserts three things at once:

- the escalated maximum permitted rate is the one computed from the smoothed baseline;
- the R3 clamp's result is the one computed from the raw (debounced) baseline;
- `sensor.smart_charging_peak_headroom_a` is the raw-based readout.

One test, because the defect this guards against is the two collapsing back onto one operand, and a
test per consumer would still pass with them collapsed.

**Implementation.** `smoothed_baseline_w` as a named local beside `smoothed_net_w`, carried on
`CycleContext`, read by `_escalated_maximum_permitted_rate_a` only (D-3). Do not derive it from
`ctx.surplus_w`.

**Mutation check.** Point `_escalated_maximum_permitted_rate_a` back at `ctx.baseline_w` and confirm
this test fails.

**Anchors:** `requirements.md` R5 and R10; `system-overview.md`'s `escalated maximum permitted rate`
and `household baseline` entries. D-3 records why no R3 deferral is applied and the `requirement`
issue #1164 filed to have that stated in the source.

## T8 — Integration checkpoint

**Tier:** HA harness · full suite (WSL)

- ADR-0006's call-order spy test passes **unchanged** — no step added, removed or reordered
  (success criterion 5).
- `grep` `custom_components/` for `urgency_latched` and for any boolean named for a hold: none
  (success criterion 1).
- The UC05 end-to-end tests pass on real resolved values, not on an accidental state left by a setup
  cycle — probe the actual `required_a` / `urgent` / pursued-occurrence values in the assertion, do
  not infer from a green run.
- `ruff format --check` and the full suite green.

## Follow-up (not this plan)

- **#1006 closes into this slice.** Its premise — a missed-deadline hold to build — no longer holds:
  T2 makes it a comparison. Close it referencing this plan rather than working it.
- **#1164**, asking R5 or the glossary to state the undeferred smoothed
  operand in one line. Non-blocking; if it ever lands contradicting D-3, the source wins.
