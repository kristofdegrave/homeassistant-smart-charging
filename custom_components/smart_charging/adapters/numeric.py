"""Numeric read and read/write adapters (ADR-0003)."""

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
            "number",
            "set_value",
            {"entity_id": self._entity_id, "value": value},
            blocking=True,
        )
