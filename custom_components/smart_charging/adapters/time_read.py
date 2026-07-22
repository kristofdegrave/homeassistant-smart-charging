"""Time-of-day read adapter (ADR-0003 extension, Task 2.1/RA2)."""

from datetime import time

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


class TimeReadAdapter:
    """Reads a time-of-day entity's native value.

    Added for the `departure_external` role (design doc §4 note): its mapped entity's
    native value is a `datetime.time`, not a float (`NumericReadAdapter`) or a
    user-translated canonical string (`StatusReadAdapter`). Neither existing class fits
    without being reshaped, so this is a new, minimal adapter class of the same shape
    ADR-0003 already establishes ("one class per role"), flagged for review per the Task
    2.1 plan instruction rather than silently repurposing either.

    Returns None when the entity is missing/unavailable/unknown OR its native state can't
    be parsed as a time (e.g. a `time` entity currently reporting "no deadline") -- the
    ADR-0007 fault signal, same as every other read adapter, and also R14's own "external
    sensor currently reports no deadline" case.
    """

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id

    async def read(self) -> time | None:
        state = self._hass.states.get(self._entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        return dt_util.parse_time(state.state)

    async def write(self, value: time) -> None:
        raise NotImplementedError("read-only role")
