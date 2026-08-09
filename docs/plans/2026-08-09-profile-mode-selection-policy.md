# Profile Mode-Selection Policy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `ModeSelectionPolicy` Protocol and a `PROFILE_POLICIES` registry to `profiles/`
(`{PROFILE_MANUAL: ManualPolicy(), PROFILE_AUTO: AutoPolicy()}`), per
[ADR-0017](../adl/0017-profile-as-composed-mode-selection-policy.md), and switch
`coordinator_cycle.py`'s two `select_mode(...)` call sites to look the `Auto` policy up in that
registry instead of importing the free function directly. **Pure internal-boundary refactor, no
observable behavior change** — `select_mode()`'s own table logic is untouched, and `Manual`'s
existing dispatch path is untouched (design doc §1, §7 — deliberately deferred, not this slice's
job).

**Architecture:** Two new files under `profiles/` (`manual.py`, `policy.py`) plus one class added
to the existing `profiles/auto.py`; no coordinator-level restructuring. Full design:
[`2026-08-09-profile-mode-selection-policy-design.md`](2026-08-09-profile-mode-selection-policy-design.md).

**Tech Stack:** Python ≥3.12, plain `pytest` (no HA harness — `profiles/` stays pure per
ADR-0009/0010), `ruff`.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

---

## Conventions used throughout

- **Named constants, no magic strings** (CLAUDE.md) — `PROFILE_MANUAL`/`PROFILE_AUTO` (already in
  `const.py`) are the only registry keys; no new key namespace.
- **`git commit --author="Claude <noreply@anthropic.com>"`** with the trailer
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Re-check `git branch --show-current` before every commit (shared checkout).
- Test docstrings name ADR-0017 and which contract (Protocol conformance / pass-through /
  delegation) they prove.
- **After every task, run the full existing test suite** (`pytest tests/ -q`) — it must keep
  passing unchanged. Do not defer this to the end.
- **`ruff check .` and `ruff format --check .`** both clean before each commit (memory:
  `feedback-run-ruff-format-check-not-just-check`).

---

## Task 1: `ManualPolicy`

**ADR honored:** ADR-0017. **Test boundary:** plain pytest (`tests/profiles/test_manual.py`, new).

**Files:**
- New: `custom_components/smart_charging/profiles/manual.py`
- New: `tests/profiles/test_manual.py`

**Step 1: Write the failing tests**

```python
"""Plain-pytest tests for the Manual profile's mode-selection pass-through (E2, ADR-0017, R16)."""

from custom_components.smart_charging.const import MODE_CAPTAR, MODE_OFF, MODE_SOLAR
from custom_components.smart_charging.profiles.manual import ManualPolicy


def test_select_returns_active_mode_unchanged():
    """resolution-rules.md: "Manual needs no table" -- a pure pass-through of the user's own
    selection (R16's acceptance criterion)."""
    assert ManualPolicy().select(active_mode=MODE_SOLAR) == MODE_SOLAR


def test_select_ignores_every_other_kwarg():
    """Manual's own contract: no automatic mode change regardless of observable conditions
    (NF1) -- proven here by passing Auto's full kwarg set alongside active_mode and
    confirming none of it changes the result."""
    result = ManualPolicy().select(
        active_mode=MODE_OFF,
        urgent=True,
        soc=10.0,
        active_soc_limit=80.0,
        available_modes=frozenset({MODE_OFF, MODE_CAPTAR}),
        solar_capability_present=True,
        sun_is_up=True,
        solar_surplus_sufficient=True,
        sun_is_down=False,
        low_tariff_active=True,
        solar_reserve_active=True,
    )
    assert result == MODE_OFF
```

**Step 2: Run to verify failure** — `pytest tests/profiles/test_manual.py -v`: both fail with
`ModuleNotFoundError: No module named 'custom_components.smart_charging.profiles.manual'`.

**Step 3: Implement**

```python
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

**Step 4: Run to verify pass**, then the full suite, then commit:

```
git commit --author="Claude <noreply@anthropic.com>" -m "$(cat <<'EOF'
Add ManualPolicy mode-selection pass-through (ADR-0017 T1)

profiles/ gains its first ManualPolicy implementation of the
ModeSelectionPolicy shape ADR-0017 decided -- a pure pass-through of
the user's own selection, ignoring every other input.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `AutoPolicy` + `ModeSelectionPolicy` Protocol + `PROFILE_POLICIES` registry

**ADR honored:** ADR-0017. **Test boundary:** plain pytest (`tests/profiles/test_policy.py`, new).

**Files:**
- Edit: `custom_components/smart_charging/profiles/auto.py`
- New: `custom_components/smart_charging/profiles/policy.py`
- New: `tests/profiles/test_policy.py`

**Step 1: Write the failing tests**

```python
"""Plain-pytest tests for the ModeSelectionPolicy Protocol and PROFILE_POLICIES registry
(E2, ADR-0017)."""

from custom_components.smart_charging.const import (
    MODE_CAPTAR,
    MODE_OFF,
    PROFILE_AUTO,
    PROFILE_MANUAL,
)
from custom_components.smart_charging.profiles.auto import AutoPolicy, select_mode
from custom_components.smart_charging.profiles.manual import ManualPolicy
from custom_components.smart_charging.profiles.policy import PROFILE_POLICIES


def test_registry_has_exactly_the_two_built_in_profiles():
    """ADR-0017 Decision: no new key namespace -- the existing PROFILE_MANUAL/PROFILE_AUTO
    constants are the only registry keys."""
    assert set(PROFILE_POLICIES) == {PROFILE_MANUAL, PROFILE_AUTO}


def test_registry_manual_entry_is_a_manual_policy():
    assert isinstance(PROFILE_POLICIES[PROFILE_MANUAL], ManualPolicy)


def test_registry_auto_entry_is_an_auto_policy():
    assert isinstance(PROFILE_POLICIES[PROFILE_AUTO], AutoPolicy)


def test_auto_policy_delegates_to_select_mode_unchanged():
    """AutoPolicy must not re-implement resolution-rules.md's table -- it delegates, so the
    table can never drift between the free function and the Protocol adapter."""
    modes = frozenset({MODE_OFF, MODE_CAPTAR})
    kwargs = dict(
        soc=50.0,
        active_soc_limit=80.0,
        available_modes=modes,
        urgent=True,
        solar_capability_present=True,
        sun_is_up=False,
        solar_surplus_sufficient=False,
        sun_is_down=True,
        low_tariff_active=True,
        solar_reserve_active=False,
    )
    assert AutoPolicy().select(**kwargs) == select_mode(**kwargs) == MODE_CAPTAR
```

**Step 2: Run to verify failure** — `pytest tests/profiles/test_policy.py -v`: fails with
`ModuleNotFoundError: No module named 'custom_components.smart_charging.profiles.policy'` (and
`ImportError: cannot import name 'AutoPolicy'` once `policy.py` exists but before `AutoPolicy` is
added to `auto.py`).

**Step 3: Implement**

In `profiles/auto.py`, append (the existing `select_mode()` function and its docstring/imports at
the top of the file are **unchanged**):

```python
class AutoPolicy:
    """Thin ModeSelectionPolicy adapter over the existing select_mode() free function
    (ADR-0017) -- no table logic duplicated or moved."""

    def select(self, **kwargs: Any) -> str:
        return select_mode(**kwargs)
```

(add `from typing import Any` to `auto.py`'s existing import block.)

New `profiles/policy.py`:

```python
"""ModeSelectionPolicy Protocol and the Manual/Auto registry (ADR-0017). Pure -- no HA imports,
no cross-engine calls (mirrors profiles/auto.py's existing purity, ADR-0009/0010)."""

from typing import Any, Protocol

from ..const import PROFILE_AUTO, PROFILE_MANUAL
from .auto import AutoPolicy
from .manual import ManualPolicy


class ModeSelectionPolicy(Protocol):
    """One role: given this cycle's observable conditions, which mode is active -- the one
    decision ADR-0017 identified as genuinely profiles/'s own. SOC-limit coordination and
    escalation levers are realized elsewhere (SOC-Target Engine; this Protocol's own Auto
    implementation's table rows), not as separate Profile roles."""

    def select(self, **kwargs: Any) -> str:
        """Return the active mode. Each implementation reads only the kwargs it needs and
        ignores the rest, so both registry entries share one call shape."""
        ...


PROFILE_POLICIES: dict[str, ModeSelectionPolicy] = {
    PROFILE_MANUAL: ManualPolicy(),
    PROFILE_AUTO: AutoPolicy(),
}
```

**Step 4: Run to verify pass**, then the full suite (including `tests/profiles/test_auto.py`'s 12
existing tests, still passing unchanged since `select_mode()` itself wasn't touched), then
`tests/test_engine_purity.py` (the new `policy.py`/`auto.py`'s added class import only `typing` and
sibling `profiles/`/`const` modules — no `homeassistant.*`), then commit:

```
git commit --author="Claude <noreply@anthropic.com>" -m "$(cat <<'EOF'
Add AutoPolicy, ModeSelectionPolicy Protocol, PROFILE_POLICIES registry (ADR-0017 T2)

profiles/ now exposes a two-entry registry keyed by the existing
PROFILE_MANUAL/PROFILE_AUTO constants. AutoPolicy delegates to the
unchanged select_mode() free function -- no table logic moved.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `coordinator_cycle.py` call-site swap

**ADR honored:** ADR-0017. **Test boundary:** plain pytest — the existing
`tests/test_coordinator_cycle.py` `resolve_deadline_urgency` tests must pass **unchanged** (no
edit to that test file at all in this task; that is the proof).

**Files:**
- Edit: `custom_components/smart_charging/coordinator_cycle.py`

**Step 1: Confirm the pre-existing tests currently pass** (baseline, before touching production
code): `pytest tests/test_coordinator_cycle.py -v` — all `resolve_deadline_urgency`-prefixed tests
green against today's direct `select_mode` import.

**Step 2: Implement** — in `coordinator_cycle.py`:

```python
# was:
from .profiles.auto import select_mode

# becomes:
from .const import PROFILE_AUTO  # new import in this module
from .profiles.policy import PROFILE_POLICIES
```

```python
# resolve_deadline_urgency, was:
baseline_mode = select_mode(urgent=False, **common_select_kwargs)
...
        resolved_mode = select_mode(urgent=urgent, **common_select_kwargs)

# becomes:
baseline_mode = PROFILE_POLICIES[PROFILE_AUTO].select(urgent=False, **common_select_kwargs)
...
        resolved_mode = PROFILE_POLICIES[PROFILE_AUTO].select(urgent=urgent, **common_select_kwargs)
```

The literal `PROFILE_AUTO` key is deliberate, not a missed generalization — this call site only
ever runs when `auto_dispatchable` is already `True`, which itself is gated on the profile being
`Auto` in `coordinator.py` (design doc §4). Do not thread a new `active_profile` parameter through
this function to "generalize" the lookup — that is explicitly out of scope (design doc §7).

**Step 3: Run to verify the existing suite still passes, with zero test-file edits**:
`pytest tests/test_coordinator_cycle.py -v` — every `resolve_deadline_urgency`-prefixed test
(`test_resolve_deadline_urgency_short_circuits_when_not_resolvable`,
`..._no_deadline_resolved_means_no_urgency`, `..._manual_profile_baseline_is_the_active_mode_itself`,
`..._escalates_from_baseline_off_to_captar_when_urgent`,
`..._no_escalation_when_baseline_already_meets_deadline`) passes unchanged. If any fails, the
call-site swap changed observable behavior — stop and re-examine before proceeding; this task must
not edit the test file to make it pass.

**Step 4:** Full suite (`pytest tests/ -q`), `ruff check .`, `ruff format --check .`, then commit:

```
git commit --author="Claude <noreply@anthropic.com>" -m "$(cat <<'EOF'
Route resolve_deadline_urgency's mode selection through PROFILE_POLICIES (ADR-0017 T3)

Both select_mode(...) call sites now look the Auto policy up in the
new registry instead of importing the free function directly. No
behavior change -- proven by the pre-existing resolve_deadline_urgency
test suite passing with zero edits.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Regression + untouched-code check

**ADR honored:** ADR-0017. **Test boundary:** full existing suite, plain pytest + HA harness (no
files in this task's scope are HA-coupled, but the full suite includes both).

**Files:** none changed — verification only.

**Step 1:** Run the complete suite: `pytest tests/ -q`. Every test must pass, with no new
skips/xfails.

**Step 2:** `ruff check .` and `ruff format --check .` clean.

**Step 3: Explicit untouched-code check** (design doc §2, criterion 5) — read the post-refactor
`coordinator.py` and confirm none of its three `active_profile == PROFILE_AUTO` branches changed:
- The R8 solar-step-up gate (`is_solar_mode_charging = self.active_profile == PROFILE_AUTO and ...`).
- The `auto_dispatchable` gate (`self.active_profile == PROFILE_AUTO and status in CHARGEABLE_STATES ...`).
- `_read_owned_entities`'s Store-read suppression (`if self.active_profile != PROFILE_AUTO: ...`).

Also confirm `profiles/auto.py`'s `select_mode()` function body is byte-for-byte unchanged from
before Task 1 (only `AutoPolicy` and an `Any` import were added, at the end of the file).

**Step 4:** No commit — this task is a verification checkpoint. If any check fails, fix in the
task that introduced the regression (re-open that task), not here.
