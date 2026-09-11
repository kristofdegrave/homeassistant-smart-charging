---
name: python-anti-patterns
description: Python anti-pattern checklist for the Smart Charging Home Assistant integration — the general-Python mistakes to catch before committing code under custom_components/smart_charging/. Use as a pre-commit self-check and during code review.
---

# Python Anti-Patterns Checklist

A short checklist of **general-Python** mistakes to catch before a change under
`custom_components/smart_charging/` is committed, and while reviewing one. Test authoring has
its own rules — `write-tests` and `test-reviewer` own those.

Scoped deliberately: this file carries only rules that are **not** owned elsewhere — HA
platform conventions belong to `ha-integration-knowledge`, everything about the event loop to
`async-python-patterns`, and this project's structural rules to `CLAUDE.md` and the ADRs.

## Error handling

### Bare exception handling

```python
# BAD: swallows everything; a broken adapter read looks like a healthy cycle
try:
    value = read()
except Exception:
    pass
```

**Fix:** catch the specific exception, and either handle it meaningfully or let it reach the
path that is designed to deal with it (in this integration, the fault path).

**Sanctioned broad catches.** This integration deliberately keeps several `except Exception`
boundaries, because a design rule requires the failure to be *absorbed* rather than propagate:
the coordinator's `_async_update_data` fault funnel (ADR-0007 — every failure becomes 0 A +
`Fault`), `Store.write`'s best-effort service call (ADR-0018 — explicitly *not* a hardware
fault), `_safe_write_zero`, the notification-delivery paths, the vehicle-limit write to a
possibly-unplugged car, and the dashboard registration a Client must not take the control loop
down with (ADR-0022).

What makes one legitimate is not the file it sits in: it is marked `# noqa: BLE001` (where the
linter would object) **and** carries a comment naming the rule that requires absorbing the
failure. A broad catch missing either is the anti-pattern above; one with both is a safety
invariant — do not flag it, and do not add a new one without the same justification.

```python
# GOOD
try:
    value = read()
except (ValueError, TypeError):
    _LOGGER.warning("Unparseable reading from %s", entity_id)
    return None
```

### Ignored partial failures

Iterating a set of independent items and letting the first error abort the whole batch loses
the results that did succeed. Decide explicitly: either collect successes and failures, or
document that one failure must fail the whole operation.

## Resources

### Unclosed resources

```python
# BAD
f = open(path)
return f.read()      # leaks the handle if read() raises

# GOOD
with open(path) as f:
    return f.read()
```

Anything with `close()`/`__exit__` (files, sessions, subscriptions) is acquired in a `with` /
`async with`, or has an explicit paired teardown.

## Type safety

### Missing type hints

Annotate every public function, method and dataclass field. An unannotated helper is invisible
to both the reader and the type checker.

```python
# BAD
def process(data):
    return data["value"] * 2

# GOOD
def process(data: dict[str, int]) -> int:
    return data["value"] * 2
```

### Untyped collections

`list`, `dict`, `tuple` without parameters say nothing. Write `list[AdapterReading]`,
`dict[str, float]`, `tuple[float, float]`.

## Quick review checklist

Run this before committing, and when reviewing a diff:

- [ ] No bare `except Exception:` — least of all one that swallows (`pass`) or hides a fault.
      A broad catch is legitimate only when it is `# noqa: BLE001`-marked *and* names the rule
      that requires absorbing the failure (see above); unmarked or unexplained is a finding
- [ ] Exceptions caught are specific, and either handled or deliberately re-raised
- [ ] No batch/loop that silently drops the successes when one item fails
- [ ] Every acquired resource is released (`with` / `async with` / paired teardown)
- [ ] All public functions, methods and dataclass fields have type hints
- [ ] Collection annotations carry their type parameters
