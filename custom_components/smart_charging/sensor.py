"""Charging status sensor (Fault/OK) — ADR-0007."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .entity import SmartChargingEntity


class ChargingStatusSensor(SmartChargingEntity, CoordinatorEntity, SensorEntity):
    """Reports Fault when the last cycle faulted (ADR-0007), else OK."""

    _attr_translation_key = "status"

    def __init__(self, entry_id: str, coordinator) -> None:
        SmartChargingEntity.__init__(self, entry_id)
        CoordinatorEntity.__init__(self, coordinator)
        self._attr_unique_id = f"{entry_id}_status"

    @property
    def native_value(self) -> str:
        data = self.coordinator.data
        if data is not None and getattr(data, "fault", False):
            return "Fault"
        return "OK"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([ChargingStatusSensor(entry.entry_id, coordinator)])
