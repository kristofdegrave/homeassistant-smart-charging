# ADR-0017: Profile as a composed mode-selection policy

Date: 2026-08-03
Status: Proposed

## Context

`profiles/` (its package home fixed by ADR-0002) currently holds a `select_mode(...)` free
function for `Auto` (`profiles/auto.py`, shipped by PR #310/epic #306) and an implicit `Manual`
pass-through, with "which profile is active" threaded through the Coordinator as a two-way
string check (`Manual`/`Auto`). Issue #308 asked to rework this into something a household could
compose or tune, rather than choosing between exactly two hardcoded behaviors, so a future profile
could recombine subsets of `Auto`'s coordination features (e.g. "`Auto`, but never escalate to
`Captar`") without a from-scratch new profile module each time.

The brainstorm behind #308 initially hypothesized three independently pluggable roles a profile
could compose: mode selection, SOC-limit coordination (R8's step-up, R9's reserve cap), and
mode-escalation levers (R5). The requirements/glossary revision (PR #473) and the subsequent
system-design.md E2 revision (PR #481) worked through where each of those actually lives at the
engine-decomposition level, with one result that narrows this ADR's scope:

- **R5's escalation and R9's top-up decline are not separate roles.** They are both rows/outcomes
  of the *one* `Auto` mode-selection table already in `resolution-rules.md` (row 2 escalates to
  `Captar`/`Power`; row 4 declines to match while the reserve cap holds). A profile does not need a
  distinct "escalation-lever" object or "reserve-coordination" object alongside its mode-selection
  object — the existing single decision already produces both outcomes as a function of its
  inputs.
- **R8's solar step-up is not part of the Profile's decision at all.** It stays entirely inside the
  (unchanged) SOC-Target Engine, gated by two plain input flags the Coordinator already holds — the
  active profile, and the previous cycle's active mode (a one-cycle-lag pattern system-design.md
  now documents explicitly). There is no "SOC-limit coordination" role for a profile class to own;
  SOC-Target already owns it, parameterized by a flag Profile has no say in beyond existing.

So the concrete, structural question this ADR must decide is narrower than #308's original
three-role brainstorm: **how should `Manual` and `Auto` be structured as composable objects around
the one role that is genuinely Profile's — mode selection — instead of a free function plus a
string check?** This is exactly the kind of choice ADRs are for: it fixes a class/protocol shape
under `profiles/` and, implicitly, the seam a future config-flow UI would need to let a household
select or (later) define a profile without rewriting `profiles/`'s internals again.

This decision does not reopen R8/SOC-Target's implementation, and does not add any end-user-facing
profile-authoring UI — `select.smart_charging_profile` still offers exactly `Manual`/`Auto`
(system-overview.md's "Out of scope: User-defined custom profiles" stands unchanged).

## Considered options

### Option A — A `ModeSelectionPolicy` Protocol, with `Manual`/`Auto` as two registry-keyed instances

Define one `Protocol` (`ModeSelectionPolicy.select(inputs) -> Mode`) that both `Manual` and `Auto`
implement as plain functions or thin stateless objects, registered in a module-level dict keyed by
a stable string (`"manual"`, `"auto_default"`) even though nothing reads that key from a
config-entry yet. The Coordinator holds the active profile's *key* (from
`select.smart_charging_profile`, unchanged) and looks up the policy to call each cycle.

- Pro: Directly matches what the system-design revision settled on — one role, one Protocol.
  Registering by string key rather than importing a fixed name is the one seam a future
  config-flow UI needs (store a key in config-entry data, not a Python object reference), and it
  costs nothing today: `Manual`/`Auto` are still two fixed, code-defined policies this release.
- Con: Introduces a `Protocol` and a registry for exactly two current implementations — mild
  ceremony that a two-branch `if`/`elif` doesn't need *yet*. The benefit (a registry seam) only
  pays off once a third profile or a config-driven lookup actually exists.

### Option B — Two independent classes/functions, no shared Protocol (mechanical wrap of the status quo)

Wrap `select_mode()` and the `Manual` pass-through each in their own class with no common interface
beyond "the Coordinator calls whichever one is active," essentially renaming the existing
`if profile == "Auto"` branch to `if isinstance(profile, Auto)` or similar.

- Pro: Minimal change from the shipped PR #310 code; no new abstraction to learn or test.
- Con: Solves nothing the issue asked for — there's still no common shape a third profile could
  implement, and no registry seam for a future config-flow UI. This is the status quo issue #308
  was opened to replace, just renamed.

### Option C — A three-role composed `Profile` (mode-selection + SOC-limit-coordination +
escalation-lever objects), per the original #308 brainstorm

Build the `Profile` class with three separately swappable strategy objects, as originally
hypothesized before the system-design pass.

- Pro: Would have given the most granular future recombination — a hypothetical profile could
  swap any one of three roles independently.
- Con: Two of the three roles don't correspond to anything Profile actually decides.
  SOC-limit coordination is already SOC-Target Engine's job (unchanged, R8/R9), and escalation is
  already a row of the one mode-selection table, not a separate decision a profile makes. Building
  three swappable objects would mean two of them are either empty pass-throughs or duplicate logic
  that must stay in sync with SOC-Target/the mode-selection table — a seam for a distinction that
  doesn't exist at the engine level, contradicting system-design.md's own conclusion (PR #481).

### Option D — Subclassing (`class Auto(Profile): ...`) instead of a Protocol/registry

`Manual` and `Auto` each subclass a common `Profile` base class that defines `select_mode` as an
abstract method.

- Pro: Familiar OO shape; no separate registry data structure needed, since subclasses are looked
  up via `isinstance`/class identity.
- Con: A subclass is a fixed, code-defined identity — there's no natural place to hang a
  config-entry-stored key for a future config-flow UI (you'd still need some external mapping from
  a stored string to a class), so it doesn't provide the registry seam any better than Option B,
  while adding an inheritance hierarchy for what is, per Option A, a single-method interface.

## Decision

**Option A.** The narrower, one-role scope the system-design pass (PR #481) established makes
Option C's three-object composition build machinery for two roles that don't exist at the engine
level — it would actively misrepresent the architecture this ADR is supposed to encode. Between the
two viable one-role shapes, Option A's Protocol + string-keyed registry costs almost nothing over
Option B's plain wrap (it is the same amount of code, organized around an interface instead of an
ad hoc pair of classes) while directly providing the one thing #308 asked for: a seam a third
profile, or a future config-flow UI, can extend without rewriting `profiles/`'s internals — which
neither Option B nor Option D provide as cleanly, since neither uses a data-addressable key.

`Manual` and `Auto` become the two entries `{"manual": ManualPolicy(), "auto_default":
AutoPolicy()}`; the Coordinator holds the active profile as a key (already true today via
`select.smart_charging_profile`) and looks up the policy each cycle. `AutoPolicy.select(...)`
reproduces today's `resolution-rules.md` table (including row 2's escalation and row 4's top-up
decline as outcomes of that one function) with the same inputs `profiles/auto.py` already takes.

## Consequences

- `profiles/` (ADR-0002's package home, unchanged) gains a small `ModeSelectionPolicy` Protocol and
  a registry dict; `Manual`/`Auto` move from a free function + implicit pass-through to two
  registered instances. No behavior change: `select.smart_charging_profile` still offers exactly
  `Manual`/`Auto`, and both reproduce today's acceptance criteria (R16) exactly.
- No config-entry schema change this release — the registry key exists in code only. A future
  config-flow UI (out of scope, per system-overview.md's "User-defined custom profiles") would read
  a key from config-entry data and look it up in the same registry, rather than requiring a new
  storage shape to be invented then.
- Closes the narrower question issue #477 opened; #308's original three-role framing is now
  answered by this ADR plus the system-design.md E2 revision (PR #481) together — a future reader
  of #308's history should follow both, not expect three roles to appear under `profiles/`.
- Issue #478 (implementation spec) is unblocked once this ADR is Accepted — it should follow this
  ADR's Option A shape (the `ModeSelectionPolicy` Protocol + registry, not a three-role split) when
  writing the TDD plan for the `profiles/` restructure.
