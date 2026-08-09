# RA3 Store — write half (implementation design)

Addendum to [`2026-08-03-ra3-store-design.md`](2026-08-03-ra3-store-design.md), which built RA3's
**read** half and named the write half as its first deliberate deferral ("**The Store's write half**
(Manager-initiated writes, e.g. M2 syncing `soc_limit_override`, M3 setting `home_day_flag`) — no
caller exists yet (M2/M3 unbuilt). Tracked as follow-up once either Manager's own implementation
spec needs it"). That caller now exists: Task 3.3 of
[`2026-07-21-vehicle-limit-manager.md`](2026-07-21-vehicle-limit-manager.md) (M2, Vehicle→System
manual adoption) must adopt a vehicle-reported charge limit into
`number.smart_charging_soc_limit_override`.

**No new architectural decision is made here.** ADR-0018 already decided both halves — "**Scope:
both the Store's read half and its write half are decided here**… a Manager that needs to set an
owned entity's value on the user's behalf (M2 syncing `soc_limit_override`; M3 setting
`home_day_flag`) writes through the same Store's write side, rather than calling a coordinator
setter or firing an event of its own" — and explicitly left the *sequencing* to the implementation
spec ("This does not commit the *implementation* of the write half to land in the same spec/PR as
the read half"). This document decides only the mechanics ADR-0018 left open: which HA mechanism
applies the value, and where the value's range clamp lives.

**This is a minimal, real-caller-driven addition, not the full write shape ADR-0018 conceptually
allows for all eight owned fields.** ADR-0018's scope covers writing any owned control entity; this
spec builds exactly one value shape — a `float` into a `number` entity — because that is what M2's
only write target needs. The read half was built the same way (its own TDD plan added `str`/`float`
in Task 2, `bool` in Task 3, `time` in Task 4, each behind its own red-green), so incremental
build-out per value shape is established precedent here, not a new compromise.

## Success criteria

1. `Store.write(entity_domain, unique_id_suffix, value)` sets a `float` on an owned `number`
   entity of this config entry, resolved by `unique_id_suffix` exactly as `read()` resolves it.
2. The write updates the **real** entity: after the call, `SocLimitOverrideNumber`'s
   `native_value` and its HA state both reflect the new value, and HA's own restore-state
   mechanism (ADR-0004) will persist it across a restart — the write goes *through* the entity,
   never around it.
3. A write that cannot be applied — entity not registered yet, `number` service unavailable,
   value rejected by the entity's own bounds — **returns a failure indication and does not
   raise**, so a Manager's reaction path cannot be broken by an owned entity being transiently
   absent.
4. `number.py`, `select.py`, `time.py`, `switch.py`, `coordinator.py` and `vehicle_limit.py` are
   **unchanged** by this addendum. It adds one method to one existing module.

## Interface

One method on the existing `Store` class, mirroring `read()`'s parameter order:

```python
# adapters/store.py
async def write(self, entity_domain: str, unique_id_suffix: str, value: float) -> bool:
    """Set `value` on this entry's owned `entity_domain` entity identified by
    `unique_id_suffix`. Returns True if the write was applied, False otherwise.
    Never raises."""
```

- `entity_domain` is kept as the first parameter — not hardcoded to `Platform.NUMBER` — so
  `write()` reads symmetrically with `read()` at every call site and so the later value shapes
  (deferred below) extend the same signature rather than replacing it. Because only the `number`
  domain is supported today, a call with any other domain returns `False` and logs at debug rather
  than silently issuing a `number.set_value` against, say, a `switch` entity. That guard is the
  honest expression of this spec's scope, and it is what a future task's genuine red will remove.
- `unique_id_suffix` is one of the existing `OWNED_SUFFIX_*` constants in `const.py` — the same
  single-source-of-truth names `read()` already takes, so the read and write sides cannot drift
  from each other or from the entity's own `_object_id_suffix` (CLAUDE.md: no magic strings).
- Returning `bool` rather than `None` matches the caller's existing shape: `VehicleLimitManager`'s
  `_write_vehicle` already returns a success flag and gates its follow-on domain event on it
  (`vehicle_limit.py:83`, `if await self._write_vehicle(default): self._fire(...)`).

## Entity resolution — identical to `read()`

`write()` resolves its target with the same two lines `read()` uses today
(`adapters/store.py:33-37`):

```python
entity_id = er.async_get(self._hass).async_get_entity_id(
    entity_domain, DOMAIN, f"{self._entry_id}_{unique_id_suffix}"
)
if entity_id is None:
    return None   # read();  write() returns False
```

Same registry lookup, same `f"{entry_id}_{unique_id_suffix}"` unique-id composition, same per-entry
scoping (one `Store` per config entry, so a write can only ever reach this entry's own owned
entities — ADR-0018's "no `entry_id` payload discipline needed"). The two halves therefore share
one resolution rule, and the not-yet-registered case (the startup race the read half's success
criterion 4 names) is a benign no-op on both sides.

## Applying the value — `number.set_value` service call

**Decision: `hass.services.async_call(Platform.NUMBER, SERVICE_SET_VALUE, {ATTR_ENTITY_ID:
entity_id, ATTR_VALUE: value}, blocking=True)`.**

The rejected alternative is writing the state machine directly
(`hass.states.async_set(entity_id, value)`, the shape `tests/helpers.py`'s `seed_owned_entity` uses
to *simulate* a user edit in tests). It fails success criterion 2 outright:

- `hass.states.async_set` writes a state object the entity does not own. The entity's
  `_attr_native_value` is untouched, so the next `async_write_ha_state()` the entity performs for
  any reason overwrites the injected state back to the entity's stale value.
- `SocLimitOverrideNumber` extends `RestoreNumber`, which persists `native_value` — not the raw
  state string — so a direct state write is silently lost across a restart, contradicting ADR-0004
  ("owned-entity state persists via HA's own restore-state mechanism").

The service call, by contrast, is dispatched by HA's `number` component to the registered entity
object, which calls `SocLimitOverrideNumber.async_set_native_value` — inherited from
`_RestoreClampedNumberMixin` (`number.py:41-43`) — whose body is exactly
`self._attr_native_value = value; self.async_write_ha_state()`. Both halves of criterion 2 fall out
of that single call, with no new entity-side code.

This also mirrors the existing ADR-0003 precedent for writing a `number` entity:
`NumericReadWriteAdapter.write` (`adapters/numeric.py:22-28`) is the same
`hass.services.async_call("number", "set_value", …, blocking=True)`. The Store's write half is the
owned-entity twin of that adapter's write, exactly as its read half is the owned-entity twin of
`NumericReadAdapter.read()`. `blocking=True` is kept for the same reason the adapter keeps it — the
caller needs the write to have been applied before it acts on the outcome. Service/attribute names
come from HA's own constants (`Platform.NUMBER`, `homeassistant.components.number.SERVICE_SET_VALUE`
/ `ATTR_VALUE`, `homeassistant.const.ATTR_ENTITY_ID`), not the bare literals `numeric.py` still
uses — CLAUDE.md's no-magic-strings rule applies to new code; retrofitting `numeric.py` is out of
scope here.

## Error handling — best effort, never raises

`Store.write` wraps the service call in a `try`/`except Exception` (with a `# noqa: BLE001` and a
debug log, matching `_write_vehicle`'s own broad catch at `vehicle_limit.py:94-96`) and returns
`False`. Three failure modes are folded into that one path:

| Failure | Cause | Result |
| --- | --- | --- |
| Entity not registered | Startup race; owned entity's platform not yet set up | `False`, no service call |
| Service unavailable / entity absent from the state machine | Entry mid-unload or mid-reload | `False`, logged at debug |
| Value outside the entity's `native_min_value`/`native_max_value` | Caller passed an unclamped value; HA's `number` component validates the range and raises | `False`, logged at debug |

This mirrors both sides of the existing contract. `Store.read()` already documents "never raises
(mirrors `NumericReadAdapter.read()`, ADR-0003)"; keeping `write()` symmetric means the whole Store
surface is total. And `Adapter.write()`'s contract (`adapters/base.py:22-24`) is *permitted* to
raise — which is precisely why its only real caller, `VehicleLimitManager._write_vehicle`, wraps it
in a try/except and converts it to a boolean. Putting that conversion inside `Store.write` instead
of at each Manager call site means the best-effort contract is guaranteed once, at the Resource
Access boundary, rather than re-implemented (or forgotten) by every future Manager.

Deliberately **not** an ADR-0007 fault: ADR-0007's fault path is for external hardware. The read
half's success criterion 4 already established that owned entities are internal and a transient
miss is not a fault condition; a failed owned-entity write is the same class of event, so it is
logged and reported to the caller, never escalated.

## Clamping — the calling Manager, with the entity's bounds as the backstop

**Decision: the caller clamps; the Store does not.**

- The Store is Resource Access (Löwy: mechanics, no policy). "The default SOC limit lives in
  50–100" is R6's policy, owned by M2 — the same reasoning that keeps `set_target_current`'s clamp
  in the Coordinator rather than in `read()`. A Store that clamped would have to know *which*
  bound applies to *which* suffix, i.e. hold policy for eight fields it otherwise knows nothing
  about.
- The retired Task 3.3 snippet already clamped in the Manager
  (`adopted = min(max(float(reported), _SOC_MIN), _SOC_MAX)`) before calling its setter. That
  placement survives the switch to the Store; only the call it wraps changes. Note the snippet's
  `_SOC_MIN`/`_SOC_MAX` module-level constants **do not exist** in the current
  `managers/vehicle_limit.py` — the Task 3.1/3.2 implementation carries no clamp at all (its module
  docstring says so: "No control-cycle logic, no clamps, no set-point"). The constants that do
  exist, and that Task 3.3 must use, are `SOC_LIMIT_OVERRIDE_MIN`/`SOC_LIMIT_OVERRIDE_MAX` in
  `const.py:234-235`, already shared by `number.py`'s own `_attr_native_min_value`/
  `_attr_native_max_value` (`number.py:73-74`). Reusing them keeps the Manager's clamp and the
  entity's bounds a single source of truth rather than two constants that can drift.
- **Defended at the boundary anyway, without duplicating the bound.** The chosen service-call
  mechanism means HA's `number` component validates the value against the *entity's own*
  min/max and raises on violation — which this spec's error handling converts to `False` plus a
  debug log. So an unclamped caller gets a loud-in-the-log, no-op write rather than a corrupted
  entity value or an exception escaping into a Manager's reaction path. That is the defence, and
  it costs no second copy of `50`/`100` anywhere.

## Mapping to `system-design.md` services

| Piece | Service |
| --- | --- |
| `adapters/store.py` `Store.write` | Resource Access, **V13 — Config/State Store access** (`system-design.md` §3: "reads **and writes** owned-entity state via HA's entity registry (ADR-0004/0005)") — the write half of the same service the read half realizes; `project-plan.md` **RA3** |
| The `number` entity the write lands on | C2 (owned control entities, Clients) — unchanged by this spec |
| Future caller `VehicleLimitManager.on_vehicle_limit_changed` | Manager, **M2 — Vehicle-Limit Manager (V12)**; built by its own plan's Task 3.3, not here |

No new service, no new call direction, no new volatility: `system-design.md` §3 already names
writes as part of V13's scope, and ADR-0018 already routes Manager→owned-entity writes through it.
This adds one method to one existing file.

## Testing approach (ADR-0009)

`adapters/store.py` is HA-coupled (entity registry, state machine, service registry) → **HA
harness**, extending the existing `tests/adapters/test_store.py`.

One deviation from the read tests' fixture: the read suite's `_register` helper
(`test_store.py:12-19`) registers an entity in the registry and pushes a state string — enough for
`hass.states.get`, but **not** enough for a service call, because no entity *object* exists to
receive `async_set_native_value`. The write tests therefore set up the real config entry
(`MockConfigEntry` + `hass.config_entries.async_setup`, the shape `tests/test_init.py` already
uses with `entry_data_base()`/`entry_options_base()` from `tests/helpers.py`), so the genuine
`SocLimitOverrideNumber` is registered and reachable. That is also what makes success criterion 2
testable at all: the assertion is against the real entity's own state, so a mechanism that merely
stamped the state machine would pass criterion 1 and still be caught here on the next entity
write.

Coverage: successful write (real entity's state changes); unregistered `unique_id_suffix` →
`False`, no raise; a non-`number` `entity_domain` → `False`, no raise; a service failure →
`False`, no raise; an out-of-range value → `False`, no raise, entity's value unchanged.

## Packaging

- **Edited:** `custom_components/smart_charging/adapters/store.py` (one new method),
  `tests/adapters/test_store.py`.
- **No new module** — ADR-0019 already homed the Store at `adapters/store.py`, and the write half
  is the same class's other half, not a separate collaborator.
- **Unedited:** `number.py`, `select.py`, `time.py`, `switch.py`, `coordinator.py`, `const.py`,
  `__init__.py`, `managers/vehicle_limit.py`.

## Deliberate deferrals

- **Write support for `bool`/`str`/`time` values** (`switch`/`select`/`time` owned entities, e.g.
  M3 setting `home_day_flag` per ADR-0018). No caller exists — M3 is unbuilt. Each will need its
  own domain service (`switch.turn_on`/`turn_off`, `select.select_option`, `time.set_value`) and so
  its own red-green, exactly as the read half added one value shape per task.
- **Config-entry data/options *writes* through the Store** — part of RA3's full `project-plan.md`
  scope; still no caller (the read half deferred the reads for the same reason).
- **Diagnostic-entity writes through the Store** (`system-design.md`'s
  Coordinator-writes-diagnostics path) — untouched, on whatever mechanism they use today, same as
  the read half's deferral.
- **Retrofitting `NumericReadWriteAdapter`'s bare `"number"`/`"set_value"` literals** onto HA's
  constants — a real (small) no-magic-strings debt, but not this spec's change surface.
- **Task 3.3 of the Vehicle-Limit Manager plan** — the first caller. That plan is separately
  approved and must be updated to call `Store.write` (with the `SOC_LIMIT_OVERRIDE_MIN`/`_MAX`
  clamp this document places in the Manager) instead of the retired `_set_default_soc_limit`
  setter-callback snippet. Not done here.
