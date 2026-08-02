# Entity→coordinator writes via HA events — design

**Date:** 2026-08-02
**Status:** draft (issue #471, ADR-0016 issue #470, supersedes the spec at
`2026-08-01-coordinator-setter-encapsulation-design.md`)
**Type:** implementation design (a slice of an architectural decision — not a new decision)

**ADR-0016 status correction (done).** ADR-0016 was merged still marked `Status: Proposed`, and
`docs/adl/README.md` agreed — the same pre-merge oversight ADR-0012 and ADR-0014 each had.
`docs/adl/0016-entity-to-coordinator-writes-via-ha-events.md` and its `docs/adl/README.md` row are
now corrected to `Accepted` as part of authoring this design doc, mirroring how the ADR-0014 spec
handled the same gap — not a pending step for the paired plan's Task 1 to redo.

This document is the implementation spec ADR-0016's first Consequence calls for ("This ADR decides
the shape; it implements nothing. An implementation spec / TDD plan is needed to carry out the
migration across `select.py`, `number.py`, `time.py`, `switch.py` and `coordinator.py`, and to
update the entity tests that currently assert against a coordinator double"). It fixes the exact
event and payload-key vocabulary, where listeners are registered and torn down, how the coordinator
learns its own `entry_id`, and the before/after at every call site.

**This is not a pure internal refactor.** Four observable changes are deliberate, and each is
named as such rather than smuggled in:

1. **The refresh moves from the entity to the coordinator's listener** (§4.3). An entity used to
   `await self._coordinator.async_request_refresh()` *before* `self.async_write_ha_state()`; it now
   fires an event and writes its HA state immediately, and the refresh is scheduled by the
   coordinator's listener. Ordering of *apply-then-refresh* is preserved (§4.3); ordering of
   *refresh-then-write_ha_state* is not, and does not need to be.
2. **Every write is now visible on the HA event bus** — eight new event types any automation or
   diagnostic can subscribe to. That is ADR-0016's "Easier" consequence, but it is still a new
   public surface, not an invisible internal change.
3. **A cross-config-entry cross-talk failure mode is newly possible and newly guarded** (§4.4,
   §6.4). The direct reference could not have this bug; the event bus can, and the entry-id filter
   is the only thing preventing it.
4. **A single `async_setup_entry` now schedules roughly a dozen refresh requests during entity
   seeding, not zero.** Today's `async_added_to_hass` seed paths (e.g. `select.py:63`, `:91`;
   `number.py:54`, `:92`) call the setter directly and request no refresh at all — only a
   user-initiated *change* awaits one. After this slice, every seed also fires an event, and every
   listener unconditionally schedules a refresh (§4.3) — so setup now schedules on the order of one
   refresh per owned control entity (2 select + 2 number + 1 switch + 9 time ≈ 14) before
   `async_config_entry_first_refresh` ever runs. `async_request_refresh`'s own debouncing makes this
   benign, but it is a real, new-on-setup behavior, not merely a relocation of an existing one —
   named here so it isn't mistaken for covered by point 1.

---

## 1. Why this slice

ADR-0016 names eight externally-writable coordinator fields and decides that every owned *control*
entity reaches them by firing an entry-scoped HA event instead of holding a coordinator reference.
Four of those fields already have entity wiring on this branch (`select.py`, `number.py`, on
ADR-0014's now-superseded held-reference shape). Four do not: `time.py` and `switch.py` on
`origin/main` — the branch this worktree is cut from — hold **no coordinator reference at all**.

| Field | State on **this branch** (`origin/main`) | This slice |
| --- | --- | --- |
| `active_mode` | Written via held reference: `select.py:63` (`ModeSelect.async_added_to_hass` → `set_active_mode`), `select.py:67-68` (`async_select_option` → `set_active_mode` + `await async_request_refresh()`) | **In scope — migration.** `EVENT_ACTIVE_MODE_CHANGE_REQUESTED` (§3), reference removed from the constructor |
| `active_profile` | Written via held reference: `select.py:91`, `select.py:95-96` | **In scope — migration.** `EVENT_ACTIVE_PROFILE_CHANGE_REQUESTED` |
| `target_current` | Written via held reference: `number.py:54` (`async_added_to_hass`), `number.py:58-59` (`async_set_native_value`) | **In scope — migration.** `EVENT_TARGET_CURRENT_CHANGE_REQUESTED`; the `[CONF_MIN_CURRENT, CONF_MAX_CURRENT]` clamp stays coordinator-side (§4.2) |
| `soc_limit_override` | Written via held reference: `number.py:92`, `number.py:96-97` | **In scope — migration.** `EVENT_SOC_LIMIT_OVERRIDE_CHANGE_REQUESTED`; the `[SOC_LIMIT_OVERRIDE_MIN, SOC_LIMIT_OVERRIDE_MAX]` clamp stays coordinator-side |
| `home_day_flag` | **Nothing to migrate.** `switch.py:16-53` (`HomeDaySwitch`) has no `coordinator` parameter and no write of any kind; `coordinator.py:196` still defaults it `False` with the comment "that entity->coordinator wiring is not yet threaded (tracked separately, issue #402)" | **In scope — greenfield wiring.** `EVENT_HOME_DAY_FLAG_CHANGE_REQUESTED` (§6) |
| `departure_dow_defaults` (7 entities → one dict) | **Nothing to migrate.** `time.py:79-81` (`async_set_value`) writes only `_attr_native_value`; `coordinator.py:197` defaults all seven to `None` | **In scope — greenfield wiring.** `EVENT_WEEKDAY_DEPARTURE_CHANGE_REQUESTED`, payload carries the weekday (§3.2) |
| `departure_holiday_override` | **Nothing to migrate** (same as above) | **In scope — greenfield wiring.** `EVENT_HOLIDAY_DEPARTURE_CHANGE_REQUESTED` |
| `departure_home_day_override` | **Nothing to migrate** (same as above) | **In scope — greenfield wiring.** `EVENT_HOME_DAY_DEPARTURE_CHANGE_REQUESTED` |
| `active_mode` at `coordinator.py` `_run_cycle` (Auto's own `self.active_mode = select_mode(...)`) | Internal write inside the coordinator | **Out of scope** — ADR-0016, like ADR-0014, governs writes from *outside* the class |
| `sensor.py`'s five `CoordinatorEntity` subclasses | Hold a coordinator reference for coordinator→entity read sync | **Out of scope** — ADR-0016's "Out of scope: the read direction" |

### 1.1 `time.py`/`switch.py`: this spec is also PR #452's spec

The coordinator wiring for `home_day_flag` and the three departure fields is in flight on a
**separate, unmerged branch** (`origin/dev/402`, PR #452). It is **not visible in this worktree**
and is **not on `origin/main`**. That branch builds the now-superseded shape: a held
`self._coordinator` plus five setter calls
(`activate_home_day` / `deactivate_home_day` / `configure_weekday_departure` /
`override_holiday_departure` / `override_home_day_departure`, at `coordinator.py:629-657` on that
branch), with `await self._coordinator.async_request_refresh()` at each entity call site.

So for `time.py` and `switch.py` this document is **not describing a migration away from a
reference — there is no reference on this branch to migrate away from.** It specifies what their
write-path wiring must look like, so that PR #452 is *reworked onto this shape* rather than landing
the superseded pattern and being migrated afterwards. That is exactly the expectation ADR-0016's
fourth Consequence records ("that work is expected to be reworked onto this ADR's event shape
before it merges"). §6 gives the wiring in full, in the form PR #452 should adopt directly.

Whichever of the two lands second inherits a mechanical conflict in `time.py`/`switch.py`; §9 names
the two orderings and their cost.

---

## 2. Success criteria

"Works" means: **no owned control entity holds or accepts a coordinator, every user-set value still
reaches the coordinator's field with the same clamping as today, a value from another config
entry's entity never does, and every existing test passes except the entity tests whose coordinator
double this ADR deliberately deletes.**

1. `const.py` defines exactly **eight** `EVENT_*` constants (§3.1) — one per externally-writable
   coordinator field, none generic, none reusing an ADR-0011 domain-event name — plus exactly
   **three** new `ATTR_*` payload keys — `ATTR_ENTRY_ID`, `ATTR_VALUE`, `ATTR_WEEKDAY` (§3.2). Each
   event-type string matches the `smart_charging_<snake_case>` shape the existing five `EVENT_*`
   constants use (`const.py:8,12,22-24`), and each ends in `_change_requested`.
2. No entity in `select.py`, `number.py`, `time.py` or `switch.py` accepts a `coordinator`
   parameter or sets a `self._coordinator` attribute. Checkable two ways, both required: a grep for
   `_coordinator` over those four files returns nothing, and each entity's own test constructs it
   with no coordinator argument at all (§7.1) — a construction that raises `TypeError` today.
3. `SmartChargingCoordinator` knows its own config entry's id (§4.1) and exposes one method that
   registers all eight listeners and returns their unsubscribe callables (§4.2).
4. Every one of the eight listeners is a synchronous `@callback` — never `async def`. Checkable by
   reading the post-change `coordinator.py`, and behaviorally by the ordering test in §7.2
   (asserting the field is already updated when `async_fire` returns, which a coroutine listener
   cannot satisfy).
5. A listener applies the value **only** when the event's `ATTR_ENTRY_ID` equals the coordinator's
   own entry id; an event carrying a different entry id changes no field and requests no refresh
   (§7.2's cross-talk test). This is a new failure mode the held reference could not have.
6. `set_target_current` and `set_soc_limit_override` still clamp exactly as today
   (`coordinator.py:641-649`, `:617-622`), now reached from the listener instead of the entity —
   the clamp bounds and code are unchanged, only the caller is.
7. The two `__init__`-time entity clamps ADR-0014's spec added
   (`number.py:43`, `number.py:82`) are unchanged. Their existing tests
   (`test_init_clamps_out_of_range_default_target_current`,
   `test_init_clamps_out_of_range_default_soc_limit`) must keep passing after the
   constructor loses its `coordinator` argument — a signature edit only, not a behavior edit.
8. Listener subscriptions are torn down on config-entry unload and reload, verified by a test that
   unloads a `MockConfigEntry` and then fires an event with that entry's id and asserts the (now
   detached) coordinator's field did not change (§7.2). Per ADR-0008 every options/reconfigure
   change is a full reload, so a leaked listener would accumulate one stale subscription **per
   reload**, not one per install — this is the criterion that makes ADR-0008's reload policy safe
   under an event-based write path.
9. `select.py`/`number.py`/`time.py`/`switch.py`'s `async_setup_entry` no longer read
   `hass.data[DOMAIN][entry.entry_id]["coordinator"]`. (`number.py`'s `async_setup_entry` still
   reads that dict for `CONF_MIN_CURRENT`/`CONF_MAX_CURRENT`/the two defaults — only the
   `"coordinator"` key goes away, `number.py:105`.)

---

## 3. New constants (`const.py`)

All new constants go in `const.py`, immediately **below** the existing ADR-0011 domain-event block
(`const.py:7-24`) and under their own comment header, so a reader can see at a glance that the two
groups are different animals.

### 3.1 The eight event types

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
```

Eight events for eight *fields*, not for the five setter methods `origin/dev/402` currently has:
`activate_home_day`/`deactivate_home_day` are two methods writing **one** field, so they collapse
into one event carrying a boolean (§6.2). Conversely the seven day-of-week `time` entities all
write **one** field (`departure_dow_defaults`, a dict), so they share one event carrying a weekday
key (§3.2) — the per-field rule is per *coordinator field*, not per entity.

### 3.2 The three payload keys

```python
ATTR_ENTRY_ID = "entry_id"  # config entry the request is scoped to -- on all eight payloads
ATTR_VALUE = "value"        # the requested new value -- on all eight payloads
ATTR_WEEKDAY = "weekday"    # Monday=0..Sunday=6; EVENT_WEEKDAY_DEPARTURE_CHANGE_REQUESTED only
```

**Why one shared `ATTR_VALUE` rather than eight field-named keys** (the shape
`ATTR_ACTIVE_SOC_LIMIT`/`ATTR_REQUIRED_CURRENT_A` at `const.py:9,13` uses): the event *type* already
names the field, so a field-named key would restate it in every payload, and eight near-identical
one-use constants buy nothing over one. The existing two keys are field-named because each belongs
to a one-off event with an otherwise unlabelled number in it; here the label is the event name.
This is a payload-key choice, not the generic-event shape ADR-0016 rejected — dispatch is still
per-event-type, with no stringly-typed field discriminator anywhere.

`ATTR_WEEKDAY` is the one asymmetry, and it is unavoidable: `departure_dow_defaults` is a
`dict[int, time | None]`, so "which entry" is genuinely part of the request. It is an `int`
(Monday=0..Sunday=6), matching `datetime.date.weekday()` and the index `time.py`'s
`DAY_OF_WEEK_DEFAULTS` list (`time.py:46-54`, Monday-first) already implies.

### 3.3 Payload value types, and the one that must be serialized

| Event | `ATTR_VALUE` type on the bus |
| --- | --- |
| `..._ACTIVE_MODE_...`, `..._ACTIVE_PROFILE_...` | `str` |
| `..._TARGET_CURRENT_...`, `..._SOC_LIMIT_OVERRIDE_...` | `float` |
| `..._HOME_DAY_FLAG_...` | `bool` |
| `..._WEEKDAY_DEPARTURE_...`, `..._HOLIDAY_DEPARTURE_...`, `..._HOME_DAY_DEPARTURE_...` | **`str | None` — an ISO-8601 time string (`value.isoformat()`), or `None`** |

The three departure events carry an **ISO-8601 string, not a `datetime.time` object.** A fired
event is not private — any websocket client subscribing to it forces the payload through
serialization, and a bare `datetime.time` is at best an unnecessary risk to carry across that
boundary unserialized (the exact serialization path Home Assistant's frontend/websocket layer
takes for an event payload was not verified against installed-package source as part of this
design — treat "serialize defensively" as the operative reason, not a specific verified
exception). A string is also the format `RestoreEntity` already persists and what `time.py:77`
already parses back with `time.fromisoformat`, so it costs nothing new to produce or consume. The
entity serializes on fire (§6.1); the coordinator's listener parses on receive (§4.3). `None` (no
departure configured) passes through unchanged and is a valid value, not a missing key.

---

## 4. Coordinator changes (`coordinator.py`)

### 4.1 The coordinator learns its own `entry_id`

`SmartChargingCoordinator.__init__` (`coordinator.py:149`) is
`(self, hass, *, adapters, config, interval_s)` and stores nothing that identifies the config
entry. `DataUpdateCoordinator.__init__` may populate `self.config_entry` from HA's
`config_entries.current_entry` ContextVar when constructed inside `async_setup_entry`, but that is
`None` for every one of the 45 direct constructions in `tests/` (44 in test_coordinator.py, 1 in benchmarks/test_coordinator_perf.py) — so it cannot be the filter's
source of truth without silently disabling the filter under test.

**Decision:** add an explicit keyword, defaulted:

```python
def __init__(self, hass, *, adapters, config, interval_s, entry_id: str | None = None) -> None:
    ...
    self._entry_id = entry_id
```

Defaulted to `None` so the 45 existing `SmartChargingCoordinator(hass, adapters=..., config=...,
interval_s=30)` call sites across `tests/test_coordinator.py`,
`tests/benchmarks/test_coordinator_perf.py` and the three end-to-end suites keep compiling
untouched — the same "don't mass-rewrite test construction for a mechanical rename" call the
ADR-0014 spec made for its 137 field assignments. `__init__.py` passes `entry_id=entry.entry_id`
(§4.5). The default is made safe rather than silent by §4.2's guard: a coordinator with
`_entry_id is None` **raises** on listener registration instead of registering listeners that can
never match. See §10 for the open question on whether it should simply be required.

### 4.2 One registration method, returning its unsubscribes

```python
@callback
def async_register_owned_entity_listeners(self) -> list[CALLBACK_TYPE]:
    """Subscribe the coordinator to its own owned control entities' change requests
    (ADR-0016). Sync `@callback` listeners, never coroutines: HA runs a `@callback`
    listener inline inside `async_fire`, which is what preserves 'the field is applied
    before the refresh it triggers' -- a coroutine listener is scheduled as a separate
    task and loses that ordering. Returns the unsubscribe callables; the caller
    (`__init__.py`) hands each to `entry.async_on_unload`."""
    if self._entry_id is None:
        raise RuntimeError(...)
    return [
        self.hass.bus.async_listen(EVENT_ACTIVE_MODE_CHANGE_REQUESTED, self._on_active_mode_requested),
        ...  # eight in total
    ]
```

Naming: `async_`-prefixed but **not** a coroutine, per HA's convention that the prefix means
"must be called from the event loop", exactly as `hass.bus.async_listen` and
`async_write_ha_state` are. It is decorated `@callback`.

The eight listener handlers are private `@callback` methods on the coordinator, defined next to the
four existing setters (`coordinator.py:617-656`). They keep the setters as the field-owning code —
the listener is a thin filter + unwrap + delegate, so the two range clamps stay exactly where
ADR-0014 put them and ADR-0016's "the coordinator's field is still mutated only by code the
coordinator owns" holds unchanged.

### 4.3 The listener body, once (all eight are this shape)

```python
@callback
def _on_target_current_requested(self, event: Event) -> None:
    if event.data.get(ATTR_ENTRY_ID) != self._entry_id:
        return                                    # another config entry's entity -- not ours
    self.set_target_current(event.data[ATTR_VALUE])   # existing clamp, unchanged
    self._schedule_refresh()
```

Variations:

- `_on_weekday_departure_requested` also reads `event.data[ATTR_WEEKDAY]` and parses the value:
  `None if raw is None else time.fromisoformat(raw)`. Same for the two override listeners (no
  weekday).
- `_on_home_day_flag_requested` calls `activate_home_day()`/`deactivate_home_day()` on the boolean
  — the two setters `origin/dev/402` already defines, kept as-is (§6.2).
- The four `time`/`switch` listeners call setters that **do not exist on this branch**; whether
  this slice adds them or inherits them from PR #452 is the sequencing question in §9.

`_schedule_refresh()` is one shared private `@callback` helper:
`self.hass.async_create_task(self.async_request_refresh())`. A sync `@callback` cannot `await`, and
`async_request_refresh` is already debounced, so scheduling it is the correct translation of
today's `await` — and it is scheduled *after* the field is applied, in the same synchronous block,
which is criterion 4's ordering guarantee.

### 4.4 The entry-id filter is load-bearing, not defensive

With two config entries, both coordinators subscribe to all eight event types on the same global
bus. Without the `!= self._entry_id` early return, entry A's mode selector would rewrite entry B's
`active_mode` on every change. There is no way to scope an `async_listen` subscription by payload
in HA, so the filter is the mechanism. Criterion 5's test exists because a missing filter is
invisible in a single-entry test suite.

### 4.5 Wiring in `__init__.py`: registration order and teardown

`async_setup_entry` (`__init__.py:130-145`) constructs the coordinator, populates
`hass.data[DOMAIN][entry.entry_id]`, then calls
`await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)` (`:144`), which is what
runs every entity's `async_added_to_hass` — the seed fire (§5, §6.1, §6.2).

Two decisions, both load-bearing:

1. **Register before forwarding.** `coordinator.async_register_owned_entity_listeners()` is called
   with `entry_id=entry.entry_id` passed to the constructor, **before** `:144`'s
   `async_forward_entry_setups`. If registration happened after, every entity's seed event
   (fired from `async_added_to_hass`, itself run by that same forwarding call) would be fired into
   a bus nobody is listening on yet, and the coordinator would silently keep its construction-time
   defaults instead of the entities' restored/configured values — this is exactly criterion 3's
   "the coordinator learns its own `entry_id`" combined with criterion 8's ordering, made concrete
   (§7.3 names the test).
2. **Every unsub goes through `entry.async_on_unload`.** `async_register_owned_entity_listeners()`
   returns a list of unsubscribe callables (§4.2); `async_setup_entry` hands each one to
   `entry.async_on_unload(unsub)` rather than storing them itself. HA calls every registered
   `async_on_unload` callback on both unload and (per ADR-0008) reload's implicit unload-then-setup,
   so this is what prevents a stale subscription from accumulating one per reload (criterion 8;
   §7.3's second bullet).

---

## 5. Before/after — `select.py` and `number.py`

Every entity's write handler follows one shape:

```python
self.hass.bus.async_fire(EVENT_X, {ATTR_ENTRY_ID: self._entry_id, ATTR_VALUE: v})
```

`self._entry_id` is already on every owned entity — `SmartChargingEntity.__init__`
(`entity.py`) sets it from the `entry_id` constructor argument all six classes already pass.
No entity needs a new field to fire an entry-scoped event.

| Site | Before (this branch) | After |
| --- | --- | --- |
| `select.py:40-56` `ModeSelect.__init__` | `(self, entry_id, coordinator, solar_installed=False, captar_available=False)`; `self._coordinator = coordinator` (`:48`) | `coordinator` parameter **removed**; `:48` deleted |
| `select.py:63` `async_added_to_hass` | `self._coordinator.set_active_mode(self._attr_current_option)` | `self.hass.bus.async_fire(EVENT_ACTIVE_MODE_CHANGE_REQUESTED, {ATTR_ENTRY_ID: self._entry_id, ATTR_VALUE: self._attr_current_option})` |
| `select.py:65-69` `async_select_option` | `:67` `self._coordinator.set_active_mode(option)`; `:68` `await self._coordinator.async_request_refresh()` | `:67` becomes the same `async_fire`; **`:68` is deleted** — the refresh is now the listener's (§4.3). `:66` (`_attr_current_option = option`) and `:69` (`async_write_ha_state()`) unchanged |
| `select.py:80-84` `ProfileSelect.__init__` | `(self, entry_id, coordinator)`; `self._coordinator = coordinator` (`:82`) | `coordinator` removed; `:82` deleted |
| `select.py:91` / `:95-96` | `set_active_profile(...)` / `await async_request_refresh()` | `async_fire(EVENT_ACTIVE_PROFILE_CHANGE_REQUESTED, ...)` / line deleted |
| `select.py:100-117` `async_setup_entry` | `:103` reads `hass.data[DOMAIN][entry.entry_id]["coordinator"]`, passes `coordinator=` twice | `:103` deleted; both constructor calls drop `coordinator=`. `DOMAIN` becomes unused in this module and is removed from the import — `hass` stays: it is `async_setup_entry`'s own mandatory parameter (its `HomeAssistant` type annotation is unaffected) |
| `number.py:31-43` `TargetCurrentNumber.__init__` | `(self, entry_id, coordinator, min_a, max_a, default)`; `self._coordinator = coordinator` (`:35`) | `coordinator` removed; `:35` deleted. **`:37-43` unchanged**, including the `:43` default clamp (criterion 7) |
| `number.py:54` | `self._coordinator.set_target_current(self._attr_native_value)` | `async_fire(EVENT_TARGET_CURRENT_CHANGE_REQUESTED, {ATTR_ENTRY_ID: self._entry_id, ATTR_VALUE: self._attr_native_value})` |
| `number.py:56-60` `async_set_native_value` | `:58` setter; `:59` `await async_request_refresh()` | `:58` becomes `async_fire`; **`:59` deleted** |
| `number.py:74-82` `SocLimitOverrideNumber.__init__` | `(self, entry_id, coordinator, default)`; `self._coordinator = coordinator` (`:76`) | `coordinator` removed; `:76` deleted. **`:82`'s default clamp unchanged** |
| `number.py:92` / `:96-97` | `set_soc_limit_override(...)` / `await async_request_refresh()` | `async_fire(EVENT_SOC_LIMIT_OVERRIDE_CHANGE_REQUESTED, ...)` / line deleted |
| `number.py:101-121` `async_setup_entry` | `:105` `coordinator = data["coordinator"]`; passed to both entities | `:105` deleted, `coordinator=` dropped from both. **`:104`'s `data = hass.data[DOMAIN][entry.entry_id]` stays** — still the source of `CONF_MIN_CURRENT`/`CONF_MAX_CURRENT`/the two defaults |

**The deleted `await async_request_refresh()` is the one behavior relocation, and it is worth
stating precisely.** Before: the entity applied the value, awaited a full refresh cycle, *then*
wrote its own HA state — so the entity's state write was ordered after the refresh it caused.
After: the entity fires (the coordinator applies the field synchronously inside `async_fire`, §4.3)
and writes its HA state immediately, while the refresh is scheduled by the listener. What is
preserved is the property the code actually depends on — the coordinator's field is updated before
the refresh reads it. What is dropped is the entity awaiting that refresh, which nothing reads: the
entity's displayed value comes from its own `_attr_native_value`/`_attr_current_option`, never from
the coordinator (ADR-0016's Context makes this point about the clamp — the entity already never
reads back).

**Not changed in either file:** `_attr_native_value`/`_attr_current_option` assignment, the restore
paths (`async_get_last_state` / `async_get_last_number_data`) and their clamps
(`number.py:49-52,88-91`), the option-gating logic (`select.py:50-55`), and both `__init__` default
clamps.

---

## 6. New wiring — `time.py` and `switch.py`

Nothing here is a before/after: on this branch these two files have no coordinator interaction at
all (§1.1). This section is the target shape, written so PR #452 can adopt it directly instead of
landing the held-reference version and migrating.

### 6.1 `time.py` — `SmartChargingDepartureTime`

Constructor stays `(self, entry_id, id_suffix, default)` — **no `coordinator` parameter is added**
(where `origin/dev/402` adds one). It does gain `self._id_suffix = id_suffix`, which that branch
also adds and which the fire path needs to pick its event.

`origin/dev/402`'s module-level `_DAY_SUFFIX_TO_WEEKDAY` map (derived by enumerating the Monday-first
`DAY_OF_WEEK_DEFAULTS`) is kept as-is — it is the right way to turn a suffix into `ATTR_WEEKDAY`
and is independent of this ADR.

```python
def _fire_change_request(self) -> None:
    value = self._attr_native_value
    payload_value = None if value is None else value.isoformat()   # §3.3
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

Called from two places, mirroring `select.py`: at the end of `async_added_to_hass` (after the
restore block, `time.py:73-77`, so the coordinator is seeded with the restored value rather than
the construction-time default — the actual point of issue #402), and in `async_set_value`
(`time.py:79-81`) between `_attr_native_value = value` and `async_write_ha_state()`, with **no**
`await ...async_request_refresh()`.

`origin/dev/402`'s `try/except ValueError` around `time.fromisoformat(last.state)` for a malformed
restore-cache value is orthogonal to this ADR and should be kept.

### 6.2 `switch.py` — `HomeDaySwitch`

Constructor stays `(self, entry_id)`. One event, one boolean — not two events for
`activate`/`deactivate`, because §3.1's per-field rule counts *fields*, and `home_day_flag` is one
field. The coordinator's listener still dispatches onto the two existing action-named setters
(`activate_home_day`/`deactivate_home_day`, §4.3), so the action-named vocabulary
`origin/dev/402` chose survives inside the coordinator where it reads well; it is just not what
crosses the bus.

```python
def _fire_change_request(self) -> None:
    self.hass.bus.async_fire(
        EVENT_HOME_DAY_FLAG_CHANGE_REQUESTED,
        {ATTR_ENTRY_ID: self._entry_id, ATTR_VALUE: self._attr_is_on},
    )
```

Called from four places: `async_added_to_hass` (`switch.py:31-35`, after the midnight-reset
subscription — seeds the coordinator's `False`), `async_turn_on` (`:47-49`), `async_turn_off`
(`:51-53`), and `_async_reset_at_midnight` (`:43-45`). The midnight reset is the one that matters
most and is easiest to forget: R13's daily expiry has to reach the coordinator, not just the
entity's own `is_on`. None of the four awaits a refresh.

`async_will_remove_from_hass` (`:37-41`) is unchanged — the midnight-reset unsubscribe is the
entity's own timer, unrelated to the event bus.

### 6.3 Both `async_setup_entry`s

`time.py:84-92` and `switch.py:56-59` are unchanged — neither looks up a coordinator today, and
neither starts to. (`origin/dev/402` adds that lookup plus a `DATA_COORDINATOR` constant to both;
under this shape neither is needed. If `DATA_COORDINATOR` lands separately as a de-magic-stringing
of `hass.data[...]["coordinator"]`, it is still useful for `number.py` and `sensor.py` — just not
here.)

### 6.4 The four fields become genuinely live for the first time

Today `coordinator.py:196-199` defaults `home_day_flag=False` and all four departure values to
`None`, with a comment pointing at issue #402. This slice (or PR #452 reworked onto it) is what
makes R9's solar-reserve trigger and R14's deadline resolution see real user input. That is a
**behavior change relative to `origin/main`**, not a refactor, and the end-to-end suites that
currently rely on those defaults (or set the fields directly) should be re-read rather than assumed
unaffected.

---

## 7. Testing (ADR-0009 harness split)

Everything in this slice is HA-coupled — `hass.bus`, `DataUpdateCoordinator`, entity platforms — so
per ADR-0009 **every test here is HA harness**
(`pytest-homeassistant-custom-component`). No plain-pytest test is added: there is no HA-free logic
in this slice. No new test file; assertions land in the five existing suites.

### 7.1 Entity tests — `test_select.py`, `test_number.py`, `test_time.py`, `test_switch.py`

The `_StubCoordinator` classes at `tests/test_select.py:13-26` and `tests/test_number.py:17-38` are
**deleted**, not adapted. That is the point of the ADR: there is no coordinator to double. Their
`refreshed` flag has nothing to assert against either — the refresh is no longer the entity's.

Each write-path test becomes, using
`pytest_homeassistant_custom_component.common.async_capture_events`:

```python
async def test_select_option_requests_active_mode_change(hass):
    events = async_capture_events(hass, EVENT_ACTIVE_MODE_CHANGE_REQUESTED)
    entity = ModeSelect(entry_id="abc", solar_installed=True)     # no coordinator argument
    await MockEntityPlatform(hass, domain="select").async_add_entities([entity])
    await entity.async_select_option(MODE_SOLAR)
    await hass.async_block_till_done()
    assert events[-1].data == {ATTR_ENTRY_ID: "abc", ATTR_VALUE: MODE_SOLAR}
    assert entity.current_option == MODE_SOLAR
```

Three things each entity suite must cover, per criterion 2:

1. **The right event with the right payload** — asserting the whole `event.data` dict by equality,
   not just the value key, so a missing `ATTR_ENTRY_ID` fails loudly. (`async_added_to_hass` fires
   too, hence `events[-1]`; the seeding fire is itself asserted by the restore tests, which now
   check that adding the entity fires the restored value.)
2. **No coordinator handle.** `assert not hasattr(entity, "_coordinator")` is the weak version;
   the strong version is that every construction in these four files passes no coordinator and
   would `TypeError` against today's signature. Both are cheap — do both, since the `hasattr`
   assertion is what catches a reference re-introduced later by a different route.
3. **No refresh awaited.** Not directly assertable (there is nothing to observe), but it follows
   from (2) — with no coordinator there is nothing to call `async_request_refresh` on.

Per-file specifics:

- `test_select.py`: `ModeSelect` select-option and restore; `ProfileSelect` the same. The existing
  option-gating tests (`test_restore_rejects_solar_option_when_solar_not_installed`, …) keep their
  assertions and only drop the `coordinator=coord` argument.
- `test_number.py`: both entities' set-value and restore paths. The two `__init__`-clamp tests
  (criterion 7) drop `coordinator=_StubCoordinator()` and are otherwise untouched.
- `test_time.py`: one weekday entity (payload includes the right `ATTR_WEEKDAY`), the holiday
  override, the home-day override, a `None` value (payload carries `ATTR_VALUE: None`, not a
  missing key), and the ISO-string form of a set time.
- `test_switch.py`: turn-on, turn-off, add-to-hass seeding, and **the midnight reset firing the
  event** (§6.2).

### 7.2 Coordinator tests — `tests/test_coordinator.py`

Constructed with the new `entry_id="abc"` keyword (§4.1) plus
`coord.async_register_owned_entity_listeners()`:

- **Apply, per field, eight tests** — fire the event with the matching entry id, assert the field
  holds the requested value. For `target_current`/`soc_limit_override`, one of these fires an
  out-of-range value and asserts the **clamped** result, proving the listener goes through the
  clamping setter (criterion 6) rather than assigning the field.
- **Entry-id mismatch (criterion 5)** — fire each event (at minimum a representative one, but this
  is cheap enough to do for all eight) with `ATTR_ENTRY_ID: "other"`; assert the field is
  **unchanged** and no refresh was requested. This is the genuinely new edge case ADR-0016
  introduces; it is the one test that would silently pass in a naive implementation with no filter
  if only the matching-id case were covered — so it must assert the *unchanged* field, not just
  "no exception".
- **Synchronous ordering (criterion 4)** — after `hass.bus.async_fire(...)` returns, **without**
  `await hass.async_block_till_done()`, assert the field already holds the new value. A coroutine
  listener fails this; a `@callback` listener passes. This is the only test that distinguishes the
  two, and ADR-0016's "Harder" consequence explicitly asks for it.
- **Refresh is requested by the listener** — patch/spy `async_request_refresh`, fire a matching
  event, `await hass.async_block_till_done()`, assert it was called once. Pairs with the mismatch
  test asserting it was *not*.
- **Weekday routing** — one event with `ATTR_WEEKDAY: 2` writes `departure_dow_defaults[2]` and
  leaves the other six `None`.
- **ISO parsing** — `ATTR_VALUE: "07:30:00"` becomes `time(7, 30)`; `ATTR_VALUE: None` clears.
- **Registration guard** — a coordinator constructed without `entry_id` raises on
  `async_register_owned_entity_listeners()` (§4.1's guard against a silently-dead filter).

The 45 existing `SmartChargingCoordinator(...)` constructions and the existing direct field
assignments across `test_coordinator.py`, the three end-to-end suites and
`benchmarks/test_coordinator_perf.py` are **untouched** (§4.1's defaulted keyword is what buys
this) — except where §6.4's newly-live departure/home-day fields change an end-to-end expectation.

### 7.3 Setup/teardown tests — `tests/test_init.py`

- Listeners are registered by `async_setup_entry` **before** platforms are forwarded, so an
  entity's `async_added_to_hass` seed event is not dropped (§4.5). Assert by setting up a
  `MockConfigEntry` end-to-end and checking the coordinator's `active_mode`/`target_current` hold
  the entities' seeded values rather than the constructor defaults — this is the test that would
  catch the ordering being wrong.
- **Teardown (criterion 8)** — unload the entry, then fire a matching-entry-id event, and assert
  the coordinator's field did not change. Then reload and assert exactly one apply per event (not
  two), which is the observable form of "no leaked duplicate subscription per ADR-0008 reload".

---

## 8. Packaging

```text
custom_components/smart_charging/
  const.py        # + 8 EVENT_* (§3.1) and 3 ATTR_* (§3.2) constants, below the ADR-0011 block
  coordinator.py  # + entry_id kwarg and self._entry_id (§4.1); + async_register_owned_entity_listeners
                  #   (§4.2); + 8 @callback listener methods and _schedule_refresh (§4.3).
                  #   The 4 existing setters (:617-656) are unchanged; the 4 time/switch setters
                  #   are added here or inherited from PR #452 (§9)
  __init__.py     # + entry_id=entry.entry_id on construction; + listener registration before
                  #   async_forward_entry_setups, each unsub via entry.async_on_unload (§4.5)
  select.py       # both constructors drop `coordinator`; 4 write sites fire events; 2 awaited
                  #   refreshes deleted; async_setup_entry drops the coordinator lookup
  number.py       # same, 4 write sites; async_setup_entry keeps its hass.data read for the
                  #   CONF_* values, drops only the "coordinator" key
  time.py         # + _id_suffix, + _fire_change_request, 2 call sites (new wiring, §6.1)
  switch.py       # + _fire_change_request, 4 call sites incl. the midnight reset (new wiring, §6.2)

tests/
  test_select.py      # _StubCoordinator deleted; event-payload assertions
  test_number.py      # _StubCoordinator deleted; event-payload assertions
  test_time.py        # new write-path tests (§7.1)
  test_switch.py      # new write-path tests incl. midnight reset (§7.1)
  test_coordinator.py # apply / mismatch / ordering / refresh / weekday / ISO / guard (§7.2)
  test_init.py        # registration-before-platforms and unload/reload teardown (§7.3)
docs/adl/
  0016-...md, README.md   # Proposed -> Accepted (done as part of authoring this design, header note)
```

Five production files plus `const.py` and `__init__.py` — seven in all. ADR-0016's Con names five
(`select.py`, `number.py`, `time.py`, `switch.py`, `coordinator.py`) "plus new constants, plus
listener teardown"; `const.py` and `__init__.py` are those two, counted explicitly here.

### 8.1 Suggested build order

`const.py` constants → coordinator `entry_id` + registration + the four *existing* fields'
listeners → `__init__.py` wiring → `select.py` (two entities) → `number.py` (two entities) →
`switch.py` → `time.py` → the `test_init.py` setup/teardown pass. Each of the four migrated
entities is independently shippable: its listener can land and be tested before its call site
moves. `time.py`/`switch.py` come last because §9's sequencing risk is concentrated there.

---

## 9. Sequencing against PR #452 (`dev/402`)

**Decided (human partner): Option A.** This slice covers all eight fields in one build sequence
(§§6, 8). PR #452 is reduced to nothing this slice hasn't already done — its coordinator-wiring
half is superseded by this plan — and is expected to be closed, or rebased down to only its
non-coordinator parts (the `try/except ValueError` restore-cache hardening; `DATA_COORDINATOR` if
still wanted, §10). This avoids two in-flight PRs racing on the same two files
(`time.py`/`switch.py`) and matches ADR-0016's own Consequence that the in-flight work "is expected
to be reworked onto this ADR's event shape before it merges."

---

## 10. Deliberately deferred

- **RA3's "Store" abstraction** (`docs/design/project-plan.md:149-161,361,364`: "M1 reads owned
  values through the Store", "Depends on: RA3 (Store owned-write path)"). Still exactly as relevant,
  and as deferred, as it was for ADR-0014's spec: no `Store` class exists under
  `custom_components/` today. This slice changes the *access path* of the current direct
  entity→coordinator write from a held reference to an event; it does not build, and does not
  preclude, the Store the project plan targets. If anything, an event bus is a plausible substrate
  for one — but that is a future decision, not this one.
- **ADR-0011's five domain events are untouched.** `EVENT_ACTIVE_SOC_LIMIT_CHANGED`,
  `EVENT_DEADLINE_UNREACHABLE_NOTIFIED`, `EVENT_VEHICLE_CHARGE_LIMIT_SYNCED`,
  `EVENT_MANUAL_CHARGE_LIMIT_ADOPTED`, `EVENT_VEHICLE_CHARGE_LIMIT_RESET` keep their current names,
  payloads, and — notably — their **lack of an `entry_id` key**. Adding `ATTR_ENTRY_ID` to them
  would be defensible (the same cross-talk argument applies to any consumer that appears), but they
  are Coordinator→Manager notifications with no consumer that dispatches on identity today, and
  changing a published event payload is its own decision. Named here so its absence is a choice.
- **`CycleContext` and the coordinator's internal decomposition** (`coordinator_cycle.py`,
  ADR-0012) — untouched, as under ADR-0014.
- **The read direction.** `sensor.py`'s five `CoordinatorEntity` subclasses keep their coordinator
  reference; ADR-0016 scopes itself to the write path of owned *control* entities.
- **`coordinator.py`'s internal Auto-mode `self.active_mode = ...` write** — internal, not the
  external-write concern.
- **Test fixtures assigning coordinator fields directly** (the 137 sites ADR-0014's spec counted).
  Unchanged and still deliberate: this ADR governs the production write path, not white-box test
  arrangement.
- **A return path for "your value was clamped."** ADR-0016 accepts this as a named Con: the entity
  bounds its own display via `native_min_value`/`native_max_value`, the coordinator clamps its own
  field, and the two agree by both deriving from the same config. No read-back mechanism is added
  here.
- **`DATA_COORDINATOR` as a named constant** for `hass.data[DOMAIN][entry.entry_id]["coordinator"]`
  (which `origin/dev/402` introduces). Worth doing under the no-magic-strings rule, but it is an
  unrelated cleanup and this slice *removes* three of the four remaining readers of that key
  (`select.py`, `time.py`, `switch.py`), leaving `number.py` and `sensor.py`. Left to whichever PR
  wants it.
- **Rate-limiting or coalescing repeated change requests.** A slider dragged across ten values
  fires ten events and schedules ten refreshes — identical in count to today's ten awaited
  refreshes, and `async_request_refresh`'s debouncer already collapses them. No new mechanism.

---

## 11. `entry_id` shape — confirmed

**Decided (human partner): defaulted, not required.** `entry_id: str | None = None` (§4.1), guarded
by a raise at `async_register_owned_entity_listeners()` rather than a required constructor keyword.
This keeps the 45 existing `SmartChargingCoordinator(...)` test constructions untouched, consistent
with the ADR-0014 spec's refusal to mass-rewrite test setup for a mechanical signature change.

---

## 12. Next step

This design feeds the `writing-plans` skill to produce the ordered, test-driven implementation plan
(`2026-08-02-entity-coordinator-events.md`), following §8.1's build order. No `custom_components/`
code is written until that plan exists and is approved. PR #452 (`dev/402`) is expected to be
closed or reduced to its non-coordinator parts once this slice lands (§9).
