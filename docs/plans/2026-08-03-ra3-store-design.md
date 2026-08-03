# RA3 Store — implementation design

Slice: `docs/design/project-plan.md` Phase 1, **RA3 — Config/State Store access** (the read half
consumed by M1), realizing ADR-0018 (entity-to-coordinator access via the Store) and ADR-0019
(package home: `adapters/store.py`). This spec covers the read half only — the Store's write half
(a Manager writing an owned entity on the user's behalf, e.g. M2/M3) is out of scope; neither
Manager exists yet (ADR-0018 Decision, "Scope: both... decided here" / "does not commit the
*implementation* of the write half to land in the same spec").

## Success criteria

1. The Coordinator reads all eight owned control-entity values (`active_mode`, `active_profile`,
   `target_current`, `soc_limit_override`, `home_day_flag`, `departure_dow_defaults` ×7,
   `departure_holiday_override`, `departure_home_day_override`) through the Store once per cycle,
   before the rest of `_run_cycle` runs — realizing `system-design.md`'s revised §5.1 sequence.
2. `select.py`'s `ModeSelect`/`ProfileSelect` and `number.py`'s `TargetCurrentNumber`/
   `SocLimitOverrideNumber` no longer hold a coordinator reference or call a coordinator setter —
   they only manage their own HA-native state (ADR-0018 Consequences: "entity platform code…
   needs no coordinator reference and no event-firing code at all").
3. `time.py`'s `SmartChargingDepartureTime` and `switch.py`'s `HomeDaySwitch` are unchanged — they
   already have no coordinator reference (confirmed by reading the current code), so issue #402
   ("R9/R14 currently inert") is closed purely by the Coordinator-side read wiring.
4. A missing/unresolvable owned-entity read (entity not yet registered, or `unknown`/`unavailable`)
   leaves the Coordinator's current value for that field unchanged and does **not** enter
   ADR-0007's fault path — confirmed with the human partner: owned entities are internal, not
   external hardware, and a transient startup race is not a fault condition.

## The Store's read interface

One generic method, called once per field (confirmed with the human partner over a
one-dedicated-method-per-field or one-snapshot-method alternative):

```python
# adapters/store.py
async def read(self, entity_domain: str, unique_id_suffix: str, value_type: type[T]) -> T | None:
    """Resolve f"{entry_id}_{unique_id_suffix}" as an entity_domain entity via the entity
    registry, read its current HA state, and coerce to value_type. None if the entity isn't
    registered yet, its state is missing/unknown/unavailable, or coercion fails."""
```

- `entity_domain` is `Platform.SELECT`/`Platform.NUMBER`/`Platform.SWITCH`/`Platform.TIME` (HA's
  own `homeassistant.const.Platform` enum — no new magic strings). Named `entity_domain` rather
  than `platform` to match HA's own `async_get_entity_id(domain, platform, unique_id)` vocabulary,
  where `domain` is the entity's domain and `platform` means the integration.
- `unique_id_suffix` is one of the `OWNED_SUFFIX_*` constants added to `const.py` (Task 1), shared
  between `select.py`/`number.py`'s `_attr_unique_id` and the Store's read calls, so those two
  sides cannot drift apart, the same "single source of truth" property `CONF_MIN_CURRENT` already
  gives `coordinator.py`/`number.py`. `time.py`/`switch.py` keep their own inline suffix strings
  (they're out of scope for this slice's edits — see Entity-side changes below); nothing
  structurally prevents those from drifting from the matching `OWNED_SUFFIX_*` constant, but the
  TDD plan's Task 8 (migrating the end-to-end suites to seed the *real* time/switch entities) is
  what actually exercises that path end-to-end, so a drift would surface as a failing assertion
  there, not pass silently.
- `value_type` is `str`, `float`, `bool`, or `datetime.time` — the four value shapes the eight
  fields need. Coercion:
  - `str`: the raw state string (mode/profile options), unless it's `unknown`/`unavailable`.
  - `float`: `float(state.state)`, `None` on `ValueError`/`TypeError`/`unknown`/`unavailable` —
    mirrors `NumericReadAdapter.read()` exactly (ADR-0003 precedent).
  - `bool`: `state.state == "on"` for a `switch` entity's `on`/`off` state; `unavailable` → `None`.
  - `time`: `time.fromisoformat(state.state)`, `None` on `unknown`/`unavailable`/absent — mirrors
    `SmartChargingDepartureTime.async_added_to_hass`'s own restore-parsing.
- Entity resolution: `entity_registry.async_get(self._hass).async_get_entity_id(entity_domain,
  DOMAIN, f"{self._entry_id}_{unique_id_suffix}")`. Returns `None` if the entity isn't registered
  yet (the startup-race case success criterion 4 names) — `read()` returns `None` in that case too,
  never raises.
- No config-entry **data**/**options** reads are built in this slice. RA3's full scope
  (project-plan.md) includes those, but nothing in this slice's callers needs them —
  `coordinator.py` already reads `CONF_*` config directly from the `config` dict `__init__.py`
  assembles (unaffected by this change). Adding that surface to the Store is deferred to whichever
  future slice first needs a caller for it, named here so it isn't silently forgotten.

## Coordinator wiring

A new first step in `_run_cycle`, before the existing `read raw (status, net_w, charger_w,
optionally voltage, optionally ev_soc)` step (`system-design.md` §5.1's revised sequence):

```python
async def _read_owned_entities(self) -> None:
    mode = await self._store.read(Platform.SELECT, OWNED_SUFFIX_MODE, str)
    if mode is not None:
        self.set_active_mode(mode)
    profile = await self._store.read(Platform.SELECT, OWNED_SUFFIX_PROFILE, str)
    if profile is not None:
        self.set_active_profile(profile)
    target_current = await self._store.read(Platform.NUMBER, OWNED_SUFFIX_TARGET_CURRENT, float)
    if target_current is not None:
        self.set_target_current(target_current)
    soc_limit = await self._store.read(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, float)
    if soc_limit is not None:
        self.set_soc_limit_override(soc_limit)
    home_day = await self._store.read(Platform.SWITCH, OWNED_SUFFIX_HOME_DAY, bool)
    if home_day is not None:
        self.home_day_flag = home_day
    for weekday, suffix in enumerate(OWNED_SUFFIX_DEPARTURE_DOW):  # Monday=0 .. Sunday=6
        value = await self._store.read(Platform.TIME, suffix, time)
        self.departure_dow_defaults[weekday] = value if value is not None else \
            self.departure_dow_defaults[weekday]
    holiday = await self._store.read(Platform.TIME, OWNED_SUFFIX_DEPARTURE_HOLIDAY, time)
    if holiday is not None:
        self.departure_holiday_override = holiday
    home_day_override = await self._store.read(Platform.TIME, OWNED_SUFFIX_DEPARTURE_HOME_DAY, time)
    if home_day_override is not None:
        self.departure_home_day_override = home_day_override
```

**Why these stay coordinator fields, not local values used directly:** all eight are read from
`self` at several points scattered through `_run_cycle`, not once right after being set —
`self.active_mode` alone at ~36 sites (mode dispatch, the SOC-gate check, `CycleResult`
construction, …), and `self.home_day_flag`/`self.departure_*` each at two separate
`resolve_departure_deadline` calls (today's and tomorrow's deadline, `coordinator.py:358-365` /
`:410-417`) with unrelated logic (SOC-Target resolution) in between. Keeping them as fields means
none of those existing downstream read sites change at all — only the entity-facing write path
does. Four of the eight (`active_mode`/`active_profile`/`target_current`/`soc_limit_override`)
have been coordinator fields since ADR-0014; the other four (`home_day_flag`/`departure_*`) were
already declared this way in `__init__` before this spec, waiting on exactly this wiring (the
"tracked separately, issue #402" comment at `coordinator.py:190-195`). Converting any of them to
pure local variables threaded as explicit parameters through every downstream call site would be a
materially larger, riskier diff for no behavioral difference — and would be redesigning the
Coordinator's internal data-flow shape, not populating it via a new mechanism, which is this
slice's actual job.

Each field keeps its current value when the Store returns `None` (success criterion 4) — the
`if x is not None:` guard is the whole mechanism, no separate fault branch. `set_active_mode`/
`set_active_profile`/`set_target_current`/`set_soc_limit_override`'s *bodies* (the clamping logic)
are unchanged — only their *caller* changes, from an entity's `async_select_option`/
`async_set_native_value` to the Coordinator's own read step. ADR-0018 supersedes ADR-0016 (which
superseded ADR-0014), but its Consequences keep this coordinator-side clamp as the mutation point
going forward ("the caller's access path changes… not the mutation point") — this spec's setters
are that continuation, not a citation of ADR-0014 as still-governing.

`_read_owned_entities()` is called first inside `_run_cycle`, so a mode/profile change the user
made since the last cycle is visible to every step that follows in the same cycle it's read —
matching `system-design.md` §5.1's placement (before the hardware-adapter read).

## Entity-side changes

- `select.py` (`ModeSelect`, `ProfileSelect`) and `number.py` (`TargetCurrentNumber`,
  `SocLimitOverrideNumber`): remove the `coordinator` constructor parameter, the
  `self._coordinator = coordinator` assignment, and every `self._coordinator.set_*`/
  `async_request_refresh()` call. `async_added_to_hass`/`async_select_option`/
  `async_set_native_value` keep exactly their existing restore/clamp/`async_write_ha_state()`
  behavior — they already write their own state correctly today; only the coordinator-facing calls
  are removed.
- `async_setup_entry` in both files stops passing `coordinator=coordinator` to these four
  entities' constructors (it still reads `coordinator` from `hass.data` for nothing else these
  entities need, so the local variable may become unused there — checked per file).
- `time.py`/`switch.py`: **no changes.** Confirmed neither `SmartChargingDepartureTime` nor
  `HomeDaySwitch` holds a coordinator reference today.
- `__init__.py`: construct `Store(hass, entry.entry_id)` alongside the existing `adapters` dict,
  pass it to `SmartChargingCoordinator(..., store=store, ...)`.

## Mapping to `system-design.md` services

| Piece | Service |
| --- | --- |
| `adapters/store.py` `Store` class | Resource Access, V13 (Config/State Store access) |
| `Coordinator._read_owned_entities` | Manager (Charging Coordinator, M1) — new first read step |
| `OWNED_SUFFIX_*` constants | shared by C2 (owned control entities, Clients) and the Store |

No new service, call direction, or volatility — this slice only adds a concrete file
(`adapters/store.py`), a coordinator method, and constants, per ADR-0018/ADR-0019's already-decided
shape.

## Deliberate deferrals

- **The Store's write half** (Manager-initiated writes, e.g. M2 syncing `soc_limit_override`, M3
  setting `home_day_flag`) — no caller exists yet (M2/M3 unbuilt). Tracked as follow-up once
  either Manager's own implementation spec needs it.
- **Config-entry data/options reads through the Store** — RA3's full project-plan.md scope, not
  needed by any caller in this slice (`coordinator.py` already reads `CONF_*` directly).
- **Sub-cycle responsiveness** (ADR-0018's Option C, HA state-change subscription) — explicitly
  not built; a user's change takes effect on the Coordinator's next scheduled cycle, per ADR-0018's
  accepted trade-off.
- **Diagnostic-entity writes through the Store** (`system-design.md`'s Coordinator-writes-diagnostics
  path, e.g. `sensor.smart_charging_monthly_peak_kw`) — this slice only adds the Store's *read*
  side for owned control entities; diagnostic writes stay on whatever mechanism they use today,
  untouched.

## Testing approach (ADR-0009)

- `adapters/store.py` is HA-coupled (reads `hass.states`, the entity registry) → **HA harness**,
  `tests/adapters/test_store.py`, mirroring `test_numeric.py`'s edge-case matrix (absent entity,
  `unknown`, `unavailable`, successful read) for each `value_type`, plus the entity-registry
  resolution itself (registered vs. not-yet-registered unique_id).
- `Coordinator._read_owned_entities` is HA-coupled (calls the Store, mutates coordinator state) →
  **HA harness**, extending `tests/test_coordinator.py`: each field updates from a Store value,
  each field is left unchanged when the Store returns `None`, and the four already-clamped setters
  still clamp when fed a Store-read out-of-range value.
- `select.py`/`number.py`'s four entities lose their coordinator-double assertions; their existing
  restore/clamp/display tests are otherwise unaffected — confirmed no other behavior changes.

## Packaging

- New: `custom_components/smart_charging/adapters/store.py`, `tests/adapters/test_store.py`.
- Edited: `coordinator.py` (`_read_owned_entities`, constructor `store` param), `select.py`,
  `number.py`, `__init__.py`, `const.py` (`OWNED_SUFFIX_*`).
- Unedited: `time.py`, `switch.py`.
