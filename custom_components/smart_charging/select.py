"""Mode selector entity (C2). ADR-0004 native naming."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import SmartChargingConfigEntry
from .const import (
    BASE_CAPABLE_MODES,
    CAPTAR_CAPABLE_MODES,
    CONF_CAPTAR_AVAILABLE,
    CONF_SOLAR_INSTALLED,
    DEFAULT_CAPTAR_AVAILABLE,
    OWNED_SUFFIX_MODE,
    OWNED_SUFFIX_PROFILE,
    PROFILE_AUTO,
    PROFILE_MANUAL,
    SOLAR_CAPABLE_MODES,
)
from .entity import SmartChargingEntity

BASE_MODE_OPTIONS = list(BASE_CAPABLE_MODES)
PROFILE_OPTIONS = [PROFILE_MANUAL, PROFILE_AUTO]


class _RestoreOptionMixin:
    """Shared restore + select body for select entities that restore their last option
    into `_attr_current_option` when it's still a valid member of `_attr_options`
    (issue #507). Must appear before `RestoreEntity` in a subclass's bases so its
    `async_added_to_hass` override's `super()` call resolves onward to
    `RestoreEntity.async_added_to_hass` (the actual restore-state read)."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in self._attr_options:
            self._attr_current_option = last.state

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self.async_write_ha_state()


class ModeSelect(SmartChargingEntity, _RestoreOptionMixin, RestoreEntity, SelectEntity):
    """User-set active charging mode. Option list is gated by Solar installed and CapTar
    available (design doc §3/§4, R18 scoped), composing independently -- each mode family
    is only offered when its own config-time toggle is True."""

    _attr_translation_key = "mode"
    _object_id_suffix = OWNED_SUFFIX_MODE

    def __init__(
        self,
        entry_id: str,
        solar_installed: bool = False,
        captar_available: bool = False,
    ) -> None:
        super().__init__(entry_id)
        options = list(BASE_MODE_OPTIONS)
        if solar_installed:
            options += SOLAR_CAPABLE_MODES
        if captar_available:
            options += CAPTAR_CAPABLE_MODES
        self._attr_options = options
        self._attr_current_option = BASE_MODE_OPTIONS[0]


class ProfileSelect(SmartChargingEntity, _RestoreOptionMixin, RestoreEntity, SelectEntity):
    """User-set charging profile -- `Manual` (the mode selector drives dispatch) or `Auto`
    (E2's own mode-selection drives dispatch, R16). Mirrors `ModeSelect` (design doc §4)."""

    _attr_translation_key = "profile"
    _object_id_suffix = OWNED_SUFFIX_PROFILE
    _attr_options = PROFILE_OPTIONS

    def __init__(self, entry_id: str) -> None:
        super().__init__(entry_id)
        self._attr_current_option = PROFILE_MANUAL


async def async_setup_entry(
    hass: HomeAssistant, entry: SmartChargingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [
            ModeSelect(
                entry_id=entry.entry_id,
                solar_installed=entry.data.get(CONF_SOLAR_INSTALLED, False),
                captar_available=entry.data.get(CONF_CAPTAR_AVAILABLE, DEFAULT_CAPTAR_AVAILABLE),
            ),
            ProfileSelect(
                entry_id=entry.entry_id,
            ),
        ]
    )
