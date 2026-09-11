---
name: async-python-patterns
description: asyncio rules that apply inside a Home Assistant custom integration — event-loop discipline, awaiting, cancellation, entry-scoped listeners and shared state across awaits. Use when writing or reviewing any Smart Charging file that is not pure modes/ or engines/ logic.
---

# Async patterns inside a Home Assistant integration

Home Assistant **owns the event loop**. The integration never creates, runs or closes one:
no `asyncio.run()`, no `new_event_loop()`, no hand-rolled `ThreadPoolExecutor`, no
`asyncio.to_thread()`. Everything below assumes HA's loop is already running and that the
integration's job is to not block it and not leak work off it.

Scoped deliberately — HA platform conventions live in `ha-integration-knowledge`, general
(non-async) Python mistakes in `python-anti-patterns`, and this project's structural rules in
`CLAUDE.md` and the ADRs.

**When this file applies** — the single statement of the condition, which everything else
points at: any changed file under `custom_components/smart_charging/` that is **not** pure
`modes/`/`engines/` logic. That is the coordinator, `adapters/`, `managers/`, `config_flow.py`,
`__init__.py`, `dashboard.py` and the entity platform files — all of them run on HA's loop.

## 1. Never block the event loop

A blocking call inside a coroutine stalls every integration in the instance, not just this one.

```python
# BAD
async def _write_dashboard(path, payload):
    time.sleep(1)
    path.write_text(payload)      # blocking file I/O on the loop
```

**Fix:** `await asyncio.sleep(...)` for delays, and push blocking work to HA's own executor.

```python
# GOOD
await hass.async_add_executor_job(_write)
```

Blocking includes: file and socket I/O, `requests`, `time.sleep`, `subprocess`, and any
library call that is not documented as async-safe.

## 2. Always await a coroutine

```python
result = adapter.async_read()          # BAD: a coroutine object, never executed
result = await adapter.async_read()    # GOOD
```

A coroutine created and never awaited skips its work and surfaces as a "never awaited"
warning far from the line that caused it.

## 3. Anything that outlives the call is tied to the config entry

Every timer, state listener and subscription registered during setup must stop when the entry
unloads. This is load-bearing here: ADR-0008 reloads the entry on every reconfigure and every
options change, so a leaked registration is not a rare edge case — each reload adds another
one. Register the unsubscribe with `entry.async_on_unload(...)` **at the point you create
it**, or hand the unsub straight back to setup, which does — both shapes are in use here:

```python
# register at creation (__init__.py)
entry.async_on_unload(
    async_track_time_interval(
        hass, notification_manager.async_evaluate, timedelta(seconds=interval_s)
    )
)

# or hand the unsubs back to setup, which registers them (managers/vehicle_limit.py)
for unsub in vehicle_limit_manager.register_listeners(...):
    entry.async_on_unload(unsub)
```

(The coordinator itself needs none of this: `DataUpdateCoordinator` takes `update_interval`
and HA owns that timer.)

A registration whose unsubscribe is dropped survives the reload and then fires twice — see
`__init__.py`'s own note on the leak this fixed.

For a genuinely long-running coroutine, use `entry.async_create_background_task(...)` so it is
tracked and cancelled with the entry — never a bare `asyncio.create_task(...)`, whose reference
is dropped, which can be garbage-collected mid-flight, and which outlives the unload.

## 4. Handle cancellation, re-raise it

`CancelledError` is how HA shuts an entry down. Clean up and re-raise; never swallow it into a
generic handler.

```python
try:
    while True:
        await asyncio.sleep(interval)
        await self._cycle()
except asyncio.CancelledError:
    self._release()
    raise            # propagate, always
```

This is a specific catch, so it satisfies `python-anti-patterns`' rule — with one twist:
`CancelledError` is caught **only** to clean up, never to handle. Re-raising is mandatory.

## 5. Mind what an `await` interleaves

Every `await` is a yield point: other code runs before the next line does. State read before
an `await` may be stale after it.

- Read all of a cycle's inputs in one uninterrupted stretch, so the cycle sees a single
  consistent snapshot — this is why `coordinator.py`'s `_read_owned_entities` reads
  sequentially rather than through `asyncio.gather`, and documents why in its own docstring.
- Do not mutate shared state across an `await`; compute, then assign in one uninterrupted
  step. If you genuinely need mutual exclusion, an `asyncio.Lock` held across the smallest
  possible region — not a re-entrant cycle.

## 6. Concurrency only where there is real concurrency

`asyncio.gather` costs `Task` creation and gives up snapshot atomicity. Use it only for calls
that genuinely wait on independent external I/O. Reads that resolve from HA's in-memory state
machine have nothing to overlap — a sequential loop is both faster and safer there.

## 7. Bound anything that can hang

No current call site — every read today resolves from `hass.states` in memory. This applies
the first time an adapter talks to a device or a network: bound every such await with an
explicit timeout, so one unresponsive device cannot wedge a control cycle.

```python
async with asyncio.timeout(5):
    await client.request()
```

## Quick review checklist

- [ ] No `asyncio.run`, no new event loop, no hand-rolled executor — blocking work goes
      through `hass.async_add_executor_job`
- [ ] No blocking I/O, `time.sleep`, or sync HTTP inside a coroutine
- [ ] Every coroutine call is awaited (or deliberately handed to a tracked task creator)
- [ ] Every timer, listener and subscription created during setup has its unsubscribe passed
      to `entry.async_on_unload(...)`
- [ ] No bare `asyncio.create_task`; background work uses HA's tracked creators and dies with
      the entry
- [ ] `CancelledError` is cleaned up after and re-raised, never swallowed
- [ ] No shared state mutated across an `await`; a cycle's inputs are read as one snapshot
- [ ] `gather` used only for genuinely independent external I/O
- [ ] External waits are bounded by a timeout
