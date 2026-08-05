"""Boolean-flag read adapter (ADR-0003 extension, Task 2.1/RA2)."""

from homeassistant.const import STATE_OFF, STATE_ON

from ._read_only import _ReadOnlyAdapter


class BooleanReadAdapter(_ReadOnlyAdapter):
    """Reads a boolean-flag entity's native on/off state.

    Added for the `home_day_external` role (design doc §4 note): its mapped entity is a
    calendar/presence source whose native state is the fixed `on`/`off` vocabulary, not a
    float (`NumericReadAdapter`) or a user-translated canonical string (`StatusReadAdapter`
    exists to let the user map arbitrary firmware strings onto the three canonical charger
    states -- there is no such user-configured translation here). Neither existing class
    fits without being reshaped, so this is a new, minimal adapter class of the same shape
    ADR-0003 already establishes ("one class per role"), flagged for review per the Task 2.1
    plan instruction rather than silently repurposing `StatusReadAdapter`.

    Returns None when the entity is missing/unavailable/unknown OR its state is neither
    `on` nor `off` -- the ADR-0007 fault signal, same as every other read adapter.
    """

    async def read(self) -> bool | None:
        state = self._live_state()
        if state is None:
            return None
        if state.state == STATE_ON:
            return True
        if state.state == STATE_OFF:
            return False
        return None
