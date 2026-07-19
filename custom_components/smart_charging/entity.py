"""Base class for Smart Charging owned entities (ADR-0002/0004)."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class SmartChargingEntity(Entity):
    """Common device grouping + unique-id prefixing for owned entities."""

    _attr_has_entity_name = True

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Smart Charging",
        )
