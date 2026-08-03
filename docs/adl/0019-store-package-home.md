# ADR-0019: Package home for the RA3 Config/State Store

Date: 2026-08-03
Status: Accepted

## Context

ADR-0002 fixed the package layout for `custom_components/smart_charging/`: `adapters/`,
`modes/`, `profiles/` as subpackages, platform files and `entity.py` at the package root, and
`coordinator.py` driving the control cycle. ADR-0010 later added `engines/` for the eight
cross-cutting engines, and ADR-0015 added `managers/` for the Managers beyond the Coordinator.
None of the three names a home for the RA3 Config/State Store: `docs/design/system-design.md`
places it as a third member of the Resource-Access layer alongside the hardware adapters (V1)
and Notification Resource Access (V11), and ADR-0018 decided the Store's shape (reads
config-entry data/options and owned-entity state; the Coordinator reads through it, a Manager
can write through it) but explicitly left its package home open, naming this as the same
question ADR-0010 and ADR-0015 each needed their own ADR to answer.

`adapters/` today holds fourteen `Adapter`-protocol hardware roles (`base.py`'s
`read()`/`write(value)` shape, `@runtime_checkable`) plus `adapters/notify.py`'s `NotifyAdapter` —
the Notification Resource Access (V11) class. `NotifyAdapter` *does* implement that same
`read()`/`write(value)` shape — its own docstring frames this as "a one-line typing widening, not
a structural change": `write` takes a `NotificationRequest` dataclass rather than the
`float | str | bool | time` union `base.py` declares today, and `read` returns the captured
action response. So the existing precedent is narrower than "any Resource-Access class, any
shape": `adapters/` has so far only ever held classes that keep the `Adapter` protocol's two-method
read/write pair, widening the *value type* it carries but not the method surface. The Store (V13)
is a different case — reading config-entry data, options, and up to eight owned-entity roles (and
writing some of them) is not obviously expressible as one `read()`/`write(value)` pair; its exact
interface shape is the implementation spec's job, not this ADR's. What this ADR can say with
certainty, independent of that shape question, is system-design.md's own classification: V1
(adapters), V11 (notification), and V13 (Store) are the same Resource-Access layer.

Two forces constrain the choice:

- **A single class, not a family.** Unlike `engines/` (eight modules) or the `managers/` this
  project's Managers will eventually fill (M1–M3), the Store is one class. ADR-0010's own
  reasoning against over-structuring (Option B: "nesting with no grouping payoff… for the sake of
  one real pair") applies with more force to a *single* new module: a dedicated subpackage for
  one class has no sibling to justify the directory.
- **`tests/` mirrors the package 1:1** (ADR-0002, ADR-0009), so wherever the Store lives fixes
  where its HA-harness test module lives.

## Considered options

### Option A — `adapters/store.py`, joining the existing Resource-Access package

Add the Store class to `custom_components/smart_charging/adapters/store.py`, alongside the
hardware-role adapters and `notify.py`. `tests/adapters/test_store.py` joins the existing mirror.

- Pro: Matches system-design.md's own grouping of V1/V11/V13 as one Resource-Access layer, and
  costs nothing today: no new subpackage, no import churn, no renamed package.
- Con: Unlike `notify.py`, the Store is not guaranteed to fit the `Adapter` protocol's
  `read()`/`write(value)` shape — it may need several differently-named methods (config data,
  options, per-role owned-entity reads/writes) rather than one pair. If it doesn't,
  `adapters/store.py` would be the first member of this package that isn't even loosely
  `Adapter`-shaped, a real (if deferred) cost against ADR-0002/ADR-0003's description of
  `adapters/` as "one class per role, sharing the `Adapter` protocol."

### Option B — Top-level `store.py`, sibling to `coordinator.py` and `entity.py`

Place the Store as a new top-level module at the package root, alongside `coordinator.py`,
`entity.py`, `const.py`, and the platform files. `tests/test_store.py` joins the `tests/` root.

- Pro: No subpackage for a single class; the root already holds single-purpose HA-adjacent
  modules (`entity.py`, `const.py`), so a single-class Store fits that shelf without disturbing
  `adapters/`'s existing contents.
- Con: Splits the Resource-Access layer across two locations — two of three members
  (`adapters/notify.py`, the hardware roles) inside `adapters/`, the third at the root — with no
  structural signal that all three are the same layer. A reader asking "what is Resource Access
  in this codebase?" has to already know to check both places; system-design.md's own three-way
  RA grouping (adapters, notification, store) would have no directory-level counterpart at all.

### Option C — New `resource_access/` subpackage; move `adapters/` (including `notify.py`) under it, alongside a new `store.py`

Rename/relocate the existing `adapters/` package to `resource_access/adapters/` (or flatten its
contents directly under `resource_access/`), add `resource_access/store.py`, so all Resource
Access classes sit under one directory whose name matches the system-design layer exactly.

- Pro: Full structural consistency — the tree states the Resource-Access layer with no naming
  mismatch and no split, mirroring how `engines/`/`managers/` each got a layer-named home.
- Con: Moves already-merged, working code (fourteen hardware-role adapters, `notify.py`, and
  every import site across `coordinator.py` and their tests) for a naming improvement, not a
  behavior change — the same cost ADR-0015's Option B weighed and rejected for `coordinator.py`,
  at a larger scale here (more files, more import sites). It also has no caller today: nothing
  about the Store's own shape requires `adapters/` to be renamed first.

## Decision

Option A. system-design.md's own classification is decisive, not a code precedent: V1, V11, and
V13 are one Resource-Access layer, and `adapters/` is that layer's existing home. Option A's Con —
the Store may not fit the `Adapter` protocol's method shape the way `notify.py` does — is accepted
rather than avoided, because Option B does not actually avoid it: splitting the Store out to the
package root would still leave the same question (does its interface look like an `Adapter`?)
unanswered, while additionally scattering the Resource-Access layer across two locations for no
compensating benefit. Between the two real choices, joining `adapters/` costs nothing today and
keeps every Resource-Access class discoverable in one place; if the Store's eventual interface
turns out not to share `Adapter`'s shape, that is a fact about the Store, not a reason to place it
somewhere the design doesn't consider a Resource-Access layer at all. Option C is rejected for the
reason ADR-0015 already established for `coordinator.py`: renaming and relocating working, merged,
well-cited code buys a naming consistency the Store's own implementation does not need, at a real
(and here, larger) cost, with nothing about this decision requiring it as a prerequisite.

## Consequences

- The Store lives at `custom_components/smart_charging/adapters/store.py`, joining the fourteen
  hardware-role adapters and `notify.py`; `tests/adapters/test_store.py` mirrors it per
  ADR-0002/ADR-0009. No existing file moves.
- **The rule for future contributors:** `adapters/` is the home for every Resource-Access class
  system-design.md names (hardware roles, Notification RA, the Store), not only classes
  implementing the `Adapter` protocol. A future Resource-Access addition follows the
  system-design classification, not a search for an `Adapter`-shaped precedent.
- **ADR-0002/ADR-0003's description of `adapters/** — "one class per role, sharing the `Adapter`
  protocol" — is relaxed by this decision, not merely extended, if the Store's interface (decided
  by its own implementation spec, not here) turns out not to share that protocol's
  `read()`/`write(value)` shape. `notify.py` only ever widened the *value type* the shared shape
  carries; the Store may be the first member with a genuinely different method surface. Neither
  ADR-0002 nor ADR-0003's Context/Decision text is edited (the immutability rule) — this
  Consequence is the record of the relaxation.
- `adapters/__init__.py`'s exports (if any) and its factory (`factory.py`, which builds
  hardware-role adapters from config-entry role mappings per ADR-0003) are unaffected — the Store
  is a separate class with its own construction, not a role the factory produces; the
  implementation spec that builds it decides how the Coordinator/Managers obtain a Store
  instance, and what its own read/write method surface looks like.
- This unblocks the RA3 Store implementation spec — it can now cite an exact file path
  (`adapters/store.py`) rather than leaving the Store's location as an open question inherited
  from ADR-0018.
- ADR-0002, ADR-0010, and ADR-0015 are **extended, not superseded**: none of their placements
  change; this ADR only fills the gap ADR-0018 left open.
- If `adapters/` later grows enough non-`Adapter`-shaped members that the mismatch this ADR
  accepts becomes actively confusing, revisiting toward Option C stays available as its own ADR —
  this decision does not foreclose it, it just isn't justified by one class today.
