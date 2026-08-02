# Entity→Coordinator Writes via HA Events Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace every owned *control* entity's held coordinator reference with an entry-scoped
Home Assistant event, per [ADR-0016](../adl/0016-entity-to-coordinator-writes-via-ha-events.md), and
wire the four coordinator fields that have no entity write path at all today
(`home_day_flag`, `departure_dow_defaults`, `departure_holiday_override`,
`departure_home_day_override`) onto that same shape.

**Architecture:** Eight new `EVENT_*` types and three `ATTR_*` payload keys in `const.py`; the
coordinator learns its own `entry_id` and registers eight synchronous `@callback` listeners that
filter on it and delegate to its existing (and four new) setters; `select.py`, `number.py`,
`switch.py` and `time.py` fire events and hold no coordinator. Full design:
[`2026-08-02-entity-coordinator-events-design.md`](2026-08-02-entity-coordinator-events-design.md).
This is **not a pure refactor** — the design names three deliberate observable changes (design §"This
is not a pure internal refactor", and §6.4's four newly-live fields).

**Tech Stack:** Python ≥3.12, `pytest-homeassistant-custom-component` (HA harness), `ruff`.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

---

## Conventions used throughout

- **Test boundary, once for the whole plan:** every test in this plan is **HA harness**
  (`pytest_homeassistant_custom_component`), per [ADR-0009](../adl/0009-testing-strategy.md) and
  design §7. Every production surface this slice touches is `hass.bus`, `DataUpdateCoordinator`,
  or an entity platform — none of it is HA-free logic. (A handful of individual assertions, e.g.
  Task 1's constant-shape checks and Task 9's `hasattr` checks, need no live `hass` fixture
  themselves; they still live in the harness suites because the modules they import do, per
  ADR-0009's file-level split, not because each assertion is independently HA-coupled.) **No new
  test file** is created; assertions land in the six existing suites (`tests/test_select.py`,
  `tests/test_number.py`, `tests/test_time.py`, `tests/test_switch.py`, `tests/test_coordinator.py`,
  `tests/test_init.py`). Individual tasks therefore name only the *files*, not the harness.
- **Named constants, no magic strings** (CLAUDE.md) — every event type and payload key comes from
  `const.py`; no bare `"entry_id"`/`"value"`/`"smart_charging_..."` literals in production **or**
  test code.
- **`git commit --author="Claude <noreply@anthropic.com>"`** with the trailer
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Re-check `git branch --show-current` before every commit (shared checkout).
- Test docstrings name ADR-0016 and the field or criterion the test pins.
- **After every task, run the full existing test suite** (`pytest tests/ -q`) — it must be green
  before the commit. Do not defer this to the end. The one deliberate exception is Task 12, whose
  green depends on Task 13; that pairing is spelled out in both tasks.
- **Genuine red before green.** Two tasks in this plan (Tasks 4 and 5) exist *specifically* because
  their property is invisible unless the preceding task's implementation is deliberately the naive
  one. Tasks 3's listeners are therefore written unfiltered and `async def` on purpose, and Tasks 4
  and 5 are what make them filtered and `@callback`. Do not "helpfully" implement Tasks 4/5's
  behavior inside Task 3 — that would leave the plan's two genuinely new correctness properties
  covered by tests that never failed. If you deviate anyway, you must still prove the red by
  temporarily reverting the property and watching the test fail before you accept green.
- **Line numbers in this plan were verified against the worktree on 2026-08-02** and may drift as
  earlier tasks land. Where a task cites a line, treat it as a pointer to the named symbol, not a
  literal offset.

---

## Task 0: Correct ADR-0016's status (already done)

**Design section honored:** design doc header note. **Test boundary:** none — documentation fix.

**Files:** `docs/adl/0016-entity-to-coordinator-writes-via-ha-events.md`, `docs/adl/README.md` —
already edited while authoring this plan's paired design doc; nothing left to do here.

ADR-0016 merged still marked `Status: Proposed`, and its `docs/adl/README.md` row agreed — the same
pre-merge oversight ADR-0012 and ADR-0014 each had (ADR-0014's own implementation-spec PR fixed its
copy; see that plan's Task 0). Both files on disk already read `Status: Accepted`
(`0016-...md:4`) and the corrected README row (`docs/adl/README.md:25`) before Task 1 starts — an
executing agent should **confirm this with one grep**, not expect a diff to make here:

```bash
grep -n "Status:" docs/adl/0016-entity-to-coordinator-writes-via-ha-events.md
grep -n "0016" docs/adl/README.md
```

These edits land in the same commit as the design/plan docs themselves, not in Task 1's diff.

**Not in this plan:** closing or rebasing PR #452 (`dev/402`). Design §9 records that decision
(Option A — this slice covers all eight fields); it is a human git-hygiene action outside this
plan's `custom_components/` scope.

---

## Task 1: The eight event types and three payload keys

**Design section honored:** §3.1, §3.2, §3.3 (criterion 1).

**Files:**
- Modify: `custom_components/smart_charging/const.py` (insert below the ADR-0011 domain-event block,
  which currently ends at `:24`; **not** inside it)
- Test: `tests/test_coordinator.py`

**Step 1: Write the failing test**

In `tests/test_coordinator.py` (extend the existing
`from custom_components.smart_charging.const import (...)` block, `:7-58`):

```python
def test_owned_entity_change_request_event_names_follow_the_domain_prefix_shape():
    """ADR-0016 criterion 1: eight events, one per externally-writable coordinator field,
    each `smart_charging_<snake_case>` like the existing five EVENT_* constants and each
    ending in `_change_requested` -- the suffix that marks them as inward *requests*, not
    ADR-0011 past-tense domain events."""
    events = [
        EVENT_ACTIVE_MODE_CHANGE_REQUESTED,
        EVENT_ACTIVE_PROFILE_CHANGE_REQUESTED,
        EVENT_TARGET_CURRENT_CHANGE_REQUESTED,
        EVENT_SOC_LIMIT_OVERRIDE_CHANGE_REQUESTED,
        EVENT_HOME_DAY_FLAG_CHANGE_REQUESTED,
        EVENT_WEEKDAY_DEPARTURE_CHANGE_REQUESTED,
        EVENT_HOLIDAY_DEPARTURE_CHANGE_REQUESTED,
        EVENT_HOME_DAY_DEPARTURE_CHANGE_REQUESTED,
    ]
    assert len(set(events)) == 8
    for name in events:
        assert name.startswith(f"{DOMAIN}_")
        assert name.endswith("_change_requested")


def test_change_request_payload_keys_are_named_constants():
    """ADR-0016 §3.2: one shared ATTR_VALUE (the event type already names the field) plus
    ATTR_ENTRY_ID on all eight payloads and ATTR_WEEKDAY on the weekday event only."""
    assert (ATTR_ENTRY_ID, ATTR_VALUE, ATTR_WEEKDAY) == ("entry_id", "value", "weekday")
```

**Step 2: Run to verify failure**

Run: `pytest tests/test_coordinator.py -q`
Expected: collection error — `ImportError: cannot import name 'EVENT_ACTIVE_MODE_CHANGE_REQUESTED'
from 'custom_components.smart_charging.const'`.

**Step 3: Write the minimal implementation**

In `const.py`, immediately **below** the ADR-0011 block (after `:24`,
`EVENT_VEHICLE_CHARGE_LIMIT_RESET`) and above the `# Canonical charger states` header:

```python
# Owned-control-entity change requests (ADR-0016). NOT ADR-0011 domain events: these are
# *inward requests to change state*, fired by an owned control entity at its own coordinator
# before anything has been computed -- not past-tense notifications of a computed transition.
# Hence the `_change_requested` suffix rather than a past-tense transition name. Every payload
# carries ATTR_ENTRY_ID and every listener filters on it: the bus is instance-global, so two
# config entries would otherwise cross-talk (ADR-0016 Decision, mechanic 1).
EVENT_ACTIVE_MODE_CHANGE_REQUESTED = "smart_charging_active_mode_change_requested"
EVENT_ACTIVE_PROFILE_CHANGE_REQUESTED = "smart_charging_active_profile_change_requested"
EVENT_TARGET_CURRENT_CHANGE_REQUESTED = "smart_charging_target_current_change_requested"
EVENT_SOC_LIMIT_OVERRIDE_CHANGE_REQUESTED = "smart_charging_soc_limit_override_change_requested"
EVENT_HOME_DAY_FLAG_CHANGE_REQUESTED = "smart_charging_home_day_flag_change_requested"
EVENT_WEEKDAY_DEPARTURE_CHANGE_REQUESTED = "smart_charging_weekday_departure_change_requested"
EVENT_HOLIDAY_DEPARTURE_CHANGE_REQUESTED = "smart_charging_holiday_departure_change_requested"
EVENT_HOME_DAY_DEPARTURE_CHANGE_REQUESTED = "smart_charging_home_day_departure_change_requested"

# Change-request payload keys (ADR-0016 §3.2). One shared ATTR_VALUE rather than eight
# field-named keys: the event *type* already names the field, so a field-named key would
# restate it in every payload. ATTR_WEEKDAY is the one asymmetry -- departure_dow_defaults is
# a dict, so "which entry" is genuinely part of the request.
ATTR_ENTRY_ID = "entry_id"  # config entry the request is scoped to -- on all eight payloads
ATTR_VALUE = "value"        # the requested new value -- on all eight payloads
ATTR_WEEKDAY = "weekday"    # Monday=0..Sunday=6; EVENT_WEEKDAY_DEPARTURE_CHANGE_REQUESTED only
```

**Step 4: Run to verify pass**

Run: `pytest tests/test_coordinator.py -q` → PASS. Then `pytest tests/ -q`,
`ruff check .`, `ruff format --check .`.

**Step 5: Commit**

```bash
git add custom_components/smart_charging/const.py tests/test_coordinator.py
git commit --author="Claude <noreply@anthropic.com>" -m "$(cat <<'EOF'
Add the eight owned-entity change-request events (ADR-0016 T1)

One EVENT_* per externally-writable coordinator field, plus the three
shared payload keys. Constants only -- nothing fires or listens yet.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: The coordinator learns its own `entry_id`, and the registration entry point

**Design section honored:** §4.1, §4.2, §11 (criterion 3, and §7.2's "Registration guard").

**Files:**
- Modify: `custom_components/smart_charging/coordinator.py`
  (`SmartChargingCoordinator.__init__`, currently `:149`)
- Test: `tests/test_coordinator.py`

**Step 1: Write the failing tests**

```python
async def test_coordinator_records_its_own_entry_id(hass):
    """ADR-0016 §4.1/§11 (decided: defaulted, not required) -- the entry-id filter's source of
    truth is an explicit keyword, not DataUpdateCoordinator.config_entry, which is None for every
    direct construction in tests and would silently disable the filter."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, entry_id="abc"
    )
    assert coord.async_register_owned_entity_listeners() == []


async def test_registration_raises_without_an_entry_id(hass):
    """ADR-0016 §4.1: the default is made safe rather than silent -- a coordinator that cannot
    identify its own entry must refuse to register listeners that could never match, instead of
    registering eight dead subscriptions."""
    coord = SmartChargingCoordinator(hass, adapters=_adapters(), config=_config(), interval_s=30)
    with pytest.raises(RuntimeError):
        coord.async_register_owned_entity_listeners()
```

> The first test asserts `== []` only because Task 2 registers nothing yet; Task 3 replaces that
> assertion with a length check. This is deliberate scaffolding, not a permanent assertion.

**Step 2: Run to verify failure**

Run: `pytest tests/test_coordinator.py -k "entry_id or registration" -v`
Expected: `TypeError: __init__() got an unexpected keyword argument 'entry_id'` for the first,
`AttributeError: ... has no attribute 'async_register_owned_entity_listeners'` for the second.

**Step 3: Write the minimal implementation**

In `coordinator.py`, add to the imports (`homeassistant.core`, currently `:10`):

```python
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
```

(`Event` is not needed until Task 3's handlers reference it as a parameter annotation — add it to
this same import line there, not here. `ruff check .` would flag it F401-unused if added now.)

Change the signature (`:149`) and store the id next to `self._interval_s`:

```python
    def __init__(
        self,
        hass: HomeAssistant,
        *,
        adapters,
        config,
        interval_s: int,
        entry_id: str | None = None,
    ) -> None:
        ...
        self._interval_s = interval_s
        # ADR-0016 §4.1/§11: the entry-id filter's own source of truth. Defaulted to None so the
        # ~44 existing direct constructions in tests/ keep compiling; made safe rather than
        # silent by async_register_owned_entity_listeners' guard below.
        self._entry_id = entry_id
```

Add, immediately above the existing `set_soc_limit_override` (`:617`):

```python
    @callback
    def async_register_owned_entity_listeners(self) -> list[CALLBACK_TYPE]:
        """Subscribe the coordinator to its own owned control entities' change requests
        (ADR-0016 §4.2). `async_`-prefixed but not a coroutine, per HA's convention that the
        prefix means "must be called from the event loop" -- exactly like `hass.bus.async_listen`.
        Returns the unsubscribe callables; the caller (`__init__.py`) hands each to
        `entry.async_on_unload`."""
        if self._entry_id is None:
            raise RuntimeError(
                "SmartChargingCoordinator was constructed without entry_id; its owned-entity "
                "change-request listeners could never match an event (ADR-0016 §4.1)."
            )
        return []
```

**Step 4: Run to verify pass** — the two new tests PASS. Then `pytest tests/ -q` (all 44 existing
direct constructions must still pass **untouched** — that is what the defaulted keyword buys),
`ruff check .`, `ruff format --check .`.

**Step 5: Commit** (`ADR-0016 T2`, message shape as Task 1).

---

## Task 3: Listeners for the four fields that already have entity wiring

**Design section honored:** §4.2, §4.3 (criteria 3 and 6).

**Deliberately naive:** the listeners written here are `async def` and do **not** filter on
`ATTR_ENTRY_ID`. Tasks 4 and 5 are what add those two properties, each behind its own failing test.
See "Genuine red before green" above.

**Files:**
- Modify: `custom_components/smart_charging/coordinator.py`
- Test: `tests/test_coordinator.py`

**Step 1: Write the failing tests**

```python
def _wired(hass, entry_id="abc"):
    """A coordinator with its owned-entity listeners registered (ADR-0016 §4.2)."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, entry_id=entry_id
    )
    coord.async_register_owned_entity_listeners()
    return coord


async def test_active_mode_change_request_applies_the_value(hass):
    """ADR-0016 §4.3: the listener delegates to the coordinator's own setter."""
    coord = _wired(hass)
    hass.bus.async_fire(
        EVENT_ACTIVE_MODE_CHANGE_REQUESTED, {ATTR_ENTRY_ID: "abc", ATTR_VALUE: MODE_SOLAR}
    )
    await hass.async_block_till_done()
    assert coord.active_mode == MODE_SOLAR


async def test_active_profile_change_request_applies_the_value(hass):
    coord = _wired(hass)
    hass.bus.async_fire(
        EVENT_ACTIVE_PROFILE_CHANGE_REQUESTED, {ATTR_ENTRY_ID: "abc", ATTR_VALUE: PROFILE_AUTO}
    )
    await hass.async_block_till_done()
    assert coord.active_profile == PROFILE_AUTO


async def test_target_current_change_request_goes_through_the_clamping_setter(hass):
    """ADR-0016 criterion 6: the clamp stays coordinator-side at set_target_current; the
    listener is a thin unwrap+delegate, so an out-of-range request lands clamped, not raw.
    _config()'s CONF_MAX_CURRENT is 16.0."""
    coord = _wired(hass)
    hass.bus.async_fire(
        EVENT_TARGET_CURRENT_CHANGE_REQUESTED, {ATTR_ENTRY_ID: "abc", ATTR_VALUE: 99.0}
    )
    await hass.async_block_till_done()
    assert coord.target_current == 16.0


async def test_soc_limit_override_change_request_goes_through_the_clamping_setter(hass):
    coord = _wired(hass)
    hass.bus.async_fire(
        EVENT_SOC_LIMIT_OVERRIDE_CHANGE_REQUESTED, {ATTR_ENTRY_ID: "abc", ATTR_VALUE: 10.0}
    )
    await hass.async_block_till_done()
    assert coord.soc_limit_override == SOC_LIMIT_OVERRIDE_MIN


async def test_change_request_schedules_a_refresh(hass):
    """ADR-0016 §5: the awaited refresh moves from the entity to the listener. Pairs with
    Task 4's mismatch test, which asserts the negative."""
    coord = _wired(hass)
    refresh = AsyncMock()
    coord.async_request_refresh = refresh
    hass.bus.async_fire(
        EVENT_ACTIVE_MODE_CHANGE_REQUESTED, {ATTR_ENTRY_ID: "abc", ATTR_VALUE: MODE_OFF}
    )
    await hass.async_block_till_done()
    refresh.assert_awaited_once()
```

`AsyncMock` comes from `unittest.mock` — add the import to `tests/test_coordinator.py`. An
`AsyncMock` is used rather than a hand-rolled lambda because Task 5 turns the listener's
`await self.async_request_refresh()` into `hass.async_create_task(self.async_request_refresh())`,
and the spy has to keep returning an awaitable across that change.

Also update Task 2's scaffold assertion:
`assert coord.async_register_owned_entity_listeners() == []` becomes
`assert len(coord.async_register_owned_entity_listeners()) == 4` (it becomes `== 8` in Task 11).

**Step 2: Run to verify failure**

Run: `pytest tests/test_coordinator.py -k change_request -v`
Expected: all five fail — `assert coord.active_mode == 'Solar'` where `active_mode` is still
`MODE_POWER` (nothing is subscribed), and the registration-count assertion fails `0 == 4`.

**Step 3: Write the minimal implementation**

In `coordinator.py`, add `Event` to the `homeassistant.core` import (Task 2 deliberately left it out
— it's unused until these four handlers reference it as a parameter annotation):
`from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback`. Extend the
`from .const import (...)` block with the four event constants and `ATTR_ENTRY_ID`/`ATTR_VALUE`.
Fill in the registration list:

```python
        return [
            self.hass.bus.async_listen(
                EVENT_ACTIVE_MODE_CHANGE_REQUESTED, self._on_active_mode_requested
            ),
            self.hass.bus.async_listen(
                EVENT_ACTIVE_PROFILE_CHANGE_REQUESTED, self._on_active_profile_requested
            ),
            self.hass.bus.async_listen(
                EVENT_TARGET_CURRENT_CHANGE_REQUESTED, self._on_target_current_requested
            ),
            self.hass.bus.async_listen(
                EVENT_SOC_LIMIT_OVERRIDE_CHANGE_REQUESTED,
                self._on_soc_limit_override_requested,
            ),
        ]
```

And the four handlers, next to the existing setters they delegate to (`:617-656`) — **naive shape,
Tasks 4 and 5 fix both defects**:

```python
    async def _on_active_mode_requested(self, event: Event) -> None:
        self.set_active_mode(event.data[ATTR_VALUE])
        await self.async_request_refresh()

    async def _on_active_profile_requested(self, event: Event) -> None:
        self.set_active_profile(event.data[ATTR_VALUE])
        await self.async_request_refresh()

    async def _on_target_current_requested(self, event: Event) -> None:
        self.set_target_current(event.data[ATTR_VALUE])
        await self.async_request_refresh()

    async def _on_soc_limit_override_requested(self, event: Event) -> None:
        self.set_soc_limit_override(event.data[ATTR_VALUE])
        await self.async_request_refresh()
```

**Step 4: Run to verify pass** — five new tests PASS; `pytest tests/ -q` green;
`ruff check .` + `ruff format --check .` clean.

**Step 5: Commit** (`ADR-0016 T3`).

---

## Task 4: The entry-id filter — cross-config-entry cross-talk

**Design section honored:** §4.4, §7.2 criterion 5. **This is one of the two genuinely new
correctness properties ADR-0016 introduces**, and it has its own task precisely so it cannot be
buried inside Task 3's bulk. The held reference could not have this bug; the event bus can, and
the filter is the only thing preventing it.

**Files:**
- Modify: `custom_components/smart_charging/coordinator.py`
- Test: `tests/test_coordinator.py`

**Step 1: Write the failing test**

```python
@pytest.mark.parametrize(
    ("event_type", "value", "field", "unchanged"),
    [
        (EVENT_ACTIVE_MODE_CHANGE_REQUESTED, MODE_SOLAR, "active_mode", MODE_POWER),
        (EVENT_ACTIVE_PROFILE_CHANGE_REQUESTED, PROFILE_AUTO, "active_profile", PROFILE_MANUAL),
        (EVENT_TARGET_CURRENT_CHANGE_REQUESTED, 12.0, "target_current", 0.0),
        (
            EVENT_SOC_LIMIT_OVERRIDE_CHANGE_REQUESTED,
            90.0,
            "soc_limit_override",
            DEFAULT_SOC_LIMIT,
        ),
    ],
)
async def test_change_request_from_another_config_entry_is_ignored(
    hass, event_type, value, field, unchanged
):
    """ADR-0016 §4.4 / criterion 5: the HA bus is instance-global, so with two config entries
    both coordinators see all eight event types. A listener applies only when ATTR_ENTRY_ID
    matches its own -- otherwise entry A's mode selector would rewrite entry B's active_mode.
    Asserts the field is *unchanged*, not merely that nothing raised: a missing filter is
    invisible in a single-entry suite."""
    coord = _wired(hass, entry_id="abc")
    refresh = AsyncMock()
    coord.async_request_refresh = refresh
    hass.bus.async_fire(event_type, {ATTR_ENTRY_ID: "other", ATTR_VALUE: value})
    await hass.async_block_till_done()
    assert getattr(coord, field) == unchanged
    refresh.assert_not_awaited()          # and no refresh was requested either
```

**Step 2: Run to verify failure**

Run: `pytest tests/test_coordinator.py -k another_config_entry -v`
Expected: all four parametrizations FAIL — e.g. `assert 'Solar' == 'Power'` — because Task 3's
listeners apply unconditionally, and `assert [1] == []` for the refresh half.

**Step 3: Write the minimal implementation**

Add the early return as the first statement of each of the four handlers:

```python
    async def _on_active_mode_requested(self, event: Event) -> None:
        if event.data.get(ATTR_ENTRY_ID) != self._entry_id:
            return  # another config entry's entity -- not ours (ADR-0016 §4.4)
        self.set_active_mode(event.data[ATTR_VALUE])
        await self.async_request_refresh()
```

`.get()` rather than `[...]`: a third-party event fired with no `entry_id` at all must be ignored,
not raise inside the bus dispatch.

**Step 4: Run to verify pass** — the four parametrizations PASS, Task 3's matching-id tests still
PASS. `pytest tests/ -q`, `ruff check .`, `ruff format --check .`.

**Step 5: Commit** (`ADR-0016 T4`).

---

## Task 5: Synchronous `@callback` listeners — apply-before-refresh ordering

**Design section honored:** §4.2, §4.3, §7.2 criterion 4. **This is the second genuinely new
correctness property**, and likewise gets its own task. It is the only test that distinguishes a
`@callback` listener from a coroutine one, and ADR-0016's "Harder" consequence explicitly asks
for it.

**Files:**
- Modify: `custom_components/smart_charging/coordinator.py`
- Test: `tests/test_coordinator.py`

**Step 1: Write the failing test**

```python
async def test_change_request_is_applied_synchronously_inside_async_fire(hass):
    """ADR-0016 criterion 4: every listener is a sync `@callback`, never `async def`. HA runs a
    `@callback` listener inline inside `async_fire`, which is what preserves 'the coordinator's
    field is applied before the refresh it triggers'. Note the deliberate absence of
    `await hass.async_block_till_done()` -- a coroutine listener is scheduled as a separate task
    and fails here; a @callback listener passes."""
    coord = _wired(hass)
    hass.bus.async_fire(
        EVENT_ACTIVE_MODE_CHANGE_REQUESTED, {ATTR_ENTRY_ID: "abc", ATTR_VALUE: MODE_SOLAR}
    )
    assert coord.active_mode == MODE_SOLAR      # no await in between -- this is the whole point
    await hass.async_block_till_done()          # drain the scheduled refresh so the test is clean
```

**Step 2: Run to verify failure**

Run: `pytest tests/test_coordinator.py -k synchronously -v`
Expected: FAIL — `assert 'Power' == 'Solar'`. Task 3's `async def` handler has only been
*scheduled* when `async_fire` returns.

**Step 3: Write the minimal implementation**

Convert all four handlers to sync `@callback`, and introduce the one shared refresh helper (a sync
callback cannot `await`):

```python
    @callback
    def _schedule_refresh(self) -> None:
        """Schedule the refresh a listener used to `await` at the entity (ADR-0016 §4.3). A sync
        `@callback` cannot await, and `async_request_refresh` is already debounced, so scheduling
        it is the correct translation -- and it is scheduled *after* the field is applied, in the
        same synchronous block, which is criterion 4's ordering guarantee."""
        self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _on_active_mode_requested(self, event: Event) -> None:
        if event.data.get(ATTR_ENTRY_ID) != self._entry_id:
            return  # another config entry's entity -- not ours (ADR-0016 §4.4)
        self.set_active_mode(event.data[ATTR_VALUE])
        self._schedule_refresh()
```

…and the same for `_on_active_profile_requested`, `_on_target_current_requested`,
`_on_soc_limit_override_requested`. Update the docstring on
`async_register_owned_entity_listeners` to state the `@callback`-never-coroutine rule
(design §4.2's docstring text).

**Step 4: Run to verify pass** — the ordering test PASSES; Tasks 3 and 4's tests still pass
(the `AsyncMock` spies there now return a coroutine that `async_create_task` schedules rather than
one the listener awaits directly — `await hass.async_block_till_done()` still drains it, so the
`assert_awaited_once` / `assert_not_awaited` expectations hold unchanged; verify rather than assume).
`pytest tests/ -q`, `ruff check .`,
`ruff format --check .`.

**Step 5: Commit** (`ADR-0016 T5`).

---

## Task 6: `__init__.py` — pass the entry id, register before platforms, unregister on unload

**Design section honored:** §4.5 (as summarized in §8's packaging table), §7.3 (criterion 8's
production half).

**Files:**
- Modify: `custom_components/smart_charging/__init__.py` (`:130-145`)
- Test: `tests/test_init.py` (the deeper setup/teardown assertions are Tasks 14 and 15; this task
  only needs the entry-id to reach the coordinator)

**Step 1: Write the failing test**

In `tests/test_init.py`:

```python
async def test_setup_gives_the_coordinator_its_own_entry_id(hass):
    """ADR-0016 §4.1: __init__.py is the one place that knows the entry id; without it every
    change-request listener would filter itself out."""
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    assert coordinator._entry_id == entry.entry_id
```

**Step 2: Run to verify failure**

Run: `pytest tests/test_init.py -k own_entry_id -v`
Expected: FAIL — `assert None == '<entry_id>'`.

**Step 3: Write the minimal implementation**

```python
    coordinator = SmartChargingCoordinator(
        hass,
        adapters=adapters,
        config=config,
        interval_s=interval_s,
        entry_id=entry.entry_id,
    )
    ...
    # ADR-0016: register BEFORE forwarding the platforms, so an entity's async_added_to_hass
    # seed event is not fired into a bus nobody is listening on. Each unsub goes through
    # entry.async_on_unload, so an ADR-0008 reload cannot leak a duplicate subscription.
    for unsub in coordinator.async_register_owned_entity_listeners():
        entry.async_on_unload(unsub)

    # First refresh AFTER platforms so the number entity can seed target_current on add.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
```

The registration loop goes **between** the `hass.data.setdefault(...)` block (`:135-141`) and the
existing `async_forward_entry_setups` call (`:144`). Do not reorder the existing
`async_forward_entry_setups` / `async_config_entry_first_refresh` pair.

**Step 4: Run to verify pass** — new test PASSES; `pytest tests/ -q` green; ruff clean.

**Step 5: Commit** (`ADR-0016 T6`).

---

## Task 7: `select.py` fires events; delete `test_select.py`'s two coordinator doubles

**Design section honored:** §5's before/after table (rows `select.py:40-56` … `:100-117`), §7.1
(criterion 2).

**Files:**
- Modify: `custom_components/smart_charging/select.py`
- Modify: `tests/test_select.py`

**Step 1: Write the failing tests — starting with the deletions**

Delete `_StubCoordinator` (`tests/test_select.py:13-26`) and `_StubProfileCoordinator` (`:119-134`)
outright. They are not adapted: **there is no coordinator to double** — that is the point of
ADR-0016 — and their `refreshed` flag has nothing left to assert against, because the refresh is no
longer the entity's.

Then remove `coordinator=coord` / `coordinator=_StubCoordinator()` from **every** construction in the
file (`:31, :44, :56, :68, :78, :86, :91, :96, :110-115, :138, :145, :160, :175, :185, :193`), and
convert the four write-path/seed assertions from `coord.active_mode == ...` to event-payload
assertions, e.g.:

```python
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.smart_charging.const import (
    ATTR_ENTRY_ID,
    ATTR_VALUE,
    EVENT_ACTIVE_MODE_CHANGE_REQUESTED,
    EVENT_ACTIVE_PROFILE_CHANGE_REQUESTED,
    MODE_OFF,
    MODE_SOLAR,
)


async def test_select_option_requests_an_active_mode_change(hass):
    """ADR-0016: the entity fires an entry-scoped request instead of holding a coordinator.
    Whole-dict equality, not just the value key, so a missing ATTR_ENTRY_ID fails loudly."""
    events = async_capture_events(hass, EVENT_ACTIVE_MODE_CHANGE_REQUESTED)
    entity = ModeSelect(entry_id="abc", solar_installed=True)
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    await entity.async_select_option(MODE_SOLAR)
    await hass.async_block_till_done()
    assert events[-1].data == {ATTR_ENTRY_ID: "abc", ATTR_VALUE: MODE_SOLAR}
    assert entity.current_option == MODE_SOLAR
```

`events[-1]` because `async_added_to_hass` fires a seed event too — and that seeding fire is itself
what the restore tests now assert (`test_restores_last_selection`,
`test_restore_rejects_solar_option_when_solar_not_installed`,
`test_restore_rejects_captar_option_when_captar_not_available`,
`test_added_to_hass_seeds_coordinator_with_default_when_no_restored_state` and their four
`ProfileSelect` counterparts): each becomes `assert events[0].data == {ATTR_ENTRY_ID: "abc",
ATTR_VALUE: <restored-or-default>}`. Rename the two `*_seeds_coordinator_*` tests to
`*_requests_*` — nothing seeds a coordinator from here any more.

**Step 2: Run to verify failure**

Run: `pytest tests/test_select.py -v`
Expected: every test in the file FAILS with
`TypeError: ModeSelect.__init__() missing 1 required positional argument: 'coordinator'`. That is
the genuine red for the whole file: the constructions no longer match today's signature. If any test in
this file stays green, a `coordinator=` argument was missed.

**Step 3: Write the minimal implementation**

In `select.py`:

- `ModeSelect.__init__` (`:40-46`): drop the `coordinator` parameter; delete `:48`
  (`self._coordinator = coordinator`).
- `async_added_to_hass` `:63`:
  ```python
  self.hass.bus.async_fire(
      EVENT_ACTIVE_MODE_CHANGE_REQUESTED,
      {ATTR_ENTRY_ID: self._entry_id, ATTR_VALUE: self._attr_current_option},
  )
  ```
- `async_select_option` `:67`: same `async_fire`, with `ATTR_VALUE: option`. **Delete `:68`**
  (`await self._coordinator.async_request_refresh()`) — the refresh is now the coordinator
  listener's (§4.3). `:66` and `:69` are unchanged.
- `ProfileSelect.__init__` (`:80`): drop `coordinator`; delete `:82`. `:91` and `:95` become
  `async_fire(EVENT_ACTIVE_PROFILE_CHANGE_REQUESTED, ...)`; **delete `:96`**.
- `async_setup_entry`: delete `:103` (the `hass.data[DOMAIN][entry.entry_id]["coordinator"]` read)
  and drop `coordinator=coordinator` from both constructor calls (criterion 9).
- Imports: `DOMAIN` becomes unused in this module — **remove it** from the `.const` import block and
  add `ATTR_ENTRY_ID`, `ATTR_VALUE`, `EVENT_ACTIVE_MODE_CHANGE_REQUESTED`,
  `EVENT_ACTIVE_PROFILE_CHANGE_REQUESTED`. `HomeAssistant` stays — it is still the
  `async_setup_entry` parameter annotation. (`ruff check .` will catch the `DOMAIN` slip if missed.)

`self._entry_id` needs no new plumbing: `SmartChargingEntity.__init__`
(`custom_components/smart_charging/entity.py:18`) already sets it from the `entry_id` argument both
classes already pass.

**Step 4: Run to verify pass** — `pytest tests/test_select.py -v` all green, then `pytest tests/ -q`
(`tests/test_init.py::test_select_entity_is_registered_on_setup` and
`::test_select_omits_captar_when_unavailable` go through the real coordinator and must still pass —
they now exercise the full fire→listen→apply path for the first time), `ruff check .`,
`ruff format --check .`.

**Step 5: Commit** (`ADR-0016 T7`).

---

## Task 8: `number.py` fires events; delete `test_number.py`'s coordinator double

**Design section honored:** §5's before/after table (rows `number.py:31-43` … `:101-121`), §7.1,
criteria 7 and 9.

**Files:**
- Modify: `custom_components/smart_charging/number.py`
- Modify: `tests/test_number.py`

**Step 1: Write the failing tests — starting with the deletion**

Delete `_StubCoordinator` (`tests/test_number.py:17-38`) — the single double shared by both number
entities. Strip `coordinator=coord` / `coordinator=_StubCoordinator()` from all thirteen
constructions in the file (`:44, 57, 70, 79, 87, 114, 125, 136, 147, 174, 200, 226, 237`), and
convert the write-path/seed assertions to event assertions in the same shape as Task 7:

```python
async def test_set_value_requests_a_target_current_change(hass):
    events = async_capture_events(hass, EVENT_TARGET_CURRENT_CHANGE_REQUESTED)
    entity = TargetCurrentNumber(entry_id="abc", min_a=6.0, max_a=16.0, default=10.0)
    platform = MockEntityPlatform(hass, domain="number")
    await platform.async_add_entities([entity])
    await entity.async_set_native_value(12.0)
    await hass.async_block_till_done()
    assert events[-1].data == {ATTR_ENTRY_ID: "abc", ATTR_VALUE: 12.0}
    assert entity.native_value == 12.0
```

Tests that must keep their **existing** assertions and only lose the `coordinator=` argument
(criterion 7 — a signature edit, not a behavior edit):
`test_init_seeds_bounds_and_default`, `test_init_clamps_out_of_range_default_target_current`,
`test_init_clamps_out_of_range_default_target_current_below_minimum`,
`test_soc_limit_override_init_seeds_bounds_and_default`,
`test_init_clamps_out_of_range_default_soc_limit`, and the two restore-clamp tests
`test_soc_limit_override_added_to_hass_clamps_restored_value_above_max` / `_below_min` (their
`entity.native_value` assertions stay; their `coord.soc_limit_override` assertions become
`events[0].data` assertions).

**Step 2: Run to verify failure**

Run: `pytest tests/test_number.py -v`
Expected: every test FAILS with `TypeError: __init__() missing 1 required positional argument:
'coordinator'`.

**Step 3: Write the minimal implementation**

In `number.py`:

- `TargetCurrentNumber.__init__` (`:31-33`): drop `coordinator`; delete `:35`. **`:37-43` unchanged**,
  including the `:43` default clamp (criterion 7).
- `:54` → `async_fire(EVENT_TARGET_CURRENT_CHANGE_REQUESTED, {ATTR_ENTRY_ID: self._entry_id,
  ATTR_VALUE: self._attr_native_value})`.
- `async_set_native_value` `:58` → the same `async_fire` with `ATTR_VALUE: value`; **delete `:59`**.
- `SocLimitOverrideNumber.__init__` (`:74`): drop `coordinator`; delete `:76`. **`:82`'s default
  clamp unchanged.**
- `:92` / `:96` → `async_fire(EVENT_SOC_LIMIT_OVERRIDE_CHANGE_REQUESTED, ...)`;
  **delete `:97`**.
- `async_setup_entry`: delete `:105` (`coordinator = data["coordinator"]`) and drop
  `coordinator=coordinator` from both constructions. **`:104`'s `data = hass.data[DOMAIN][entry.entry_id]`
  stays** — it is still the source of `CONF_MIN_CURRENT`/`CONF_MAX_CURRENT`/the two defaults, so
  `DOMAIN` stays imported here (unlike `select.py`). Only the `"coordinator"` key goes away.
- Add `ATTR_ENTRY_ID`, `ATTR_VALUE`, `EVENT_SOC_LIMIT_OVERRIDE_CHANGE_REQUESTED`,
  `EVENT_TARGET_CURRENT_CHANGE_REQUESTED` to the `.const` import block.

Both restore paths (`:47-52`, `:86-91`) and both entity-side clamps are untouched.

**Step 4: Run to verify pass** — `pytest tests/test_number.py -v` green; `pytest tests/ -q` green
(`test_init.py::test_end_to_end_commands_target_current` now exercises fire→listen→apply for
`target_current` end to end, and `test_setup_falls_back_to_default_soc_limit_for_pre_solar_entries`
for `soc_limit_override` — confirm both still pass rather than assuming). `ruff check .`,
`ruff format --check .`.

**Step 5: Commit** (`ADR-0016 T8`).

---

## Task 9: No-double, no-reference audit

**Design section honored:** §7.1's criterion 2 — *"Checkable two ways, both required"*. Tasks 7 and 8
each satisfied one way (the constructions pass no coordinator and would `TypeError` against the old
signature). This task adds the second, which is what catches a reference **re-introduced later by a
different route**, and makes the grep half an executable, non-optional check rather than a habit.

**Files:**
- Modify: `tests/test_select.py`, `tests/test_number.py`
- Verify only: `custom_components/smart_charging/select.py`, `number.py`, `time.py`, `switch.py`

**Step 1: Write the failing tests**

Add one `hasattr` assertion per owned control-entity class — four here (`ModeSelect`,
`ProfileSelect`, `TargetCurrentNumber`, `SocLimitOverrideNumber`), plus `HomeDaySwitch` and
`SmartChargingDepartureTime` which Tasks 10 and 12 will add their own copies of (six in all):

```python
def test_mode_select_holds_no_coordinator_reference():
    """ADR-0016 criterion 2, the standing half: the constructions in this file already prove the
    signature has no `coordinator`; this catches a reference re-introduced by a different route
    (a lazy hass.data lookup, an attribute set in async_added_to_hass, ...)."""
    entity = ModeSelect(entry_id="abc", solar_installed=True)
    assert not hasattr(entity, "_coordinator")


def test_profile_select_holds_no_coordinator_reference():
    assert not hasattr(ProfileSelect(entry_id="abc"), "_coordinator")
```

…and in `tests/test_number.py`, the same two for `TargetCurrentNumber(entry_id="abc", min_a=6.0,
max_a=16.0, default=10.0)` and `SocLimitOverrideNumber(entry_id="abc", default=80.0)`.

**Step 2: Run to verify failure** — these pass immediately after Tasks 7/8, so **prove the red the
other way**: temporarily re-add `self._coordinator = None` to `ModeSelect.__init__`, run
`pytest tests/test_select.py -k no_coordinator -v`, watch it FAIL, then revert. Record that you did
this; do not accept a green assertion you never saw fail.

**Step 3: Run the grep half**

```bash
grep -rn "_coordinator" custom_components/smart_charging/select.py \
    custom_components/smart_charging/number.py \
    custom_components/smart_charging/time.py \
    custom_components/smart_charging/switch.py
grep -rn "_StubCoordinator\|_StubProfileCoordinator" tests/
grep -rn '\["coordinator"\]' custom_components/smart_charging/select.py \
    custom_components/smart_charging/time.py custom_components/smart_charging/switch.py
```

All three must return **nothing**. (`number.py`'s and `sensor.py`'s `hass.data` reads are out of
scope — `number.py` keeps its `data = hass.data[DOMAIN][entry.entry_id]` for the `CONF_*` values,
criterion 9; `sensor.py`'s coordinator reference is the read direction, design §10.)

**Step 4: Run to verify pass** — `pytest tests/ -q` green, ruff clean.

**Step 5: Commit** (`ADR-0016 T9`).

---

## Task 10: `home_day_flag` — coordinator setters, listener, and `switch.py` wiring

**Design section honored:** §3.1 (one event for one field, not two for the two setter methods),
§4.3, §6.2, §6.4. **New wiring, not a migration** — `switch.py` holds no coordinator today and
`coordinator.py:196` still defaults `home_day_flag` to `False` with a comment pointing at issue #402.

**Files:**
- Modify: `custom_components/smart_charging/coordinator.py`
- Modify: `custom_components/smart_charging/switch.py`
- Modify: `tests/test_coordinator.py`, `tests/test_switch.py`

**Step 1: Write the failing tests**

In `tests/test_coordinator.py`:

```python
@pytest.mark.parametrize(("requested", "expected"), [(True, True), (False, False)])
async def test_home_day_flag_change_request_applies_the_boolean(hass, requested, expected):
    """ADR-0016 §6.2: one event carrying a boolean, not two events for activate/deactivate --
    the per-event rule counts coordinator *fields*, and home_day_flag is one field. The
    action-named setters survive inside the coordinator; they just don't cross the bus."""
    coord = _wired(hass)
    coord.home_day_flag = not expected
    hass.bus.async_fire(
        EVENT_HOME_DAY_FLAG_CHANGE_REQUESTED, {ATTR_ENTRY_ID: "abc", ATTR_VALUE: requested}
    )
    await hass.async_block_till_done()
    assert coord.home_day_flag is expected


async def test_home_day_flag_change_request_from_another_entry_is_ignored(hass):
    coord = _wired(hass, entry_id="abc")
    hass.bus.async_fire(
        EVENT_HOME_DAY_FLAG_CHANGE_REQUESTED, {ATTR_ENTRY_ID: "other", ATTR_VALUE: True}
    )
    await hass.async_block_till_done()
    assert coord.home_day_flag is False
```

In `tests/test_switch.py` — four fire sites (§6.2), the midnight reset being the one that matters
most and is easiest to forget:

```python
async def test_turn_on_requests_the_home_day_flag(hass):
    events = async_capture_events(hass, EVENT_HOME_DAY_FLAG_CHANGE_REQUESTED)
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    await entity.async_turn_on()
    await hass.async_block_till_done()
    assert events[-1].data == {ATTR_ENTRY_ID: "abc", ATTR_VALUE: True}
    await entity.async_remove()


async def test_turn_off_requests_the_home_day_flag(hass):
    ...  # same shape, ATTR_VALUE: False


async def test_added_to_hass_requests_the_initial_off_state(hass):
    """Seeds the coordinator on add, mirroring ModeSelect (§6.2)."""
    events = async_capture_events(hass, EVENT_HOME_DAY_FLAG_CHANGE_REQUESTED)
    entity = HomeDaySwitch(entry_id="abc")
    await MockEntityPlatform(hass, domain="switch").async_add_entities([entity])
    await hass.async_block_till_done()
    assert events[0].data == {ATTR_ENTRY_ID: "abc", ATTR_VALUE: False}
    await entity.async_remove()


async def test_midnight_reset_requests_the_home_day_flag_off(hass):
    """R13's daily expiry has to reach the coordinator, not just the entity's own is_on --
    the fire site §6.2 calls out as the one most easily forgotten."""
    events = async_capture_events(hass, EVENT_HOME_DAY_FLAG_CHANGE_REQUESTED)
    entity = HomeDaySwitch(entry_id="abc")
    await MockEntityPlatform(hass, domain="switch").async_add_entities([entity])
    await entity.async_turn_on()
    async_fire_time_changed(hass, dt_util.start_of_local_day() + timedelta(days=1))
    await hass.async_block_till_done()
    assert events[-1].data == {ATTR_ENTRY_ID: "abc", ATTR_VALUE: False}
    await entity.async_remove()


def test_home_day_switch_holds_no_coordinator_reference():
    assert not hasattr(HomeDaySwitch(entry_id="abc"), "_coordinator")
```

**Step 2: Run to verify failure**

Run: `pytest tests/test_coordinator.py tests/test_switch.py -k home_day -v`
Expected: coordinator tests FAIL (`assert False is True` — nothing is subscribed); switch tests FAIL
with `IndexError: list index out of range` (no event is fired at all).

**Step 3: Write the minimal implementation**

In `coordinator.py`, next to the existing setters:

```python
    def activate_home_day(self) -> None:
        """R9/R13's home-day flag, set (ADR-0016 §6.2 keeps the action-named vocabulary inside
        the coordinator; what crosses the bus is one event carrying a boolean)."""
        self.home_day_flag = True

    def deactivate_home_day(self) -> None:
        """R9/R13's home-day flag, cleared -- including R13's daily midnight expiry."""
        self.home_day_flag = False

    @callback
    def _on_home_day_flag_requested(self, event: Event) -> None:
        if event.data.get(ATTR_ENTRY_ID) != self._entry_id:
            return
        if event.data[ATTR_VALUE]:
            self.activate_home_day()
        else:
            self.deactivate_home_day()
        self._schedule_refresh()
```

Register it in `async_register_owned_entity_listeners` (the returned list becomes 5; update Task 2's
count assertion to `== 5`). Delete the now-false half of `coordinator.py:191-195`'s comment — the
`home_day_flag` line no longer says "that entity->coordinator wiring is not yet threaded (tracked
separately, issue #402)"; the departure lines keep it until Task 11.

In `switch.py`:

```python
    def _fire_change_request(self) -> None:
        self.hass.bus.async_fire(
            EVENT_HOME_DAY_FLAG_CHANGE_REQUESTED,
            {ATTR_ENTRY_ID: self._entry_id, ATTR_VALUE: self._attr_is_on},
        )
```

Called from four places, none awaiting a refresh: `async_added_to_hass` (`:31-35`, after the
midnight-reset subscription), `_async_reset_at_midnight` (`:43-45`), `async_turn_on` (`:47-49`) and
`async_turn_off` (`:51-53`) — in each of the last three, between the `_attr_is_on` assignment and
`self.async_write_ha_state()`. `async_will_remove_from_hass` (`:37-41`) is **unchanged** — that
unsubscribe is the entity's own timer, unrelated to the event bus. `async_setup_entry` (`:56-59`) is
unchanged: it does not look up a coordinator today and does not start to (§6.3).

**Step 4: Run to verify pass** — all new tests PASS. Then `pytest tests/ -q`: `home_day_flag`
becoming genuinely live is a §6.4 behavior change, but the switch seeds `False`, which equals
today's default, so no end-to-end expectation should move. **Confirm that rather than assume it** —
`tests/test_init.py::test_solar_reserve_soc_option_threaded_engages_configured_cap_live` and
`tests/test_deadline_soc_management_end_to_end.py` (`:390, :421, :443`) set `home_day_flag = True`
directly *after* setup, so their direct assignment still wins. `ruff check .`,
`ruff format --check .`.

**Step 5: Commit** (`ADR-0016 T10`).

---

## Task 11: The three departure fields — coordinator setters and listeners

**Design section honored:** §3.2 (`ATTR_WEEKDAY`), §3.3 (ISO-8601 on the bus, not a `datetime.time`),
§4.3. Coordinator side only — `time.py`'s call sites are Task 12, which is exactly the
"each listener can land and be tested before its call site moves" independence §8.1 notes.

**Files:**
- Modify: `custom_components/smart_charging/coordinator.py`
- Modify: `tests/test_coordinator.py`

**Step 1: Write the failing tests**

```python
async def test_weekday_departure_change_request_writes_only_that_weekday(hass):
    """ADR-0016 §3.2: the seven day-of-week `time` entities all write ONE coordinator field
    (departure_dow_defaults, a dict), so they share one event carrying a weekday key --
    Monday=0..Sunday=6, matching datetime.date.weekday() and time.py's Monday-first
    DAY_OF_WEEK_DEFAULTS ordering."""
    coord = _wired(hass)
    hass.bus.async_fire(
        EVENT_WEEKDAY_DEPARTURE_CHANGE_REQUESTED,
        {ATTR_ENTRY_ID: "abc", ATTR_WEEKDAY: 2, ATTR_VALUE: "07:30:00"},
    )
    await hass.async_block_till_done()
    assert coord.departure_dow_defaults[2] == time(7, 30)
    assert all(coord.departure_dow_defaults[d] is None for d in (0, 1, 3, 4, 5, 6))


async def test_weekday_departure_change_request_clears_on_none(hass):
    """§3.3: None is a valid value (no departure configured), not a missing key."""
    coord = _wired(hass)
    coord.departure_dow_defaults[2] = time(7, 30)
    hass.bus.async_fire(
        EVENT_WEEKDAY_DEPARTURE_CHANGE_REQUESTED,
        {ATTR_ENTRY_ID: "abc", ATTR_WEEKDAY: 2, ATTR_VALUE: None},
    )
    await hass.async_block_till_done()
    assert coord.departure_dow_defaults[2] is None


@pytest.mark.parametrize(
    ("event_type", "field"),
    [
        (EVENT_HOLIDAY_DEPARTURE_CHANGE_REQUESTED, "departure_holiday_override"),
        (EVENT_HOME_DAY_DEPARTURE_CHANGE_REQUESTED, "departure_home_day_override"),
    ],
)
async def test_departure_override_change_request_parses_the_iso_string(hass, event_type, field):
    """§3.3: the bus carries an ISO-8601 string, never a datetime.time -- a fired event isn't
    private (any websocket client can subscribe), and a string is the format RestoreEntity
    already persists and time.py already parses back, so it costs nothing new. The listener
    parses on receive."""
    coord = _wired(hass)
    hass.bus.async_fire(event_type, {ATTR_ENTRY_ID: "abc", ATTR_VALUE: "07:30:00"})
    await hass.async_block_till_done()
    assert getattr(coord, field) == time(7, 30)


@pytest.mark.parametrize(
    "event_type",
    [
        EVENT_WEEKDAY_DEPARTURE_CHANGE_REQUESTED,
        EVENT_HOLIDAY_DEPARTURE_CHANGE_REQUESTED,
        EVENT_HOME_DAY_DEPARTURE_CHANGE_REQUESTED,
    ],
)
async def test_departure_change_request_from_another_entry_is_ignored(hass, event_type):
    coord = _wired(hass, entry_id="abc")
    hass.bus.async_fire(
        event_type, {ATTR_ENTRY_ID: "other", ATTR_WEEKDAY: 0, ATTR_VALUE: "07:30:00"}
    )
    await hass.async_block_till_done()
    assert coord.departure_dow_defaults[0] is None
    assert coord.departure_holiday_override is None
    assert coord.departure_home_day_override is None
```

Update Task 2's registration-count assertion to `== 8` — all eight listeners now exist (criterion 3).

**Step 2: Run to verify failure**

Run: `pytest tests/test_coordinator.py -k departure -v`
Expected: FAIL — `assert None == datetime.time(7, 30)`; the count assertion fails `5 == 8`.

**Step 3: Write the minimal implementation**

`coordinator.py` already imports `from datetime import time as time_of_day` (`:7`) — reuse it, do
not add a second `time` import.

```python
    def configure_weekday_departure(self, weekday: int, value: time_of_day | None) -> None:
        """R14's per-day-of-week departure default (Monday=0..Sunday=6)."""
        self.departure_dow_defaults[weekday] = value

    def override_holiday_departure(self, value: time_of_day | None) -> None:
        """R14's public-holiday departure override."""
        self.departure_holiday_override = value

    def override_home_day_departure(self, value: time_of_day | None) -> None:
        """R14's home-day departure override."""
        self.departure_home_day_override = value

    @staticmethod
    def _parse_departure(raw: str | None) -> time_of_day | None:
        """ADR-0016 §3.3: the bus carries an ISO-8601 string (or None), never a datetime.time."""
        return None if raw is None else time_of_day.fromisoformat(raw)

    @callback
    def _on_weekday_departure_requested(self, event: Event) -> None:
        if event.data.get(ATTR_ENTRY_ID) != self._entry_id:
            return
        self.configure_weekday_departure(
            event.data[ATTR_WEEKDAY], self._parse_departure(event.data[ATTR_VALUE])
        )
        self._schedule_refresh()

    @callback
    def _on_holiday_departure_requested(self, event: Event) -> None:
        if event.data.get(ATTR_ENTRY_ID) != self._entry_id:
            return
        self.override_holiday_departure(self._parse_departure(event.data[ATTR_VALUE]))
        self._schedule_refresh()

    @callback
    def _on_home_day_departure_requested(self, event: Event) -> None:
        if event.data.get(ATTR_ENTRY_ID) != self._entry_id:
            return
        self.override_home_day_departure(self._parse_departure(event.data[ATTR_VALUE]))
        self._schedule_refresh()
```

Register all three (the list reaches eight). Delete the remaining "wiring is not yet threaded
(tracked separately, issue #402)" sentence from `coordinator.py:191-195`'s comment — as of this
task all four of those fields have a real write path; the defaults now only matter for a coordinator
never wired to entities (a direct test construction), which is what the `active_mode` comment above
already says.

**Step 4: Run to verify pass** — new tests PASS. `pytest tests/ -q` must still be green: nothing
*fires* these three events yet (that is Task 12), so no end-to-end expectation can have moved.
`ruff check .`, `ruff format --check .`.

**Step 5: Commit** (`ADR-0016 T11`).

---

## Task 12: `time.py` fires the departure change requests

**Design section honored:** §6.1, §6.3, §6.4.

> **Paired with Task 13.** This is the task that makes `departure_dow_defaults` genuinely live for
> the first time, seeding Mon–Fri 06:00 where the coordinator previously saw `None` everywhere. If
> `tests/test_deadline_soc_management_end_to_end.py` or
> `tests/test_init.py::test_solar_reserve_soc_option_threaded_engages_configured_cap_live` go red
> here, **do not patch them blindly** — that is exactly §6.4's predicted behavior change. Stop, do
> Task 13, and commit the two together.

**Files:**
- Modify: `custom_components/smart_charging/time.py`
- Modify: `tests/test_time.py`

**Step 1: Write the failing tests**

```python
async def test_setting_a_weekday_departure_requests_the_change_with_its_weekday(hass):
    """ADR-0016 §6.1: the suffix picks the event; a day-of-week suffix also carries
    ATTR_WEEKDAY, derived from time.py's own Monday-first DAY_OF_WEEK_DEFAULTS."""
    events = async_capture_events(hass, EVENT_WEEKDAY_DEPARTURE_CHANGE_REQUESTED)
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=DAY_WED, default=WEEKDAY_DEFAULT)
    await MockEntityPlatform(hass, domain="time").async_add_entities([entity])
    await entity.async_set_value(time(7, 30))
    await hass.async_block_till_done()
    assert events[-1].data == {ATTR_ENTRY_ID: "abc", ATTR_WEEKDAY: 2, ATTR_VALUE: "07:30:00"}


@pytest.mark.parametrize(
    ("suffix", "event_type"),
    [
        (DEPARTURE_OVERRIDE_HOLIDAY, EVENT_HOLIDAY_DEPARTURE_CHANGE_REQUESTED),
        (DEPARTURE_OVERRIDE_HOME_DAY, EVENT_HOME_DAY_DEPARTURE_CHANGE_REQUESTED),
    ],
)
async def test_setting_an_override_departure_requests_its_own_event(hass, suffix, event_type):
    """The two overrides get their own events and carry no ATTR_WEEKDAY."""
    events = async_capture_events(hass, event_type)
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=suffix, default=None)
    await MockEntityPlatform(hass, domain="time").async_add_entities([entity])
    await entity.async_set_value(time(7, 30))
    await hass.async_block_till_done()
    assert events[-1].data == {ATTR_ENTRY_ID: "abc", ATTR_VALUE: "07:30:00"}


async def test_a_none_departure_is_carried_as_an_explicit_none(hass):
    """§3.3: None (no departure configured) passes through as a value, not a missing key --
    the Sat/Sun entities' own default."""
    events = async_capture_events(hass, EVENT_WEEKDAY_DEPARTURE_CHANGE_REQUESTED)
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=DAY_SAT, default=None)
    await MockEntityPlatform(hass, domain="time").async_add_entities([entity])
    await hass.async_block_till_done()
    assert events[0].data == {ATTR_ENTRY_ID: "abc", ATTR_WEEKDAY: 5, ATTR_VALUE: None}


async def test_added_to_hass_requests_the_restored_value_not_the_constructor_default(hass):
    """§6.1: the seed fires AFTER the restore block, so the coordinator gets the restored
    value -- the actual point of issue #402."""
    entity_id = "time.smart_charging_departure_mon"
    mock_restore_cache(hass, (State(entity_id, "07:30:00"),))
    events = async_capture_events(hass, EVENT_WEEKDAY_DEPARTURE_CHANGE_REQUESTED)
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT)
    entity.entity_id = entity_id
    await MockEntityPlatform(hass, domain="time").async_add_entities([entity])
    await hass.async_block_till_done()
    assert events[0].data == {ATTR_ENTRY_ID: "abc", ATTR_WEEKDAY: 0, ATTR_VALUE: "07:30:00"}


def test_departure_time_holds_no_coordinator_reference():
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT)
    assert not hasattr(entity, "_coordinator")
```

**Step 2: Run to verify failure**

Run: `pytest tests/test_time.py -k request -v`
Expected: FAIL with `IndexError: list index out of range` — `time.py` fires nothing today.

**Step 3: Write the minimal implementation**

In `time.py`, below `OVERRIDE_DEFAULTS` (`:60`):

```python
# Suffix -> Python weekday index, derived from the Monday-first table above so the two can't
# drift apart (ADR-0016 §3.2: Monday=0..Sunday=6, matching datetime.date.weekday()).
_DAY_SUFFIX_TO_WEEKDAY = {suffix: index for index, (suffix, _) in enumerate(DAY_OF_WEEK_DEFAULTS)}
```

`SmartChargingDepartureTime.__init__` keeps its `(self, entry_id, id_suffix, default)` signature —
**no `coordinator` parameter is added** — and gains one line the fire path needs:

```python
        self._id_suffix = id_suffix
```

Add the fire helper and its two call sites:

```python
    def _fire_change_request(self) -> None:
        value = self._attr_native_value
        payload_value = None if value is None else value.isoformat()  # ADR-0016 §3.3
        if self._id_suffix == DEPARTURE_OVERRIDE_HOLIDAY:
            event, extra = EVENT_HOLIDAY_DEPARTURE_CHANGE_REQUESTED, {}
        elif self._id_suffix == DEPARTURE_OVERRIDE_HOME_DAY:
            event, extra = EVENT_HOME_DAY_DEPARTURE_CHANGE_REQUESTED, {}
        else:
            event = EVENT_WEEKDAY_DEPARTURE_CHANGE_REQUESTED
            extra = {ATTR_WEEKDAY: _DAY_SUFFIX_TO_WEEKDAY[self._id_suffix]}
        self.hass.bus.async_fire(
            event, {ATTR_ENTRY_ID: self._entry_id, ATTR_VALUE: payload_value, **extra}
        )
```

- `async_added_to_hass` (`:73-77`): call it at the **end**, after the restore block.
- `async_set_value` (`:79-81`): call it between `self._attr_native_value = value` and
  `self.async_write_ha_state()`, with **no** `await ...async_request_refresh()`.
- `async_setup_entry` (`:84-92`) is unchanged (§6.3).

**Out of scope here:** `origin/dev/402`'s `try/except ValueError` hardening around
`time.fromisoformat(last.state)` for a malformed restore-cache value. Design §6.1 calls it
orthogonal to this ADR and §9 leaves it to PR #452's reduced form — do not fold it in.

**Step 4: Run to verify pass** — `pytest tests/test_time.py -v` green. Then `pytest tests/ -q`;
if the two suites named in the callout above go red, go to Task 13 **before** committing.
`ruff check .`, `ruff format --check .`.

**Step 5: Commit** (`ADR-0016 T12`) — together with Task 13's adjustments if there were any.

---

## Task 13: Re-read the end-to-end suites whose expectations rested on inert defaults

**Design section honored:** §6.4 — *"This slice is what makes R9's solar-reserve trigger and R14's
deadline resolution see real user input. That is a behavior change relative to `origin/main`, not a
refactor, and the end-to-end suites that currently rely on those defaults (or set the fields
directly) should be re-read rather than assumed unaffected."* This task is that re-read, made
concrete.

**Files:**
- Verify, and adjust only where §6.4 demands it: `tests/test_deadline_soc_management_end_to_end.py`,
  `tests/test_init.py`
- Verify (the true blast radius is wider than "no departure/home-day dependency expected" — see
  Step 1's second paragraph): `tests/test_solar_end_to_end.py`, `tests/test_captar_end_to_end.py`,
  `tests/benchmarks/test_coordinator_perf.py`

**Step 1: Identify every expectation that rested on an inert default**

```bash
grep -rn "departure_dow_defaults\|departure_holiday_override\|departure_home_day_override\|home_day_flag" tests/
```

This also surfaces `tests/helpers.py`'s `seed_today_deadline` (a shared helper imported by
`test_coordinator.py`, `test_init.py`, `test_solar_end_to_end.py`, `test_captar_end_to_end.py`
and `test_deadline_soc_management_end_to_end.py`) and the direct field assignments at
`tests/test_coordinator.py:921-930` — read every hit, not just the two sites below.

**`Platform.TIME` and `Platform.SWITCH` are both in `PLATFORMS`** (`__init__.py:67-73`), so after
Task 12 this is not scoped to two files: **every** test that goes through a real
`async_setup_entry` now sees `departure_dow_defaults` seeded Mon–Fri 06:00, not just the two named
below. Whether `test_solar_end_to_end.py`/`test_captar_end_to_end.py` are actually affected is
something this step verifies by running them, not a classification to trust up front.

Two sites are known in advance, both flagged by the design:

1. `tests/test_deadline_soc_management_end_to_end.py` — its module docstring (`:6-10`) states
   outright that these four fields "are set directly on the live coordinator instance" because the
   entity wiring "is not yet threaded (issue #402)". As of Task 12 that premise is **false**: a full
   `async_setup_entry` now seeds `departure_dow_defaults` with Mon–Fri 06:00 from the `time`
   entities' own defaults, where the suite previously saw all-`None`. Any test in that file that
   depends on "no configured deadline anywhere" while running through a real config entry can now
   see a 06:00 weekday deadline. The direct assignments at `:390, :421, :443, :453` still win —
   they happen *after* setup — but the *absence* of an assignment no longer means "no deadline".
2. `tests/test_init.py::test_solar_reserve_soc_option_threaded_engages_configured_cap_live` — its
   docstring says "Sun down, ample forecast, home day, **no departure deadline anywhere** → R9's
   reserve engages". After Task 12 the `time` entities seed a weekday deadline, so that premise
   needs re-checking against R9/UC07 rather than assumed.

**Step 2: For each affected test, decide deliberately — do not chase green**

For every expectation that moved, choose and record which of these it is:

- **The test's premise is now unreachable through a real config entry.** Make the premise explicit
  in the test's own arrangement (clear the seeded weekday defaults on the live coordinator after
  setup, exactly as the suite already sets `home_day_flag` directly) and say so in the docstring.
  This is the expected resolution for the "no departure deadline anywhere" cases.
- **The new value is the correct behavior** (real user input reaching R14 is the whole point of
  issue #402). Update the expectation and the docstring to state the newly-live input.

Also correct the two now-stale comments in the same pass: the `# entity->coordinator wiring pending,
issue #402` trailers at `tests/test_init.py:277` and
`tests/test_deadline_soc_management_end_to_end.py:390`, and that suite's module docstring
(`:6-10`) — the wiring is no longer pending.

**Step 3: Run to verify pass**

Run: `pytest tests/test_deadline_soc_management_end_to_end.py tests/test_init.py tests/test_solar_end_to_end.py tests/test_captar_end_to_end.py -q`
Expected: all green, with **no test deleted, skipped or xfailed** to get there. If the only way you
found to make one pass was to weaken its assertion, stop and report — that is a design question,
not a test-maintenance one.

**Step 4: Commit** — folded into Task 12's commit if Task 12 was left uncommitted, otherwise its own
(`ADR-0016 T13`), with a message that names §6.4's behavior change explicitly rather than calling it
a test fix.

---

## Task 14: Listeners are registered before the platforms are forwarded

**Design section honored:** §7.3's first bullet — the test that would catch the registration
ordering being wrong.

**Files:**
- Modify: `tests/test_init.py`

**Step 1: Write the test**

```python
async def test_owned_entities_seed_the_coordinator_through_the_event_bus_on_setup(hass):
    """ADR-0016 §7.3: listeners are registered BEFORE async_forward_entry_setups, so an
    entity's async_added_to_hass seed event is not fired into a bus nobody is listening on.
    Asserts the coordinator holds the entities' seeded values rather than its own constructor
    defaults (target_current defaults to 0.0, active_mode to MODE_POWER)."""
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    # target_current/active_mode are the two assertions that actually prove the ordering: the
    # coordinator's own constructor defaults are 0.0 and MODE_POWER (coordinator.py's __init__),
    # so seeing the entities' seeded values instead is only possible if the seed events reached a
    # listener. (active_profile's constructor default is already PROFILE_MANUAL -- asserting it
    # would pass whether or not the seed event was ever delivered, so it's omitted here.)
    assert coordinator.target_current == entry.options[CONF_DEFAULT_TARGET_CURRENT]
    assert coordinator.active_mode == MODE_OFF   # ModeSelect's own default seed
```

**Step 2: Prove the red** — this passes as soon as Task 6 landed, so demonstrate it the other way:
temporarily move `__init__.py`'s registration loop to *after*
`await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)`, run
`pytest tests/test_init.py -k seed_the_coordinator -v`, watch it FAIL (`assert 0.0 == 10.0` — the
seed events were fired before anything subscribed), then revert. Do not accept a green assertion you
never saw fail; this test's entire value is that it pins an ordering nothing else enforces.

**Step 3: Run to verify pass** — `pytest tests/ -q` green, ruff clean.

**Step 4: Commit** (`ADR-0016 T14`).

---

## Task 15: Teardown — unload detaches, reload does not duplicate

**Design section honored:** §7.3's second bullet, criterion 8. Per ADR-0008 every options or
reconfigure change is a full reload, so a leaked listener accumulates one stale subscription **per
reload**, not one per install — this is the criterion that makes ADR-0008's reload policy safe under
an event-based write path.

**Files:**
- Modify: `tests/test_init.py`
- Modify (only if the tests below go red): `custom_components/smart_charging/__init__.py`

**Step 1: Write the tests**

```python
async def test_unload_detaches_the_change_request_listeners(hass):
    """ADR-0016 criterion 8, half one: after unload, an event carrying this entry's own id
    must change nothing on the (now detached) coordinator."""
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    before = coordinator.active_mode
    hass.bus.async_fire(
        EVENT_ACTIVE_MODE_CHANGE_REQUESTED,
        {ATTR_ENTRY_ID: entry.entry_id, ATTR_VALUE: MODE_POWER},
    )
    await hass.async_block_till_done()
    assert coordinator.active_mode == before


async def test_reload_does_not_accumulate_a_duplicate_listener(hass):
    """ADR-0016 criterion 8, half two: the observable form of 'no leaked duplicate subscription
    per ADR-0008 reload'. Reload constructs a brand-new SmartChargingCoordinator instance
    (__init__.py's async_setup_entry runs fresh) -- a leaked pre-reload subscription would be
    bound to the OLD instance's method, not the new one, so spying on the new coordinator's
    setter cannot observe it. hass.bus.async_listeners() counts registered listeners per event
    type across the whole bus, independent of which object they're bound to, and is what
    actually distinguishes 'the old subscription was torn down' from 'it leaked'."""
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    before = hass.bus.async_listeners()[EVENT_ACTIVE_MODE_CHANGE_REQUESTED]

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    after = hass.bus.async_listeners()[EVENT_ACTIVE_MODE_CHANGE_REQUESTED]
    assert after == before      # same count -- the pre-reload listener was torn down, not doubled
```

The listener-count assertion is what actually detects a leak. An assertion against the *field*
(fire an event, check `active_mode`) cannot: a duplicate subscription applies the same value
twice, which is invisible on the resulting field either way, and spying on the post-reload
coordinator's own `set_active_mode` only observes calls made through the *new* instance — a
leaked pre-reload subscription is bound to the *old* instance's method entirely, so it would never
appear in that spy at all.

**Step 2: Run to verify failure or prove the red**

Run: `pytest tests/test_init.py -k "detaches or duplicate_listener" -v`. Task 6 routed every unsub
through `entry.async_on_unload`, so these should pass. Prove the red by temporarily dropping the
`entry.async_on_unload(unsub)` wrapper (just call
`coordinator.async_register_owned_entity_listeners()` and discard the result): the first test then
FAILS on the detach assertion, and the second FAILS with `after == before * 2` (one leaked
pre-reload listener plus the new one). Revert.

If they do **not** pass, the fix belongs in `__init__.py` (Task 6's registration loop), not in the
test.

**Step 3: Run to verify pass** — `pytest tests/ -q` green, ruff clean.

**Step 4: Commit** (`ADR-0016 T15`).

---

## Task 16: Full regression + untouched-code check

**Design section honored:** §2 (all nine criteria), §10 (deliberately deferred).

**Files:** none changed — verification only.

**Step 1:** Run the complete suite: `pytest tests/ -q`. Every test must pass, with **no new skips or
xfails** and none deleted to get there.

**Step 2:** `ruff check .` and `ruff format --check .` — both clean (CLAUDE.md/memory: always pair
`check` with `format --check`; CI lint runs both).

**Step 3: Criteria sweep** — read the post-change files and confirm each of design §2's nine
criteria holds, in particular the ones no single earlier task owned end to end:

- **Criterion 1** — exactly eight `EVENT_*_CHANGE_REQUESTED` and exactly three new `ATTR_*` in
  `const.py`, all below the ADR-0011 block, none reusing an ADR-0011 name.
- **Criterion 2** — `grep -rn "_coordinator" custom_components/smart_charging/select.py
  custom_components/smart_charging/number.py custom_components/smart_charging/time.py
  custom_components/smart_charging/switch.py` returns nothing, and every construction in the four
  entity test files passes no coordinator.
- **Criterion 3/4** — `async_register_owned_entity_listeners` returns eight unsubs, and **all eight
  handlers are decorated `@callback` and are `def`, never `async def`.** Read them; the ordering
  test (Task 5) only exercises one of the eight.
- **Criterion 6** — `set_target_current` and `set_soc_limit_override`'s clamp bodies are
  byte-for-byte what they were before this slice; only the caller changed.
- **Criterion 9** — `select.py`, `time.py` and `switch.py`'s `async_setup_entry` no longer read
  `hass.data[DOMAIN][entry.entry_id]["coordinator"]`; `number.py` still reads that dict for the
  `CONF_*` values but not for the `"coordinator"` key.

**Step 4: Explicit untouched-code check** (design §10) — confirm this slice did **not** touch, by
habit while working nearby:

- `coordinator.py`'s internal Auto-mode `self.active_mode = select_mode(...)` (around `:513` before
  this slice's edits shift line numbers) — still a direct assignment, out of scope: ADR-0016, like
  ADR-0014, governs writes from *outside* the class.
- ADR-0011's five domain events (`EVENT_ACTIVE_SOC_LIMIT_CHANGED`,
  `EVENT_DEADLINE_UNREACHABLE_NOTIFIED`, `EVENT_VEHICLE_CHARGE_LIMIT_SYNCED`,
  `EVENT_MANUAL_CHARGE_LIMIT_ADOPTED`, `EVENT_VEHICLE_CHARGE_LIMIT_RESET`) — unchanged names,
  unchanged payloads, and still **no `ATTR_ENTRY_ID` key**. Their absence from this slice is a
  choice, not an oversight.
- `sensor.py`'s five `CoordinatorEntity` subclasses — still hold their coordinator reference. This
  ADR scopes itself to the write path of owned *control* entities; the read direction is out of
  scope.
- `coordinator_cycle.py` / `CycleContext` (ADR-0012) — untouched.
- No `Store` class was introduced (design §10: RA3 remains deferred), and no `DATA_COORDINATOR`
  constant was added (design §10 leaves that to whichever PR wants it).
- The ~44 direct `SmartChargingCoordinator(...)` constructions and the pre-existing direct field
  assignments across `tests/test_coordinator.py`, the three end-to-end suites and
  `tests/benchmarks/test_coordinator_perf.py` are unchanged **except** where Task 13 deliberately
  adjusted a §6.4-affected expectation. Confirm the diff contains no incidental rewrites of test
  arrangement — that is explicitly out of scope (design §10).

**Step 5:** No commit — this task is a verification checkpoint. If any check fails, fix it in the
task that introduced the regression (re-open that task), not here.

**Step 6: Fresh-agent review** — per CLAUDE.md, hand the finished branch to the `code-reviewer`
agent (Opus) and post its findings to the PR via the `submit-pr-review` skill in local mode before
requesting the human partner's approval. Merge is gated on that approval, always.
