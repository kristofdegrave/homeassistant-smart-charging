# ADR-0017: Mode-selection policy Protocol and registry for `profiles/`

Date: 2026-08-03
Status: Accepted

## Context

`profiles/` (its package home fixed by ADR-0002) currently holds a `select_mode(...)` free
function for `Auto` and an implicit `Manual` pass-through, with "which profile is active" threaded
through the Coordinator as a two-way string check (`Manual`/`Auto`). The goal is to rework this
into something a household could compose or tune, rather than choosing between exactly two
hardcoded behaviors, so a future profile could recombine subsets of `Auto`'s coordination features
(e.g. "`Auto`, but never escalate to `Captar`") without a from-scratch new profile module each time.

R16's acceptance criteria and the `profile` glossary entry (`system-overview.md`) describe a
profile's user-visible **behaviour** as three things: which mode is active (mode selection),
whether the active SOC limit steps up or is capped (SOC-limit coordination, R8/R9), and which modes
departure-deadline urgency may escalate to (mode-escalation levers, R5). That is the correct
description of what a household experiences and is unchanged by this decision. What this ADR
decides is a narrower, structural question: which of those three *behaviours* requires its own
object inside a `Profile` class, at the engine-decomposition level — i.e. which of them is a
decision `profiles/` itself makes, versus a decision already made elsewhere that `profiles/` merely
receives as an input. The system-design.md E2 revision worked through exactly that split:

- **The escalation lever and the reserve top-up decline are not separate decisions Profile makes.**
  They are both rows/outcomes of the *one* `Auto` mode-selection table already in
  `resolution-rules.md` (row 2 escalates to `Captar`/`Power` under deadline urgency, R5; row 4
  declines to match while the reserve cap holds, R9's top-up-decline half). A single mode-selection
  function already produces both outcomes as a function of its inputs — no second object is needed
  alongside it.
- **SOC-limit coordination is not part of the Profile's decision at all.** Both halves of it — R8's
  solar step-up and R9's cap-lowering — stay entirely inside the (unchanged) SOC-Target Engine,
  gated by two plain input flags the Coordinator already holds: the active profile, and the
  previous cycle's active mode (a one-cycle-lag pattern system-design.md documents explicitly).
  `profiles/` has no object to own here; SOC-Target already owns it, parameterized by a flag
  Profile has no say in beyond existing.

So the concrete, structural question this ADR decides is: **how should `Manual` and `Auto` be
structured as composable objects around the one decision that is genuinely `profiles/`'s — mode
selection — instead of a free function plus a string check?** This fixes a Protocol/registry shape
under `profiles/` and, implicitly, the seam a future config-flow UI would need to let a household
select, or later define, a profile without rewriting `profiles/`'s internals again. It does not
reopen R8/SOC-Target's implementation, and does not add any end-user-facing profile-authoring UI —
`select.smart_charging_profile` still offers exactly `Manual`/`Auto` (system-overview.md's
"Out of scope: User-defined custom profiles" stands unchanged).

ADR-0012 already established the precedent for this kind of delegation elsewhere in the control
cycle — a `ModeHandler` Protocol plus a lookup, replacing an `if`/`elif` dispatch chain for mode
selection — and explicitly left the door open for "a similarly-shaped SRP/OCP violation elsewhere
in `_run_cycle`" to need its own follow-up decision. This ADR is that decision for profile
selection, one step earlier in the cycle than mode dispatch.

## Considered options

### Option A — A `ModeSelectionPolicy` Protocol, with `Manual`/`Auto` as two registry-keyed instances

Define one `Protocol` (`ModeSelectionPolicy.select(inputs) -> Mode`) that both `Manual` and `Auto`
implement as plain functions or thin stateless objects, registered in a module-level dict inside
`profiles/`, keyed by the same values `select.smart_charging_profile` already stores (`"Manual"`,
`"Auto"` — the existing `PROFILE_MANUAL`/`PROFILE_AUTO` constants, no new key namespace). The
Coordinator already holds the active profile as exactly this string; it looks the policy up and
calls it each cycle instead of branching on it.

- Pro: Directly matches the one-decision scope above — one role, one Protocol. Looking a policy up
  by the profile's own stored key, rather than branching on it inline, is the one seam a future
  config-flow UI needs (a third profile is a third registry entry, not a new `if` branch), and it
  costs nothing today: `Manual`/`Auto` are still two fixed, code-defined policies this release, and
  no new key mapping is introduced beyond the constants that already exist.
- Con: Introduces a `Protocol` and a registry for exactly two current implementations — mild
  ceremony that a two-branch `if`/`elif` doesn't need *yet*. The benefit (a registry seam) only
  pays off once a third profile or a config-driven lookup actually exists.

### Option B — Two independent classes/functions, no shared Protocol (mechanical wrap of the status quo)

Wrap `select_mode()` and the `Manual` pass-through each in their own class with no common interface
beyond "the Coordinator calls whichever one is active," essentially renaming the existing
`if profile == "Auto"` branch to `if isinstance(profile, Auto)` or similar.

- Pro: Minimal change from the shipped code; no new abstraction to learn or test.
- Con: Solves nothing this rework is for — there's still no common shape a third profile could
  implement, and no registry seam for a future config-flow UI. This is the status quo this ADR
  exists to replace, just renamed.

### Option C — A three-role composed `Profile` (mode-selection + SOC-limit-coordination + escalation-lever objects)

Build the `Profile` class with three separately swappable strategy objects, matching the three
user-visible behaviours R16/the glossary describe, one-to-one.

- Pro: Would give the most granular future recombination — a hypothetical profile could swap any
  one of three roles independently — and mirrors the requirements-layer language most directly.
- Con: Two of the three roles don't correspond to anything `profiles/` actually decides, per
  Context above: SOC-limit coordination is already SOC-Target Engine's job, and escalation is
  already a row of the one mode-selection table, not a separate decision a profile makes. Building
  three swappable objects would mean two of them are either empty pass-throughs or duplicate logic
  that must stay in sync with SOC-Target/the mode-selection table — a seam for a distinction that
  doesn't exist at the engine level. Conflating "behaviour a household experiences" with "object a
  class must own" is exactly the mistake Context's split is meant to prevent.

### Option D — Protocol with two module-level instances, no keyed registry

Define the same `ModeSelectionPolicy` Protocol as Option A, but the Coordinator imports and holds
direct references to two fixed instances (`MANUAL_POLICY`, `AUTO_POLICY`) rather than looking them
up in a dict by key.

- Pro: Gets the Protocol's main benefit (a common interface a future profile could implement)
  without the registry's bookkeeping — arguably the leanest option that still names the shared
  interface.
- Con: A direct object reference is not the seam a config-flow UI needs — nothing about a Python
  variable name is data a config-entry can store. Adding a third profile, or driving the choice
  from config, would still mean editing a fixed `if profile == PROFILE_X: policy = X_POLICY` chain
  at the call site, the same problem Option A's registry solves for the cost of one dict.

### Option E — Subclassing (`class Auto(Profile): ...`) instead of a Protocol/registry

`Manual` and `Auto` each subclass a common `Profile` base class that defines `select_mode` as an
abstract method.

- Pro: Familiar OO shape; no separate registry data structure needed, since subclasses are looked
  up via `isinstance`/class identity.
- Con: A subclass is a fixed, code-defined identity — there's no natural place to hang a
  config-entry-stored key for a future config-flow UI (you'd still need some external mapping from
  a stored string to a class), so it doesn't provide the registry seam any better than Option D,
  while adding an inheritance hierarchy for what is, per Option A, a single-method interface.

## Decision

**Option A.** The one-decision scope established in Context makes Option C's three-object
composition build machinery for two roles that don't exist at the engine level — it would actively
misrepresent the architecture this ADR is supposed to encode. Among the remaining one-role shapes,
Option A's registry is the only one that stores profiles by a data-addressable key rather than a
fixed code identity (Options B, D, and E all resolve "which policy" through Python identity —
`isinstance`, a variable reference, or a class — not through data): a third profile becomes a third
registry entry, and a future config-flow UI reads the same key `select.smart_charging_profile`
already stores today, rather than requiring a new mapping or a rewritten dispatch site. This is the
same "user-visible string vs. stable internal key" shape ADR-0013 already establishes for owned
entity `object_id`s, applied here to profile selection instead. The registry costs no more than
Option D's direct references (one dict literal), so there is no reason to accept D's weaker seam
for the same implementation cost.

The registry lives inside `profiles/` itself — the package already named as these two policies'
home by ADR-0002 — rather than in the Coordinator the way ADR-0012's `ModeHandler` dispatch dict
does. That precedent's registry sits in the Coordinator because mode dispatch is threaded through
`CycleContext` alongside other per-cycle Coordinator state; profile selection has no comparable
per-cycle state to thread — the Coordinator only ever needs to pass the active profile's key in and
get a mode back out — so keeping the lookup next to the two policies it selects between, inside
their own package, needs no Coordinator-side scaffolding to do the same job.

`Manual` and `Auto` become the two entries `{PROFILE_MANUAL: ManualPolicy(), PROFILE_AUTO:
AutoPolicy()}`, reusing the existing constants — no new key namespace. The Coordinator holds the
active profile as exactly this key (already true today via `select.smart_charging_profile`) and
looks up the policy each cycle instead of branching on it. `AutoPolicy.select(...)` reproduces
today's `resolution-rules.md` table — including row 2's escalation and row 4's top-up decline as
outcomes of that one function — with the same inputs `profiles/auto.py`'s `select_mode()` already
takes.

## Consequences

- `profiles/` (ADR-0002's package home, unchanged) gains a small `ModeSelectionPolicy` Protocol and
  a registry dict; `Manual`/`Auto` move from a free function + implicit pass-through to two
  registered instances. No behavior change to mode selection itself: `select.smart_charging_profile`
  still offers exactly `Manual`/`Auto`, and `AutoPolicy` reproduces today's mode-selection table
  exactly. R16's SOC-limit-coordination criteria (R8/R9) remain satisfied jointly by SOC-Target
  Engine and the plain input flags described in Context — this decision does not change, and does
  not need to reproduce, that half of R16.
- This extends, rather than reopens, ADR-0006's step-5 sketch of a `profiles/manual.py` module —
  that sketch never shipped; this ADR is the first decision to fix `profiles/`'s actual internal
  shape.
- No config-entry schema change this release — the registry key is an existing constant, not new
  storage. A future config-flow UI (out of scope, per system-overview.md's "User-defined custom
  profiles") would read a key from config-entry data and look it up in the same registry, rather
  than requiring a new storage shape to be invented then.
- An implementation spec and TDD plan for the `profiles/` restructure can follow once this ADR is
  Accepted, building the `ModeSelectionPolicy` Protocol and registry this Decision describes rather
  than a three-role split.
