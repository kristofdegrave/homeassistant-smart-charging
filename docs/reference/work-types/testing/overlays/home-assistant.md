# Work type: `testing` — the `home-assistant` overlay

Stack material for the `testing` work type, read with the core files beside it as one work file,
one bar and one checklist — each core file's **Overlays** section says which section below it
takes. Every entry names the core rule or bar item it extends; what an overlay may and may not say
is this tree's `README.md`'s **Stack overlays**.

## Implement

**The authorities.** Tests are written per
[ADR-0009](../../../../adl/0009-testing-strategy.md) — the authoritative plain-pytest vs
HA-harness split — and the extension of its mandated coverage in
[ADR-0040](../../../../adl/0040-fifth-mandated-adapter-case-unit-set.md). Tests mirror the package
1:1 (`tests/` matches `custom_components/smart_charging/`).

**The layers** — the work file's implement step identifies the unit's: pure logic vs HA-coupled.

**Before writing an HA-harness test** — the work file's *Choose the harness first*: read the
**Testing Requirements** section of the
`ha-integration-knowledge` skill — in particular its rule that tests exercise the integration
through its public surface (config entry, entity state, services) rather than mocking internal
integration details. Plain-pytest tests under `tests/modes/` and `tests/engines/` don't need it.

If you cannot test a piece with plain pytest without importing `homeassistant`, it belongs in an
adapter/coordinator/entity — that is a design signal, not a reason to reach for the harness in a
`modes/`/`engines/` test.

**The boundary** the work file's *Mock at the boundary* rule names is the bar's item 4's, and
is stated once, under **Done** below.

**A common mistake** — the work file's list: reaching for the HA harness to dodge a design
signal. A piece that cannot be tested with plain
pytest belongs in an adapter/coordinator/entity — moving the test is not the fix.

## Done

**Item 1, *Harness split* (ADR-0009).** The directory-to-harness mapping is stated here, once, and
both sides read it from here:
- **Plain pytest** — `tests/modes/`, `tests/engines/`: pure logic, importing no
  `homeassistant.*`. Fast, no runtime; this is where mode/engine behaviour, clamp math and the
  resolution rules are verified. A test in these directories that pulls in the HA harness is
  **Major** — it defeats the package boundary that makes the logic HA-free.
- **HA harness** (`pytest-homeassistant-custom-component` + `MockConfigEntry`) —
  `tests/adapters/`, `tests/test_coordinator.py`, entity/platform tests,
  `tests/test_config_flow.py`, `tests/test_init.py`: anything HA-coupled (entity state,
  config-entry lifecycle, registration, services). One of these tested with plain pytest where it
  needs a real (mocked) HA runtime is **Major** — the test either bypasses the wiring it claims
  to cover or re-implements it.

**Item 2, *Mandated coverage*.** The cases the item judges:
- **Every adapter role:** present, absent, unavailable, and — for the status/enum role — an
  unmapped raw state. ADR-0009 requires all four.
- **Every numeric role whose catalogued unit column names a unit:** the fifth mandated case —
  the role states its expected unit set, and the adapter class that defines its read carries a
  foreign-unit case and an absent-unit case. ADR-0040, which extends ADR-0009, is the authority
  on the trigger, the per-class discharge and the exclusions — read it before judging a role in
  or out, and before judging a pinned behaviour adequate. It also requires a docstring on a case
  pinning "used as-is", and is the authority on what that docstring must say.
- **Engines:** each behavioural row / branch, plus **worked examples** for the clamp math
  (grid-safety, floor/cap) and the NF4 voltage fallback. A clamp test asserting only that a
  number came back is a missing worked example, not a present one.
- **Coordinator:** happy path, status-gating-to-zero, clamp applied, and the fault path
  (required adapter `None` → 0 A + `Fault`; grid voltage `None` → not a fault).
- **Config flow:** a full flow creates a valid entry; validation rejects a bad mapping.

**Item 4, *Test honesty* — the boundary.** Where the item and the work file's *Mock at the
boundary* rule say *the boundary*, it is the HA boundary the unit talks to.

## Review

**What to read first — always:**

- The test files under review in `tests/` and the code under
  `custom_components/smart_charging/` they exercise.
- `docs/adl/0009-testing-strategy.md` — the authoritative plain-pytest vs HA-harness split.
- ADR-0040, which extends ADR-0009's mandated coverage with the fifth, unit case — where the
  change touches or wires an adapter that reads a numeric role. Locate it by number per
  `CLAUDE.md`'s **Architecture Decision Records (ADRs)** section.

**Read conditionally:**

- The **Testing Requirements** section of the `ha-integration-knowledge` skill — where the
  change includes HA-harness tests (`tests/adapters/`, `tests/test_coordinator.py`, entity/
  platform, config-flow, `tests/test_init.py`). Skip it for a change confined to
  `tests/modes/` or `tests/engines/`.
