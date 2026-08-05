"""Charger-status adapter: translates raw hardware states to canonical ones (ADR-0003)."""

from homeassistant.core import HomeAssistant

from ._read_only import _ReadOnlyAdapter


class StatusReadAdapter(_ReadOnlyAdapter):
    """Reads a status entity and maps its raw state to a canonical charger state.

    Returns None when the entity is missing/unavailable/unknown OR when the raw
    state has no entry in the translation table — both are the ADR-0007 fault signal.
    """

    def __init__(self, hass: HomeAssistant, entity_id: str, translation: dict[str, str]) -> None:
        super().__init__(hass, entity_id)
        self._translation = translation

    async def read(self) -> str | None:
        state = self._live_state()
        if state is None:
            return None
        return self._translation.get(state.state)
