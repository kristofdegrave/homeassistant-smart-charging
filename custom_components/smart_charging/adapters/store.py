"""RA3: reads owned control-entity state through the entity registry + HA state machine
(ADR-0018/0019)."""

from __future__ import annotations

import logging
from datetime import time
from typing import TypeVar

from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ..const import DOMAIN

T = TypeVar("T", str, float, bool, time)

_LOGGER = logging.getLogger(__name__)


class Store:
    """One instance per config entry (mirrors the Adapter factory's per-entry scoping,
    ADR-0003) -- read() only ever resolves this entry's own owned entities."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._entry_id = entry_id

    async def read(
        self, entity_domain: str, unique_id_suffix: str, value_type: type[T]
    ) -> T | None:
        """Resolve f"{entry_id}_{unique_id_suffix}" as an entity_domain entity via the entity
        registry, read its HA state, and coerce to value_type. None if unregistered,
        missing/unknown/unavailable, or the value doesn't coerce -- never raises (mirrors
        NumericReadAdapter.read(), ADR-0003)."""
        entity_id = er.async_get(self._hass).async_get_entity_id(
            entity_domain, DOMAIN, f"{self._entry_id}_{unique_id_suffix}"
        )
        if entity_id is None:
            return None
        state = self._hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        if value_type is float:
            try:
                return float(state.state)
            except (ValueError, TypeError):
                return None
        if value_type is bool:
            return state.state == STATE_ON
        if value_type is time:
            try:
                return time.fromisoformat(state.state)
            except ValueError:
                return None
        return state.state

    async def write(self, entity_domain: str, unique_id_suffix: str, value: float) -> bool:
        """Set `value` on this entry's owned `entity_domain` entity identified by
        `unique_id_suffix`. Returns True if applied, False otherwise; never raises
        (symmetric with read(), and the best-effort contract VehicleLimitManager's
        _write_vehicle expects -- ADR-0003/ADR-0018).

        Only the `number` domain is supported: this is the one value shape a caller needs
        today (M2 -> soc_limit_override). Other domains return False rather than issuing a
        number.set_value against an entity that cannot take it -- see the design doc's
        deferrals.
        """
        if entity_domain != Platform.NUMBER:
            _LOGGER.debug("Store.write: unsupported entity domain %s", entity_domain)
            return False
        entity_id = er.async_get(self._hass).async_get_entity_id(
            entity_domain, DOMAIN, f"{self._entry_id}_{unique_id_suffix}"
        )
        if entity_id is None:
            return False
        await self._hass.services.async_call(
            Platform.NUMBER,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
            blocking=True,
        )
        return True
