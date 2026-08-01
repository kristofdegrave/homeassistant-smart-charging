# Coordinator setter-method encapsulation — design

**Date:** 2026-08-01
**Status:** draft (issue #422, ADR-0014 issue #420, epic n/a — internal refactor)
**Type:** implementation design (a slice of an architectural decision — not a new decision)

**ADR-0014 status correction (done).** ADR-0014 was merged (#421) still marked `Status: Proposed`
— an oversight from before merge, the same class of gap ADR-0012 had and fixed in its own
implementation-spec PR (#386). `docs/adl/0014-state-mutation-encapsulation.md` and
`docs/adl/README.md` are already corrected to `Accepted` as part of authoring this design doc —
not a pending step for Task 1 to redo (plan Task 0 records this for the commit-message trail
only).

This document is the follow-up docs/plans implementation spec [ADR-0014](../adl/0014-state-mutation-encapsulation.md)
itself calls for ("add `set_active_mode`, `set_active_profile`, `set_target_current`, and
`set_soc_limit_override` to `SmartChargingCoordinator` ... an implementation-spec-level choice, not
part of this decision"). It derives the concrete method signatures, call-site changes, and TDD
build order for closing the one gap ADR-0014 identified: four coordinator fields written directly
from outside the class by the owning entity platforms, with no method enforcing what belongs to
the coordinator's own boundary.

**This is a pure internal-boundary refactor: no observable behavior, entity, or event change**,
except two deliberate exceptions: (1) the two numeric setters now enforce a range clamp the
coordinator's own field did not enforce before (mostly redundant with the entities' own HA-level
validation, §7); and (2) `TargetCurrentNumber`/`SocLimitOverrideNumber`'s `__init__` now clamp
their config-flow-sourced `default` too, which **was** reachable in practice (`config_flow.py`
range-validates neither field, §1's last two rows) — an out-of-range configured default now
displays clamped instead of raw.

---

## 1. Why this slice

ADR-0014 named four externally-writable coordinator fields with no owning method:
`active_mode`, `active_profile` (written by `select.py`), `target_current`,
`soc_limit_override` (written by `number.py`). This spec derives the four setter methods and
updates the four call sites; it invents no new field, service, or behavioral rule.

| ADR-0014 field | Current write sites | This slice |
| --- | --- | --- |
| `active_mode` | `select.py:62` (`ModeSelect.async_added_to_hass`), `:66` (`async_select_option`) | **In scope** — `set_active_mode(mode)` |
| `active_profile` | `select.py:89` (`ProfileSelect.async_added_to_hass`), `:93` (`async_select_option`) | **In scope** — `set_active_profile(profile)` |
| `target_current` | `number.py:47` (`TargetCurrentNumber.async_added_to_hass`), `:51` (`async_set_native_value`) | **In scope** — `set_target_current(value)`, clamped to the configured `[CONF_MIN_CURRENT, CONF_MAX_CURRENT]` bound |
| `soc_limit_override` | `number.py:80` (`SocLimitOverrideNumber.async_added_to_hass`), `:84` (`async_set_native_value`) | **In scope** — `set_soc_limit_override(value)`, clamped to `[SOC_LIMIT_OVERRIDE_MIN, SOC_LIMIT_OVERRIDE_MAX]` (new named constants, §3) |
| `active_mode` at `coordinator.py:464` (`self.active_mode = select_mode(...)`, Auto's own mode-selection) | Internal write, inside the coordinator's own `_run_cycle` | **Out of scope** — ADR-0014's rule is about writes from *outside* the class; this is the coordinator setting its own field, not a caller reaching in. Untouched. |
| `_reset_mode_state_if_changed()` (`coordinator.py:587-595`) | Already the sole owner of the `_mode_state`/`_last_active_mode` reset invariant | **Out of scope** — already correctly encapsulated per ADR-0014's own Context; not touched by this slice. |
| `CycleContext` (`coordinator_cycle.py`, ADR-0012) | Not yet wired into `coordinator.py` | **Out of scope** — explicitly excluded by ADR-0014. |
| Test fixtures assigning `coordinator.active_mode = ...` / `.target_current = ...` / etc. directly (137 assignments across `tests/test_coordinator.py`, `tests/test_solar_end_to_end.py`, `tests/test_captar_end_to_end.py`, `tests/test_deadline_soc_management_end_to_end.py`, `tests/test_init.py`, `tests/benchmarks/test_coordinator_perf.py` — a full grep count, not an estimate) | White-box test setup, already an explicitly-endorsed pattern (`coordinator.py:167-172`'s own comment: "tests set them directly, the same way they already set `soc_limit_override`") | **Out of scope** — ADR-0014's rule targets *production* external callers (the entity platforms); test setup poking a coordinator's fields directly to arrange a scenario is not the anemic-model concern Fowler's rule addresses, and rewriting 137 existing assignments across six files is a mechanical rename with no behavior or design payoff. Confirmed as a deliberate deferral (§7), not an oversight; Task 5's untouched-code check (§2.5) covers all six files, not just four. |
| `SocLimitOverrideNumber.__init__`'s unclamped `default` (`number.py:70`) | `config_flow.py:202` validates `default_soc_limit` with `vol.Coerce(float)` only, no 50-100 range; a configured default outside `[50, 100]` is currently pushed to the coordinator's `soc_limit_override` un-clamped, and would diverge from the entity's own display once the coordinator clamps | **In scope, folded into Task 4** — clamp `default` in `__init__` the same way `async_added_to_hass` already clamps a restored value, so the entity's displayed value and the coordinator's clamped field always agree |
| `TargetCurrentNumber.__init__`'s unclamped `default` (`number.py:36`) | Same shape as the SOC row above: `config_flow.py:170` validates `default_target_current` with `vol.Coerce(float)` only, no `[min_a, max_a]` range | **In scope, folded into Task 3** — clamp `default` in `__init__` to `[min_a, max_a]`, the same fix applied symmetrically |

---

## 2. Success criteria

"Works" means: **every existing test passes unchanged, plus new tests proving each setter is the
intended production write path, that the two numeric setters clamp out-of-range input, and that
the two entities' `__init__` clamp their config-flow-sourced default the same way.**

1. `SmartChargingCoordinator` gains four public setter methods (§3); each is the *intended*
   production write path for `select.py`/`number.py` — the coordinator's fields themselves stay
   plain writable attributes (137 existing test call sites depend on being able to set them
   directly, §7; this slice does not, and cannot without rewriting those, make the field itself
   unwritable). The enforcement this slice actually adds lives at the two entity platforms, not as
   a language-level guarantee on the coordinator.
2. `set_target_current`/`set_soc_limit_override` clamp their input to the field's own valid range
   before assigning — a value passed through the setter can no longer reach the field un-clamped.
   (A caller that bypasses the setter and assigns the coordinator's field directly still bypasses
   the clamp too, same as before this slice — see criterion 1.)
3. `set_active_mode`/`set_active_profile` perform no clamp (no numeric range to violate) — they
   exist solely to move the write behind a method, per ADR-0014's rule applying to the *role*
   (externally-writable coordinator state), not each field's current behavior.
4. The four `select.py`/`number.py` call sites (§1's table) call the new setters instead of
   assigning the attribute; entity-side behavior (restore-state seeding, `async_request_refresh`)
   is otherwise unchanged.
5. `coordinator.py:464`'s internal Auto-mode write and `_reset_mode_state_if_changed()` are
   untouched, verified by an explicit read of the post-refactor `coordinator.py`, not just a green
   test suite (the same discipline ADR-0012's design doc used for its own clamp-untouched check).
6. `TargetCurrentNumber.__init__`/`SocLimitOverrideNumber.__init__` clamp their `default` parameter
   to the same bound their own `min`/`max` attrs already enforce on restore, so a configured
   default outside that bound displays clamped instead of raw (§1's last two rows) — this is an
   entity-side fix (`_attr_native_value`), distinct from criterion 2's coordinator-side clamp.

---

## 3. New coordinator methods

All four live on `SmartChargingCoordinator` in `coordinator.py`, next to
`_reset_mode_state_if_changed` (the existing example of a method owning one of the coordinator's
invariants):

```python
def set_active_mode(self, mode: str) -> None:
    """Coordinator's own boundary for `active_mode` (ADR-0014) -- the intended write path for
    select.py; no language-level enforcement stops a caller from assigning `active_mode`
    directly (§2's criterion 1), only entity.py's own call sites are updated. No range to
    clamp: `SelectEntity`'s own `options` list already rejects any value outside the enum
    before this is ever called."""
    self.active_mode = mode

def set_active_profile(self, profile: str) -> None:
    """Coordinator's own boundary for `active_profile` (ADR-0014). Same rationale as
    `set_active_mode` -- no clamp, `SelectEntity` already gates the enum."""
    self.active_profile = profile

def set_target_current(self, value: float) -> None:
    """Coordinator's own boundary for `target_current` (ADR-0014). Clamps to
    the configured `[CONF_MIN_CURRENT, CONF_MAX_CURRENT]` bound -- previously enforced only by
    `TargetCurrentNumber`'s own `native_min_value`/`native_max_value`, bypassable by any other
    caller writing the field directly."""
    self.target_current = min(
        max(value, self._config[CONF_MIN_CURRENT]), self._config[CONF_MAX_CURRENT]
    )

def set_soc_limit_override(self, value: float) -> None:
    """Coordinator's own boundary for `soc_limit_override` (ADR-0014). Clamps to
    `[SOC_LIMIT_OVERRIDE_MIN, SOC_LIMIT_OVERRIDE_MAX]` (const.py, §3.1) -- the same bound
    `SocLimitOverrideNumber` already enforces on its own restored value, now also enforced at the
    coordinator's own field."""
    self.soc_limit_override = min(
        max(value, SOC_LIMIT_OVERRIDE_MIN), SOC_LIMIT_OVERRIDE_MAX
    )
```

No new class, no new module -- these are four methods on the existing `SmartChargingCoordinator`.
`__init__`'s existing field initialization (`coordinator.py:150-158`) is unchanged; only the write
*after* construction moves behind these methods.

### 3.1 New named constants (`const.py`)

`SocLimitOverrideNumber` (`number.py:63-64`) currently hardcodes its bounds as bare `50.0`/`100.0`
class attributes, with no named constant anywhere for the coordinator's own clamp to share. This
slice adds:

```python
SOC_LIMIT_OVERRIDE_MIN = 50.0  # percent (R6) -- shared by number.py's own bounds and the
SOC_LIMIT_OVERRIDE_MAX = 100.0  # coordinator's set_soc_limit_override clamp (single source of truth)
```

`SocLimitOverrideNumber._attr_native_min_value`/`_attr_native_max_value` (`number.py:63-64`) switch
from the bare literals to these constants -- the same two numbers, now named once instead of
duplicated between the entity and the new coordinator clamp. `CONF_MIN_CURRENT`/`CONF_MAX_CURRENT`
already exist and need no new constant; `set_target_current` reads them from `self._config`
exactly as the rest of `coordinator.py` already does (`coordinator.py:441,512,533,...`).

---

## 4. Before/after in `select.py`/`number.py`

- `select.py:62,66` (`ModeSelect`): `self._coordinator.active_mode = ...` →
  `self._coordinator.set_active_mode(...)`.
- `select.py:89,93` (`ProfileSelect`): `self._coordinator.active_profile = ...` →
  `self._coordinator.set_active_profile(...)`.
- `number.py:47,51` (`TargetCurrentNumber`): `self._coordinator.target_current = ...` →
  `self._coordinator.set_target_current(...)`.
- `number.py:80,84` (`SocLimitOverrideNumber`): `self._coordinator.soc_limit_override = ...` →
  `self._coordinator.set_soc_limit_override(...)`.

No other line in either file changes -- `_attr_native_value`/`_attr_current_option` (the entity's
own displayed state) are set exactly as today, since that half of each method is the entity's own
display state, not the coordinator's field.

---

## 5. Testing (ADR-0009 harness split)

`SmartChargingCoordinator` is a `DataUpdateCoordinator` subclass (HA-coupled per ADR-0006), so
per ADR-0009 every test here is **HA harness**, added to the existing suites (no new test file):

- `tests/test_coordinator.py`: `set_target_current`/`set_soc_limit_override` clamp a
  below-minimum and an above-maximum input to the configured bound; `set_active_mode`/
  `set_active_profile` simply assign (one test each is enough -- there is no clamp behavior to
  cover, only that the method exists and the field ends up set).
- `tests/test_select.py`/`tests/test_number.py`: both files' stub coordinators
  (`_StubCoordinator`, `_StubProfileCoordinator`) currently hold each field as a bare
  `__init__`-assigned attribute with no `_config`, so they cannot exercise the real clamp -- the
  plan (Task 1-4) converts the relevant field on each stub to a read-only property backed by a
  private attribute, so only the new setter method can write it. This makes "the entity calls the
  setter, not the bare attribute" a genuinely failing test before the call-site edit, not just an
  assertion on the resulting value (which would pass either way, since a plain stub allows
  arbitrary attribute assignment regardless of whether `__init__` declared the field). The
  existing `test_select_option_pushes_to_coordinator`/`test_set_value_pushes_to_coordinator`-style
  assertions keep passing unchanged once the call site is updated. No *coordinator-clamp* test
  belongs in these two files -- the stubs deliberately don't clamp (§3, they mirror the field, not
  the coordinator's validation); `set_target_current`/`set_soc_limit_override`'s own clamp is
  covered only in `tests/test_coordinator.py` against the real `SmartChargingCoordinator`, which
  does have `_config`. `tests/test_number.py` does gain two *unrelated* tests
  (`test_init_clamps_out_of_range_default_target_current`,
  `test_init_clamps_out_of_range_default_soc_limit`, criterion 6) -- these exercise each entity's
  own `__init__` clamp on its `default` parameter directly against the entity, not the
  coordinator's setter, so they don't contradict "no clamp-specific test belongs in these two
  files" as applied to the *coordinator's* clamp. Note the asymmetry this
  leaves: the *stub* coordinators end up with real, language-level write enforcement (a read-only
  property with no setter), while the *real* `SmartChargingCoordinator` does not (§2, criterion 1)
  -- a future reader should not take the stub's stricter shape as evidence the real class enforces
  the same thing.

**Regression**: the full existing suite (`tests/test_select.py`, `tests/test_number.py`,
`tests/test_coordinator.py`, `tests/test_solar_end_to_end.py`, `tests/test_captar_end_to_end.py`,
`tests/test_deadline_soc_management_end_to_end.py`, `tests/test_init.py`,
`tests/benchmarks/test_coordinator_perf.py`) must pass unchanged. `tests/test_select.py`'s and
`tests/test_number.py`'s stub classes *do* change (the read-only-property conversion, §5 above) --
every other file's test bodies are untouched, only the two production files (`select.py`,
`number.py`) and the coordinator itself gain new production code.

---

## 6. Packaging

```text
custom_components/smart_charging/
  coordinator.py   # + four setter methods (§3), next to _reset_mode_state_if_changed
  select.py        # 4 call sites switch from attribute assignment to the new setters (§4)
  number.py        # 4 call sites switch from attribute assignment to the new setters (§4);
                   #   SocLimitOverrideNumber's bounds switch to the new named constants (§3.1);
                   #   both entities' __init__ now clamp their config-flow-sourced `default` (§1)
  const.py         # + SOC_LIMIT_OVERRIDE_MIN / SOC_LIMIT_OVERRIDE_MAX; corrected DEFAULT_SOC_LIMIT
                   #   comment (§7)
```

`tests/` needs no new file -- new assertions land in the existing suites named in §5.

---

## 7. Deliberately deferred

- **RA3's "Store" abstraction** (`docs/design/project-plan.md`'s M1/C2 rows: "M1 reads owned
  values through the Store", "C2 ... Depends on: RA3 (Store owned-write path)"). The target
  end-state design has entities writing through a Store rather than calling the coordinator
  directly at all; that Store does not exist in the codebase today (no `Store` class anywhere
  under `custom_components/`) -- the current direct entity→coordinator write *is* today's actual
  implementation, not a shortcut this slice introduces. Building RA3's Store is a separate,
  materially larger architectural gap, pre-existing and out of scope for both ADR-0014 and this
  spec; this slice only decides how the *current* direct write path is encapsulated, not whether
  it should eventually be replaced by a Store-mediated one.
- Test fixtures' direct field assignment (§1's table, 137 sites across six files) -- confirmed
  deliberate, not an oversight; Task 5's untouched-code check reads all six files, not a sample.
- `CycleContext` and any change to the coordinator's internal cycle-transition state -- both
  explicitly out of scope per ADR-0014.
- Any change to `active_mode`'s internal Auto-mode write (`coordinator.py:464`) -- internal, not
  the external-write concern this ADR addresses.
- **Practical severity of the clamp gap.** Home Assistant's own `number` platform validates a
  `number.set_value` service call against the entity's `native_min_value`/`native_max_value`
  before `async_set_native_value` is ever invoked, so in normal use the entity's existing bounds
  already make an out-of-range value unreachable through the UI/service layer. The coordinator's
  new clamp is a defense-in-depth boundary for any caller that bypasses that layer (a different
  entity, a future service call, direct test code reaching the coordinator) -- named as such, not
  overstated as fixing a live production bug. `SocLimitOverrideNumber`'s and
  `TargetCurrentNumber`'s config-flow-sourced `default` values are the two paths where this *was*
  reachable in practice (both `config_flow.py` fields are validated with `vol.Coerce(float)` only,
  no range), and both are fixed as part of this slice (§1, Tasks 3 and 4), not merely deferred.
- **`const.py:143`'s comment on `DEFAULT_SOC_LIMIT`** currently reads "range enforced by
  config_flow/number entity" -- half true before this slice (the number entity's restore path
  enforces it; `config_flow` does not) and fully true only after Task 4's `__init__` clamp lands.
  Task 4 corrects this comment while it's already touching the area.
- **`set_target_current`'s minimum clamp never blocks a stop.** ADR-0007's fault path writes 0 A
  via `self._write(0.0)` directly (`coordinator.py:653-660` today), bypassing `target_current`
  entirely -- `set_target_current`'s floor at `CONF_MIN_CURRENT` cannot prevent a commanded stop,
  since a stop never goes through this field. Stated explicitly since the field's own `__init__`
  comment ("0 A is the safe default for cycle 0", `coordinator.py:150`) could otherwise read as in
  tension with a setter that floors above 0.

---

## 8. Next step

This design feeds the `writing-plans` skill to produce the ordered, test-driven implementation
plan (`2026-08-01-coordinator-setter-encapsulation.md`). Build order: `set_active_mode` +
`select.py` (ModeSelect) → `set_active_profile` + `select.py` (ProfileSelect) →
`set_target_current` + `number.py` (TargetCurrentNumber) → `set_soc_limit_override` + new
constants + `number.py` (SocLimitOverrideNumber) → full regression pass, including the explicit
untouched-code check named in §2.5. No `custom_components/` code is written until the paired plan
exists and is approved.
