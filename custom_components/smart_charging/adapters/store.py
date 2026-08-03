"""RA3: reads owned control-entity state through the entity registry + HA state machine
(ADR-0018/0019)."""

from __future__ import annotations

from typing import TypeVar

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ..const import DOMAIN

T = TypeVar("T", str, float)


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
        return state.state
