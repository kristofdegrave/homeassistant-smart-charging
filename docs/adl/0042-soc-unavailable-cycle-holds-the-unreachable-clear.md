# ADR-0042: A state-of-charge-unavailable cycle holds the deadline-unreachable clear rather than firing it (narrows ADR-0024)

Date: 2026-09-14
Status: Accepted

## Context

[ADR-0024](0024-deadline-unreachable-cleared-event.md) added `DeadlineUnreachableCleared` as the
paired clearing edge of the level-signal `DeadlineUnreachableNotified`, so R5's notice is delivered
once **per occasion** rather than once per Manager instance. Its chosen mechanism is deliberately
minimal: the edge check sits on `RequiredCurrentResult.unreachable` itself, *"not on any one
guard"*, on the reasoning that every path to `unreachable=False` is an exit from `Unreachable` and so
every exit clears "for free".

That reasoning holds for two of the three paths ADR-0024 enumerates and fails for a case bundled into
the third. Its exit table's second row reads:

> Car disconnects, or `ev_soc` becomes `None` | `deadline_resolvable = status in CHARGEABLE_STATES
> and ev_soc is not None` … goes false, so `resolve_deadline_urgency` returns its early
> `RequiredCurrentResult(required_a=None, urgent=False, unreachable=False)` without calling the
> engine | `DeadlineUnreachableCleared`

`requirements.md` R5 decides the second half of that row the other way, as a Must acceptance
criterion:

> A control cycle on which state of charge is unavailable ends no occasion: no required current can
> be computed on it, so the system holds the notification state it already had and neither notifies
> nor re-arms.

`UC05`'s state model says the same, and cites ADR-0024 as its reason. So the record and the
requirement it serves disagree, and the shipped code follows the record: `coordinator.py`'s
`_unreachable_edge.resolve(required.unreachable)` sees `False` on such a cycle, fires the clear, and
`notification_manager.py`'s `on_deadline_unreachable_cleared` re-arms `_deadline_unreachable_notified`
mid-occasion.

**The step the row rests on is false.** ADR-0024 never states it outright. Two paragraphs below the
table it records something narrower and literally true — that both of `_run_cycle`'s fault
early-returns *"return before the deadline-urgency block runs"*, so the edge check is not reached on
a fault cycle. Row 2 is consistent with the rest of that record only if a missing `ev_soc` always
produces one of those fault cycles, and it does not: the `ev_soc` fault return is gated
(`coordinator.py`):

```python
if (
    self._mode_handlers[self.active_mode].is_soc_gated
    and status in CHARGEABLE_STATES
    and ev_soc is None
):
```

`is_soc_gated` is **False** on `_OffModeHandler` and `_PowerModeHandler` and True on the three
SOC-gated handlers (`coordinator_cycle.py`), by design: success-criterion 6/S2 forbids `Power`/`Off`
regressing to needing an SOC sensor. So `Manual`+`Off`, `Manual`+`Power`, and `Auto` without the
CapTar capability — whose urgency row escalates to `Power` — reach the deadline block with
`ev_soc is None`, a live occasion, and no fault. R5 is cross-cutting: it applies in every mode, which
is precisely why `ev_soc`'s absence is not a fault outside the SOC-gated gate.

Four forces bear on the fix:

- **R5's criterion is a Must and is not in doubt.** What is in doubt is one row of one table in an
  Accepted record. The requirement, the use-case and the glossary already agree with each other; only
  the ADR dissents, and ADR-0001's immutability rule forbids correcting it in place.
- **The defect is latent today and stops being latent with the next slice.** On the shipped tree the
  same cycle also clears `_urgency_latched` (`coordinator.py`, downstream of
  `deadline_resolvable=False` → `urgent=False`), so urgency ends outright and a later notice is a
  legitimately new occasion — benign by accident. `docs/plans/2026-09-14-r5-pursued-occurrence-design.md`
  preserves the urgency state across such a cycle, as R5 requires, and not the notification state;
  its *Known deviation* bullet records the sequence that then re-notifies for one occasion, and
  defers the fix here rather than letting a spec silently contradict an Accepted ADR.
- **`unreachable=False` carries two different meanings and the detector cannot tell them apart.**
  "The engine computed a required current within the escalated maximum permitted rate" and "no
  required current was computable, so nothing was established" reach the detector as the same value.
  That collapse is what makes ADR-0024's "read the outcome flag alone" mechanism unsafe, and any fix
  has to restore the distinction somewhere.
- **A disconnect and a missing state of charge genuinely differ.** They share one predicate in code
  and nothing else in the domain. A disconnect ends the connected session and with it `UC05`'s own
  precondition — a real exit, which `UC05` states explicitly ("A *disconnect* is different in kind").
  A missing reading is an absence of information about a session that is still running.

**Recording shape.** ADR-0024's decision — publish a paired clear event rather than materialize the
flag, move notify-once to the producer, or reuse `DeadlineUrgencyReverted` — is correct, current and
implemented; its rows 1 and 3, its forward obligation on the missed-deadline hold, and its durable
level-signal-needs-a-clearing-edge rule all stand untouched. Retiring the whole record to correct one
row would mark as historical a decision the shipped code implements, which is the cost
[ADR-0036](0036-step-2-smooths-net-power-only.md) weighed under its own Option C. This project has a
settled alternative for exactly that: the **partial supersede**, adopted as a consequence by
[ADR-0033](0033-captar-step-gains-a-mapping-half.md) and used since by ADR-0035, ADR-0036, ADR-0037
and ADR-0040 — the superseding record replaces the named clause, the predecessor stays `Accepted`,
and the narrowing is recorded in its ADL row. This ADR takes that shape, and says below exactly which
clauses it replaces.

## Considered options

### Option A — Do nothing: keep ADR-0024's row 2 as written

Leave the record and the code alone; treat R5's acceptance criterion and `UC05` as the documents in
need of correction instead.

- Pro: Zero cost, and the behaviour is benign on the shipped tree — the same cycle clears
  `_urgency_latched`, so a later notice really is a new occasion and no user sees a duplicate today.
  It is also the only option that needs no new record at all.
- Con: It resolves a contradiction by overturning a **Must** acceptance criterion in favour of an
  implementation detail of one guard, with no argument for why the user is better served by a second
  notification for one occasion. It also does not survive the next slice: preserving the pursued
  occurrence across a SOC-unavailable cycle is what R5 requires, and once that lands this option
  ships the duplicate notice it currently only risks. And it leaves the false step about
  `is_soc_gated` in the record for the next reader to build on.

### Option B — Make the step true: drop the `is_soc_gated` gate on the `ev_soc` fault return

Fault on a missing `ev_soc` in every mode, so the step row 2 reads into ADR-0024's fault-cycles
paragraph becomes true and the exit table needs no change.

- Pro: The smallest edit to the record — none at all — and it restores the single, simple mental
  model ADR-0024 was written under: one guard decides, and the edge check downstream of it never sees
  a cycle that established nothing. It would also make every fault-cycle hold rule in the coordinator
  apply uniformly instead of per-mode.
- Con: It regresses the very requirement `is_soc_gated` exists to protect — success-criterion 6/S2,
  that `Power` and `Off` must not need an SOC sensor — turning a working `Manual`+`Power` install with
  no SOC integration into one that forces 0 A and logs a fault every cycle. It fixes a notification
  defect by breaking charging, and it does so for a mode that never reads state of charge for any
  other purpose. It also cures the symptom in the wrong layer: the collapse of two meanings into one
  `unreachable=False` survives untouched, waiting for the next guard that short-circuits.

### Option C — Split the non-resolvable early return; the detector holds its prior flag when nothing was established

Keep the detector reading `RequiredCurrentResult.unreachable` for *which* exit occurred, and give it
one further input for *whether this cycle established an outcome at all*. The early return in
`resolve_deadline_urgency` distinguishes its two halves — a disconnect establishes a genuine exit,
state of charge being unavailable establishes nothing — and on the latter the detector holds its
prior flag and reports no clear, exactly as it already does across the two fault early-returns.

- Pro: It restores the distinction at the site that destroyed it, so the rule is stated once, where
  the two halves are still separable. The holding behaviour it needs is not new — ADR-0024 already
  requires precisely it for fault cycles, with the same justification ("a cycle that established
  nothing must not decide anything"), so this generalises an existing rule rather than adding one.
  `docs/plans/2026-09-14-r5-pursued-occurrence-design.md`'s D-5 already splits that same early return
  for the pursued occurrence, so the shape exists and the two halves of one guard stop being split
  differently for two consumers. It leaves `RequiredCurrentResult`'s type and every other consumer of
  it untouched.
- Con: It costs ADR-0024 its "every exit clears for free" property, which was a real simplification:
  from here on, every new path that short-circuits to `unreachable=False` must declare which half it
  is, and one that forgets fails silently — the same trap ADR-0024 named for hold exits, now reaching
  one step further up. The detector also stops being a one-line comparison, and the fact that a cycle
  established nothing has to be threaded from the guard to the fire site.

### Option D — Widen `unreachable` to a tri-state on `RequiredCurrentResult`

Let `unreachable` be `True` / `False` / `None`, where `None` means "not established this cycle", and
have the detector hold on `None`. The distinction then travels inside the value every consumer
already reads.

- Pro: It fixes the collapse in the type itself, so the two meanings can never be conflated again by
  any consumer, present or future — strictly stronger than threading a separate flag, and it needs no
  agreement between the guard and the detector about what was passed alongside. A future consumer of
  `unreachable` gets the distinction whether or not it knew to ask for it.
- Con: It changes a shared dataclass field's type for one consumer's benefit, so every other reader of
  `required.unreachable` — the notified-fire block, `urgent = required.urgent or required.unreachable`
  in `coordinator_cycle.py`, and the tests pinning them — must be revisited and each given a
  three-way answer it has no use for, where today a two-way one is correct. `bool | None` is also a
  shape that reads as "unknown" at every site while meaning "not established this cycle" at exactly
  one, and the truthiness of `None` in the `urgent` expression is a silent-wrong-answer hazard rather
  than a type error. Large blast radius for a distinction only the edge detector consumes.

### Option E — Leave the producer alone; make the consumer ignore the clear

Keep firing the clear on every `unreachable=False`, and have the Notification Manager decline to
re-arm when it has reason to believe the occasion may still be running.

- Pro: Touches one Manager and no coordinator structure, and keeps the producer's single-flag
  simplicity that ADR-0024 chose. The latch is the consumer's state, so scoping it is arguably the
  consumer's business.
- Con: M3 cannot form that belief. Whether an occasion is still running is exactly the determination
  the Coordinator makes and the event exists to communicate; the Manager has no state of charge, no
  charger status and no deadline, so it would have to re-derive the producer's computation from
  adapter reads — the thing ADR-0011's criterion exists to forbid, and which ADR-0024 rejected under
  its own Option C for the same reason. It also makes the event mean "something changed, work out
  whether it counts", which is strictly worse than the level/edge asymmetry ADR-0024 already
  apologises for.

## Decision

**Option C.** `DeadlineUnreachableCleared` fires only on a control cycle that **established** the
deadline is no longer unreachable. `DeadlineUnreachableEdge` gains one further input — whether this
cycle established an outcome about the deadline at all — and on a cycle that did not, it holds its
prior flag unchanged and reports no clear. `resolve_deadline_urgency`'s non-resolvable early return
is where the two halves of `deadline_resolvable` separate: a disconnect (charger status outside
`CHARGEABLE_STATES`) establishes a genuine exit, and state of charge being unavailable establishes
nothing.

Option A is rejected because it settles a contradiction against a Must acceptance criterion in favour
of a guard's incidental shape, and stops being harmless the moment the pursued occurrence is
preserved across such a cycle. Option B is rejected because its route to making ADR-0024's row-2 step
true runs through the requirement `is_soc_gated` was introduced to protect, trading a duplicate
notification for a `Power`/`Off` install that faults every cycle — and leaves the underlying collapse
of two meanings into one flag in place. Between the two options that do restore the distinction, C is
chosen over D because D pays a shared-dataclass type change, and a three-way answer at every reader,
for a distinction exactly one consumer uses — and because `None` flowing into
`urgent = required.urgent or required.unreachable` is a silent wrong answer rather than a loud one. C
accepts D's real advantage as its own stated cost: the guarantee lives in an agreement between the
guard and the detector rather than in the type, so a future short-circuit that forgets to declare its
half fails silently. Option E is rejected because the consumer cannot make the determination without
re-deriving the producer's computation, which ADR-0011's criterion forbids and ADR-0024 already
rejected on that ground.

**This narrows ADR-0024; it does not replace it.** ADR-0024 stays `Accepted` and its text is
untouched, per the partial-supersede shape ADR-0033 adopted. Precisely two clauses are replaced:

1. **Exit table, row 2** — "Car disconnects, or `ev_soc` becomes `None` → `DeadlineUnreachableCleared`"
   — splits in two:

| Exit | Mechanism in code | Fires |
| --- | --- | --- |
| Car disconnects | Charger status leaves `CHARGEABLE_STATES`, so `deadline_resolvable` goes false and `resolve_deadline_urgency` returns early without calling the engine. The connected session, and with it `UC05`'s own precondition, has ended — a real exit | `DeadlineUnreachableCleared` |
| State of charge unavailable while the car stays connected | `ev_soc is None` makes `deadline_resolvable` false through the *other* half of the same predicate. No required current is computable, so the cycle establishes nothing about the deadline | **Nothing.** `DeadlineUnreachableEdge` holds its prior flag; the notification state is held and neither notifies nor re-arms (R5, `UC05`) |

2. **The reach of "Fault cycles hold the prior state"** — the paragraph is right about the two
   returns it names, and row 2 reads as though a cycle with no state of charge is always one of
   them. It is so only when the active mode's handler has
   `is_soc_gated = True`; `Off` and `Power` have it `False`, deliberately (success-criterion 6/S2), so
   such a cycle reaches the edge check with a live occasion and no fault. The *rule* that paragraph
   states is right and is kept — a cycle that established nothing must not decide anything — and this
   ADR restates its reach: **holding is owed to every cycle on which no outcome was established, not
   only to the two that also fault.** Whether the cycle faults is incidental to it.

Everything else in ADR-0024 stands: its Decision and the Option B analysis behind it, exit-table rows
1 and 3, its ADR-0011 table row, the forward obligation it places on whichever slice implements the
missed-deadline hold, and its durable rule that a level signal must be paired with a clearing edge.

The durable rule this ADR adds, generalising the one it narrows:
**an outcome flag may carry an edge only while every path to it means the outcome was computed. A
guard that short-circuits to the flag's default without computing it makes one value mean two
things, and the edge detector must then be told which — it cannot be recovered downstream.**

## Consequences

- **ADR-0024's ADL row** is annotated in this ADR's own PR (per the `adr` work file's one-PR rule), in
  the established narrowing form: its exit table's `ev_soc`-becomes-`None` clause narrowed by this
  ADR. Its Status stays `Accepted`; no other line of that record changes.
- **Implementation follow-up** — a `development` issue against
  `docs/plans/2026-09-14-r5-pursued-occurrence-design.md`, not opened here: split
  `resolve_deadline_urgency`'s non-resolvable early return for the *event* the way D-5 already splits
  it for the pursued occurrence; give `DeadlineUnreachableEdge.resolve` its "established an outcome"
  input and the hold behaviour on it; thread that fact from the guard to the fire site in
  `coordinator.py`. Tests: the detector's hold at the `coordinator_cycle.py` tier, and a coordinator
  cycle with `Manual`+`Power`/`Off`, the car connected and `ev_soc` `None`, firing no clear. That
  slice's T5 lands a strict-xfail test of exactly this, which turns red the moment the fix lands —
  un-xfailing it belongs to the same change.
- **Analysis-doc follow-up** — a `uc`/`requirement` issue, not opened here.
  `docs/analysis/use-cases/UC05-guarantee-ready-by-departure.md` and the
  `DeadlineUnreachableCleared` glossary entry in `docs/analysis/system-overview.md` both state the
  **correct** rule and justify it as "a *fault* cycle", which is true only when the active mode is
  SOC-gated. The durable reason is that the cycle establishes nothing; the wording should say that,
  so the rule does not rest on a premise a `Power`/`Off` reader can falsify.
- **Plan-doc follow-up** — `docs/plans/2026-07-21-deadline-soc-management-design.md` states the clear
  fires on "`deadline_resolvable` going false" without splitting the halves; it needs the split on its
  own side of the edge.
- **Not this ADR's to fix**: `docs/analysis/resolution-rules.md`'s unconditional "a hold never
  outlives one deadline cycle", which the same spec's second known deviation shows a sustained SOC-role
  outage can suspend. That is a requirement-level clause in a different tree with a different
  reviewer, and gets its own `requirement` issue.
- **What becomes harder.** ADR-0024's "every exit clears for free" no longer holds: a future guard
  that short-circuits to `unreachable=False` must declare which half it is, and one that forgets fires
  a spurious clear with nothing to notice it — the trap ADR-0024 named for hold exits, now one step
  further up the cycle. The edge detector also stops being a one-line comparison, and the
  "established an outcome" fact has to travel from the guard to the fire site.
- **What this forecloses.** `RequiredCurrentResult.unreachable` stays a plain `bool` for every
  consumer, so "not established this cycle" is never expressible in that field; a future need for it
  there reopens Option D rather than extending this decision.

**Blast radius.**

1. **Search.**

   ```
   rg -n 'DeadlineUnreachableCleared|DEADLINE_UNREACHABLE_CLEARED|DeadlineUnreachableEdge|_unreachable_edge|deadline_resolvable' custom_components docs tests
   ```

   …plus one site listed explicitly, `docs/analysis/requirements.md`, per the template's
   "short explicitly listed set" allowance. The reason it has to be listed rather than found is
   itself the width argument's limit: R5's acceptance criterion states this decision's own rule in
   domain vocabulary — "ends no occasion … neither notifies nor re-arms" — and carries none of the
   five tokens, because a requirement names no code identifier. No pattern over identifiers reaches
   it, so it is named instead of pretended to.

   The pattern is three name families, because every *other* governed site reaches this decision
   through one of them: the **event** in both its PascalCase and constant spellings (every record,
   producer or consumer stating when the clear fires), the **detector** by class or attribute name
   (every owner of the prior flag, including the two fault-return comments that already hold it), and
   the **guard predicate** `deadline_resolvable` (the site whose two halves this decision separates,
   which names neither of the other two). A pattern on the event name alone drops
   `coordinator_cycle.py`'s early return — the site that causes the defect; a pattern on the guard
   alone drops every record stating the firing rule.

   The search returns **24 files**, one of which is this record: **16** of them in the table below
   and **8** out of scope under 3. With the explicitly listed `requirements.md` the table accounts
   for 17 files, so 25 sites are enumerated in all.

2. **Per-hit verdict** (rows grouped by verdict; every file the search returns appears here or in 3).

| Site | What it does today | Verdict |
| --- | --- | --- |
| `custom_components/smart_charging/coordinator_cycle.py` | `DeadlineUnreachableEdge.resolve` takes `unreachable` alone, and `resolve_deadline_urgency`'s `if not inputs.deadline_resolvable` returns one `unreachable=False` for both halves of the predicate | **Does not conform** — the split and the further input land here |
| `custom_components/smart_charging/coordinator.py` | Fires the clear off `self._unreachable_edge.resolve(required.unreachable)` alone; its two fault early-returns already hold the prior flag, but a non-SOC-gated cycle with `ev_soc is None` reaches neither | **Does not conform** — fires the spurious clear; must thread the "established an outcome" fact to the fire site |
| `docs/analysis/use-cases/UC05-guarantee-ready-by-departure.md`, `docs/analysis/system-overview.md` | State the correct rule — the state is held and the event does not fire — justified as "a *fault* cycle" | **Does not conform in its stated reason only**; the rule itself is what this ADR records |
| `docs/analysis/requirements.md` (the explicitly listed site) | R5's acceptance criterion states the rule this decision aligns to: a cycle on which state of charge is unavailable ends no occasion, and the system neither notifies nor re-arms | Conforms — it is the authority, not a site this decision changes; unlike UC05 and the glossary it gives no reason that `is_soc_gated` can falsify |
| `docs/plans/2026-07-21-deadline-soc-management-design.md` | States the clear fires on the guard paths "(`deadline_resolvable` going false …)", unsplit | **Does not conform** |
| `custom_components/smart_charging/const.py`, `custom_components/smart_charging/__init__.py` | Define the event constant and subscribe before the first refresh | Conform — unaffected; the narrowing is entirely about *when* the producer fires |
| `custom_components/smart_charging/managers/notification_manager.py` | Re-arms `_deadline_unreachable_notified` on every clear received | Conforms — the consumer must trust the producer (ADR-0011); it keeps re-arming on exactly the events it gets |
| `tests/test_coordinator_cycle.py`, `tests/test_coordinator.py`, `tests/managers/test_notification_manager.py` | Pin the `True`→`False` detection, the disconnect and R18 exits firing, a fault cycle not firing, and the consumer's re-arm | Conform — every behaviour they pin survives; none pins the SOC-unavailable case, which the implementation follow-up adds |
| `docs/plans/2026-09-14-r5-pursued-occurrence-design.md`, `docs/plans/2026-09-14-r5-pursued-occurrence.md` | Record the deviation as deferred pending this ADR, and already split the same early return for the pursued occurrence | Conform |
| `docs/plans/2026-07-21-notifications-design.md` | Describes the consumer side and the edge's `True`→`False` trigger, without claiming which guard paths reach it | Conforms |
| `docs/design/project-plan.md`, `docs/design/system-design.md` | Name the event pairing in a service's published-events list | Conform |

3. **Out of scope** (8 files):
   `docs/adl/0042-soc-unavailable-cycle-holds-the-unreachable-clear.md` — this record, which the
   search matches because it states the decision; it governs itself trivially and needs no verdict.
   `docs/adl/0024-deadline-unreachable-cleared-event.md` — the record being narrowed; immutable, stays
   `Accepted`, and keeps stating its decision, with the narrowing recorded in its ADL row.
   `docs/plans/2026-07-21-deadline-soc-management.md` and `docs/plans/2026-07-21-notifications.md` —
   task plans of shipped slices; they keep describing the code as it was built, and the correction
   belongs to the code and to the design docs that state the rule, not to a build record.
   `docs/plans/2026-08-10-run-cycle-named-steps-design.md`,
   `docs/plans/2026-08-10-run-cycle-named-steps.md`,
   `docs/plans/2026-08-10-dashboard-prerequisite-sensors-design.md` and
   `docs/plans/2026-08-10-dashboard-prerequisite-sensors.md` — hit on `deadline_resolvable` only, in
   the unrelated contexts of extracting the named cycle steps and placing a diagnostic sensor; they
   state nothing about when the clear fires and keep doing exactly that.
