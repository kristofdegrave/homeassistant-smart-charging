# Low-tariff adapter role state-translation — design

**Date:** 2026-08-17
**Status:** draft (issue #746, analysis: #743 / PR #745, epic n/a)
**Type:** implementation design (a slice of RA2 / C4 in `docs/design/project-plan.md` — not a new
architectural decision)

This document derives the concrete config-flow fields, adapter class, and TDD build order for the
`low_tariff` adapter role widening merged into the analysis layer in PR #745
(`docs/analysis/entity-catalog.md`'s `low_tariff` row, `docs/analysis/system-overview.md`'s
`low-tariff flag` glossary term, and `docs/analysis/use-cases/UC12-configure-installation-through-guided-flow.md`
steps 7 and 9): the `low_tariff` role must accept a tariff signal whose raw state is not already
`on`/`off`, translated to a boolean via a user-supplied list of raw states that count as low
tariff — any other raw state resolving to not-low-tariff.

---

## 1. Why this slice

Today `low_tariff` is read by `BooleanReadAdapter` (`adapters/boolean.py`), which only recognises
the entity's native `on`/`off` state and returns `None` (the ADR-0007 fault signal) for anything
else. `config_flow.py`'s `CONF_LOW_TARIFF_ENTITY` selector (`UNGATED_MAPPING_SCHEMA`) restricts the
picker to `binary_sensor`/`input_boolean` domains, so a real-world tariff signal exposed as a
`sensor` with a textual state (e.g. `low`/`high`) cannot be mapped at all.

This mirrors, but does not reuse, `charger_status`'s existing translation mechanism
(`StatusReadAdapter`, `CONF_CONNECTED_STATES`/`CONF_CHARGING_STATES` → derived
`CONF_STATUS_TRANSLATION`): that translation is a required, exhaustive raw→canonical mapping
between three values, and an unmatched raw state is a *fault* (`None`). `low_tariff`'s translation
is optional, one-directional (only "which raw states count as low"), and an unmatched raw state is
a defined **non-fault** boolean value (`False`) — the entity-catalog's own wording ("every other raw
state resolving to not-low-tariff") is deliberately not "fault", matching the role's existing
permissive default (single-tariff installations already treat an unmapped signal as always `on`).
Reusing `StatusReadAdapter`'s shape would misrepresent an unmatched state as a fault; a new adapter
class is the correct fit, the same reasoning `adapters/boolean.py`'s own docstring already gives for
why `BooleanReadAdapter` itself is a distinct class from `StatusReadAdapter`.

| Analysis requirement (PR #745) | This slice |
| --- | --- |
| `low_tariff` accepts an entity whose state is not already on/off | Widen `CONF_LOW_TARIFF_ENTITY`'s selector domains (§2) |
| A user-supplied table lists which raw states count as low tariff | New `CONF_LOW_TARIFF_STATES` config field + `_parse_states` reuse (§2) |
| Every other raw state resolves to not-low-tariff (not a fault) | New `LowTariffReadAdapter` (§3) |
| UC12 step 7: low-tariff mapping shown with its own state-translation table | Field added to the existing ungated-mappings step (§2) — no new step, no new gate |

**Out of scope:** widening `home_day_external`/`car_home` the same way — the analysis change is
scoped to `low_tariff` only (PR #745 touches no other adapter role); `BooleanReadAdapter` is
untouched and keeps serving those two roles.

---

## 2. Config-flow surface

`custom_components/smart_charging/config_flow.py`, `UNGATED_MAPPING_SCHEMA` (currently only
`CONF_LOW_TARIFF_ENTITY: _entity(["binary_sensor", "input_boolean"])`):

```python
vol.Optional(CONF_LOW_TARIFF_ENTITY): _entity(
    ["binary_sensor", "input_boolean", "sensor", "input_select"]
),
vol.Optional(CONF_LOW_TARIFF_STATES): str,  # comma-separated raw states, same shape as
                                             # CONF_CONNECTED_STATES/CONF_CHARGING_STATES
```

`const.py` gains one new key, next to `CONF_LOW_TARIFF_ENTITY`:

```python
CONF_LOW_TARIFF_STATES = "low_tariff_states"  # user input: raw states meaning "low tariff"
```

`_split_data` (`config_flow.py`) currently builds `data` as every submitted key not in
`OPTION_KEYS` and not `CONF_CONNECTED_STATES`/`CONF_CHARGING_STATES`, then adds the derived
`CONF_STATUS_TRANSLATION`. `CONF_LOW_TARIFF_STATES` needs no such exclude/derive pair — its raw
comma-separated string is parsed **in place** to a `list[str]` before being stored, reusing the
existing `_parse_states()` helper (already used for `CONF_CONNECTED_STATES`/`CONF_CHARGING_STATES`):

```python
if CONF_LOW_TARIFF_STATES in data:
    data[CONF_LOW_TARIFF_STATES] = _parse_states(data[CONF_LOW_TARIFF_STATES])
```

No new step, no new gate: `low_tariff` stays on the existing ungated `mappings` step
(`STEP_MAPPINGS`, `CONFIG_TABLE`) — UC12 step 7 already presents it unconditionally, and PR #745's
UC12 edit only added a parenthetical to that same field, not a new step.

`OPTIONS_TABLE`/`OPTIONS_FLOW` are untouched: per ADR-0005, an entity mapping (and its
translation) is config-entry **data**, set at install/reconfigure time only, exactly like
`CONF_CONNECTED_STATES`/`CONF_CHARGING_STATES` today.

---

## 3. New adapter

`custom_components/smart_charging/adapters/tariff.py` (new file, one class per role per ADR-0003):

```python
"""Low-tariff adapter: normalizes a tariff signal to a boolean (ADR-0003, RA2 extension)."""

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from ._read_only import _ReadOnlyAdapter


class LowTariffReadAdapter(_ReadOnlyAdapter):
    """Reads the tariff signal and normalizes it to the boolean low-tariff flag.

    A raw state matching HA's native on/off vocabulary is used directly (the
    `binary_sensor`/`input_boolean` case, unchanged from `BooleanReadAdapter`'s prior
    behaviour). Otherwise `low_states` -- the user-supplied list of raw states that
    count as low tariff -- decides membership; any other raw state resolves to
    `False`, not the ADR-0007 fault signal, per the low-tariff flag's own permissive
    default (entity-catalog.md). Returns `None` only when the entity itself is
    missing/unavailable/unknown -- the ADR-0007 fault signal proper.
    """

    def __init__(self, hass: HomeAssistant, entity_id: str, low_states: list[str]) -> None:
        super().__init__(hass, entity_id)
        self._low_states = set(low_states)

    async def read(self) -> bool | None:
        state = self._live_state()
        if state is None:
            return None
        if state.state == STATE_ON:
            return True
        if state.state == STATE_OFF:
            return False
        return state.state in self._low_states
```

`adapters/factory.py`'s `build_adapters` (currently `if data.get(CONF_LOW_TARIFF_ENTITY):
adapters[ROLE_LOW_TARIFF] = BooleanReadAdapter(hass, data[CONF_LOW_TARIFF_ENTITY])`) switches to:

```python
if data.get(CONF_LOW_TARIFF_ENTITY):
    adapters[ROLE_LOW_TARIFF] = LowTariffReadAdapter(
        hass, data[CONF_LOW_TARIFF_ENTITY], data.get(CONF_LOW_TARIFF_STATES, [])
    )
```

`BooleanReadAdapter` is otherwise untouched and keeps building `home_day_external`.

---

## 4. Success criteria

"Works" means: **every existing test passes unchanged, plus new tests proving the widened
selector, the state-translation table's round-trip through the config flow, and the new
adapter's three-way behaviour (native on/off, listed raw state, unlisted raw state).**

1. `CONF_LOW_TARIFF_ENTITY` accepts a `sensor` or `input_select` entity in the config flow, not
   only `binary_sensor`/`input_boolean`.
2. A submitted `CONF_LOW_TARIFF_STATES` comma-separated string is stored in config-entry **data**
   as a parsed `list[str]`, exactly like `CONF_CONNECTED_STATES`/`CONF_CHARGING_STATES` are parsed
   into `CONF_STATUS_TRANSLATION` today.
3. `LowTariffReadAdapter.read()`:
   - returns `True`/`False` directly when the entity's raw state is `on`/`off` (unchanged from
     `BooleanReadAdapter`'s existing behaviour for `binary_sensor`/`input_boolean` mappings — no
     regression for installations that never adopt the new field);
   - returns `True` when the raw state is a member of `low_states`;
   - returns `False` for any other raw state, including when `low_states` is empty (the
     entity-catalog's stated default);
   - returns `None` when the entity is missing/unavailable/unknown (ADR-0007 fault signal,
     unchanged).
4. `low_tariff_entity` left unmapped still builds no adapter (`resolution-rules.md`'s "always
   active" fallback is a **resolution-rules** concern — the flag defaults to active only because
   nothing reads a wired role, not because this adapter returns a default itself — unchanged from
   today).
5. `CONF_LOW_TARIFF_STATES` left unmapped while `CONF_LOW_TARIFF_ENTITY` **is** mapped defaults to
   an empty list (criterion 3's third case) — a non-boolean entity with no configured translation
   always resolves to not-low-tariff, never a fault.

---

## 5. Testing (ADR-0009 harness split)

- `LowTariffReadAdapter` is HA-coupled (reads live entity state via `_ReadOnlyAdapter`), so per
  ADR-0009 its tests are **HA harness**, in a new `tests/adapters/test_tariff.py` (mirroring
  `tests/adapters/test_status.py`'s existing shape for `StatusReadAdapter`): on/off passthrough,
  listed-state membership, unlisted-state default, missing-entity fault.
- `adapters/factory.py`'s `build_adapters` change is covered by extending its existing HA-harness
  test file's `low_tariff` case (whichever file today asserts `ROLE_LOW_TARIFF` resolves to a
  `BooleanReadAdapter` — Task 2 locates and updates it to assert `LowTariffReadAdapter` instead,
  plus a new case passing `CONF_LOW_TARIFF_STATES`).
- `config_flow.py`'s widened selector and the `CONF_LOW_TARIFF_STATES` round-trip are HA harness
  (ADR-0009 — config flow is HA-coupled), extending `tests/test_config_flow.py`'s existing ungated
  `mappings` step coverage.

**Regression**: the full existing suite must pass unchanged, in particular every existing
`low_tariff`/`home_day_external` adapter-factory test and every existing `mappings`-step
config-flow test — `BooleanReadAdapter` and `home_day_external`'s config-flow field are untouched.

---

## 6. Packaging

```text
custom_components/smart_charging/
  adapters/
    tariff.py       # NEW — LowTariffReadAdapter
    factory.py       # low_tariff branch switches from BooleanReadAdapter to LowTariffReadAdapter
  config_flow.py      # CONF_LOW_TARIFF_ENTITY selector widened; + CONF_LOW_TARIFF_STATES field;
                       #   _split_data parses it via _parse_states
  const.py             # + CONF_LOW_TARIFF_STATES
tests/
  adapters/
    test_tariff.py    # NEW
  (existing adapter-factory and config-flow test files gain low_tariff cases)
```

---

## 7. Deliberately deferred

- **Widening `home_day_external`/`car_home` the same way.** Not requested by the merged analysis
  change (PR #745 scopes `low_tariff` only); `BooleanReadAdapter` stays exactly as it is for those
  two roles. A future analysis change would need its own issue if either signal turns out to need
  a translation table too.
- **Rejecting an empty `CONF_LOW_TARIFF_STATES` at config-flow validation time.** The entity-catalog
  wording treats "no list" and "empty list" as the same not-low-tariff default (§4, criterion 5),
  so there is nothing to reject — an empty/absent table is valid, expected input for an
  installation that maps a non-boolean signal but (for whatever reason) currently has no known
  "low" states to list.
- **A dedicated glossary/const name distinguishing the raw input field from a derived value**, the
  shape `CONF_CONNECTED_STATES`/`CONF_CHARGING_STATES` → `CONF_STATUS_TRANSLATION` uses. Not needed
  here: `low_tariff`'s translation is a single flat list, not a two-category split requiring a
  merge step, so the submitted field and the stored value can safely share one key
  (`CONF_LOW_TARIFF_STATES`) parsed in place (§2).

---

## 8. Next step

This design feeds the `writing-plans` skill to produce the ordered, test-driven implementation
plan (`2026-08-17-low-tariff-state-translation.md`). Build order: `LowTariffReadAdapter` (new,
standalone, plain-file HA harness test) → `adapters/factory.py` wiring → `config_flow.py` selector
widening + `CONF_LOW_TARIFF_STATES` field + `_split_data` parsing → full regression pass. No
`custom_components/` code is written until the paired plan exists and is approved.
