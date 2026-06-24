# UC0a — Integration Reconfiguration

## Description & goal

The user modifies the integration's entity mappings after initial setup — for
example, to add a solar sensor to an existing installation, replace a renamed
sensor, or remove solar features. The options flow re-validates all fields,
updates the `sc_` wrapper bindings, adjusts `sc_active_profile` options if the
solar capability changed, and reloads the integration.

---

## Actors & entities

| Actor / Entity | Role |
| --- | --- |
| User (system maintainer) | Initiates reconfiguration via the integration card |
| HA Options Flow | Presents the reconfiguration form pre-populated with current values |
| Net power sensor (user-supplied) | May be updated to a different entity |
| Charger status entity (user-supplied) | May be updated |
| EV SOC entity (user-supplied) | May be updated |
| Charger power entity (user-supplied) | May be updated |
| Solar power sensor (user-supplied, optional) | May be added, changed, or removed |
| `input_select.sc_active_profile` | Updated if the solar capability set changes |
| Smart Charging integration | Active control is paused while changes are applied and resumed after reload |

---

## Preconditions & triggers

**Preconditions:**

- Smart Charging integration is already installed (UC0 completed)
- Integration may be running and actively controlling the charger

**Trigger:**

User selects Configure on the Smart Charging card in Settings → Integrations.

---

## Main flow

1. Options flow presents the same fields as UC0, pre-populated with the current
   entity mappings.
2. User modifies one or more fields and confirms.
3. Integration validates each provided entity using the same rules as UC0 step 3.
4. If validation passes:
   a. Stop the coordinator.
   b. Update the `sc_` wrapper sensor bindings to the new entity IDs.
   c. Recalculate the capability set from the updated solar sensor field.
   d. If the capability set changed, update `sc_active_profile` options
      (see A1 and A2).
5. Reload the integration — coordinator restarts with the new configuration.

---

## Alternative flows

### A1 — Solar sensor removed while a solar profile is active

If the solar sensor field is cleared and `sc_active_profile` is currently
`Solar` or `SolarOnly`:

1. Force `sc_active_profile` to `Off` before reloading.
2. Log a warning: solar sensor removed while a solar profile was active;
   profile reset to Off.
3. Remove Solar and SolarOnly from the `sc_active_profile` option set.
4. Reload.

*Leaving the profile set to Solar with no solar sensor configured would cause
every subsequent control cycle to fail with a missing entity error.*

### A2 — Solar sensor added to a non-solar installation

If a valid solar sensor is provided where none existed before:

1. Add Solar and SolarOnly to the `sc_active_profile` option set.
2. Leave `sc_active_profile` at its current value — the user switches to a
   solar profile explicitly.
3. Reload.

### A3 — Required entity changed to an invalid entity

Same as UC0 A1: field-level error, form does not submit until corrected.

### A4 — No fields changed

If the user opens the options flow and confirms without modifying anything:

1. Validation runs as normal.
2. If all entities still pass, integration reloads (harmless).
3. If a previously valid entity has since been removed from HA, A3 applies —
   the user must correct it before confirming.

---

## Acceptance criteria

- The reconfiguration form is pre-populated with the current entity mappings.
- After reconfiguration, all `sc_` wrapper sensors resolve to the updated
  entity IDs.
- Removing the solar sensor while a solar profile is active resets
  `sc_active_profile` to Off and logs a warning.
- Adding a solar sensor makes Solar and SolarOnly available in
  `sc_active_profile` without changing the current profile value.
- The integration reloads after every confirmed reconfiguration.
- An invalid entity in any required required field blocks submission with a
  field-level error.

---

Derived from: UC0, solar capability split
