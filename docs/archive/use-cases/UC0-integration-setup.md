# UC0 — Integration Setup

## Description & goal

The user installs the Smart Charging integration for the first time and maps
it to their hardware by providing HA entity IDs for the required sensors. The
config flow validates each entity, creates the canonical `sc_` wrapper sensors,
and determines the capability set of the installation. If a solar power sensor
is provided, Solar and SolarOnly profiles are enabled; if omitted, only Captar,
Power, and Off are available in `sc_active_profile`.

---

## Actors & entities

| Actor / Entity | Role |
| --- | --- |
| User (system maintainer) | Initiates setup via the HA Integrations UI |
| HA Config Flow | Presents the setup form and validates input |
| Net power sensor (user-supplied) | Raw grid import entity; wrapped as the integration's `net_w` source |
| Charger status entity (user-supplied) | Raw charger state entity; wrapped into `sensor.sc_charger_status` |
| EV SOC entity (user-supplied) | Raw EV battery entity; wrapped into `sensor.sc_ev_soc` |
| Charger power entity (user-supplied) | Raw charger power output entity; wrapped into `sensor.sc_charger_w` |
| Solar power sensor (user-supplied, optional) | Raw solar production entity; if provided, enables Solar and SolarOnly profiles |
| `input_select.sc_active_profile` | Created by integration; option set reflects the capability set |

---

## Preconditions & triggers

**Preconditions:**

- Smart Charging integration is not yet installed
- All hardware sensor entities the user intends to map are present in HA and
  reporting a numeric state

**Trigger:**

User adds the Smart Charging integration via Settings → Integrations →
Add Integration.

---

## Main flow

1. Config flow presents a form with four required fields and one optional field:
   - Net power sensor entity ID (required)
   - Charger status entity ID (required)
   - EV SOC entity ID (required)
   - Charger power entity ID (required)
   - Solar power sensor entity ID (optional)
2. User fills in the required fields and optionally the solar field, then confirms.
3. Integration validates each provided entity:
   - Entity exists in the HA entity registry
   - Entity reports a numeric state (not `unknown` or `unavailable` at the time
     of validation)
4. Integration creates the `sc_` wrapper sensors pointing to the provided entity IDs.
5. Determine capability set:
   - Solar sensor provided → `sc_active_profile` options: Solar, SolarOnly, Captar, Power, Off
   - Solar sensor omitted → `sc_active_profile` options: Captar, Power, Off
6. Create `input_select.sc_active_profile` with the appropriate option set.
7. Create all other helpers defined in the entity reference table with their
   documented default values.
8. The integration begins monitoring and controlling the charger.

---

## Alternative flows

### A1 — Required entity invalid or not found

If a required entity does not exist in the HA entity registry or does not report
a numeric state at the time of validation:

1. Config flow surfaces a field-level error identifying the problematic entity.
2. User corrects the value and resubmits.
3. Setup does not proceed until all required entities pass validation.

### A2 — Solar sensor provided but invalid

If the optional solar sensor is provided but fails validation:

1. Config flow surfaces a field-level error on the solar sensor field.
2. User may correct the value or clear the field to proceed without solar features.
3. Solar features are not partially enabled — solar is either fully configured or absent.

### A3 — Solar sensor omitted

Not an error. Integration initialises with Captar, Power, and Off profiles only.
Solar and SolarOnly do not appear in `sc_active_profile`. The user may add a
solar sensor later via the options flow (UC0a).

---

## Acceptance criteria

- Setup cannot complete while any required entity field fails validation.
- When a solar sensor is provided and valid, `sc_active_profile` offers exactly
  five options: Solar, SolarOnly, Captar, Power, Off.
- When no solar sensor is provided, `sc_active_profile` offers exactly three
  options: Captar, Power, Off.
- All `sc_` wrapper sensors resolve to the user-supplied entity IDs after setup.
- All helpers in the entity reference table are created with their documented
  default values.
- Providing an invalid solar sensor surfaces a field-level error; clearing the
  field allows setup to proceed without solar features.

---

Derived from: hardware context, entity naming convention, solar capability split
