# Profile mode-selection policy — design

**Date:** 2026-08-09
**Status:** draft (issue #478, part of #308; ADR-0017)
**Type:** implementation design (a slice of an architectural decision — not a new decision)

**ADR-0017 status correction (done).** ADR-0017 was merged (#487) still marked `Status: Proposed`
— the same class of pre-merge oversight ADR-0012/0014/0016/0018/0019 each had, fixed in their own
implementation-spec PRs (most recently `2026-08-03-ra3-store-design.md`'s Task 0 for ADR-0018/0019).
`docs/adl/0017-profile-as-composed-mode-selection-policy.md` and `docs/adl/README.md` are already
corrected to `Accepted` as part of authoring this design doc — not a pending step for Task 1 to
redo (the paired plan's Task 0 records this for the commit-message trail only).

This document is the implementation spec [ADR-0017](../adl/0017-profile-as-composed-mode-selection-policy.md)
itself calls for ("An implementation spec and TDD plan for the `profiles/`
restructure can follow once this ADR is Accepted ... building the `ModeSelectionPolicy` Protocol
and registry this Decision describes rather than a three-role split"). It derives the concrete
files, signatures, and TDD build order for that Protocol/registry — no service, call direction, or
behavior beyond what ADR-0017 and `system-design.md`'s E2 revision already decided, and does not
fully realize either (§4 states the remaining gap explicitly).

**This is a pure internal-boundary refactor: no observable behavior change.**
`select.smart_charging_profile` still offers exactly `Manual`/`Auto`; `Auto`'s mode-selection table
(`resolution-rules.md`) resolves identically before and after. The only production call site this
slice touches is the two `select_mode(...)` calls inside `resolve_deadline_urgency`
(`coordinator_cycle.py`), which today only ever fire when the active profile is already `Auto`
(`auto_dispatchable`'s own gate) — so no runtime branch disappears from this slice alone; what
changes is that `profiles/` now exposes a keyed registry a future profile/config-flow UI can extend,
instead of a bare free-function import.

---

## 1. Why this slice, and its explicit scope boundary

ADR-0017 decided **Option A**: one `ModeSelectionPolicy` Protocol, with `Manual`/`Auto` as two
registry-keyed instances stored inside `profiles/` itself, keyed by the existing
`PROFILE_MANUAL`/`PROFILE_AUTO` constants. It explicitly rejected a three-role composed `Profile`
(Option C) — SOC-limit coordination (both R8's step-up and R9's cap-lowering half,
`system-design.md:506-508`) stays entirely inside the unchanged SOC-Target Engine, and the
escalation lever (R5) and top-up decline (R9's other half) are already rows of the one `Auto`
mode-selection table, not separate objects. Neither of those is touched by this slice. This is
also `project-plan.md`'s E2 task ("Profile Engines (`Manual`, `Auto`)"; its own integration
checkpoint "⎔ M1 passes available modes to E2 (`Auto`); C2 reuses the same facts") — this spec
derives the concrete restructure of that already-built task, not a new one.

A second, narrower fork was resolved with the human partner before drafting this doc: how far the
registry reaches into the coordinator's existing profile-branching.

| Option | Scope | Decision |
| --- | --- | --- |
| Minimal — wrap only the `Auto` call site | Replace the two `select_mode(...)` calls in `resolve_deadline_urgency` with a `PROFILE_POLICIES[PROFILE_AUTO].select(...)` lookup. Register `ManualPolicy` as a real, tested Protocol implementation, but do not route `Manual`'s existing Store-read dispatch path (`coordinator.py`'s `_read_owned_entities`) through it. | **Chosen.** |
| Unify — one call site for both profiles | Route both profiles through one `policy.select(...)` call each cycle, folding `Manual`'s Store-read suppression logic into the same path. | Rejected — larger diff, touches `coordinator.py`'s `_read_owned_entities`/`auto_dispatchable` gate for no behavioral gain this slice needs; ADR-0017's own Consequences promise "no behavior change," and this would risk one. |

| Concern | This slice |
| --- | --- |
| `Auto`'s mode-selection table (`resolution-rules.md`, rows 1–5) | **In scope** — unchanged logic, now reached via `AutoPolicy.select(...)` instead of a direct `select_mode(...)` import. |
| `Manual`'s pass-through ("no rules table") | **In scope, as a new registered `ManualPolicy`** — but not wired into any production call site this slice; it exists so the registry is genuinely two entries, per ADR-0017's Consequences, ready for the coordinator's `Manual`-dispatch path to adopt in a later slice without another `profiles/`-side change. |
| R8's solar step-up (SOC-Target Engine, `Auto`-only input flag) | **Out of scope** — ADR-0017 Context: not a Profile decision at all. Untouched. |
| R9's reserve cap (SOC-Target) and top-up decline (`Auto` row 4) | **Out of scope** — already realized inside `AutoPolicy`'s unchanged table (decline) and SOC-Target (cap). Untouched. |
| `coordinator.py`'s `_read_owned_entities` Store-read suppression (`if self.active_profile != PROFILE_AUTO`) | **Out of scope** — a Store-read gate, not a mode-selection decision (see the fork table above). |
| `coordinator.py`'s R8 gate (`self.active_profile == PROFILE_AUTO`, line ~315) | **Out of scope** — SOC-Target's own input flag, per ADR-0017 Context. |
| Config-entry schema / config-flow UI for profiles | **Out of scope** — ADR-0017 Consequences: "No config-entry schema change this release." |

---

## 2. Success criteria

"Works" means: **every existing test passes unchanged, `profiles/` gains a `ModeSelectionPolicy`
Protocol and a two-entry registry that both `Manual` and `Auto` genuinely implement and that new
tests exercise directly, and the one production call site (`resolve_deadline_urgency`) is proven to
route through the registry rather than a direct `select_mode` import.**

1. `profiles/` gains a `ModeSelectionPolicy` Protocol (`select(self, **kwargs: Any) -> str`) and a
   `PROFILE_POLICIES: dict[str, ModeSelectionPolicy]` registry with exactly two entries, keyed by
   the existing `PROFILE_MANUAL`/`PROFILE_AUTO` constants (no new key namespace).
2. `AutoPolicy.select(...)` reproduces today's `resolution-rules.md` table exactly — it delegates
   to the existing `select_mode()` free function, unchanged, rather than re-implementing the table.
   `profiles/auto.py`'s existing `select_mode()` and its full test suite (`tests/profiles/test_auto.py`)
   are untouched.
3. `ManualPolicy.select(...)` is a pass-through: given `active_mode=X`, it returns `X`, ignoring
   every other input — mirroring `resolution-rules.md`'s "`Manual` needs no table" and R16's
   acceptance criterion that `Manual` mode selection is "a pass-through of the user's own
   selection."
4. `coordinator_cycle.py`'s `resolve_deadline_urgency` calls `PROFILE_POLICIES[PROFILE_AUTO].select(...)`
   instead of importing and calling `select_mode` directly, at both its baseline (`urgent=False`)
   and real (`urgent=urgent`) call sites. `tests/test_coordinator_cycle.py`'s five existing
   `resolve_deadline_urgency` tests pass unchanged — this is the "no behavior change" proof (§2 of
   ADR-0017's Consequences), verified by an existing, not a rewritten, test suite.
5. No file outside `profiles/` and `coordinator_cycle.py`'s two call sites changes. In particular,
   `coordinator.py`'s three `active_profile`-branching checks (R8's gate and `auto_dispatchable`,
   both `== PROFILE_AUTO`; the Store-read suppression, `!= PROFILE_AUTO`) are untouched — confirmed by an explicit read, not just a green suite
   (§1's fork table; same discipline the coordinator-setter-encapsulation design doc used).
6. `tests/test_engine_purity.py`'s structural guard (no `homeassistant.*` import under `profiles/`)
   passes for the two new files without modification to the guard itself.

---

## 3. New `profiles/` shape

```python
# profiles/policy.py — new file
"""ModeSelectionPolicy Protocol and the Manual/Auto registry (ADR-0017). Pure -- no HA imports,
no cross-engine calls (mirrors profiles/auto.py's existing purity, ADR-0009/0010)."""

from typing import Any, Protocol, runtime_checkable

from ..const import PROFILE_AUTO, PROFILE_MANUAL
from .auto import AutoPolicy
from .manual import ManualPolicy


@runtime_checkable  # matches adapters/base.py's Adapter Protocol -- makes `isinstance(x,
# ModeSelectionPolicy)` a real, testable conformance check, not just a static-typing fiction
class ModeSelectionPolicy(Protocol):
    """One role: given this cycle's observable conditions, which mode is active. The one
    decision ADR-0017 identified as genuinely profiles/'s own (Context) -- SOC-limit
    coordination and escalation levers are realized elsewhere (SOC-Target Engine, this
    Protocol's own Auto implementation's table rows), not as separate Profile roles."""

    def select(self, **kwargs: Any) -> str:
        """Return the active mode. Each implementation reads only the kwargs it needs; the
        two implementations' actual parameter sets differ (Auto requires select_mode()'s
        full 10 parameters and rejects unknown ones -- it does not filter -- while Manual
        accepts and ignores anything besides active_mode). A caller must therefore pass
        exactly the selected policy's own kwargs, not a union of both -- there is only ever
        one production call site this slice (§4), and it only ever resolves to AutoPolicy,
        so this is not yet exercised both ways; a future caller that looks up either entry
        generically would need to build each policy's own kwargs, not one shared dict."""
        ...


PROFILE_POLICIES: dict[str, ModeSelectionPolicy] = {
    PROFILE_MANUAL: ManualPolicy(),
    PROFILE_AUTO: AutoPolicy(),
}
```

```python
# profiles/manual.py — new file (extends ADR-0006's step-5 sketch, never shipped until now)
"""Manual profile mode-selection (E2, ADR-0017). Pure -- no HA imports, no cross-engine calls."""

from typing import Any


class ManualPolicy:
    """resolution-rules.md: "Manual needs no table" -- a pass-through of the user's own
    selection (R16). Reads only `active_mode`; every other kwarg a caller passes (Auto's
    observable-conditions inputs) is accepted and ignored, so both registry entries share
    one call shape (ModeSelectionPolicy.select(**kwargs))."""

    def select(self, *, active_mode: str, **_ignored: Any) -> str:
        return active_mode
```

```python
# profiles/auto.py — existing file, select_mode() body UNCHANGED; one class added
class AutoPolicy:
    """Thin ModeSelectionPolicy adapter over the existing select_mode() free function
    (ADR-0017) -- no table logic duplicated or moved."""

    def select(self, **kwargs: Any) -> str:
        return select_mode(**kwargs)
```

No `profiles/__init__.py` change — every other package in this codebase (`modes/`, `engines/`,
`managers/`, `adapters/`) keeps its `__init__.py` empty and puts real content in named modules;
this slice follows that existing convention rather than introducing a new one.

---

## 4. `coordinator_cycle.py` call-site change

`resolve_deadline_urgency`'s two `select_mode(urgent=..., **common_select_kwargs)` calls
(`coordinator_cycle.py:321,355`) become `PROFILE_POLICIES[PROFILE_AUTO].select(urgent=..., **common_select_kwargs)`.
The literal `PROFILE_AUTO` key (not a parameter threaded in from the coordinator) is deliberate,
not a missed generalization: this call site only ever executes when `auto_dispatchable` is
already `True`, and `auto_dispatchable` is itself gated on `self.active_profile == PROFILE_AUTO`
in `coordinator.py` — so the active profile at this point in the cycle can never be anything else.
Threading a redundant `active_profile` parameter through just to perform a lookup that always
resolves to the same entry would be exactly the kind of seam-for-its-own-sake ADR-0017's Decision
warns against (Option C's mistake, applied one level down). A future slice that generalizes
`auto_dispatchable` beyond a hardcoded `Auto` check is the point at which this call site would
gain a real `active_profile`-keyed lookup — out of scope here.

**This slice only partly realizes ADR-0017's Decision and `project-plan.md`'s E2 task.** ADR-0017's
own Decision text is "the Coordinator holds the active profile as exactly this key ... and looks up
the policy each cycle **instead of branching on it**" — a lookup resolved from *data* (the stored
profile key), not a fixed code identity. This slice ships the registry and its data-addressable
keys, but the one production call site still resolves through a hardcoded `PROFILE_AUTO` literal,
and all three `active_profile`-branching checks in `coordinator.py` (the R8 gate, `auto_dispatchable`,
and the Store-read suppression) are untouched (§1's scope table). The registry seam ADR-0017 wants
for a future third profile or config-flow UI now exists inside `profiles/`, but nothing in
`coordinator.py` reads a profile key dynamically yet — that generalization is real follow-up work,
not something this slice's "no behavior change" scope can claim to have finished. A later slice
should revisit `auto_dispatchable`'s hardcoded `Auto` check once a second profile actually needs to
dispatch through it.

```python
# coordinator_cycle.py, was:
from .profiles.auto import select_mode
...
    baseline_mode = select_mode(urgent=False, **common_select_kwargs)
...
        resolved_mode = select_mode(urgent=urgent, **common_select_kwargs)

# becomes:
from .const import PROFILE_AUTO  # already imported by coordinator.py; new here
from .profiles.policy import PROFILE_POLICIES
...
    baseline_mode = PROFILE_POLICIES[PROFILE_AUTO].select(urgent=False, **common_select_kwargs)
...
        resolved_mode = PROFILE_POLICIES[PROFILE_AUTO].select(urgent=urgent, **common_select_kwargs)
```

`common_select_kwargs`'s own construction (`coordinator_cycle.py:310-320`) is unchanged — it
already carries `select_mode`'s parameter set minus `urgent` (passed separately at each of the two
call sites), which `AutoPolicy.select` accepts unchanged via `**kwargs`.

---

## 5. Testing (ADR-0009 harness split)

`profiles/` is pure logic (no HA imports) — every test here is **plain pytest**, matching
`tests/profiles/test_auto.py`'s existing boundary.

- **New: `tests/profiles/test_manual.py`** — `ManualPolicy().select(active_mode=X)` returns `X`
  for a few representative modes (`MODE_OFF`, `MODE_SOLAR`, `MODE_CAPTAR`); a pass-through with
  extra, irrelevant kwargs present (`urgent=True`, `soc=10.0`, ...) still returns `active_mode`
  unchanged — proving the "ignores everything else" contract, not just the happy path.
- **New: `tests/profiles/test_policy.py`** — `PROFILE_POLICIES` has exactly two keys
  (`PROFILE_MANUAL`, `PROFILE_AUTO`); `PROFILE_POLICIES[PROFILE_MANUAL]` is a `ManualPolicy`
  instance and `PROFILE_POLICIES[PROFILE_AUTO]` is an `AutoPolicy` instance (`isinstance` checks);
  both also satisfy `isinstance(policy, ModeSelectionPolicy)` (the `@runtime_checkable` Protocol
  itself) — the actual Protocol-conformance proof the conventions promise, not just a check against
  each other's concrete class;
  `PROFILE_POLICIES[PROFILE_AUTO].select(**kwargs)` matches `select_mode(**kwargs)` across the same
  five representative row scenarios `test_auto.py` already covers, plus a `monkeypatch`-based test
  asserting `AutoPolicy.select` actually calls the real `select_mode` (not just produces an equal
  result) — the two together are what prove genuine delegation, not a re-implementation that
  happens to agree on a handful of inputs.
- **Unchanged: `tests/profiles/test_auto.py`** — all 12 existing `select_mode()` tests pass with
  no edit; this is `AutoPolicy`'s own correctness proof by construction (§2, criterion 2).
- **Unchanged: `tests/test_coordinator_cycle.py`**'s five `resolve_deadline_urgency` tests
  (`test_resolve_deadline_urgency_short_circuits_when_not_resolvable`,
  `..._no_deadline_resolved_means_no_urgency`, `..._manual_profile_baseline_is_the_active_mode_itself`,
  `..._escalates_from_baseline_off_to_captar_when_urgent`, `..._no_escalation_when_baseline_already_meets_deadline`)
  pass unchanged — this is the call-site behavior-preservation proof (§2, criterion 4). None of
  these tests import or mock `select_mode` directly; they only assert on `resolve_deadline_urgency`'s
  return value, so the internal registry-lookup swap is invisible to them if and only if the
  behavior is truly unchanged.
- **Unchanged: `tests/test_engine_purity.py`** — the structural no-`homeassistant.*`-import guard
  already scans every module under `profiles/`; the two new files need no guard change, only to
  pass it (plain-Python-only imports).

**Regression**: the full existing suite must pass with no new skips/xfails.

---

## 6. Packaging

```text
custom_components/smart_charging/
  profiles/
    auto.py     # select_mode() UNCHANGED; + AutoPolicy class
    manual.py   # NEW: ManualPolicy class
    policy.py   # NEW: ModeSelectionPolicy Protocol + PROFILE_POLICIES registry
    __init__.py # unchanged (empty, matches every other package's convention)
  coordinator_cycle.py  # 2 call sites: select_mode(...) -> PROFILE_POLICIES[PROFILE_AUTO].select(...)

tests/
  profiles/
    test_auto.py    # unchanged
    test_manual.py  # NEW
    test_policy.py  # NEW
  test_coordinator_cycle.py  # unchanged (proves no behavior change)
  test_engine_purity.py      # unchanged (already covers new files structurally)
```

---

## 7. Deliberately deferred

- **Unifying `Manual`'s dispatch through the registry.** `coordinator.py`'s `_read_owned_entities`
  Store-read suppression (`if self.active_profile != PROFILE_AUTO`) stays exactly as-is; `ManualPolicy`
  is registered and tested but not called from any production path this slice. Resolved explicitly
  with the human partner before drafting (§1) — the minimal-scope option, to keep this slice's
  "no behavior change" promise airtight and avoid touching `auto_dispatchable`'s gate for no
  behavioral payoff this slice needs.
- **A dynamic `active_profile`-keyed lookup at the `resolve_deadline_urgency` call site.** Left
  hardcoded to `PROFILE_AUTO` (§4) — that call site is unreachable under any other profile today;
  generalizing it is follow-up work for whenever `auto_dispatchable` itself generalizes, not this
  slice's job.
- **Any config-entry schema or config-flow UI change** for profile selection/definition — ADR-0017
  Consequences: explicitly out of scope this release; `select.smart_charging_profile` keeps its
  existing two-option enum untouched.
- **R8/R9's SOC-Target-side logic** (`resolve_solar_step_up`, `SocGateResolver`) — ADR-0017 Context:
  not a Profile Engine decision; untouched by construction (§1's scope table).
- **The 0013/0015/0020 `Status: Proposed` backlog.** ADR-0017 itself is corrected to `Accepted` as
  part of authoring this spec (top of doc). Several other merged ADRs in this repo (0013, 0015,
  0020) carry the same pre-existing status-field gap — a repo-wide oversight, but not ADR-0017's,
  and not this slice's to fix.

---

## 8. Next step

This design feeds the `writing-plans` skill to produce the ordered, test-driven implementation
plan (`2026-08-09-profile-mode-selection-policy.md`). Build order: ADR-0017's status correction
(already done, recorded as Task 0) → `ManualPolicy` + `tests/profiles/test_manual.py` →
`AutoPolicy` + registry (`policy.py`) + `tests/profiles/test_policy.py` → `coordinator_cycle.py`
call-site swap (with its own failing test proving the swap, not just behavior preservation) → full
regression pass, including the explicit untouched-code check named in §2's criterion 5. No
`custom_components/` code is written until the paired plan exists and is approved.
