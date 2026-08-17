# ADR-0015: Package home for the Managers beyond the Coordinator

Date: 2026-08-02
Status: Accepted

## Context

ADR-0002 fixed the package layout for `custom_components/smart_charging/`: the subpackages
`adapters/`, `modes/`, `profiles/`, the platform files and `entity.py` at the package root,
and `coordinator.py` driving the control cycle. ADR-0010 later extended that layout with an
`engines/` subpackage for the eight cross-cutting engines ADR-0002 had left homeless. Neither
ADR names a home for the **other Managers**.

`docs/design/system-design.md` §4 puts **three** Managers in the static architecture: the
Charging Coordinator (M1), the Vehicle-Limit Manager (M2), and the Notification Manager (M3);
`docs/design/project-plan.md` §3 tracks them as tasks M1/M2/M3. Only M1 exists in code, as
`coordinator.py` (plus `coordinator_cycle.py`, the state owners ADR-0012 extracted from it).
M2 is next to be built (`docs/plans/2026-07-21-vehicle-limit-manager-design.md` §9.4), M3
follows in the Notifications slice — so the question "where does a Manager module live?" has
to be answered now, before either lands, exactly as ADR-0010 had to answer it for the engines.

Four forces constrain the choice:

- **A Manager is the HA-coupled layer, not the pure one.** Per system-design §4 rule 2 a
  Manager orchestrates: it reads through Resource Access, calls pure Engines, and writes back
  through Resource Access. So — unlike ADR-0010's engines — the directory boundary here cannot
  be a *purity* guard; every Manager module is allowed to import `homeassistant.*`. ADR-0009's
  harness split puts HA-coupled code on the HA harness, and `docs/design/project-plan.md`
  records "Testable on its own: HA harness" for M1, M2, and M3 accordingly. Whatever this ADR
  decides, it must be justified by navigability and by the layer boundary being *legible*, not
  by a testability guarantee.
- **Managers must not call each other** (system-design §4 rule 5, fixed by ADR-0011:
  coordination is publish/subscribe on domain events). A directory that collects the Managers
  makes that rule checkable at a glance — and makes the "no Manager→Manager import" grep the
  M2 plan already runs a rule about a *package*, not about a hand-maintained list of filenames,
  for every Manager under it (a Manager left outside the package would stay a named exception
  the check must still spell out).
- **`coordinator.py` predates the question and is load-bearing in more than code.**
  `coordinator.py` is a Home Assistant convention (a `DataUpdateCoordinator` module at the
  integration root, which is where HA's own scaffolding and quality-scale guidance put it), it
  is named in ADR-0002's Decision, and it is cited by path — often with line numbers — on **22
  lines inside `docs/adl/`** (ADR-0002, -0006, -0009, -0010, -0012, -0014, all Accepted) and on
  155 lines across `docs/`. The project treats an Accepted ADR's Context/Decision as
  not-to-be-rewritten (ADR-0001), so a rename would either leave those 22 citations stale or
  force six edits the convention discourages. Its Python fan-in, by contrast, is trivially
  small — three import sites (`__init__.py`, `tests/test_coordinator.py`,
  `tests/benchmarks/test_coordinator_perf.py`), plus the `from .coordinator_cycle` edge a move
  would have to carry with it. The blast radius of moving it is almost entirely *documentary*,
  not mechanical.
- **`tests/` mirrors the package 1:1** (ADR-0002, ADR-0009), as `engines/` ↔ `tests/engines/`
  already does. Wherever the Managers live dictates where their HA-harness test modules live.

The M2 implementation spec's §9.4 judgment call ("M2 lives in a new `managers/` subpackage")
was confirmed by the human partner in PR review; this ADR is the record that decision requires
before any `custom_components/` code is written, and it settles the part §9.4 left open —
what happens to `coordinator.py`.

## Considered options

### Option A — New `managers/` subpackage for M2/M3; `coordinator.py` stays at the root

Add `custom_components/smart_charging/managers/`, sibling to `adapters/`, `engines/`, `modes/`,
and `profiles/`, holding one module per Manager built from now on — `vehicle_limit.py` (M2),
then `notification_manager.py` (M3). `tests/managers/` mirrors it 1:1. `coordinator.py` and
`coordinator_cycle.py` stay at the package root as a **named, documented exception**: the HA
`DataUpdateCoordinator` module keeps its conventional home.

- Pro: Gives every Manager written from here on an obvious, uniform home and a mirrored
  `tests/managers/`, and makes system-design §4 rule 5 (no Manager→Manager call) a property of
  a package rather than of a filename list. It keeps `coordinator.py` where a Home Assistant
  developer expects a coordinator to be, and — decisively — leaves the 22 by-path citations in
  the immutable Accepted ADRs (and 155 across `docs/`) correct, which no edit could repair
  after the fact. The diff is purely additive: no existing module moves, no import churn, no
  risk to the shipped control cycle.
- Con: The Managers layer is then split across two locations — a reader asking "where are the
  Managers?" finds two of three under `managers/` and the largest one at the root, so the
  layout does not by itself teach the layer. The exception has to be carried in prose (this
  ADR, and the design docs) rather than being self-evident from the tree, and each new
  Manager invites the question again.

### Option B — `managers/` subpackage including a relocated `coordinator.py`

As Option A, plus move `coordinator.py` (and, to keep the pair together, `coordinator_cycle.py`)
into `managers/`, so all three Managers sit under one directory and `tests/managers/` holds all
three test modules.

- Pro: Full structural consistency — the tree states the Managers layer with no exception to
  remember, and the one-way call rules of system-design §4 read directly off the directory
  listing. It removes the risk that "root or `managers/`?" is re-litigated for every future
  Manager.
- Con: It breaks a Home Assistant convention (coordinator at the integration root) for an
  internal taxonomy, so the layout becomes less recognizable to an HA contributor, not more.
  It also invalidates the by-path references in six Accepted ADRs, whose Context/Decision text
  this project does not rewrite (ADR-0001) — so those paths either go stale in the decision log
  or force six edits against that convention. And it drags a companion question with it: `coordinator_cycle.py` holds
  ADR-0012's extracted state owners, which are not themselves Managers, so the move either
  relocates a non-Manager into `managers/` or splits the ADR-0012 pair across directories. The
  code-side churn itself is small (three imports), but the change touches the most safety-relevant,
  most-referenced module in the package to buy tidiness rather than behavior.

### Option C — Status quo: Managers stay at the package root

No new subpackage. `vehicle_limit.py` and `notification_manager.py` join `coordinator.py`,
`entity.py`, `config_flow.py`, and the platform files at the package root, and their tests join
`tests/test_coordinator.py` in the `tests/` root — the convention
`docs/plans/2026-07-21-notifications-design.md` §0 currently assumes.

- Pro: Costs nothing to adopt (it is what happens by default), keeps import paths short, and
  is consistent with the one Manager that exists today; it also matches how most Home Assistant
  integrations are laid out, since few have more than one Manager-shaped module.
- Con: The package root is already the catch-all — platform files, `entity.py`,
  `config_flow.py`, `const.py`, `coordinator.py`, `coordinator_cycle.py` — and adding two more
  orchestration modules to it makes the one layer with the strictest call rule (§4 rule 5) the
  least visible one in the tree. It leaves the "no Manager→Manager import" check as a grep over
  a hand-maintained list of root filenames that must be updated whenever a Manager is added, and
  it breaks parity with ADR-0002/ADR-0010, where every other multi-member layer
  (`adapters/`, `engines/`, `modes/`, `profiles/`) got a subpackage as soon as it had more than
  one member. It also leaves `tests/` placement ambiguous for the Manager tests.

## Decision

Option A. Add `custom_components/smart_charging/managers/` as the home for every Manager module
written from now on — `vehicle_limit.py` (M2) first, `notification_manager.py` (M3) next —
sibling to `adapters/`, `engines/`, `modes/`, and `profiles/`, with `tests/managers/` mirroring
it 1:1 per ADR-0002's mirror rule and ADR-0009's harness split (Manager tests are HA-harness
tests). `coordinator.py` and `coordinator_cycle.py` remain at the package root as the single,
explicitly grandfathered exception.

Option C is rejected on the *navigability* half of ADR-0002's and ADR-0010's reasoning — their
purity half does not transfer here, as the Context notes — namely that once a layer has more
than one member, the root stops being a home and becomes a pile, and here the pile hides the
layer that carries the project's strictest call rule. The choice is therefore between A and B,
and it turns on what relocating `coordinator.py` actually costs. Its *code* cost is negligible
— three imports plus a relative sibling edge — so consistency would be cheap if code were the
whole story. It is not: the module is cited by path on 22 lines inside Accepted ADRs, whose
Context/Decision text this project does not rewrite (ADR-0001), so Option B would trade a
one-directory inconsistency for either 22 stale paths in the decision log or six edits against
that convention, plus a break with the HA convention that puts a `DataUpdateCoordinator` at the integration root, plus a forced
call on `coordinator_cycle.py` — non-Manager code that ADR-0012 deliberately kept beside its
coordinator. Option A's real Con — a Managers layer split across two places — is a
documentation problem with a documentation fix: this ADR is the named exception, and the
`managers/` package still delivers the payoff that matters, a single place where §4 rule 5 and
ADR-0011's no-direct-call rule can be checked for every Manager written from here on.

## Consequences

- The integration package gains a fifth subpackage, `managers/`, joining `adapters/`,
  `engines/`, `modes/`, and `profiles/`. ADR-0002 and ADR-0010 are **extended, not superseded**:
  ADR-0002's placement of `coordinator.py` at the root stands unchanged, and ADR-0010's
  `engines/` decision is untouched.
- **The rule for future contributors:** a new Manager gets `managers/<name>.py` and a mirrored
  `tests/managers/test_<name>.py`. `coordinator.py`/`coordinator_cycle.py` at the root are a
  historical exception, not a precedent — "mirroring `coordinator.py`" is not a reason to place
  a new Manager at the root.
- `managers/` is for **Manager modules only** — orchestration that reads/writes through Resource
  Access. Pure logic a Manager consumes keeps its ADR-0002/ADR-0010 home under `engines/` (or
  `modes/`/`profiles/`); putting a pure module in `managers/` would blur the very layer boundary
  the package exists to make visible.
- Because Manager modules are HA-coupled by design, `managers/` carries **no** import-purity
  guarantee — the inverse of `engines/`. Its tests are HA-harness tests under ADR-0009, and the
  boundary it makes checkable is ADR-0011's (no Manager imports another Manager), not
  "no `homeassistant.*` import".
- This unblocks the M2 build from **Phase 3 onward** — Task 3.1 of
  `docs/plans/2026-07-21-vehicle-limit-manager.md` is where
  `custom_components/smart_charging/managers/vehicle_limit.py` is first created. That plan
  already builds against `managers/vehicle_limit.py` and `tests/managers/test_vehicle_limit.py`,
  so its task text needs no edit; the M2 design's §8/§9.4 gate wording ("task set 4") under-states
  the first affected task and should be corrected in the follow-up.
- **`docs/plans/2026-07-21-notifications-design.md` must be updated** (§0, §7, §10, and the
  paired task plan `2026-07-21-notifications.md`): it currently states there is no `managers/`
  package and places M3 at the package root as `notification_manager.py`, "mirroring
  `coordinator.py`". Under this decision M3's Manager module is
  `managers/notification_manager.py` with `tests/managers/test_notification_manager.py`. The
  pure `notification_state.py` that `2026-07-21-notifications.md` Phase 2 will create is *not* a
  Manager module and is out of scope of this ADR; where pure notification logic lives is a
  separate question for that slice.
  Follow-up issues should track the design/plan update and, if that slice wants it, the
  placement of its pure module.
- `docs/design/system-design.md` §4 and `docs/design/project-plan.md` gain a concrete file
  mapping for M2/M3; neither's content changes, only the note of where each Manager lands.
- If `coordinator.py`'s root placement later becomes actively confusing — say a fourth Manager
  arrives, or the HA convention shifts — moving it toward Option B stays available as its own
  ADR. This decision does not foreclose it; it declines to pay the immutable-citation cost today.
