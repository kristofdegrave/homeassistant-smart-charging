"""The Smart Charging integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .adapters.factory import build_adapters
from .const import (
    CONF_CONTROL_INTERVAL_S,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_MAX_CURRENT,
    CONF_MIN_CURRENT,
    CONF_NOMINAL_VOLTAGE,
    DEFAULT_CONTROL_INTERVAL_S,
    DEFAULT_GRID_SAFETY_OFFSET_A,
    DOMAIN,
)
from .coordinator import SmartChargingCoordinator

PLATFORMS = [Platform.NUMBER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Mappings/translation live in data; thresholds/defaults + interval in options (ADR-0005).
    adapters = build_adapters(hass, entry.data)
    opts = entry.options
    config = {
        "min_current": opts[CONF_MIN_CURRENT],
        "max_current": opts[CONF_MAX_CURRENT],
        "grid_ceiling_a": opts[CONF_GRID_CEILING_A],
        "grid_safety_offset_a": opts.get(CONF_GRID_SAFETY_OFFSET_A, DEFAULT_GRID_SAFETY_OFFSET_A),
        "nominal_voltage": opts[CONF_NOMINAL_VOLTAGE],
        "default_target_current": opts[CONF_DEFAULT_TARGET_CURRENT],
    }
    interval_s = opts.get(CONF_CONTROL_INTERVAL_S, DEFAULT_CONTROL_INTERVAL_S)

    coordinator = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=interval_s
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "min_current": config["min_current"],
        "max_current": config["max_current"],
        "default_target_current": config["default_target_current"],
    }

    # First refresh AFTER platforms so the number entity can seed target_current on add.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_config_entry_first_refresh()

    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))
    return True


async def _async_reload_on_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
