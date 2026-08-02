"""Presence (car_home) read adapter: maps a presence entity's state to a bool (ADR-0003)."""

from homeassistant.const import STATE_HOME, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

_HOME_STATES = (STATE_HOME, STATE_ON)


class PresenceReadAdapter:
    """Reads a presence/device_tracker/binary_sensor entity as car-at-home (True/False).

    None when the entity is missing/unavailable/unknown -- for this role that is not the
    ADR-0007 fault path (M2 is outside the control cycle); the Manager treats None as
    "cannot confirm presence" and suppresses a System write (design §9.1 alternative).
    """

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id

    async def read(self) -> bool | None:
        state = self._hass.states.get(self._entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        return state.state in _HOME_STATES

    async def write(self, value: bool) -> None:
        raise NotImplementedError("car_home is read-only")
