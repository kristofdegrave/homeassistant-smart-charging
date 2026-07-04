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
adapter layer per mapped role, one module per mode (`solar.py`, `captar.py`, ...), and a
testing strategy (NF2) that requires mode/profile logic to be unit-testable without a
running Home Assistant instance — i.e. pure logic needs to live somewhere a test can
import without pulling in HA.

## Considered options

### Option A — Flat package (`__init__.py`, `config_flow.py`, `coordinator.py`, mode logic
and adapters as top-level modules or one `helpers.py` grab-bag)

- Pro: Fewer files and directories; matches the simplest HA custom-integration examples.
- Con: Mode logic, adapters, and profile logic would sit in the same namespace as
  HA-coupled code (`coordinator.py`, the platform files), making it easy to accidentally
  import `homeassistant.*` into what's supposed to be pure, unit-testable logic (NF2) —
  the flat layout doesn't enforce the boundary the testing strategy depends on.

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
leak into the pure-logic modules with no structural guard against it — exactly what NF2's
unit-testability requirement exists to prevent.

## Consequences

- Every new mode or profile gets its own file in `modes/`/`profiles/`; every new mapped
  role gets its own adapter class in `adapters/`, one class per role, sharing the
  `Adapter` protocol (`async def read()`, `async def write(value)`).
- `tests/` structure is dictated by this layout, not decided independently — a new
  `modes/foo.py` implies `tests/modes/test_foo.py`.
- `docs/` is unaffected; `docs/analysis/` remains the source of truth for behavior.
- This ADR does not decide anything about entity mapping, adapters' internal behavior, or
  the coordinator's pipeline — those are ADR-0003 through ADR-0006 (backfilling
  Decisions 2, 3, 5 of PR #30), all of which build on this layout without changing it.
