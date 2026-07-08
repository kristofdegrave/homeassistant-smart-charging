# Runtime Dashboard Design — Smart Charging v3

*Date: 2026-07-08*

## Context

[UC11](../analysis/use-cases/UC11-monitor-and-manage-charging-configuration.md) documents the
goal — a dashboard showing current charging status and every
[runtime configuration](../analysis/system-overview.md#ubiquitous-language) entity, with no
[install-time configuration](../analysis/system-overview.md#ubiquitous-language) entity ever
shown ([R19](../analysis/requirements.md#r19--runtime-dashboard)) — but deliberately says nothing
about *how* the dashboard is built; that is implementation design, out of scope for an analysis
document. This doc makes that "how" concrete: card types, layout, and — the part that most needs a
decision — the mechanism that keeps the dashboard in sync with
[`entity-catalog.md`](../analysis/entity-catalog.md)'s `Setup` classification without a
dashboard-specific code change every time a runtime entity is added (R19's extensibility
acceptance criterion, restated in UC11's postconditions).

This is a downstream design/implementation deliverable, produced after UC11 was reviewed and
merged (#67). It is not an analysis document, so it does not go through the `docs/analysis`
review protocol in `CLAUDE.md` (no fresh-agent review requirement) — but it is still presented for
manual approval before any dashboard file is built from it, since it fixes decisions (card types,
the label convention) that would be awkward to unwind later.

Tracking issue: #68.

---

## Requirement recap

`entity-catalog.md` currently lists 13 entities classified `runtime` (see its `Setup` column):

| Entity | Configuration area |
| --- | --- |
| `input_select.sc_active_profile` | Core & coordinator |
| `input_select.sc_active_mode` | Core & coordinator (`state`, user-set under `Manual`) |
| `input_number.sc_power_target_current_a` | `Power` mode |
| `input_number.sc_active_soc` | SOC & battery |
| `input_number.sc_solar_reserve_soc` | Solar-reserve cap (conditional on the solar capability, R18) |
| `input_datetime.sc_departure_mon` … `sc_departure_sun` (7 entities) | Departure times |
| `input_datetime.sc_departure_holiday` | Departure times |
| `input_datetime.sc_departure_home_day` | Departure times |
| `input_boolean.sc_home_day` | Home day (`state`, user-set) |

Plus the read-only charging-status values UC11 displays: `charger_status`, `sc_active_profile`,
`sc_active_mode`, `sc_active_soc` (as the resolved active SOC limit), `charger_current`,
`solar surplus` (`charger_power − net_power`), and `net_power`.

Everything else in `entity-catalog.md` is `install-time` (or an adapter role / pure system status)
and must never appear here.

---

## Decision 1 — An HA label drives the runtime list, not a hand-maintained card

**Problem:** if the runtime section is a hand-written list of entity ids, every new runtime entity
requires editing the dashboard — exactly the coupling R19's last acceptance criterion and UC11's
final postcondition rule out.

**Decision:** every entity `entity-catalog.md` classifies as `runtime` gets the HA label
`sc_runtime`, applied when the integration creates it (config flow / entity registry, at
integration-implementation time — out of scope for this doc). The dashboard's runtime section is
built with an `auto-entities` card filtered by that label, not by explicit entity ids:

```yaml
type: custom:auto-entities
card:
  type: entities
  title: Runtime settings
filter:
  include:
    - label: sc_runtime
  exclude:
    - label: sc_install
sort:
  method: friendly_name
```

Adding a new runtime entity to `entity-catalog.md` and labelling it `sc_runtime` at creation time
is then the only change needed — no dashboard YAML edit — which is exactly the mechanism UC11's
Diagram section shows as "Read `entity-catalog.md` `Setup` classification" (the label *is* that
classification, materialized in HA).

**Alternatives considered:**

- **Hand-maintained `entities` card, one row per `sc_` id.** Rejected — fails the extensibility
  criterion outright; every UC would need to reopen this design doc.
- **Area-based filtering instead of a label.** Rejected — areas group entities by physical
  location (a Home Assistant concept for rooms/devices), not by configuration semantics; runtime
  vs. install-time is a domain classification this integration owns, so a label (a free-form,
  purpose-built tag) is the closer native fit.
- **A single dashboard strategy (Python) that reads `entity-catalog.md` directly.** Rejected as
  overengineered — a strategy needs custom Python shipped with the integration and a rebuild
  pipeline; a label plus `auto-entities` (an existing, widely used custom card) gets the same
  extensibility with a one-line addition per entity and no additional code path to maintain.

**Consequence for install-time exclusion (R19's fourth AC):** install-time entities are never
labelled `sc_runtime`, so they are structurally absent from the filter — there is no exclusion
logic to get wrong, only a labelling step to get right when an entity is created.

**Consequence for capability gating (UC11's alt-flow 4a):** when the solar capability is off, the
integration never creates `sc_solar_reserve_soc` at all (per `entity-catalog.md`'s existing
capability-gating note), so it never receives the label and is never queried — again no
dashboard-side conditional needed.

---

## Decision 2 — Card types

| Section | Card | Rationale |
| --- | --- | --- |
| Charging status | `tile` cards (one per value: charger status, active profile, active mode, active SOC limit, charger current) | Built-in card, no custom-card dependency; a `tile` reads state directly and needs no template for a plain value display. |
| Solar surplus / net import | `tile` cards, `state_content: state` | Same reasoning; both are plain sensor-shaped values (net import is a real adapter-role reading, solar surplus is `charger_power − net_power` — see Decision 3). |
| Runtime settings | `custom:auto-entities` wrapping an `entities` card (Decision 1) | Only card type that supports label-based filtering with zero maintenance per entity. |

No Mushroom cards are used: the reference dashboard shared for UX inspiration (the "Slim Laden"
dashboard, mentioned in #28) used Mushroom, but this design intentionally minimizes custom-card
dependencies — `tile` and `auto-entities` are the only ones required, and `tile` already covers
every plain-value display UC11 asks for. Mushroom can be swapped in later purely as a styling
change; it does not change the label-driven extensibility mechanism.

---

## Decision 3 — Solar surplus has no entity; expose one rather than templating it on the dashboard

`entity-catalog.md` notes explicitly that solar surplus has no dedicated entity (it is `charger_w
− net_w`, computed fresh each control cycle by `control-cycle.md`, not stored).

**Decision:** the integration exposes solar surplus as a read-only diagnostic sensor
(`sensor.sc_solar_surplus_w`), the same pattern already used for `sensor.sc_monthly_peak_kw` (a
`state`-role, system-computed value with no runtime/install-time classification, per
`entity-catalog.md`'s own precedent). The dashboard then shows it with a plain `tile` card like
every other status value:

```yaml
type: tile
entity: sensor.sc_solar_surplus_w
name: Solar surplus
```

**Alternative considered:** compute `charger_power − net_power` directly in a dashboard template
card. Rejected — it duplicates a calculation `control-cycle.md` already owns and risks drifting
from it (e.g. if the formula's sign convention or smoothing ever changes, the dashboard would need
a separate, easy-to-miss update); a dedicated sensor keeps the computation in exactly one place.

Adding `sensor.sc_solar_surplus_w` is a small `entity-catalog.md` addition (a new `state` row, no
requirement wording changes), tracked as a follow-up rather than made inline in this design doc,
since it touches the analysis layer (see Open questions).

---

## Layout

Sections view (per the Decision Matrix in `home-assistant-manager`'s dashboard guidance —
multiple cards, responsive grid, not a single full-screen element):

```yaml
type: sections
title: Smart Charging
sections:
  - type: grid
    title: Charging status
    cards:
      - type: tile
        entity: sensor.sc_charger_status
      - type: tile
        entity: input_select.sc_active_profile
      - type: tile
        entity: input_select.sc_active_mode
      - type: tile
        entity: sensor.sc_active_soc_limit   # resolved active SOC limit, R7
      - type: tile
        entity: sensor.sc_charger_current_a
  - type: grid
    title: Power flow
    cards:
      - type: tile
        entity: sensor.sc_solar_surplus_w    # new entity-catalog.md row, Decision 3 / Open questions
      - type: tile
        entity: sensor.sc_net_power_w
  - type: grid
    title: Runtime settings
    cards:
      - type: custom:auto-entities
        card:
          type: entities
        filter:
          include:
            - label: sc_runtime
        sort:
          method: friendly_name
```

`sensor.sc_active_soc_limit` and `sensor.sc_charger_current_a` above are illustrative ids for the
resolved/read-back values UC11 needs (the active SOC limit resolution has no entity today per
`entity-catalog.md`; `charger_current` is an adapter role, not a catalogued `sc_` id) — exact ids
are an implementation detail for whichever step wires the dashboard to real entities, not fixed by
this design.

---

## Open questions / follow-ups

- **`sensor.sc_solar_surplus_w` as a new `entity-catalog.md` row.** Recommended, but is an analysis
  change — take it through `write-requirement`'s propagation step (or a lighter catalog-only edit,
  since no requirement's wording changes) before implementation, rather than deciding it here.
- **Exposing the resolved active SOC limit and read-back charger current as concrete sensors** for
  the status tiles — same category as above: a small `entity-catalog.md` addition, not decided by
  this doc.
- **Mushroom vs. built-in `tile`/`auto-entities`** — this design deliberately avoids a HACS
  dependency; revisit only if the built-in cards prove visually insufficient once a real dashboard
  is built and reviewed against the "Slim Laden" reference for UX parity.
- **Tablet-specific column counts / touch-target sizing** — deferred to the actual dashboard build,
  per `home-assistant-manager`'s tablet-optimization guidance (3–4 columns, 44×44px minimum touch
  targets); this doc fixes card types and the extensibility mechanism, not pixel-level layout.

---

## Requirements / use-cases realized

- [R19](../analysis/requirements.md#r19--runtime-dashboard) — every acceptance criterion, via the
  card/layout choices above.
- [UC11](../analysis/use-cases/UC11-monitor-and-manage-charging-configuration.md) — this doc is
  UC11's "how"; UC11 remains the authoritative "what".
