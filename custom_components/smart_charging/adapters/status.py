"""Charger-status adapter: translates raw hardware states to canonical ones (ADR-0003)."""

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant


class StatusAdapter:
    """Reads a status entity and maps its raw state to a canonical charger state.

    Returns None when the entity is missing/unavailable OR when the raw state has
    no entry in the translation table — both are the ADR-0007 fault signal.
    """

    def __init__(self, hass: HomeAssistant, entity_id: str, translation: dict[str, str]) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self._translation = translation

    async def read(self) -> str | None:
        state = self._hass.states.get(self._entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        return self._translation.get(state.state)

    async def write(self, value) -> None:
        raise NotImplementedError("status is read-only")
