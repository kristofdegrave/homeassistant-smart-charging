# UC4 — Power Mode

## Description & goal

Charge the EV at a fixed current configured by the user. No solar tracking, no monthly peak rules, and no tariff-window logic apply. This is the simplest mode: the coordinator reads one helper, clamps the value to a safe range, and sets the charger. It is used when the user wants predictable, immediate charging regardless of solar or grid conditions.

---

## Actors & entities

| Actor / Entity | Role |
| --- | --- |
| Coordinator | Calls this module on every control cycle |
| `input_select.sc_active_profile` | Read by coordinator to determine that Power mode is active |
| `sensor.sc_charger_status` | Read: must be `connected` or `charging` for the module to set a non-zero current |
| `input_number.sc_power_mode_amps` | Read: user-configured target current |
| EV charger | Written: receives the current set-point in amperes |

---

## Preconditions & triggers

**Preconditions:**

- `input_select.sc_active_profile` is set to `Power`
- `sensor.sc_charger_status` is `connected` or `charging`
- `input_number.sc_power_mode_amps` holds a value in the range 6–32 A

**Trigger:**

Each coordinator control cycle.

---

## Main flow

1. Read `input_number.sc_power_mode_amps` → `target_amps`.
2. Enforce C1: if `target_amps` is in the range 1–5 A (invalid), raise it to 6 A.
3. Clamp `target_amps` to the charger's maximum: if > 32 A, cap at 32 A.
4. Return `target_amps` to the coordinator, which writes it to the charger.

---

## Alternative flows

### A1 — Entity unavailable

If `input_number.sc_power_mode_amps` is unavailable or cannot be read:

1. Log a warning identifying the missing entity.
2. Return 0 A — the charger is stopped rather than left at an unknown set-point.

### A2 — Value below minimum (defensive)

The helper's HA range constraint (6–32 A) prevents this during normal operation. If a value of 1–5 A is received anyway (e.g. direct state injection in tests or a misconfigured helper):

1. Clamp up to 6 A (C1).
2. Continue with step 4 of the main flow.

---

## Acceptance criteria

- When `sc_power_mode_amps` = 15 A, the charger is set to 15 A.
- When `sc_power_mode_amps` = 6 A (minimum), the charger is set to 6 A.
- When `sc_power_mode_amps` = 32 A (maximum), the charger is set to 32 A.
- A configured value in the range 1–5 A is clamped to 6 A and never sent to the charger (C1).
- No solar surplus, net power, tariff window, or peak limit values are read or used.
- If `sc_power_mode_amps` is unavailable, the charger is set to 0 A and a warning is logged.

---

Requirements: NF2 (Power module), C1
