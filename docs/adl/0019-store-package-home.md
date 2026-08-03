# ADR-0019: Package home for the RA3 Config/State Store

Date: 2026-08-03
Status: Proposed

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

The Resource-Access layer already has a placement precedent worth citing directly rather than
re-deriving: `adapters/` today holds not only the thirteen `Adapter`-protocol hardware roles
(`base.py`'s `read()`/`write(value)` shape) but also `adapters/notify.py`'s `NotifyAdapter` —
the Notification Resource Access (V11) class, which does not implement the `Adapter` protocol at
all (it sends a notification and awaits an actionable response, not a per-role value read/write).
`adapters/` is, in practice, already the home for "reaches one external resource," not strictly
for "implements the `Adapter` protocol." The Store (V13) is Resource Access under the same
system-design classification as V1 and V11.

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

- Pro: Matches the precedent `adapters/notify.py` already set — this package is already where a
  Resource-Access class lives regardless of whether it implements the per-role `Adapter`
  protocol, so the Store joining it extends an established pattern rather than starting a new
  one. Costs nothing: no new subpackage, no import churn, no renamed package.
- Con: `adapters/` is named for the `Adapter` protocol, and now two of its members (`notify.py`,
  `store.py`) don't implement it — the package name describes a shrinking fraction of its own
  contents. This cost already exists today because of `notify.py`; this option accepts it rather
  than introduces it, but does not fix it either.

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
- Con: Moves already-merged, working code (thirteen hardware-role adapters, `notify.py`, and
  every import site across `coordinator.py`, the Vehicle-Limit Manager design, and their tests)
  for a naming improvement, not a behavior change — the same cost ADR-0015's Option B weighed
  and rejected for `coordinator.py`, at a larger scale here (more files, more import sites). It
  also has no caller today: nothing about the Store's own shape requires `adapters/` to be
  renamed first.

## Decision

Option A. The `adapters/notify.py` precedent is decisive: this codebase has already established
that `adapters/` is where a Resource-Access class lives, independent of whether it implements the
`Adapter` protocol's per-role read/write shape — the Store joining it as `adapters/store.py`
extends a pattern already in production rather than choosing between "purity" and "practicality"
for the first time. Option B is rejected because it would split the Resource-Access layer across
two locations for a class that has exactly the same relationship to the rest of `adapters/` that
`notify.py` already has — there is no principled reason to place the Store differently from its
nearest sibling. Option C is rejected for the reason ADR-0015 already established for
`coordinator.py`: renaming and relocating working, merged, well-cited code buys a naming
consistency the Store's own implementation does not need, at a real (and here, larger) cost, with
nothing about this decision requiring it as a prerequisite.

## Consequences

- The Store lives at `custom_components/smart_charging/adapters/store.py`, joining the thirteen
  hardware-role adapters and `notify.py`; `tests/adapters/test_store.py` mirrors it per
  ADR-0002/ADR-0009. No existing file moves.
- **The rule for future contributors:** `adapters/` is the home for every Resource-Access class
  system-design.md names (hardware roles, Notification RA, the Store), not only classes
  implementing the `Adapter` protocol. A future Resource-Access addition follows the Store/
  `notify.py` precedent rather than asking whether it "really" belongs in `adapters/`.
- `adapters/__init__.py`'s exports (if any) and its factory (`factory.py`, which builds
  hardware-role adapters from config-entry role mappings per ADR-0003) are unaffected — the Store
  is a separate class with its own construction, not a role the factory produces; the
  implementation spec that builds it decides how the Coordinator/Managers obtain a Store
  instance.
- This unblocks the RA3 Store implementation spec — it can now cite an exact file path
  (`adapters/store.py`) rather than leaving the Store's location as an open question inherited
  from ADR-0018.
- ADR-0002, ADR-0010, and ADR-0015 are **extended, not superseded**: none of their placements
  change; this ADR only fills the gap ADR-0018 left open.
- If `adapters/` later grows enough non-`Adapter`-shaped members that the naming mismatch this
  ADR accepts becomes actively confusing, revisiting toward Option C stays available as its own
  ADR — this decision does not foreclose it, it just isn't justified by one class today.
