"""Numeric read and read/write adapters (ADR-0003)."""

from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID, Platform

from ._read_only import _ReadOnlyAdapter


class NumericReadAdapter(_ReadOnlyAdapter):
    """Reads a numeric entity's native value; None if missing/unavailable/non-numeric."""

    async def read(self) -> float | None:
        state = self._live_state()
        if state is None:
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None


class NumericReadWriteAdapter(NumericReadAdapter):
    """A numeric role that can also be written, via the number.set_value service."""

    async def write(self, value: float) -> None:
        await self._hass.services.async_call(
            Platform.NUMBER,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: self._entity_id, ATTR_VALUE: value},
            blocking=True,
        )
