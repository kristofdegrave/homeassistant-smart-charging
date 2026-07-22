"""Boolean-flag read adapter (ADR-0003 extension, Task 2.1/RA2)."""

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant


class BooleanReadAdapter:
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

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id

    async def read(self) -> bool | None:
        state = self._hass.states.get(self._entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        if state.state == STATE_ON:
            return True
        if state.state == STATE_OFF:
            return False
        return None

    async def write(self, value: bool) -> None:
        raise NotImplementedError("read-only role")
