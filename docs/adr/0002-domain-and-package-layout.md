# ADR-0002: Domain slug and package layout for the `smart_charging` integration

Date: 2026-07-04
Status: Accepted

## Context

Before any scaffolding happens, the integration needs a domain slug (the string Home
Assistant uses to identify it — config flow, entity unique IDs, `manifest.json`) and a
package layout under `custom_components/`. This is backfilled from Decision 1 of
`docs/plans/2026-07-04-integration-architecture-design.md` (PR #30, still open — see
ADR-0001's plan to give each of that doc's decisions its own ADR before #30 merges).

The layout has to accommodate what's already decided elsewhere in that design: a Python
adapter layer per mapped role, and one module per mode (`solar.py`, `captar.py`, ...).
NF2 requires each mode and profile to be "implemented in its own self-contained unit with
no logic belonging to another" — that boundary needs to be structural, not just a
convention, or a later change can quietly blur it. A useful side effect of enforcing that
boundary with no direct HA access is that mode/profile logic becomes unit-testable without
a running Home Assistant instance, which the testing strategy (Decision 7 of the same
design doc) relies on — but that testability is a consequence of satisfying NF2, not
something NF2 itself states.

The domain slug (`smart_charging`) is a much smaller decision bundled into the same ADR
rather than split out: it simply follows the project's existing name, with no real
alternative debated, so it doesn't warrant its own Considered-options section.

## Considered options

### Option A — Flat package (`__init__.py`, `config_flow.py`, `coordinator.py`, mode logic
and adapters as top-level modules or one `helpers.py` grab-bag)

- Pro: Fewer files and directories; matches the simplest HA custom-integration examples.
- Con: Mode logic, adapters, and profile logic would sit in the same namespace as
  HA-coupled code (`coordinator.py`, the platform files), making it easy to accidentally
  import `homeassistant.*` into logic NF2 requires stay self-contained — the flat layout
  doesn't structurally enforce that boundary, and loses the unit-testability that
  enforcing it happens to buy.

### Option B — Modular subpackages (`adapters/`, `modes/`, `profiles/`), platform files
(`select.py`, `number.py`, ...) at the package root, `tests/` mirroring the structure

- Pro: The directory boundary matches the architectural boundary — `modes/` and
  `profiles/` contain only pure logic (smoothed readings + config in, desired current
  out), `adapters/` isolates all HA-entity I/O behind one `Adapter` protocol. A test
  importing `modes.solar` cannot accidentally pull in HA. `tests/` mirroring the package
  makes it obvious where a new module's tests belong.
- Con: More directories/files up front than the integration currently needs (e.g. `Auto`
  profile logic, R5–R13 use-cases aren't built yet) — some subpackages start nearly
  empty.

## Decision

Option B. Domain/slug: `smart_charging`. Package: `custom_components/smart_charging/`,
with `adapters/`, `modes/`, `profiles/` subpackages, platform files
(`select.py`/`number.py`/`time.py`/`sensor.py`/`switch.py`/`binary_sensor.py`) and
`entity.py` (base classes for owned entities) at the package root, and `coordinator.py`
driving the control cycle. `tests/` mirrors this structure 1:1. Option B's empty-directory
cost (Con) is accepted because the alternative (Option A) would have let HA-coupled code
leak into the pure-logic modules with no structural guard against it — exactly the
self-containment NF2 requires, with easy unit-testing as the side benefit.

## Consequences

- Every new mode or profile gets its own file in `modes/`/`profiles/`; every new mapped
  role gets its own adapter class in `adapters/`, one class per role, sharing the
  `Adapter` protocol (`async def read()`, `async def write(value)`).
- `tests/` structure is dictated by this layout, not decided independently — a new
  `modes/foo.py` implies `tests/modes/test_foo.py`.
- `docs/` is unaffected; `docs/analysis/` remains the source of truth for behavior.
- This ADR does not decide anything about entity mapping, adapters' internal behavior, the
  coordinator's pipeline, error handling, or testing — those are ADR-0003 through ADR-0008
  (backfilling Decisions 2–7 of PR #30), all of which build on this layout without
  changing it.
