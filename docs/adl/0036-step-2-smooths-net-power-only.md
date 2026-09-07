# ADR-0036: The control cycle's step 2 smooths net power only — which readings are smoothed is an R10 matter

Date: 2026-09-07
Status: Accepted

## Context

[ADR-0006](0006-coordinator-and-data-flow.md) fixes the control cycle's implementation shape:
one `DataUpdateCoordinator` subclass running ten named steps, with the R3 peak-protection
clamp and the C4 grid-supply-ceiling clamp as two distinct methods. Two places in that record
state that the cycle smooths two readings. Its second Context force opens "R10 smooths net and
solar power for the mode's set-point decision", and step 2 of the Decision's ten-step order
reads "Smooth net power and solar power per R10 (rolling mean over N cycles)."

Nothing consumes a smoothed solar reading, and nothing is designed to. [Solar
surplus](../analysis/system-overview.md#ubiquitous-language) is `charger_w − net_w`
(`entity-catalog.md` states this for both operands, and explicitly records `solar_power` as
*not* an operand of it), so the one derived quantity the solar modes set their rate from
already inherits its smoothing from net grid power alone. No mode module reads the
`solar_power` role at all today; it is a production reading, surfaced for display. A rolling
window over it would therefore be a second window's worth of per-cycle state, threaded through
the cycle by the Coordinator, feeding no charging-rate decision. The shipped implementation
reflects that: `engines/signal_conditioning.py` exposes `smooth_net_power` and nothing else,
and `const.py`'s `ROLE_SOLAR_POWER` comment records the role as unsmoothed.

So ADR-0006's step 2 overstates what the cycle does — and, given the surplus formula, what it
ever needed to do. Correcting the analysis layer to match (R10's "What" and its first
acceptance criterion, `control-cycle.md`'s step 2 and its diagram node) is ordinary
requirements work. But ADR-0006's Consequences contain a bar that names this class of change
by name:

> `coordinator.py` is the one place the ten-step order lives in code; a change to step order
> or to which reading (raw/smoothed) a step consumes is a change to this ADR (a new ADR
> superseding this one), not a silent refactor.

Editing R10 alone would leave an Accepted ADR asserting a step the requirements and the code
both contradict, against a rule that record set for itself.
[ADR-0001](0001-use-architecture-decision-records.md)'s immutability rule forbids correcting
ADR-0006's text in place.

Two distinct facts are bundled inside that one clause, and telling them apart is what sizes
this decision:

- **The composition of the smoothed set** — which raw readings get a rolling window at step 2
  at all. This is a rule about which values the domain wants averaged before a rate decision,
  which is what R10 states and what `CLAUDE.md`'s domain/business-rule carve-out ("a formula,
  a precedence order, which values are surfaced") places in `requirements.md` rather than an
  ADR. Adding or removing a window changes one engine call and one piece of coordinator-held
  state; it does not move a boundary.
- **The raw-versus-smoothed pairing per consuming step** — that steps 7 and 8 clamp on raw
  readings while step 6 dispatches smoothed ones, and that the raw net-power reading is kept
  in scope alongside the smoothed one for the whole cycle. This is ADR-0006's *other* Context
  force, and it is a cross-module invariant: it is what stops the clamps silently operating on
  lagged data, and switching it would reach `coordinator.py`, the engine, and the tests that
  pin it. Nothing about that is a domain rule.

`CLAUDE.md` also states what to do when a still-Accepted ADR's forward-looking bar reaches
into a category one of its carve-outs now excludes: the carve-out governs going forward, and
the ADR "should be superseded to say so, rather than the conflict being left implicit". That
is the situation here, for the first of the two facts only.

The question this ADR answers is therefore: **what does step 2 smooth, and which layer owns
that answer from here?**

## Considered options

### Option A — Correct the analysis layer only, with no ADR

Reword R10 and `control-cycle.md` to say net power alone, and leave ADR-0006 untouched.

- Pro: Zero record cost, and nothing ships differently either way — the code already smooths
  net only, so the discrepancy is arguably a wording slip in a record whose actual decision
  (Option B, the ten steps, the two clamps) is entirely unaffected.
- Con: It leaves an `Accepted` ADR contradicted by both the requirements and the code, with
  nothing marking which is current — the precise outcome ADR-0006's own Consequences bar
  exists to prevent, and a reader arriving at step 2 has no signal that it is stale. It also
  leaves the bar itself still claiming ADR jurisdiction over the smoothed set, so the next
  reading that gains or loses a window faces this same question from scratch.

### Option B — Implement solar smoothing, so ADR-0006 becomes true

Add a second rolling window for `solar_power` in `signal_conditioning.py`, threaded by the
Coordinator like the net window, matching step 2 as written.

- Pro: No record changes at all, ADR-0006 becomes literally accurate, and R10's first
  acceptance criterion is satisfied verbatim for both readings. A future consumer wanting a
  smoothed solar reading would find one already there.
- Con: It pays real, permanent cost — a second window of cross-cycle state, a second engine
  call, month-rollover and restart handling for it, and test coverage — to produce a value no
  charging-rate decision reads, and none is designed to, since solar surplus already inherits
  net's smoothing. Not one set-point would change. It makes a sentence true by building the
  dead computation the sentence describes, which is the wrong direction of fit between a
  record and the system.

### Option C — Supersede ADR-0006 in full

Write a replacement coordinator-and-data-flow ADR restating all ten steps with step 2
corrected, and set ADR-0006's Status to `Superseded by ADR-0036`.

- Pro: The only shape [ADR-0001](0001-use-architecture-decision-records.md)'s status
  vocabulary actually has, so it needs no convention that isn't already written down, and it
  leaves exactly one current record of the cycle with no split reading.
- Con: Grossly disproportionate to a two-word correction, and destructive: it would mark as
  historical a decision the shipped code implements literally, forcing either verbatim
  restatement of nine untouched steps, three considered options and the Option A
  clamp-merging failure mode, or their survival only inside a `Superseded` record.
  ADR-0012, ADR-0018 and ADR-0023 all build on ADR-0006 as current and cite its step order;
  each would then point at a retired record.

### Option D — Narrow the whole raw/smoothed clause out of ADR-0006

Keep ADR-0006 Accepted but read its bar as covering step *order* only, making every
raw-versus-smoothed question — including which reading the clamps consume — an R10 matter.

- Pro: One simple, memorable bar (order is architectural, readings are domain) with a single
  home for every smoothing question, and no need to draw the finer distinction this ADR's
  Context draws.
- Con: It gives away the invariant ADR-0006 exists to protect. That record's second Context
  force is precisely that both the raw and the smoothed net-power value must stay in scope
  through the whole cycle "or the clamps silently start operating on smoothed (lagged) data" —
  a structural guarantee about which module reads which value, whose failure mode is a safety
  clamp reacting a window late. Under this option a requirements edit alone could move steps 7
  and 8 onto smoothed readings, a change reaching `coordinator.py`, the engine and the tests
  that pin it, with no ADR anywhere.

### Option E — Correct step 2's reading list and narrow only the smoothed-set half of the bar

Record that step 2 smooths net power alone, and narrow ADR-0006's forward-looking bar so that
*which raw readings have a smoothing window* is an R10 question, while *which of raw or
smoothed a given step consumes* — and step order — remain ADR-0006's, unchanged.

- Pro: Fixes the contradiction at its actual size. It follows the analysis layer and the code
  rather than bending either, keeps every structural claim ADR-0006 makes in force under
  ADR-0006, and applies `CLAUDE.md`'s domain/business-rule carve-out exactly where that
  carve-out points — with the supersede the same passage requires when a live bar reaches into
  an excluded category.
- Con: It leaves ADR-0006's step 2 readable-but-wrong on the page, reachable by anyone who
  opens the file directly rather than arriving via the index, and it splits one sentence of
  the bar into two clauses a future contributor has to tell apart before knowing which layer
  owns their change — a finer boundary than Option D's, and one that has to be applied rather
  than pattern-matched.

## Decision

**Option E.** Step 2 of ADR-0006's cycle smooths **net power** per R10; `solar_power` is read
raw each cycle and has no smoothing window. Which raw readings have a smoothing window is
settled by R10 in `requirements.md` from here on, not by an ADR.

Option A's cost is the one thing an ADR set cannot absorb — an `Accepted` record contradicted
in silence, against its own explicit instruction — and its saving is only the writing of this
page. Option B removes the contradiction by building the computation nobody asked for: its Pro
is real but buys nothing, since solar surplus already carries net's smoothing into every solar
set-point, so the second window would run forever with no reader. Option C is correctly shaped
in ADR-0001's vocabulary and wrong in proportion; ADR-0006 is current, implemented and depended
on by three later ADRs, and retiring it whole to fix two words would leave its actual decision
recorded only as history — the same reasoning [ADR-0033](0033-captar-step-gains-a-mapping-half.md)
applied when it narrowed one clause of ADR-0027 instead of replacing it.

Option D is the close call, since its simpler bar is genuinely easier to remember than the
line drawn below. It is rejected on its Con: ADR-0006's two Context forces are not the same
kind of fact, and folding them together would surrender the one that is structural. The
clamps-consume-raw pairing is a contract between the coordinator, the engine and the clamp
methods; the composition of the smoothed set is a statement about which values the domain
wants averaged. Only the second fits `CLAUDE.md`'s carve-out, and only the second is narrowed
here. Option E's own Con — a finer boundary to apply — is accepted, and the boundary is stated
directly rather than left to inference:

- **R10's** (a requirements change, no ADR): whether a given raw reading has a smoothing
  window at all, and the window's size.
- **ADR-0006's** (still a superseding ADR): the ten steps and their order; that steps 7 and 8
  clamp on raw readings and step 6 dispatches smoothed ones; that the raw net-power reading is
  kept in scope alongside the smoothed one for the whole cycle; and, once a reading has both a
  raw and a smoothed form, which of the two any given step consumes.

Concretely: adding a smoothing window for `solar_power` later — should some future mode
actually need one — would be an R10 change under this decision. Routing a *step* onto the
smoothed form rather than the raw one, for any reading that has both, would still be an
ADR-0006 change.

**This narrows ADR-0006's step 2 and one clause of its Consequences; it supersedes neither
ADR-0006 nor anything else in it.** ADR-0006 keeps Status `Accepted` and its body is not
edited, per this project's precedent for a narrowing that leaves the rest of a record standing
(the shape ADR-0033 used against ADR-0027 and
[ADR-0035](0035-charger-status-unmatched-state-defaults-to-disconnected.md) used against
ADR-0003/0007/0009/0034). The rest of ADR-0006's step 2 is untouched: charger power is still
used raw and is still not an operand of solar surplus via the smoothed channel, and the raw
net-power reading is still kept alongside the smoothed one so a breach cannot hide behind the
smoothing window.

## Consequences

- **ADR-0006's step 2 and its second Context force are narrowed; everything else in it stands.**
  ADR-0006 keeps Status `Accepted` and its body is not edited. From here, step 2's "Smooth net
  power and solar power per R10" reads as "Smooth net power per R10", and the Context force's
  "R10 smooths net and solar power for the mode's set-point decision" reads the same narrowed
  way. Step order, the step 7/8 clamp split, the raw-reading plumbing, the pure mode-module
  rule and every other Consequence of ADR-0006 are unaffected.
- **ADR-0006's forward-looking bar keeps its step-order half and its per-step raw/smoothed
  half, and loses only its smoothed-set half.** A change to step order, or to which of raw or
  smoothed an existing step consumes, is still a change to ADR-0006 requiring a superseding
  ADR. A change to which readings have a smoothing window is a change to R10, with the
  ordinary requirements review and doc pass — no ADR.
- **`docs/adl/README.md` gains a row for this ADR and annotates the *title* cell of ADR-0006's
  row to point at it**, in this same change, leaving that row's Status cell verbatim
  `Accepted`. That pointer only reaches a reader who arrives via the index; ADR-0007,
  ADR-0008, ADR-0012, ADR-0018 and ADR-0023 all link straight to ADR-0006's file and will land
  on an unmarked step 2. That is an accepted residual cost — none of those five restates the
  smoothed-reading pairing, each citing ADR-0006 for step order, the coordinator's read phase
  or the clamp split instead, all of which this decision leaves intact.
- **The analysis layer must state net-only smoothing in every place it currently names two
  readings.** R10's "What" and its first acceptance criterion ("Net grid power and solar power
  are each sampled once per control cycle…"); `control-cycle.md`'s step 2 narrative, its
  `Smooth net_w & solar_w` diagram node, its opening summary line and its R10
  requirements-satisfied entry. `entity-catalog.md`'s `solar_power` row cites R10 for the
  production reading and already records the role as not an operand of solar surplus; it must
  not be readable as implying a smoothing window. R10's peak-protection exemption criterion is
  unchanged — that criterion is the per-step pairing, which stays as it is.
- **`docs/design/system-design.md` carries the same two-reading claim twice** — its
  Coordinator/Signal-Conditioning sequence line (`smooth net/solar (R10) + resolve voltage
  (NF4)`) and the surrounding Signal-Conditioning engine description — and both need the same
  correction. The engine's classification as *stateful* is unchanged: one window is still
  cross-cycle state the Coordinator owns and threads in.
- **No product-code change follows from this decision.** `engines/signal_conditioning.py`
  already implements net-only smoothing and `coordinator.py`/`coordinator_cycle.py` already
  thread exactly one window. Two comments describe the state as provisional rather than
  decided and should be re-worded to match: the engine module's docstring, which says
  `solar_power` smoothing is "deferred to whichever later slice first consumes that role", and
  `const.py`'s `ROLE_SOLAR_POWER` comment, which says the role "is NOT yet smoothed" pending a
  real-consumer decision. Both are now settled, not pending — the role is unsmoothed, and
  giving it a window would be an R10 change. No test asserts solar smoothing, so none inverts.
- **What becomes harder.** ADR-0006's ten-step list can no longer be read as a complete
  statement of which readings are smoothed — R10 is the authority for that set, and the two
  documents have to be read together. A contributor changing anything about smoothing must
  first classify their change against the boundary in the Decision above rather than assuming
  a single owner. That is the price of Option E over Option D, accepted deliberately.
- **What becomes easier, and what this does not open.** A reading gaining or losing a
  smoothing window is now ordinary requirements work with a doc pass, at the cost of one R10
  edit rather than an ADR cycle. This establishes nothing beyond that: it does not make the
  cycle's *step* definitions generally amendable from `requirements.md`, and in particular the
  clamps-consume-raw guarantee — the failure mode ADR-0006 named — is untouched and still
  requires a superseding ADR to change.
