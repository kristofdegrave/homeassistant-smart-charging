# RA3 Store — write half: Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan
> task-by-task.

**Goal:** Add the RA3 Store's **write** half — `Store.write(entity_domain, unique_id_suffix,
value)` setting a `float` on an owned `number` entity — per ADR-0018, which decided both halves and
left the write half's sequencing to the implementation spec. This unblocks Task 3.3 of
[`2026-07-21-vehicle-limit-manager.md`](2026-07-21-vehicle-limit-manager.md) (M2 adopting a
vehicle-reported charge limit into `number.smart_charging_soc_limit_override`).

**Architecture:** One new method on the existing `Store` class. It resolves the target with the
same entity-registry lookup `read()` already uses, then applies the value via the
`number.set_value` service so the write goes *through* the real `SocLimitOverrideNumber` entity
(`native_value` + restore-state persistence, ADR-0004) rather than around it. Best-effort: returns
`bool`, never raises. Range clamping stays with the calling Manager, backstopped by the entity's
own bounds via the service call. Full design:
[`2026-08-09-ra3-store-write-half-design.md`](2026-08-09-ra3-store-write-half-design.md).

**Scope guard — this plan does NOT touch `managers/vehicle_limit.py`.** Wiring M2 to call
`Store.write` is Task 3.3 of that Manager's own separately-approved plan, which will be updated
against this method's signature. This plan builds and tests the Store method alone.

**Tech Stack:** Python ≥3.12, Home Assistant, `pytest-homeassistant-custom-component` (HA harness —
both tasks touch the entity registry, the state machine and the service registry, all HA-coupled
per ADR-0009), `ruff`.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

---

## Conventions used throughout

- **Named constants, no magic strings** (CLAUDE.md) — `Platform.NUMBER`, `SERVICE_SET_VALUE`,
  `ATTR_VALUE`, `ATTR_ENTITY_ID` from HA's own modules; `OWNED_SUFFIX_*` from `const.py`. Never a
  bare `"number"`/`"set_value"` literal in `store.py`.
- **`git commit --author="Claude <noreply@anthropic.com>"`** with the trailer
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Re-check `git branch --show-current` before every commit (shared checkout).
- **After every task, run the full existing test suite** (`pytest tests/ -q`) — it must keep
  passing unchanged; nothing outside `adapters/store.py` and `tests/adapters/test_store.py` is
  edited by this plan, so any other failure is a regression to fix before committing.
- `ruff check .` and `ruff format --check .` both clean before each commit.
- **Genuine red before green** — Task W1's first test fails on `AttributeError: 'Store' object has
  no attribute 'write'`; Task W2's tests fail on behavior (an exception escaping / a wrong domain
  being written), not on a missing name.

---

## Task W1: `Store.write()` — resolve + apply a float to an owned `number` entity

**ADR honored:** ADR-0018 (Manager-initiated writes go through the Store's write side),
ADR-0019 (package home: `adapters/store.py`), ADR-0004 (the write lands on the entity, so HA's
restore-state mechanism persists it). **Test boundary:** HA harness,
`tests/adapters/test_store.py`.

**Files:**
- Edit: `custom_components/smart_charging/adapters/store.py`
- Edit: `tests/adapters/test_store.py`

**Step 1: Write the failing tests**

The existing `_register` helper in this file registers an entity id + state string, which is enough
for `read()` but **not** for a service call — no entity object exists to receive
`async_set_native_value`. The write tests therefore set up the real config entry, so the genuine
`SocLimitOverrideNumber` is registered. Add near the existing helper:

```python
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    DOMAIN,
    OWNED_SUFFIX_SOC_LIMIT_OVERRIDE,
)
from tests.helpers import entry_data_base, entry_options_base

SOC_LIMIT_ENTITY_ID = "number.smart_charging_soc_limit_override"


async def _setup_entry(hass):
    """Set up the real integration so the genuine SocLimitOverrideNumber entity exists --
    a registry row + a seeded state string (this file's `_register`) is enough for read(),
    but a service call needs a real entity object to dispatch to."""
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
```

```python
async def test_write_sets_the_real_number_entity(hass):
    """ADR-0018 write half: the value reaches the real entity (native_value + HA state),
    not just the state machine -- so RestoreNumber persists it (ADR-0004)."""
    entry = await _setup_entry(hass)
    store = Store(hass, entry.entry_id)

    assert await store.write(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 70.0) is True
    await hass.async_block_till_done()

    assert float(hass.states.get(SOC_LIMIT_ENTITY_ID).state) == 70.0


async def test_write_goes_through_the_entity_not_around_it(hass):
    """The value survives the entity writing its own state again -- a direct
    hass.states.async_set would be reverted here, since _attr_native_value would be stale."""
    entry = await _setup_entry(hass)
    store = Store(hass, entry.entry_id)
    await store.write(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 70.0)
    await hass.async_block_till_done()

    entity = hass.data["entity_components"][Platform.NUMBER].get_entity(SOC_LIMIT_ENTITY_ID)
    entity.async_write_ha_state()
    await hass.async_block_till_done()

    assert float(hass.states.get(SOC_LIMIT_ENTITY_ID).state) == 70.0


async def test_write_unregistered_entity_returns_false(hass):
    """Startup race: nothing registered for this suffix -- a benign no-op, same as read()."""
    store = Store(hass, "entry1")
    assert await store.write(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 70.0) is False
```

> If `hass.data["entity_components"]` proves awkward to reach in this harness version, the second
> test's forcing property can equivalently be asserted by reading the entity object out of the
> `number` component via `homeassistant.helpers.entity_component.EntityComponent`'s registry — the
> point of the test is *only* that the entity's own subsequent state write preserves the value.
> Do not weaken it into a second copy of the first test.

**Step 2: Run to verify failure** — `pytest tests/adapters/test_store.py -k write -v`: all three
fail with `AttributeError: 'Store' object has no attribute 'write'`.

**Step 3: Implement** — add to `adapters/store.py`:

```python
import logging

from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID, Platform

_LOGGER = logging.getLogger(__name__)


    async def write(self, entity_domain: str, unique_id_suffix: str, value: float) -> bool:
        """Set `value` on this entry's owned `entity_domain` entity identified by
        `unique_id_suffix`. Returns True if applied, False otherwise; never raises
        (symmetric with read(), and the best-effort contract VehicleLimitManager's
        _write_vehicle expects -- ADR-0003/ADR-0018).

        Only the `number` domain is supported: this is the one value shape a caller needs
        today (M2 -> soc_limit_override). Other domains return False rather than issuing a
        number.set_value against an entity that cannot take it -- see the design doc's
        deferrals.
        """
        if entity_domain != Platform.NUMBER:
            _LOGGER.debug("Store.write: unsupported entity domain %s", entity_domain)
            return False
        entity_id = er.async_get(self._hass).async_get_entity_id(
            entity_domain, DOMAIN, f"{self._entry_id}_{unique_id_suffix}"
        )
        if entity_id is None:
            return False
        await self._hass.services.async_call(
            Platform.NUMBER,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
            blocking=True,
        )
        return True
```

(The service call is deliberately still unguarded here — the try/except is Task W2's own
red-green, not shipped ahead of the tests that force it.)

**Step 4: Run to verify pass**, full suite, `ruff` clean, commit.

```bash
git add custom_components/smart_charging/adapters/store.py tests/adapters/test_store.py docs/plans/2026-08-09-ra3-store-write-half-design.md docs/plans/2026-08-09-ra3-store-write-half.md
git commit --author="Claude <noreply@anthropic.com>" -m "$(cat <<'EOF'
feat: RA3 Store.write() for owned number entities (ADR-0018)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task W2: `Store.write()` never raises — failed service call, out-of-range value

**ADR honored:** ADR-0018; ADR-0003 (the best-effort write contract `Adapter.write` /
`VehicleLimitManager._write_vehicle` already establish — the Store guarantees it once, at the
Resource-Access boundary, so no future Manager has to re-implement it). **Test boundary:** HA
harness, `tests/adapters/test_store.py`.

**Files:**
- Edit: `custom_components/smart_charging/adapters/store.py`
- Edit: `tests/adapters/test_store.py`

**Step 1: Write the failing tests**

```python
async def test_write_out_of_range_value_returns_false_and_leaves_entity_unchanged(hass):
    """The clamp is the caller's job (design: Managers hold R6's 50-100 policy) -- the
    entity's own bounds are the backstop, and a violation is a logged no-op, never an
    exception escaping into a Manager's reaction path."""
    entry = await _setup_entry(hass)
    store = Store(hass, entry.entry_id)
    before = hass.states.get(SOC_LIMIT_ENTITY_ID).state

    assert await store.write(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 120.0) is False
    await hass.async_block_till_done()

    assert hass.states.get(SOC_LIMIT_ENTITY_ID).state == before


async def test_write_service_failure_returns_false(hass):
    """A failing service call (entry mid-unload, entity gone) is best-effort, not fatal."""
    entry = await _setup_entry(hass)
    store = Store(hass, entry.entry_id)

    async def _boom(*args, **kwargs):
        raise HomeAssistantError("service unavailable")

    with patch.object(hass.services, "async_call", _boom):
        assert await store.write(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 70.0) is False
```

Imports these tests add: `from unittest.mock import patch` and
`from homeassistant.exceptions import HomeAssistantError`.

**Step 2: Run to verify failure** — genuine red on **behavior**, not a missing name: Task W1's
`write()` calls the service unguarded, so both tests fail with the raised exception propagating out
of `store.write` (HA's `number` component validates `value` against the entity's
`native_min_value`/`native_max_value` and raises for `120.0`, above `SOC_LIMIT_OVERRIDE_MAX`).
Confirm the failure is the escaping exception, not an assertion mismatch — if the out-of-range call
somehow *succeeds*, stop and re-check the entity's bounds before writing any guard, because the
backstop the design doc relies on would not exist.

**Step 3: Implement** — wrap the service call:

```python
        try:
            await self._hass.services.async_call(
                Platform.NUMBER,
                SERVICE_SET_VALUE,
                {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 - best-effort owned-entity write (ADR-0018);
            # an out-of-range value or an entry mid-unload must not break a Manager's
            # reaction path, and is not an ADR-0007 hardware fault either.
            _LOGGER.debug("Store.write %s failed: %s", entity_id, err)
            return False
        return True
```

**Step 4: Run to verify pass**, full suite, `ruff check .` / `ruff format --check .` clean, commit.

```bash
git add custom_components/smart_charging/adapters/store.py tests/adapters/test_store.py
git commit --author="Claude <noreply@anthropic.com>" -m "$(cat <<'EOF'
fix: Store.write() is best-effort and never raises (ADR-0003/0018)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Completion check

- `pytest tests/ -q` fully green; `ruff check .` and `ruff format --check .` clean.
- `git diff main --stat` lists exactly two code paths —
  `custom_components/smart_charging/adapters/store.py` and `tests/adapters/test_store.py` — plus
  this plan's two docs. In particular `managers/vehicle_limit.py`, `number.py`, `coordinator.py`,
  `const.py` and `__init__.py` have **zero** diff (scope guard above).
- `Store.read()`'s body is unchanged — this plan only appends a method.

## Follow-up (not this plan)

- **Task 3.3 of `docs/plans/2026-07-21-vehicle-limit-manager.md`** — update it to call
  `await self._store.write(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, adopted)` with
  `adopted = min(max(float(reported), SOC_LIMIT_OVERRIDE_MIN), SOC_LIMIT_OVERRIDE_MAX)`, replacing
  its retired `_set_default_soc_limit` setter-callback snippet (whose `_SOC_MIN`/`_SOC_MAX`
  constants never landed — `const.py` has `SOC_LIMIT_OVERRIDE_MIN`/`_MAX` instead).
- **Write support for `bool`/`str`/`time` owned entities** (M3's `home_day_flag`, etc.) — no caller
  yet; one task per value shape when one appears, per the design doc's deferrals.
