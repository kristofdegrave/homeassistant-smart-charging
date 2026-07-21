"""Mode selector entity (C2). ADR-0004 native naming."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_SOLAR_INSTALLED,
    DEFAULT_CAPTAR_AVAILABLE,
    DOMAIN,
    MODE_CAPTAR,
    MODE_OFF,
    MODE_POWER,
    MODE_SOLAR,
    MODE_SOLAR_ONLY,
)
from .entity import SmartChargingEntity

BASE_MODE_OPTIONS = [MODE_OFF, MODE_POWER]
SOLAR_MODE_OPTIONS = [MODE_SOLAR, MODE_SOLAR_ONLY]
CAPTAR_MODE_OPTIONS = [MODE_CAPTAR]


class ModeSelect(SmartChargingEntity, RestoreEntity, SelectEntity):
    """User-set active charging mode. Option list is gated by Solar installed and CapTar
    available (design doc §3/§4, R18 scoped), composing independently -- each mode family
    is only offered when its own config-time toggle is True."""

    _attr_translation_key = "mode"

    def __init__(
        self,
        entry_id: str,
        coordinator,
        solar_installed: bool = False,
        captar_available: bool = False,
    ) -> None:
        super().__init__(entry_id)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_mode"
        options = list(BASE_MODE_OPTIONS)
        if solar_installed:
            options += SOLAR_MODE_OPTIONS
        if captar_available:
            options += CAPTAR_MODE_OPTIONS
        self._attr_options = options
        self._attr_current_option = BASE_MODE_OPTIONS[0]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in self._attr_options:
            self._attr_current_option = last.state
        self._coordinator.active_mode = self._attr_current_option

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self._coordinator.active_mode = option  # coordinator resets mode-state (M1, Task 5.1)
        await self._coordinator.async_request_refresh()
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            ModeSelect(
                entry_id=entry.entry_id,
                coordinator=coordinator,
                solar_installed=entry.data.get(CONF_SOLAR_INSTALLED, False),
                captar_available=entry.data.get(CONF_CAPTAR_AVAILABLE, DEFAULT_CAPTAR_AVAILABLE),
            )
        ]
    )
