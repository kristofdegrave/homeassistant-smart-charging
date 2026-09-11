---
name: async-python-patterns
description: asyncio rules that apply inside a Home Assistant custom integration — event-loop discipline, awaiting, cancellation, background tasks and shared state across awaits. Use when writing or reviewing async code in Smart Charging (coordinator*.py, adapters/, config_flow.py, __init__.py).
---

# Async patterns inside a Home Assistant integration

Home Assistant **owns the event loop**. The integration never creates, runs or closes one:
no `asyncio.run()`, no `new_event_loop()`, no hand-rolled `ThreadPoolExecutor`, no
`asyncio.to_thread()`. Everything below assumes HA's loop is already running and that the
integration's job is to not block it and not leak work off it.

Scoped deliberately — HA platform conventions live in `ha-integration-knowledge`, general
(non-async) Python mistakes in `python-anti-patterns`, and this project's structural rules in
`CLAUDE.md` and the ADRs. Read this file when the change touches `coordinator*.py`,
`adapters/`, `config_flow.py` or `__init__.py`.

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

A coroutine that is created and never awaited both skips its work and surfaces as a
"coroutine was never awaited" warning at an unrelated point in the log, far from the line
that caused it.

## 3. Background tasks are owned, not fire-and-forget

Never leave a bare `asyncio.create_task(...)`: the reference is dropped, the task can be
garbage-collected mid-flight, and it outlives a config-entry unload. Use HA's tracked
creators so the task is cancelled with the entry:

```python
entry.async_create_background_task(hass, _poll(), name="smart_charging_poll")
# or, for work that must finish before setup completes:
hass.async_create_task(_one_shot())
```

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

Note this is the one exception to `python-anti-patterns`' "catch specific exceptions and
handle them" rule: `CancelledError` is caught only to clean up.

## 5. Mind what an `await` interleaves

Every `await` is a yield point: other code runs before the next line does. State read before
an `await` may be stale after it.

- Read all of a cycle's inputs in one uninterrupted stretch, so the cycle sees a single
  consistent snapshot — this is why `coordinator.py` reads adapters sequentially rather than
  through `asyncio.gather` (see its own note there).
- Do not mutate shared state across an `await`; compute, then assign in one uninterrupted
  step. If you genuinely need mutual exclusion, an `asyncio.Lock` held across the smallest
  possible region — not a re-entrant cycle.

## 6. Concurrency only where there is real concurrency

`asyncio.gather` costs `Task` creation and gives up snapshot atomicity. Use it only for calls
that genuinely wait on independent external I/O. Reads that resolve from HA's in-memory state
machine have nothing to overlap — a sequential loop is both faster and safer there.

## 7. Bound anything that can hang

Any await on an external device, network call or unbounded queue gets an explicit timeout, so
one unresponsive device cannot wedge a control cycle.

```python
async with asyncio.timeout(5):
    await client.request()
```

## Quick review checklist

- [ ] No `asyncio.run`, no new event loop, no hand-rolled executor — blocking work goes
      through `hass.async_add_executor_job`
- [ ] No blocking I/O, `time.sleep`, or sync HTTP inside a coroutine
- [ ] Every coroutine call is awaited (or deliberately handed to a tracked task creator)
- [ ] No bare `asyncio.create_task`; background work uses HA's tracked creators and dies with
      the entry
- [ ] `CancelledError` is cleaned up after and re-raised, never swallowed
- [ ] No shared state mutated across an `await`; a cycle's inputs are read as one snapshot
- [ ] `gather` used only for genuinely independent external I/O
- [ ] External waits are bounded by a timeout
