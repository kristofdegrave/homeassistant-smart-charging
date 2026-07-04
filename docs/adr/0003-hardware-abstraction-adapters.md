# ADR-0003: Hardware abstraction via config-flow entity mapping and Python adapters

Date: 2026-07-04
Status: Proposed

## Context

The coordinator's control logic (UC01-UC04) needs a small, fixed set of inputs regardless
of which charger, EV, or grid-metering hardware a given installation uses: charger
current (read/write), EV SOC, solar power, charger power, grid voltage, monthly peak
demand, and charger status. Real installations expose these through wildly different
entities — a Tesla's SOC sensor looks nothing like a Zaptec charger's current number
entity — and the integration must be hardware-agnostic (see the project's hardware-
agnostic scope: reference hardware is an example, not a hard dependency).

This is backfilled from Decision 2 of
`docs/plans/2026-07-04-integration-architecture-design.md` (PR #30, still open — see
ADR-0001's plan to give each of that doc's decisions its own ADR before #30 merges).
ADR-0002 already assumes an `adapters/` subpackage and an `Adapter` protocol
(`async def read()`, `async def write(value)`) exist; this ADR is the decision that
subpackage implements.

**Known conflict — issue #29.** `requirements.md` NF3 (Must) currently reads literally:
"every sensor value used by the charging logic is read from an `sc_`-prefixed wrapper
**entity**," and `entity-catalog.md` operationalizes that literally as concrete HA
entities (`sensor.sc_net_power_w`, `number.sc_charger_current`, etc.), stating raw
upstream entities are "never catalog rows." The decision recorded below treats the "`sc_`
wrapper" as a Python-side adapter layer, not new HA entities — which conflicts with that
committed text. Until NF3 and `entity-catalog.md` are actually reworded (tracked in issue
#29, via the standard write-requirement flow), they remain the authoritative source of
truth per `CLAUDE.md`. **This ADR's decision is not implementable ahead of that reword
landing.**

This ADR is scoped to the roles UC01-UC04 actually need, plus the four control-cycle
inputs already wired into the coordinator pipeline (grid voltage, monthly peak demand, and
net/solar/charger power). Everything else currently in `entity-catalog.md` (low-tariff
flag, solar forecast, home-day/departure entities, battery-capacity sensor, vehicle
charge-limit write-back, car-home presence, and the remaining config thresholds) is out of
scope here and deferred to a follow-up design once UC05-UC10 exist.

## Considered options

### Option A — Synthetic `sc_`-prefixed proxy entities, kept in sync via automations/templates

Create new HA helper/template entities (e.g. `sensor.sc_net_power_w`) that mirror the raw
upstream entities, updated by automations or template sensors; the coordinator reads only
these proxies, never the raw entities directly.

- Pro: Matches NF3 and `entity-catalog.md` exactly as currently worded — no requirements
  conflict, and the wrapper is visible and inspectable directly in the HA UI/entity
  registry, with no code to read.
- Con: Adds an extra state hop (raw entity -> template/automation -> proxy entity) between
  every hardware change and the value the coordinator sees, adding latency and another
  place for staleness or a misconfigured template to silently break the value chain; it
  isn't how integrations that sit on top of arbitrary hardware normally solve this problem
  — comparable HA integrations (e.g. Versatile Thermostat, Better Thermostat) resolve
  hardware variation in Python code, not by generating parallel HA entities kept in sync
  by automations.

### Option B — Config-flow entity mapping + Python adapters, no new HA entities

Each required role is mapped once during config flow to the user's real `entity_id`; a
Python adapter class per role (`adapters/`, sharing a common `Adapter` protocol) reads/
writes that entity directly, and the coordinator only ever talks to adapters, never to a
raw entity_id.

- Pro: No extra state hop — the adapter reads the live entity value directly, so there is
  no staleness window and no automation/template to maintain per installation; matches how
  other hardware-agnostic HA integrations solve the same problem in code.
- Con: Conflicts with NF3 and `entity-catalog.md` as currently worded (both describe the
  wrapper as a literal HA entity) — not implementable until that text is reworded (issue
  #29); also makes the mapping invisible in the HA entity registry (it lives in config-
  entry data instead), so debugging "which entity feeds this role" requires opening the
  integration's config flow or its diagnostics, not just browsing entities.

## Decision

Option B. No new HA entities are created for hardware inputs; each role is mapped once,
during config flow, to the user's real `entity_id`. Config flow validates the mapped
entity exists and is the expected platform (e.g. the charger-current role must resolve to
a `number` entity). Numeric roles read/write the entity's native value directly.

Enum/status roles (charger status) additionally capture a state-translation table during
config flow: the user maps each of their hardware's actual state strings to the three
canonical charger states already defined in `system-overview.md`'s glossary and
`entity-catalog.md` — `disconnected`, `connected`, `charging` (not a new vocabulary). The
adapter translates in one direction, raw -> canonical; the coordinator never writes charger
status back to the hardware. A raw state with no entry in the translation table (e.g. an
unmapped firmware state) is treated the same as an unavailable entity — the adapter
returns `None`, which the error-handling decision (ADR-0007, backfilling Decision 6) picks
up: a mapping the user never provided is treated as missing data, the same as a sensor
that's actually offline.

Adapters live in `adapters/`, one class per role, sharing the `Adapter` protocol
(`async def read()`, `async def write(value)`) already assumed by ADR-0002.

Option A's extra state hop and non-idiomatic automation dependency (its Con) outweighs
its advantage of matching the current requirements wording (its Pro) — that wording gap is
a known, tracked defect (issue #29) in the requirement, not a reason to build the more
fragile design. Option B is accepted with its Con (invisible-in-registry mapping, and the
implementability block) explicitly recorded rather than silently worked around.

## Consequences

- **This decision cannot be implemented until issue #29 lands** (NF3 reworded to describe
  an adapter abstraction, `entity-catalog.md`'s framing note and hardware-I/O rows updated
  to describe roles rather than literal entities). No adapter code should be scaffolded
  against this ADR until that reword is committed.
- Debugging "which raw entity feeds role X" now requires the config entry's mapping data
  (or a diagnostics view exposing it), not just the HA entity registry — a diagnostics
  sensor or config-flow "review mapping" step becomes useful follow-up work once
  implementation starts.
- The charger-status translation table is config-entry data, not a requirements-doc
  constant — adding a new canonical charger state (beyond `disconnected`/`connected`/
  `charging`) would still require a glossary change first, but adding support for a new
  *raw* firmware string does not.
- This ADR only covers the roles UC01-UC04 and the four wired control-cycle inputs need;
  mapping the remaining `entity-catalog.md` rows (solar forecast, home-day/departure,
  battery capacity, vehicle charge-limit write-back, car-home presence, remaining
  thresholds) is deferred to a follow-up design once UC05-UC10 exist, and will need its own
  ADR if it changes this mapping/adapter mechanism.
- Config-flow validation (entity exists, expected platform) becomes the first line of
  defense against misconfiguration, which the config-flow implementation work must budget
  for explicitly rather than treating as an afterthought.
