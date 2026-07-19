"""Numeric read and read/write adapters (ADR-0003)."""

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant


class NumericReadAdapter:
    """Reads a numeric entity's native value; None if missing/unavailable/non-numeric."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id

    async def read(self) -> float | None:
        state = self._hass.states.get(self._entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    async def write(self, value: float) -> None:
        raise NotImplementedError("read-only role")


class NumericReadWriteAdapter(NumericReadAdapter):
    """A numeric role that can also be written, via the number.set_value service."""

    async def write(self, value: float) -> None:
        await self._hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": self._entity_id, "value": value},
            blocking=True,
        )
