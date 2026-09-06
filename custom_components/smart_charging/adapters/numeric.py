"""Numeric read and read/write adapters (ADR-0003)."""

from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID, ATTR_UNIT_OF_MEASUREMENT, Platform, UnitOfPower
from homeassistant.util.unit_conversion import PowerConverter

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


class PowerKilowattReadAdapter(_ReadOnlyAdapter):
    """Reads a power entity's value, normalised to kW (ADR-0030; design D-1).

    An absent/non-power unit reads as None rather than being assumed kW -- a
    misread W value as kW would widen the billing-protection clamp instead of
    narrowing it, the asymmetric mistake ADR-0030 chooses against.
    """

    async def read(self) -> float | None:
        state = self._live_state()
        if state is None:
            return None
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if unit not in PowerConverter.VALID_UNITS:
            return None
        try:
            value = float(state.state)
        except (ValueError, TypeError):
            return None
        return PowerConverter.convert(value, unit, UnitOfPower.KILO_WATT)


class NumericReadWriteAdapter(NumericReadAdapter):
    """A numeric role that can also be written, via the number.set_value service."""

    async def write(self, value: float) -> None:
        await self._hass.services.async_call(
            Platform.NUMBER,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: self._entity_id, ATTR_VALUE: value},
            blocking=True,
        )
