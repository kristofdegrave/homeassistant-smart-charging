"""Target-current number entity (C2). ADR-0004 native naming."""

from __future__ import annotations

from homeassistant.components.number import RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DEFAULT_SOC_LIMIT,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_MAX_CURRENT,
    CONF_MIN_CURRENT,
    DOMAIN,
)
from .entity import SmartChargingEntity


class TargetCurrentNumber(SmartChargingEntity, RestoreNumber):
    """User-set target charging current for Power mode."""

    _attr_translation_key = "target_current"
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_step = 1.0

    def __init__(
        self, entry_id: str, coordinator, min_a: float, max_a: float, default: float
    ) -> None:
        super().__init__(entry_id)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_target_current"
        self._attr_native_min_value = min_a
        self._attr_native_max_value = max_a
        self._attr_native_value = default

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = min(
                max(last.native_value, self._attr_native_min_value),
                self._attr_native_max_value,
            )
        # Seed the coordinator with the (restored or default) value.
        self._coordinator.target_current = self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self._coordinator.target_current = value
        await self._coordinator.async_request_refresh()
        self.async_write_ha_state()


class SocLimitOverrideNumber(SmartChargingEntity, RestoreNumber):
    """User-set active SOC limit override (R6/R7)."""

    _attr_translation_key = "soc_limit_override"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_step = 1.0
    _attr_native_min_value = 50.0
    _attr_native_max_value = 100.0

    def __init__(self, entry_id: str, coordinator, default: float) -> None:
        super().__init__(entry_id)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_soc_limit_override"
        self._attr_native_value = default

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = min(
                max(last.native_value, self._attr_native_min_value),
                self._attr_native_max_value,
            )
        self._coordinator.soc_limit_override = self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self._coordinator.soc_limit_override = value
        await self._coordinator.async_request_refresh()
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    async_add_entities(
        [
            TargetCurrentNumber(
                entry_id=entry.entry_id,
                coordinator=coordinator,
                min_a=data[CONF_MIN_CURRENT],
                max_a=data[CONF_MAX_CURRENT],
                default=data[CONF_DEFAULT_TARGET_CURRENT],
            ),
            SocLimitOverrideNumber(
                entry_id=entry.entry_id,
                coordinator=coordinator,
                default=data[CONF_DEFAULT_SOC_LIMIT],
            ),
        ]
    )
