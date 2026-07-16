# Install-Time Config Flow Design — Smart Charging v3

*Date: 2026-07-08*

## Context

[docs/plans/2026-07-08-runtime-dashboard-design.md](2026-07-08-runtime-dashboard-design.md) designed
where [runtime configuration](../analysis/system-overview.md#ubiquitous-language) lives (a Lovelace
dashboard). This doc is its counterpart for the other half of `entity-catalog.md`'s `Setup` column:
[install-time configuration](../analysis/system-overview.md#ubiquitous-language) — values set once
when the integration is installed and rarely revisited (R19's exclusion side).

`entity-catalog.md` currently lists **~29 install-time `config` rows plus ~14 adapter-role mappings**
(NF3 — every device I/O crosses an adapter role, and that role is bound to the user's real entity
during setup) — roughly 40 fields total, spread across every configuration area in the catalog. That
volume is the problem this doc solves: HA's native setup surface for an integration is the
`config_flow` (initial "Add integration" wizard) and `options_flow` (the gear-icon "Configure" dialog
afterward). Presenting 40 fields as one flat form fails usability outright; this doc fixes the
grouping and navigation so it doesn't.

Like the runtime dashboard doc, this is a downstream design/implementation deliverable, not an
analysis document — no fresh-agent review requirement — but it is still presented for manual approval
before a real `config_flow.py` is built from it, since it fixes decisions (step boundaries, the
menu-vs-wizard choice) that would be awkward to unwind later.

Tracking issue: #68 (same as the runtime dashboard doc — both are UC11/R19 "how").

### Visual mockup

A static HTML mockup lives at
[`assets/2026-07-08-install-time-config-flow-mockup.html`](assets/2026-07-08-install-time-config-flow-mockup.html)
(open it directly in a browser). It shows the menu screen and two example detail steps in the style
described below.

---

## Requirement recap

Every row in `entity-catalog.md` classified `install-time`, or with no `Setup` classification but an
`adapter role` (NF3's "mapped to the user's real upstream entity during config flow" rows), belongs
here. Grouped by the catalog's own subgroup headings:

| Step | Catalog subgroup(s) | Field count | Notes |
| --- | --- | --- | --- |
| Capabilities | Capabilities | 1 | Gates whether the Solar step appears at all (R18) |
| Core & coordinator | Core & coordinator | 2 | |
| Installation & metering | Installation | 3 config + 3 adapter roles | |
| Charger | Charger | 2 config + 3 adapter roles | Includes the charger-status state-translation table (NF3) |
| Peak protection | Peak protection | 4 | |
| Power mode | `Power` mode (install-time rows only) | 2 | `sc_power_target_current_a` is runtime — excluded |
| EV | SOC & battery (install-time rows only) | 1 config + 4 adapter roles | `sc_active_soc` is runtime — excluded |
| Solar | `Solar`/`SolarOnly`/step-up/reserve-cap (install-time rows only) | 10 config + 2 adapter roles | Largest step; skipped entirely when the solar capability is off (R18) |
| Notifications | Reminders & prompts | 4 | |
| Deadline & home day | Departure times / Home day (adapter roles only) | 2 | `departure_external`, `home_day_external` |

Everything `entity-catalog.md` classifies `runtime` is excluded here — it belongs only on the
dashboard (`2026-07-08-runtime-dashboard-design.md`'s Decision 1), never in this flow.

---

## Decision 1 — A menu, not a linear wizard, for both first-time setup and later reconfiguration

**Problem:** a single ~40-field linear "Next → Next → Next → Finish" wizard forces the installer
through every step in a fixed order even to change one value later, and re-running it from scratch is
the only way HA's `options_flow` normally supports revisiting settings.

**Decision:** both the initial `config_flow` and the later `options_flow` (gear icon → *Configure*)
present the same step list as an HA **menu step** (`async_step_init` returning
`self.async_show_menu(step_id="init", menu_options=[...])`) — the standard HA pattern for integrations
with many independently-meaningful settings groups (e.g. how larger integrations organize their
options). Each menu entry is one row from the table above and jumps straight to that step's form;
finishing a step returns to the menu instead of advancing to the next one.

- **First-time setup** shows the same menu with a completion indicator per entry (done / not started)
  and a "Finish setup" action once every required step (all except the ones gated off by Decision 3)
  is done — this is a required-completeness gate, not a fixed order.
- **Later reconfiguration** shows the identical menu, unrestricted — the installer opens exactly the
  one step they need (e.g. only *Peak protection*, after the utility changes the grid contract) without
  touching the other 8.

**Alternatives considered:**

- **One long linear wizard.** Rejected — reopening it to change a single value means re-clicking
  through unrelated steps every time (poor for the actual usage pattern: install-time settings are
  set once, then very occasionally revisited one at a time, not as a batch).
- **One flat options page with all ~40 fields via `section()` collapsibles.** Rejected — `section()`
  handles grouping *within* a step (used in Decision 2) but a single step with nine collapsed sections
  is still one wall of a form to scroll through, and HA's per-step schema validation would apply to
  the whole page at once rather than one coherent group.

---

## Decision 2 — `section()` groups fields within a step

**Problem:** even one step (e.g. *Solar*, 12 fields) is too much as a flat list of inputs.

**Decision:** each step's `data_schema` uses HA's `section()` schema helper (config-flow sections,
collapsible field groups within one step) to split it into its natural sub-groups — the same
subgroup names `entity-catalog.md` already uses:

| Step | Sections |
| --- | --- |
| Installation & metering | *Grid parameters* (ceiling, safety offset, nominal voltage) · *Metering sources* (grid voltage, net power, tariff signal) |
| Charger | *Current limits* (min/max A) · *Charger entities* (power, status, current set-point) · *Status mapping* (state-translation table) |
| EV | *Battery* (capacity) · *Vehicle entities* (SOC, capacity sensor, presence, charge-limit) |
| Solar | *Solar mode thresholds* · *SolarOnly rounding* · *SOC step-up* · *Solar-reserve cap* · *Solar entities* |

Steps with ≤4 fields (Capabilities, Core & coordinator, Peak protection, Power mode, Notifications,
Deadline & home day) use a flat schema — sectioning a 2–4 field form adds a click for no readability
gain.

**Alternative considered:** splitting *Solar* into multiple menu entries instead of sections (e.g.
"Solar mode", "SolarOnly", "SOC step-up", "Solar-reserve cap" as four separate menu rows). Rejected —
these four sub-concerns are all gated by the same single capability flag and are meaningless in
isolation from each other; keeping them as one menu entry with internal sections keeps "configure
solar" a single, findable action while still avoiding a flat 12-field form.

---

## Decision 3 — Adapter-role fields use HA's native entity selector; capability gates the whole Solar menu entry

**Adapter roles** (NF3's "mapped to the user's real upstream entity") are exactly what HA's
`selector.EntitySelector` exists for — each adapter-role field (`net_power`, `charger_power`,
`charger_status`, `charger_current`, `ev_soc`, `battery_capacity`, `car_home`,
`vehicle_charge_limit`, `solar_power`, `solar_forecast`, `grid_voltage`, `low_tariff`,
`departure_external`, `home_day_external`) is rendered as a live entity picker (optionally filtered
by domain/device-class, e.g. `sensor` + `device_class: power` for `net_power`) rather than a free-text
entity-id field — the installer picks from their real HA entities, which is both the standard HA UX
and removes an entire class of typo bugs a text field would allow.

**Capability gating (R18):** the *Solar* menu entry is present only when `sc_solar_available` (set in
the *Capabilities* step) is on — computed each time the menu step renders, so toggling the capability
off in a later reconfiguration immediately removes the *Solar* entry from the menu (and, per the
runtime dashboard doc's Decision 1, drops `sc_solar_reserve_soc`'s `sc_runtime` label at the same
time) rather than leaving stale, inapplicable fields reachable.

**Charger-status state-translation table (NF3):** `charger_status`'s mapping is not a single entity
picker — the upstream charger entity's own state strings (e.g. a specific EVSE's `"Preparing"` /
`"Charging"` / `"Finishing"`) must translate to the three [charger status](../analysis/system-overview.md#ubiquitous-language)
values (`disconnected`/`connected`/`charging`). The mockup shows this as a small three-row mapping
table (one dropdown per target status, populated from the picked entity's currently-observed state
attribute options) inside the *Status mapping* section — the only field in this entire flow that
isn't a plain number/boolean/select/entity-selector.

---

## Layout & visual language

The mockup deliberately looks like Home Assistant's own settings UI (not the runtime dashboard's
Lovelace card style) — because it *is* HA's native config/options flow chrome, not a custom card:

- A **dialog** (not a full page) with a title bar, HA's rounded outlined text fields and toggle
  switches, and *Back* / *Next* / *Submit* buttons — matching `ha-dialog` / `ha-form` conventions.
- The **menu screen** lists all applicable steps (Solar included/excluded per Decision 3) as tappable
  rows with a status icon (✓ configured / a plain chevron for "open"), so the installer always sees
  what's left during first-time setup and can jump straight to one item during reconfiguration.
- Each **detail step** shows its `section()` groups as collapsible headers (per Decision 2), with
  entity-selector fields visually distinguished (an entity-picker chip style) from plain
  number/boolean/select inputs.

---

## Open questions / follow-ups

- **Exact `EntitySelector` domain/device-class filters per adapter role** (e.g. whether `net_power`
  should also accept a template sensor) — an implementation detail for whichever step writes
  `config_flow.py`, not decided here.
- **Whether "Finish setup" should hard-block on all required steps or allow finishing with defaults
  and a banner listing what's still unset** — both are reasonable; deferred to the actual flow build
  since it doesn't affect this doc's step/section boundaries.
- **Charger-status mapping UX when the upstream entity's possible states aren't discoverable
  up front** (some integrations don't expose an options/state-attribute list) — may need a free-text
  fallback per row; flagged for whoever implements `charger_status`'s adapter-role binding.

---

## Requirements / use-cases realized

- [R19](../analysis/requirements.md#r19--runtime-dashboard) — the exclusion side: this flow is where
  every install-time field actually lives, keeping it structurally absent from the dashboard.
- [NF3](../analysis/requirements.md) — every adapter-role mapping in `entity-catalog.md` is bound to a
  real upstream entity through this flow's entity selectors.
- [R18](../analysis/requirements.md) — the Solar menu entry (and its fields) exist only when the solar
  capability is on.
