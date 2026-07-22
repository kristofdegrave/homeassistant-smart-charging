"""Home-day flag switch (C2, R9/R13). New `switch.py` platform."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change

from .entity import SmartChargingEntity


class HomeDaySwitch(SmartChargingEntity, SwitchEntity):
    """User-set "home day" flag (R9's solar-reserve trigger, one of R13's configured
    mechanisms). Defaults off and resets to off at local midnight every day (R13) --
    a daily flag, not a persisted preference, so no `RestoreEntity`: surviving a restart
    is not the point, only ever expiring at the day's own boundary is."""

    _attr_translation_key = "home_day"

    def __init__(self, entry_id: str) -> None:
        super().__init__(entry_id)
        self._attr_unique_id = f"{entry_id}_home_day"
        self._attr_is_on = False
        self._unsub_midnight_reset: CALLBACK_TYPE | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._unsub_midnight_reset = async_track_time_change(
            self.hass, self._async_reset_at_midnight, hour=0, minute=0, second=0
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_midnight_reset is not None:
            self._unsub_midnight_reset()
            self._unsub_midnight_reset = None
        await super().async_will_remove_from_hass()

    async def _async_reset_at_midnight(self, now: datetime) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([HomeDaySwitch(entry_id=entry.entry_id)])
