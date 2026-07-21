"""The Smart Charging integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .adapters.factory import build_adapters
from .const import (
    CONF_CONTROL_INTERVAL_S,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_MAX_CURRENT,
    CONF_MIN_CURRENT,
    CONF_NOMINAL_VOLTAGE,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_START_THRESHOLD_W,
    DEFAULT_CONTROL_INTERVAL_S,
    DEFAULT_GRID_SAFETY_OFFSET_A,
    DEFAULT_SMOOTHING_WINDOW,
    DEFAULT_SOC_LIMIT,
    DEFAULT_SOLAR_COOLDOWN_MIN,
    DEFAULT_SOLAR_HOLD_MIN,
    DEFAULT_SOLAR_ONLY_MIDPOINT,
    DEFAULT_SOLAR_ONLY_START_THRESHOLD_W,
    DEFAULT_SOLAR_ONLY_STRATEGY,
    DEFAULT_SOLAR_START_THRESHOLD_W,
    DOMAIN,
)
from .coordinator import SmartChargingCoordinator

PLATFORMS = [Platform.NUMBER, Platform.SELECT, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Mappings/translation live in data; thresholds/defaults + interval in options (ADR-0005).
    adapters = build_adapters(hass, entry.data)
    opts = entry.options
    min_current = opts[CONF_MIN_CURRENT]
    max_current = opts[CONF_MAX_CURRENT]
    default_target_current = opts[CONF_DEFAULT_TARGET_CURRENT]
    default_soc_limit = opts.get(CONF_DEFAULT_SOC_LIMIT, DEFAULT_SOC_LIMIT)
    config = {
        "min_current": min_current,
        "max_current": max_current,
        "grid_ceiling_a": opts[CONF_GRID_CEILING_A],
        "grid_safety_offset_a": opts.get(CONF_GRID_SAFETY_OFFSET_A, DEFAULT_GRID_SAFETY_OFFSET_A),
        "nominal_voltage": opts[CONF_NOMINAL_VOLTAGE],
        CONF_SMOOTHING_WINDOW: opts.get(CONF_SMOOTHING_WINDOW, DEFAULT_SMOOTHING_WINDOW),
        CONF_SOLAR_START_THRESHOLD_W: opts.get(
            CONF_SOLAR_START_THRESHOLD_W, DEFAULT_SOLAR_START_THRESHOLD_W
        ),
        CONF_SOLAR_ONLY_START_THRESHOLD_W: opts.get(
            CONF_SOLAR_ONLY_START_THRESHOLD_W, DEFAULT_SOLAR_ONLY_START_THRESHOLD_W
        ),
        CONF_SOLAR_HOLD_MIN: opts.get(CONF_SOLAR_HOLD_MIN, DEFAULT_SOLAR_HOLD_MIN),
        CONF_SOLAR_COOLDOWN_MIN: opts.get(CONF_SOLAR_COOLDOWN_MIN, DEFAULT_SOLAR_COOLDOWN_MIN),
        CONF_SOLAR_ONLY_STRATEGY: opts.get(CONF_SOLAR_ONLY_STRATEGY, DEFAULT_SOLAR_ONLY_STRATEGY),
        CONF_SOLAR_ONLY_MIDPOINT: opts.get(CONF_SOLAR_ONLY_MIDPOINT, DEFAULT_SOLAR_ONLY_MIDPOINT),
    }
    interval_s = opts.get(CONF_CONTROL_INTERVAL_S, DEFAULT_CONTROL_INTERVAL_S)

    coordinator = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=interval_s
    )

    # Keyed by the same CONF_* constants number.py reads, so the two sides can't drift apart.
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        CONF_MIN_CURRENT: min_current,
        CONF_MAX_CURRENT: max_current,
        CONF_DEFAULT_TARGET_CURRENT: default_target_current,
        CONF_DEFAULT_SOC_LIMIT: default_soc_limit,
    }

    # First refresh AFTER platforms so the number entity can seed target_current on add.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_config_entry_first_refresh()

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    # Fires on any entry update, not only options — a reconfigure (data) update also lands
    # here in addition to its own reload, which is harmless since HA serializes reloads.
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
